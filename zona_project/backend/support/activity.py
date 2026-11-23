"""Xodimlar ishi: guruhlardagi har bir xabar kunlik faollikka yoziladi (Activity) va undan to'liq statistika va ish
grafigi chiqadi — kim qancha yozdi, nechida boshladi va tugatdi, nima qildi (javob, aniqlashtirish, uzatish, reaksiya,
"jarayonda", yopdi), qanchalik tez javob berdi.

Ishning o'zi (javoblar, aniqlashtirishlar) Message jadvalidan olinadi — guruh tarixi bilan birga (xodimning to'liq
tarixi). Kunlik xabarlar soni — Activity'dan: jonli xabarlar yoziladi, oldingilari bir marta Message'dan to'ldiriladi.
"""
from collections import Counter, defaultdict
from statistics import median

from django.db import IntegrityError, transaction
from django.db.models import F, Q

from .models import Activity, Message, TgUser
from .workload import local, work_hours, work_secs

WORK_KINDS = [Message.STAFF, Message.CLARIFY]


def _hours():
    return [0] * 24


def record(user, group, when):
    """Bitta xabar: shu kunning hisobiga qo'shiladi (birinchi / oxirgi vaqt, soat bo'yicha)."""
    if user is None:
        return
    lt = local(when)
    for _ in range(2):  # bir vaqtda ikki xabar — unikal cheklov; ikkinchi urinishda yangilanadi
        row = Activity.objects.filter(user=user, group=group, date=lt.date()).first()
        if row is None:
            hours = _hours()
            hours[lt.hour] = 1
            try:
                with transaction.atomic():
                    Activity.objects.create(user=user, group=group, date=lt.date(), count=1, first_at=when, last_at=when,
                                            hours=hours)
                return
            except IntegrityError:
                continue
        hours = list(row.hours or _hours())
        hours[lt.hour] += 1
        Activity.objects.filter(pk=row.pk).update(count=F("count") + 1, hours=hours, first_at=min(row.first_at, when),
                                                  last_at=max(row.last_at, when))
        return


def backfill(before):
    """Activity yozila boshlagunga qadar bo'lgan xabarlar — Message jadvalidan (bir marta). Qaytaradi: nechta xabar."""
    agg = {}
    for uid, gid, at in (Message.objects.filter(user__isnull=False, created_at__lt=before)
                         .values_list("user_id", "group_id", "created_at").iterator()):
        lt = local(at)
        key = (uid, gid, lt.date())
        a = agg.get(key)
        if a is None:
            a = agg[key] = {"count": 0, "first": at, "last": at, "hours": _hours()}
        a["count"] += 1
        a["hours"][lt.hour] += 1
        a["first"], a["last"] = min(a["first"], at), max(a["last"], at)
    n = 0
    with transaction.atomic():
        for (uid, gid, d), a in agg.items():
            row = Activity.objects.filter(user_id=uid, group_id=gid, date=d).first()
            if row is None:
                Activity.objects.create(user_id=uid, group_id=gid, date=d, count=a["count"], first_at=a["first"],
                                        last_at=a["last"], hours=a["hours"])
            else:  # bugun: jonli hisob allaqachon bor — oldingi xabarlar qo'shiladi
                hours = [x + y for x, y in zip(row.hours or _hours(), a["hours"])]
                Activity.objects.filter(pk=row.pk).update(count=row.count + a["count"], hours=hours,
                                                          first_at=min(row.first_at, a["first"]),
                                                          last_at=max(row.last_at, a["last"]))
            n += a["count"]
    return n


def staff_users():
    return TgUser.objects.filter(Q(member__isnull=False) | Q(contact__isnull=False)).select_related("member", "contact")


def _minutes(dt):
    lt = local(dt)
    return lt.hour * 60 + lt.minute


def _hm(m):
    return None if m is None else f"{int(m) // 60:02d}:{int(m) % 60:02d}"


def _days(rows):
    """Activity qatorlari -> kunlar: {sana: {count, first, last, hours}} (bir necha guruh birlashtiriladi)."""
    days = {}
    for r in rows:
        d = days.get(r.date)
        if d is None:
            days[r.date] = {"count": r.count, "first": r.first_at, "last": r.last_at, "hours": list(r.hours or _hours())}
        else:
            d["count"] += r.count
            d["first"], d["last"] = min(d["first"], r.first_at), max(d["last"], r.last_at)
            d["hours"] = [x + y for x, y in zip(d["hours"], r.hours or _hours())]
    return days


def _work(users, start, end):
    """Xodimlarning ishi (Message): javob, aniqlashtirish, uzatish, birinchi javob tezligi, reaksiya, jarayonda, yopdi."""
    from .engine import handoff_to, is_handoff
    ids = [u.pk for u in users]
    names = {u.pk: u.staff_name() for u in users}
    per = defaultdict(lambda: {"answers": 0, "clarifications": 0, "handoffs": 0, "questions": set(), "times": [],
                               "groups": Counter()})
    rows = (Message.objects.filter(kind__in=WORK_KINDS, user_id__in=ids, created_at__gte=start, created_at__lt=end)
            .select_related("question", "group").order_by("created_at"))
    first_by_q = {}
    hours = work_hours()
    for m in rows:
        p = per[m.user_id]
        p["groups"][m.group.title if m.group_id else "—"] += 1
        if m.kind == Message.CLARIFY:
            p["clarifications"] += 1
        elif is_handoff(m.text) or handoff_to(m.text) is not None:
            p["handoffs"] += 1
        else:
            p["answers"] += 1
        if m.question_id:
            p["questions"].add(m.question_id)
            if m.question_id not in first_by_q and m.question is not None:
                first_by_q[m.question_id] = m.question_id
                p["times"].append(work_secs(m.question.created_at, m.created_at, hours))
    qs = Message.objects.filter(kind=Message.QUESTION, created_at__gte=start, created_at__lt=end)
    reacts = Counter(qs.filter(handler_id__in=ids, stage="react").values_list("handler_id", flat=True))
    working = Counter(qs.filter(handler_id__in=ids, resolution=Message.WORK).values_list("handler_id", flat=True))
    closed = Counter()
    for by in qs.filter(resolution=Message.YES, resolved_by__startswith="xodim: ").values_list("resolved_by", flat=True):
        closed[by[len("xodim: "):]] += 1
    res = dict(Message.objects.filter(pk__in={q for p in per.values() for q in p["questions"]}).values_list("pk", "resolution"))
    from django.utils import timezone as _tz
    now = _tz.now()
    open_now, oldest = Counter(), {}
    for hid, at in (Message.objects.filter(kind=Message.QUESTION, handler_id__in=ids, source="live",
                                           created_at__gte=now - _tz.timedelta(days=30))
                    .filter(Q(resolution__in=[Message.ASKED, Message.NO, Message.WORK]) | Q(status=Message.ESCALATED, resolution=""))
                    .values_list("handler_id", "created_at")):
        open_now[hid] += 1
        oldest[hid] = min(oldest.get(hid, at), at)
    from .rating import summary
    stars = summary(ids)
    out = {}
    for uid in ids:
        p = per[uid]
        out[uid] = {"answers": p["answers"], "clarifications": p["clarifications"], "handoffs": p["handoffs"],
                    "questions": len(p["questions"]),
                    "resolved": sum(1 for q in p["questions"] if res.get(q) == Message.YES),
                    "unresolved": sum(1 for q in p["questions"] if res.get(q) == Message.NO),
                    "reactions": reacts.get(uid, 0), "working": working.get(uid, 0), "closed": closed.get(names[uid], 0),
                    "median_s": round(median(p["times"]), 1) if p["times"] else None,
                    "open_now": open_now.get(uid, 0),
                    "rating": stars.get(uid, {}).get("avg"), "ratings": stars.get(uid, {}).get("n", 0),
                    "rating_dist": stars.get(uid, {}).get("dist", [0] * 5),
                    "oldest_open_h": round((now - oldest[uid]).total_seconds() / 3600, 1) if uid in oldest else None,
                    "groups": [{"title": g, "n": n} for g, n in p["groups"].most_common(6)]}
    return out


def board(start, end, info=None):
    """Barcha xodimlar: xabarlar, faol kunlar, ish vaqti (o'rtacha boshlash/tugatish), ish turlari, tezlik."""
    users = list(staff_users())
    acts = defaultdict(list)
    for r in Activity.objects.filter(user__in=users, date__gte=local(start).date(), date__lt=local(end).date()):
        acts[r.user_id].append(r)
    work = _work(users, start, end)
    out = []
    for u in users:
        days = _days(acts[u.pk])
        firsts = [_minutes(d["first"]) for d in days.values()]
        lasts = [_minutes(d["last"]) for d in days.values()]
        spans = [(d["last"] - d["first"]).total_seconds() / 3600 for d in days.values()]
        out.append({"id": u.pk, "name": u.staff_name(), "username": u.username,
                    "team": u.contact.member.name if u.contact_id and u.contact.member_id else "",
                    "messages": sum(d["count"] for d in days.values()), "active_days": len(days),
                    "start": _hm(median(firsts)) if firsts else None, "end": _hm(median(lasts)) if lasts else None,
                    "span_h": round(sum(spans) / len(spans), 1) if spans else 0,
                    "last_seen": u.last_msg_at, **work[u.pk]})
    out.sort(key=lambda x: -(x["messages"] + x["answers"]))
    return {**(info or {}), "staff": out,
            "totals": {"staff": sum(1 for x in out if x["messages"] or x["answers"]),
                       "messages": sum(x["messages"] for x in out), "answers": sum(x["answers"] for x in out),
                       "clarifications": sum(x["clarifications"] for x in out),
                       "handoffs": sum(x["handoffs"] for x in out)}}


def detail(user, start, end, info=None):
    """Bitta xodim: kunma-kun ish grafigi, soat × hafta kuni, guruhlar, so'nggi harakatlari (havola bilan)."""
    rows = list(Activity.objects.filter(user=user, date__gte=local(start).date(), date__lt=local(end).date())
                .select_related("group"))
    days = _days(rows)
    heat = [[0] * 24 for _ in range(7)]
    for d, v in days.items():
        for h, n in enumerate(v["hours"]):
            heat[d.weekday()][h] += n
    groups = Counter()
    for r in rows:
        groups[r.group.title if r.group_id else "—"] += r.count
    work = _work([user], start, end)[user.pk]
    per_day_work = Counter()
    for at in (Message.objects.filter(kind__in=WORK_KINDS, user=user, created_at__gte=start, created_at__lt=end)
               .values_list("created_at", flat=True)):
        per_day_work[local(at).date()] += 1
    timeline = [{"date": d.isoformat(), "weekday": d.weekday(), "messages": v["count"], "work": per_day_work.get(d, 0),
                 "first": _hm(_minutes(v["first"])), "last": _hm(_minutes(v["last"])),
                 "first_m": _minutes(v["first"]), "last_m": _minutes(v["last"]),
                 "span_h": round((v["last"] - v["first"]).total_seconds() / 3600, 1), "hours": v["hours"]}
                for d, v in sorted(days.items())]
    recent = []
    for m in (Message.objects.filter(user=user, created_at__gte=start, created_at__lt=end)
              .exclude(kind=Message.QUESTION).select_related("group", "question").order_by("-created_at")[:120]):
        q = m.question
        recent.append({"id": m.pk, "at": m.created_at, "kind": m.kind, "text": (m.text or "")[:300],
                       "group": m.group.title if m.group_id else "",
                       "question": ((q.text or q.problem or "")[:200] if q else ""), "question_id": q.pk if q else None,
                       "link": m.group.message_link(m.message_id) if m.group_id else ""})
    return {**(info or {}), "id": user.pk, "name": user.staff_name(), "username": user.username,
            "messages": sum(v["count"] for v in days.values()), "active_days": len(days),
            "heatmap": heat, "timeline": timeline, "groups": [{"title": g, "n": n} for g, n in groups.most_common(10)],
            "recent": recent, **work}


# ====================================================================== baholash va tavsiyalar
def _tag_titles():
    from .models import Tag
    return dict(Tag.objects.values_list("key", "title"))


def _topics(user, start, end):
    """Xodimga kelib tushgan savollar (u javob bergan yoki unga biriktirilgan): mavzu va tur (teg) bo'yicha — soni,
    hal bo'lmagan, uzatgan, median javob vaqti (ish vaqti bo'yicha); eng ko'p vaqt ketgan savollar."""
    from .engine import handoff_to, is_handoff
    hours = work_hours()
    titles = _tag_titles()
    first, handoff = {}, Counter()
    for m in (Message.objects.filter(kind__in=WORK_KINDS, user=user, created_at__gte=start, created_at__lt=end, question__isnull=False)
              .only("question_id", "created_at", "kind", "text").order_by("created_at")):
        first.setdefault(m.question_id, m.created_at)
        if m.kind == Message.STAFF and (is_handoff(m.text) or handoff_to(m.text) is not None):
            handoff[m.question_id] += 1
    assigned = set(Message.objects.filter(kind=Message.QUESTION, handler=user, created_at__gte=start, created_at__lt=end)
                   .values_list("pk", flat=True))
    qs = (Message.objects.filter(pk__in=set(first) | assigned).select_related("entry", "group")
          .only("id", "text", "problem", "created_at", "resolution", "status", "tags", "entry__title", "group__title",
                "group__username", "group__chat_id", "message_id"))
    per = defaultdict(lambda: {"n": 0, "no": 0, "handoff": 0, "open": 0, "times": []})
    per_tag = defaultdict(lambda: {"n": 0, "no": 0, "handoff": 0, "open": 0, "times": []})
    slow = []
    for q in qs:
        tg = list(q.tags or [])
        topic = q.entry.title if q.entry_id else (titles.get(tg[0], tg[0]) if tg else "Turi aniqlanmagan")
        secs = work_secs(q.created_at, first[q.pk], hours) if q.pk in first else None
        is_open = q.resolution in (Message.NO, Message.WORK, Message.ASKED) or (q.status == Message.ESCALATED and q.resolution != Message.YES)
        for p in [per[topic]] + [per_tag[k] for k in (tg or ["—"])]:
            p["n"] += 1
            p["no"] += q.resolution == Message.NO
            p["handoff"] += bool(handoff.get(q.pk))
            p["open"] += is_open
            if secs is not None:
                p["times"].append(secs)
        if secs is not None:
            slow.append({"id": q.pk, "text": (q.problem or q.text or "")[:160], "secs": secs, "topic": topic,
                         "tags": [titles.get(k, k) for k in tg], "resolution": q.resolution,
                         "link": q.group.message_link(q.message_id) if q.group_id else ""})

    def pack(d, key, name=None):
        return [{key: (name(t) if name else t), "key": t, "n": v["n"], "no": v["no"], "handoff": v["handoff"], "open": v["open"],
                 "median_s": round(median(v["times"]), 1) if v["times"] else None,
                 "total_s": round(sum(v["times"]), 1)} for t, v in d.items()]
    topics = pack(per, "topic")
    tags = pack(per_tag, "tag", lambda k: "Tegsiz" if k == "—" else titles.get(k, k))
    slow.sort(key=lambda x: -x["secs"])
    return topics, tags, slow[:12]


def insights(me, team, topics, tags=None):
    """Ish holati (0–100) va tavsiyalar: kuchli (+), zaif (−), o'rgatish, yordam. Kodlar — tarjimani frontend qiladi."""
    def med(key):
        vals = sorted(x[key] for x in team if x.get(key) is not None and (x.get("answers") or x.get("messages")))
        return vals[len(vals) // 2] if vals else None
    t_speed, t_answers = med("median_s"), med("answers")
    out = []
    speed = me.get("median_s")
    decided = (me.get("resolved") or 0) + (me.get("unresolved") or 0)
    res_rate = (me["resolved"] / decided) if decided else None
    hand_share = me["handoffs"] / max(1, me["answers"] + me["handoffs"])
    rating = me.get("rating")
    if speed is not None and t_speed and speed <= 0.7 * t_speed:
        out.append({"kind": "plus", "code": "fast", "v": speed, "team": t_speed})
    if speed is not None and t_speed and speed >= 1.5 * t_speed:
        out.append({"kind": "minus", "code": "slow", "v": speed, "team": t_speed})
    if res_rate is not None and decided >= 3:
        out.append({"kind": "plus" if res_rate >= 0.8 else "minus" if res_rate < 0.6 else "info", "code": "resolve",
                    "v": round(100 * res_rate)})
    if rating is not None and me.get("ratings", 0) >= 2:
        out.append({"kind": "plus" if rating >= 4.5 else "minus" if rating < 3.5 else "info", "code": "rating", "v": rating,
                    "n": me["ratings"]})
    if t_answers and me["answers"] >= 1.3 * t_answers:
        out.append({"kind": "plus", "code": "active", "v": me["answers"], "team": t_answers})
    if me["answers"] + me["handoffs"] >= 5 and hand_share >= 0.3:
        out.append({"kind": "minus", "code": "handoffs", "v": round(100 * hand_share)})
    if (me.get("oldest_open_h") or 0) >= 24:
        out.append({"kind": "minus", "code": "open_old", "v": me["oldest_open_h"], "n": me.get("open_now", 0)})
    train = [t for t in sorted(topics, key=lambda x: -(x["no"] + x["handoff"])) if t["no"] + t["handoff"] >= 2][:5]
    for t in train:
        out.append({"kind": "train", "code": "topic", "topic": t["topic"], "no": t["no"], "handoff": t["handoff"]})
    slow = [t for t in sorted(topics, key=lambda x: -(x["median_s"] or 0)) if (t["median_s"] or 0) >= 3600 and t["n"] >= 2][:3]
    for t in slow:
        out.append({"kind": "help", "code": "slow_topic", "topic": t["topic"], "v": t["median_s"], "n": t["n"]})
    for t in sorted(tags or [], key=lambda x: -(x["no"] + x["handoff"] + x["open"])):
        if t["key"] != "—" and t["no"] + t["handoff"] + t["open"] >= 3 and len([i for i in out if i["code"] == "tag_train"]) < 3:
            out.append({"kind": "train", "code": "tag_train", "topic": t["tag"], "no": t["no"], "handoff": t["handoff"], "n": t["n"]})
    t_tag = [t for t in (tags or []) if t["key"] != "—" and t["median_s"] and t["n"] >= 3]
    if speed and t_tag:
        worst = max(t_tag, key=lambda x: x["median_s"])
        if worst["median_s"] >= max(1800, 2 * speed):
            out.append({"kind": "help", "code": "slow_tag", "topic": worst["tag"], "v": worst["median_s"], "n": worst["n"]})
    # ish holati: tezlik, hal qilish, baho, faollik — jamoaga nisbatan (har biri 0..25)
    parts = []
    if speed is not None and t_speed:
        parts.append(max(0.0, min(25.0, 25 * min(1.5, t_speed / max(speed, 1)) / 1.5)))
    if res_rate is not None:
        parts.append(25 * res_rate)
    if rating is not None:
        parts.append(25 * (rating - 1) / 4)
    if t_answers:
        parts.append(min(25.0, 25 * me["answers"] / max(t_answers, 1) / 1.3))
    score = round(sum(parts) * 4 / len(parts)) if parts else None
    return {"score": score, "items": out}


def evaluate(user, start, end):
    """Bitta xodim uchun: jamoa bilan solishtirib, ish holati va tavsiyalar."""
    team = board(start, end)["staff"]
    me = next((x for x in team if x["id"] == user.pk), None)
    if me is None:
        return {"score": None, "items": [], "topics": []}
    topics, tags, slow = _topics(user, start, end)
    res = insights(me, team, topics, tags)
    res["topics"] = sorted(topics, key=lambda x: -x["n"])[:15]
    res["tags"] = sorted(tags, key=lambda x: -x["n"])
    res["slow_topics"] = sorted([t for t in topics if t["median_s"] is not None], key=lambda x: -x["median_s"])[:10]
    res["slowest"] = slow
    res["me"] = me
    return res

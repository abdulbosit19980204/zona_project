"""Konstruktor: istalgan statistika — ma'lumot turi, davr, 1–2 ta guruhlash, ko'rsatkichlar va filtrlar.

Ma'lumot turlari:
- questions — guruhlardagi savollar (kim javob berdi, natija, tezlik, mavzu, agent va uning roli/loyihasi);
- staff — xodimlar ishi (javob, aniqlashtirish, uzatish; qaysi savolga, qancha vaqtda);
- activity — guruhlardagi barcha xabarlar (kunlik faollik: xodimlar va agentlar).

Hisob Python'da (bir necha o'n ming qator — bir soniyadan kam): har bir qatorga barcha o'lchovlar yorlig'i beriladi,
filtrlar va guruhlash shu yorliqlar bo'yicha — shuning uchun istalgan o'lchov istalgan tarzda birlashadi.
Filtr: f_<o'lchov>=qiymat1,qiymat2 (qiymat — jadvaldagi "key"). Savollar ro'yxatiga o'tish (inbox) ham shu filtrlar bilan.
"""
from collections import Counter, defaultdict
from statistics import median

from django.db.models import Q

from .models import Activity, Message
from .workload import BOT_STAGES, local, period

WD = ["Du", "Se", "Ch", "Pa", "Ju", "Sh", "Ya"]
STAFF_STAGES = ("staff", "panel", "react")
DATASETS = ("questions", "staff", "activity")
DIMS = {
    "questions": ["day", "week", "month", "hour", "weekday", "group", "asker", "role", "project", "territory", "answer",
                  "staff", "status", "resolution", "topic", "responsible", "category", "app", "origin", "source", "photo",
                  "speed"],
    "staff": ["day", "week", "month", "hour", "weekday", "group", "staff", "kind", "topic", "asker", "source"],
    "activity": ["day", "week", "month", "weekday", "group", "person", "who"],
}
METRICS = {
    "questions": ["count", "bot", "staff", "unanswered", "yes", "no", "work", "asked", "unknown", "open", "rate",
                  "bot_share", "median_s", "avg_s", "p90_s", "within_15", "photo", "askers"],
    "staff": ["count", "answers", "clarifications", "handoffs", "questions", "median_s", "avg_s", "people"],
    "activity": ["messages", "people", "days"],
}
TIME_DIMS = ("day", "week", "month", "hour", "weekday")
SPEED = [(60, "≤1 daq"), (300, "1–5 daq"), (900, "5–15 daq"), (3600, "15–60 daq"), (14400, "1–4 soat"), (10 ** 9, ">4 soat")]
LIMIT = 500


def _time_keys(at):
    lt = local(at)
    y, w, _ = lt.isocalendar()
    return {"day": lt.date().isoformat(), "week": f"{y}-W{w:02d}", "month": lt.strftime("%Y-%m"),
            "hour": f"{lt.hour:02d}", "weekday": str(lt.weekday())}


def _label(dim, key, names):
    if dim == "weekday":
        return WD[int(key)] if key.isdigit() else key
    if dim == "hour":
        return f"{key}:00"
    if dim in ("asker", "person"):
        return names.get(key, key)
    return key or "—"


def _q_rows(qs):
    """Savollar: har biri — o'lchovlar yorlig'i va hisob uchun maydonlar."""
    rows = list(qs.values("id", "created_at", "answered_at", "status", "stage", "resolution", "source", "photo_file_id",
                          "category", "app", "origin", "answered_by", "group__title", "entry__title",
                          "entry__responsible__name", "user_id", "user__name", "user__username", "user__staff_person__role",
                          "user__staff_person__project__name", "user__staff_person__territory", "handler__member__name",
                          "handler__contact__name"))
    ids = [r["id"] for r in rows]
    first, first_by = {}, {}
    for qid, at, mname, cname, uname in (Message.objects.filter(kind__in=[Message.STAFF, Message.CLARIFY], question_id__in=ids)
                                         .order_by("created_at").values_list("question_id", "created_at", "user__member__name",
                                                                             "user__contact__name", "user__name")):
        if qid not in first:
            first[qid], first_by[qid] = at, (cname or mname or uname or "")
    roles = {"SVR": "Supervayzer", "TP": "Savdo vakili", "MER": "Merchendayzer", "RSM": "RSM", "ASM": "ASM", "ROP": "ROP",
             "KAM": "KAM", "OTHER": "Boshqa"}
    names = {}
    out = []
    for r in rows:
        done = r["status"] in (Message.ANSWERED, Message.CLOSED)
        bot = done and r["stage"] in BOT_STAGES
        staff = done and r["stage"] in STAFF_STAGES
        cands = [x for x in ((r["answered_at"] if bot else None), first.get(r["id"])) if x]
        secs = max(0.0, (min(cands) - r["created_at"]).total_seconds()) if cands else None
        uid = str(r["user_id"] or "")
        if uid:
            names[uid] = r["user__name"] or ("@" + r["user__username"] if r["user__username"] else uid)
        staff_name = (r["handler__contact__name"] or r["handler__member__name"] or first_by.get(r["id"])
                      or (r["answered_by"] if staff else "") or "")
        k = {**_time_keys(r["created_at"]),
             "group": r["group__title"] or "—", "asker": uid, "role": roles.get(r["user__staff_person__role"] or "", "Noma'lum"),
             "project": r["user__staff_person__project__name"] or "Noma'lum",
             "territory": r["user__staff_person__territory"] or "Noma'lum",
             "answer": "Bot" if bot else "Xodim" if staff else "Javobsiz" if not done else "Boshqa",
             "staff": staff_name or "—", "status": r["status"], "resolution": r["resolution"] or "noma'lum",
             "topic": r["entry__title"] or "Turi aniqlanmagan", "responsible": r["entry__responsible__name"] or "—",
             "category": r["category"] or "—", "app": r["app"] or "—", "origin": r["origin"] or "—", "source": r["source"],
             "photo": "Rasmli" if r["photo_file_id"] else "Matnli",
             "speed": next(lbl for lim, lbl in SPEED if secs <= lim) if secs is not None else "Javob yo'q"}
        out.append((k, {"bot": bot, "staff": staff, "done": done, "res": r["resolution"], "secs": secs,
                        "photo": bool(r["photo_file_id"]), "uid": uid, "id": r["id"]}))
    return out, names


def _q_metrics(items):
    n = len(items)
    yes = sum(1 for x in items if x["res"] == Message.YES)
    no = sum(1 for x in items if x["res"] == Message.NO)
    work = sum(1 for x in items if x["res"] == Message.WORK)
    asked = sum(1 for x in items if x["res"] == Message.ASKED)
    bot = sum(1 for x in items if x["bot"])
    secs = sorted(x["secs"] for x in items if x["secs"] is not None)
    return {"count": n, "bot": bot, "staff": sum(1 for x in items if x["staff"]),
            "unanswered": sum(1 for x in items if not x["done"]), "yes": yes, "no": no, "work": work, "asked": asked,
            "unknown": n - yes - no - work - asked, "open": no + work + asked,
            "rate": round(100 * yes / (yes + no)) if yes + no else None, "bot_share": round(100 * bot / n) if n else None,
            "median_s": round(median(secs), 1) if secs else None, "avg_s": round(sum(secs) / len(secs), 1) if secs else None,
            "p90_s": round(secs[min(len(secs) - 1, int(0.9 * len(secs)))], 1) if secs else None,
            "within_15": round(100 * sum(1 for s in secs if s <= 900) / len(secs)) if secs else None,
            "photo": sum(1 for x in items if x["photo"]), "askers": len({x["uid"] for x in items if x["uid"]})}


def _s_rows(start, end, scope):
    from .engine import handoff_to, is_handoff
    qs = (Message.objects.filter(kind__in=[Message.STAFF, Message.CLARIFY], created_at__gte=start, created_at__lt=end,
                                 user__isnull=False)
          .filter(Q(user__member__isnull=False) | Q(user__contact__isnull=False)))
    if scope == "analytics":
        qs = qs.filter(source="live").exclude(group__in_analytics=False)
    elif scope == "live":
        qs = qs.filter(source="live")
    names = {}
    out = []
    for r in qs.values("id", "created_at", "kind", "text", "source", "group__title", "question_id", "question__created_at",
                       "question__entry__title", "question__user_id", "question__user__name", "user__member__name",
                       "user__contact__name", "user__name"):
        kind = "Aniqlashtirish" if r["kind"] == Message.CLARIFY else (
            "Uzatish" if is_handoff(r["text"]) or handoff_to(r["text"]) is not None else "Javob")
        uid = str(r["question__user_id"] or "")
        if uid:
            names[uid] = r["question__user__name"] or uid
        secs = (max(0.0, (r["created_at"] - r["question__created_at"]).total_seconds())
                if r["question__created_at"] else None)
        k = {**_time_keys(r["created_at"]), "group": r["group__title"] or "—",
             "staff": r["user__contact__name"] or r["user__member__name"] or r["user__name"] or "—", "kind": kind,
             "topic": r["question__entry__title"] or "Turi aniqlanmagan", "asker": uid, "source": r["source"]}
        out.append((k, {"kind": kind, "q": r["question_id"], "secs": secs, "who": k["staff"]}))
    return out, names


def _s_metrics(items):
    secs = sorted(x["secs"] for x in items if x["secs"] is not None)
    return {"count": len(items), "answers": sum(1 for x in items if x["kind"] == "Javob"),
            "clarifications": sum(1 for x in items if x["kind"] == "Aniqlashtirish"),
            "handoffs": sum(1 for x in items if x["kind"] == "Uzatish"),
            "questions": len({x["q"] for x in items if x["q"]}),
            "median_s": round(median(secs), 1) if secs else None, "avg_s": round(sum(secs) / len(secs), 1) if secs else None,
            "people": len({x["who"] for x in items})}


def _a_rows(start, end):
    names = {}
    out = []
    for r in Activity.objects.filter(date__gte=local(start).date(), date__lt=local(end).date()).values(
            "date", "count", "group__title", "user_id", "user__name", "user__username", "user__member_id", "user__contact_id",
            "user__contact__name", "user__member__name", "first_at"):
        uid = str(r["user_id"])
        staff = bool(r["user__member_id"] or r["user__contact_id"])
        names[uid] = r["user__contact__name"] or r["user__member__name"] or r["user__name"] or uid
        k = {**_time_keys(r["first_at"]), "group": r["group__title"] or "—", "person": uid,
             "who": "Xodim" if staff else "Agent"}
        k["day"] = r["date"].isoformat()
        out.append((k, {"n": r["count"], "uid": uid, "date": r["date"]}))
    return out, names


def _a_metrics(items):
    return {"messages": sum(x["n"] for x in items), "people": len({x["uid"] for x in items}),
            "days": len({x["date"] for x in items})}


def _questions_qs(start, end, scope):
    from .workload import scoped
    qs = Message.objects.filter(kind=Message.QUESTION, created_at__gte=start, created_at__lt=end).exclude(stage="dup")
    qs = qs.exclude(status=Message.IGNORED)
    if scope == "analytics":
        qs = scoped(qs)  # tahlil doirasi: jonli savollar, tahlilga qo'shilgan guruhlar
    elif scope == "live":
        qs = qs.filter(source="live")
    return qs


def filters_of(params, dataset):
    out = {}
    for d in DIMS[dataset]:
        v = params.get(f"f_{d}")
        if v:
            out[d] = set(v.split(","))
    return out


def rows_for(params):
    dataset = params.get("dataset") if params.get("dataset") in DATASETS else "questions"
    scope = params.get("scope") if params.get("scope") in ("analytics", "live", "all") else "analytics"
    start, end, info = period(params, max_days=3660)
    if dataset == "questions":
        rows, names = _q_rows(_questions_qs(start, end, scope))
    elif dataset == "staff":
        rows, names = _s_rows(start, end, scope)
    else:
        rows, names = _a_rows(start, end)
    flt = filters_of(params, dataset)
    rows = [(k, v) for k, v in rows if all(k.get(d) in vals for d, vals in flt.items())]
    return dataset, scope, info, rows, names


def question_ids(params):
    """Inbox uchun: konstruktor filtrlariga mos savollar id'lari."""
    p = {**{k: params.get(k) for k in params}, "dataset": "questions"}
    _ds, _sc, _info, rows, _n = rows_for(p)
    return [v["id"] for _k, v in rows]


def explore(params):
    dataset, scope, info, rows, names = rows_for(params)
    dims = [d for d in (params.get("by") or "").split(",") if d in DIMS[dataset]][:2]
    metrics = [m for m in (params.get("metrics") or "").split(",") if m in METRICS[dataset]] or METRICS[dataset][:4]
    calc = {"questions": _q_metrics, "staff": _s_metrics, "activity": _a_metrics}[dataset]
    groups = defaultdict(list)
    for k, v in rows:
        groups[tuple(k.get(d, "") for d in dims)].append(v)
    out = []
    for key, items in groups.items():
        m = calc(items)
        row = {f"k{i}": key[i] for i in range(len(dims))}
        row.update({f"l{i}": _label(dims[i], key[i], names) for i in range(len(dims))})
        row.update({x: m.get(x) for x in metrics})
        out.append(row)
    first = metrics[0]
    if dims and dims[0] in TIME_DIMS:
        out.sort(key=lambda r: (r["k0"], -(r.get(first) or 0)))
    else:
        out.sort(key=lambda r: -(r.get(first) or 0))
    # filtr tanlash uchun: har bir o'lchovning qiymatlari (eng ko'pi bilan 300 ta, ko'pdan ozga)
    options = {}
    for d in DIMS[dataset]:
        c = Counter(k.get(d, "") for k, _v in rows)
        options[d] = [{"key": key, "label": _label(d, key, names), "n": n}
                      for key, n in (sorted(c.items()) if d in TIME_DIMS else c.most_common(300))]
    total = calc([v for _k, v in rows])
    asker_meta = {}
    if "asker" in dims and dataset == "questions":
        from .models import TgUser
        ids = {r[f"k{dims.index('asker')}"] for r in out[:LIMIT] if r.get(f"k{dims.index('asker')}")}
        for u in TgUser.objects.filter(pk__in=[int(i) for i in ids if i.isdigit()]).select_related("staff_person__project"):
            sp = u.staff_person
            asker_meta[str(u.pk)] = {"username": u.username, "role": sp.get_role_display() if sp else "",
                                     "project": sp.project.name if sp and sp.project_id else "",
                                     "territory": sp.territory if sp else "", "staff": u.is_staff}
    return {**info, "dataset": dataset, "scope": scope, "by": dims, "metrics": metrics, "rows": out[:LIMIT],
            "total_rows": len(out), "totals": {x: total.get(x) for x in metrics}, "options": options,
            "dims": DIMS[dataset], "all_metrics": METRICS[dataset], "asker_meta": asker_meta}

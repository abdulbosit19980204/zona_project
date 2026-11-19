"""Ish yuklamasi tahlili: qachon ko'p savol tushadi, qaysi guruhdan, xodimlar qancha tez va qancha vaqt ishlaydi.

Asosiy o'lchov — "birinchi javob vaqti": savol berilgandan xodimning birinchi javobi yoki aniqlashtirishigacha
(panel orqali javob ham hisoblanadi). Bot javob bergan savollar alohida sanaladi.
"""
from collections import Counter, defaultdict
from statistics import median

from django.utils import timezone

from .models import Message, SupportTask

BOT_STAGES = ("template", "faq", "rule", "ai", "image")
BUCKETS = [(5, "≤5"), (15, "5–15"), (60, "15–60"), (240, "1–4h"), (10 ** 9, ">4h")]


def _q(values, p):
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))], 1)


def workload(days=30):
    since = timezone.now() - timezone.timedelta(days=days)
    questions = list(Message.objects.filter(kind=Message.QUESTION, created_at__gte=since)
                     .exclude(status=Message.IGNORED).exclude(stage="dup")
                     .values("id", "created_at", "stage", "status", "group__title", "entry__title", "entry__zone__name",
                             "answered_at", "answered_by"))
    qids = {q["id"] for q in questions}
    first = {}  # savol -> (vaqt, xodim)
    staff_msgs = list(Message.objects.filter(kind__in=[Message.STAFF, Message.CLARIFY], created_at__gte=since, user__isnull=False)
                      .select_related("user__member", "user__contact").order_by("created_at"))
    for r in staff_msgs:
        if r.question_id in qids and r.question_id not in first:
            first[r.question_id] = (r.created_at, r.user.staff_name())
    for q in questions:  # panel orqali javob
        if q["stage"] == "panel" and q["answered_at"] and (q["id"] not in first or q["answered_at"] < first[q["id"]][0]):
            first[q["id"]] = (q["answered_at"], q["answered_by"])

    heat = [[0] * 24 for _ in range(7)]
    by_weekday = [0] * 7
    by_date = Counter()
    weeks = defaultdict(lambda: {"questions": 0, "bot": 0, "human": 0, "unanswered": 0, "times": []})
    groups = defaultdict(lambda: {"questions": 0, "bot": 0, "unanswered": 0, "times": []})
    types = defaultdict(lambda: {"questions": 0, "bot": 0, "times": []})
    buckets = Counter()
    all_times = []
    for q in questions:
        lt = timezone.localtime(q["created_at"])
        heat[lt.weekday()][lt.hour] += 1
        by_weekday[lt.weekday()] += 1
        by_date[lt.date().isoformat()] += 1
        y, w, _ = lt.isocalendar()
        wk = weeks[f"{y}-W{w:02d}"]
        g = groups[q["group__title"] or "—"]
        tkey = q["entry__title"] or (q["entry__zone__name"] and f"Zona: {q['entry__zone__name']}") or "Turi aniqlanmagan"
        tp = types[tkey]
        for row in (wk, g, tp):
            row["questions"] += 1
        bot = q["stage"] in BOT_STAGES and q["status"] == Message.ANSWERED
        if bot:
            wk["bot"] += 1
            g["bot"] += 1
            tp["bot"] += 1
        if q["id"] in first:
            mins = max(0.0, (first[q["id"]][0] - q["created_at"]).total_seconds() / 60)
            all_times.append(mins)
            wk["human"] += 1
            for row in (wk, g, tp):
                row["times"].append(mins)
            buckets[next(label for lim, label in BUCKETS if mins <= lim)] += 1
        elif not bot and q["status"] not in (Message.ANSWERED, Message.CLOSED):
            wk["unanswered"] += 1
            g["unanswered"] += 1

    # xodimlar: ish soatlari, kunlik faol vaqt, javob tezligi
    per = defaultdict(lambda: {"answers": 0, "clar": 0, "hours": [0] * 24, "weekdays": [0] * 7, "days": defaultdict(list),
                               "first_times": [], "weeks": Counter()})
    for r in staff_msgs:
        name = r.user.staff_name()
        lt = timezone.localtime(r.created_at)
        p = per[name]
        p["hours"][lt.hour] += 1
        p["weekdays"][lt.weekday()] += 1
        p["days"][lt.date()].append(lt)
        y, w, _ = lt.isocalendar()
        p["weeks"][f"{y}-W{w:02d}"] += 1
        if r.kind == Message.CLARIFY:
            p["clar"] += 1
        else:
            p["answers"] += 1
    qtime = {q["id"]: q["created_at"] for q in questions}
    for qid, (at, name) in first.items():
        q_at = qtime.get(qid)
        if q_at and name in per:
            per[name]["first_times"].append(max(0.0, (at - q_at).total_seconds() / 60))
    week_keys = sorted(weeks)[-12:]
    staff = []
    for name, p in per.items():
        spans = [(max(ts) - min(ts)).total_seconds() / 3600 for ts in p["days"].values()]
        ft = p["first_times"]
        staff.append({
            "name": name, "answers": p["answers"], "clarifications": p["clar"], "active_days": len(p["days"]),
            "per_day": round((p["answers"] + p["clar"]) / max(1, len(p["days"])), 1),
            "per_week": round((p["answers"] + p["clar"]) / max(1, len(p["weeks"])), 1),
            "active_hours_avg": round(sum(spans) / len(spans), 1) if spans else 0,
            "first_answers": len(ft), "first_median": _q(ft, 0.5), "first_p90": _q(ft, 0.9),
            "within_15": round(100 * sum(1 for x in ft if x <= 15) / len(ft)) if ft else None,
            "hours": p["hours"], "weekdays": p["weekdays"],
            "weeks": [p["weeks"].get(k, 0) for k in week_keys],
            "peak_hour": max(range(24), key=lambda h: p["hours"][h]) if any(p["hours"]) else None,
        })
    staff.sort(key=lambda x: -(x["answers"] + x["clarifications"]))

    def pack(d, keyname):
        out = []
        for k, v in d.items():
            out.append({keyname: k, "questions": v["questions"], "bot": v["bot"],
                        "bot_rate": round(100 * v["bot"] / v["questions"]) if v["questions"] else 0,
                        "median": _q(v["times"], 0.5), "p90": _q(v["times"], 0.9),
                        **({"unanswered": v["unanswered"]} if "unanswered" in v else {})})
        return sorted(out, key=lambda x: -x["questions"])

    tasks = Counter(SupportTask.objects.filter(created_at__gte=since).values_list("status", flat=True))
    return {
        "days": days, "questions": len(questions), "answered_by_human": len(first),
        "first_median": _q(all_times, 0.5), "first_p90": _q(all_times, 0.9),
        "within_15": round(100 * sum(1 for x in all_times if x <= 15) / len(all_times)) if all_times else None,
        "heatmap": heat, "by_weekday": by_weekday,
        "busiest_dates": [{"date": d, "n": n} for d, n in by_date.most_common(7)],
        "buckets": [{"label": label, "n": buckets.get(label, 0)} for _lim, label in BUCKETS],
        "weeks": [{"week": k, **{x: weeks[k][x] for x in ("questions", "bot", "human", "unanswered")},
                   "median": _q(weeks[k]["times"], 0.5)} for k in week_keys],
        "groups": pack(groups, "group")[:30],
        "types": pack(types, "type")[:40],
        "staff": staff, "week_keys": week_keys,
        "tasks": dict(tasks),
    }

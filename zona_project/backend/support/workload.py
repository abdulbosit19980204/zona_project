"""Ish yuklamasi tahlili: qachon ko'p savol tushadi, qaysi guruhdan, xodimlar qancha tez va qancha vaqt ishlaydi.

Vaqtlar soniyada va aniq: savol Telegram'da yuborilgan paytdan (created_at) javob yuborilgan paytgacha.
"Birinchi javob" — kim bo'lishidan qat'i nazar (bot, xodim, aniqlashtirish yoki panel) birinchi javob;
"xodim javobi" — bot yopmagan savollarga xodimning birinchi javobi. Kunlar Toshkent vaqti (GMT+5) bilan 00:00 dan.
"""
import os
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .models import Message, SupportTask

BOT_STAGES = ("template", "faq", "rule", "ai", "image")
BUCKETS = [(10, "≤10s"), (60, "10s–1m"), (300, "1–5m"), (900, "5–15m"), (3600, "15–60m"), (14400, "1–4h"), (10 ** 9, ">4h")]
TZ = ZoneInfo("Asia/Tashkent")


def local(dt):
    return dt.astimezone(TZ)


def scoped(qs):
    """Tahlil doirasi: faqat jonli xabarlar (guruh tarixidan o'rganilganlar — faqat bilim uchun, statistikaga kirmaydi)
    va tahlilga qo'shilgan guruhlar (test guruhlari — Sozlamalar → Guruhlar)."""
    return qs.filter(source="live").exclude(group__in_analytics=False)


def period(params, default_days=30, max_days=366):
    """So'rov parametrlaridan davr: from/to (YYYY-MM-DD, ikkalasi ham kiradi) yoki days (bugun ham to'liq kiradi).
    Chegaralar Toshkent vaqti bilan 00:00. Qaytaradi: (boshlanish, tugash, ma'lumot)."""
    today = timezone.now().astimezone(TZ).date()
    try:
        d_from = date.fromisoformat(params.get("from")) if params.get("from") else None
        d_to = date.fromisoformat(params.get("to")) if params.get("to") else None
    except ValueError:
        d_from = d_to = None
    if d_from or d_to:
        d_to = min(d_to or today, today)
        d_from = d_from or d_to
        if d_from > d_to:
            d_from, d_to = d_to, d_from
        d_from = max(d_from, d_to - timedelta(days=max_days - 1))
    else:
        try:
            days = max(1, min(int(params.get("days") or default_days), max_days))
        except ValueError:
            days = default_days
        d_to, d_from = today, today - timedelta(days=days - 1)
    start = datetime.combine(d_from, time.min, TZ)
    end = datetime.combine(d_to + timedelta(days=1), time.min, TZ)
    return start, end, {"from": d_from.isoformat(), "to": d_to.isoformat(), "days": (d_to - d_from).days + 1, "tz": "Asia/Tashkent"}


def _q(values, p):
    if not values:
        return None
    v = sorted(values)
    return round(v[min(len(v) - 1, int(p * (len(v) - 1) + 0.5))], 1)


def workload(start, end, info=None):
    questions = list(scoped(Message.objects.filter(kind=Message.QUESTION, created_at__gte=start, created_at__lt=end))
                     .exclude(status=Message.IGNORED).exclude(stage="dup")
                     .values("id", "created_at", "stage", "status", "group__title", "entry__title", "entry__zone__name",
                             "answered_at", "answered_by"))
    qids = {q["id"] for q in questions}
    first = {}  # savol -> (vaqt, xodim): xodimning birinchi javobi yoki aniqlashtirishi
    # davr oxirida berilgan savolga keyinroq yozilgan javob ham hisobga olinadi
    staff_msgs = list(Message.objects.filter(kind__in=[Message.STAFF, Message.CLARIFY], question_id__in=qids, user__isnull=False)
                      .select_related("user__member", "user__contact").order_by("created_at"))
    for r in staff_msgs:
        if r.question_id not in first:
            first[r.question_id] = (r.created_at, r.user.staff_name())
    for q in questions:  # panel orqali javob / xodim reaksiyasi (savolni qabul qildi)
        if q["stage"] in ("panel", "react") and q["answered_at"] and (q["id"] not in first or q["answered_at"] < first[q["id"]][0]):
            first[q["id"]] = (q["answered_at"], q["answered_by"])

    heat = [[0] * 24 for _ in range(7)]
    by_weekday = [0] * 7
    by_date = Counter()
    weeks = defaultdict(lambda: {"questions": 0, "bot": 0, "human": 0, "unanswered": 0, "times": []})
    groups = defaultdict(lambda: {"questions": 0, "bot": 0, "unanswered": 0, "times": []})
    types = defaultdict(lambda: {"questions": 0, "bot": 0, "times": []})
    buckets = Counter()
    all_times, any_times, human_need = [], [], []
    for q in questions:
        lt = local(q["created_at"])
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
        bot = q["stage"] in BOT_STAGES and q["status"] in (Message.ANSWERED, Message.CLOSED)
        if bot:
            wk["bot"] += 1
            g["bot"] += 1
            tp["bot"] += 1
        cands = []  # birinchi javob: bot yoki xodim — qaysi biri oldin
        if bot and q["answered_at"]:
            cands.append(q["answered_at"])
        if q["id"] in first:
            cands.append(first[q["id"]][0])
            secs_h = max(0.0, (first[q["id"]][0] - q["created_at"]).total_seconds())
            all_times.append(secs_h)
            wk["human"] += 1
            if not bot:
                human_need.append(secs_h)
        if cands:
            secs = max(0.0, (min(cands) - q["created_at"]).total_seconds())
            any_times.append(secs)
            for row in (wk, g, tp):
                row["times"].append(secs)
            buckets[next(label for lim, label in BUCKETS if secs <= lim)] += 1
        elif not bot and q["status"] not in (Message.ANSWERED, Message.CLOSED):
            wk["unanswered"] += 1
            g["unanswered"] += 1

    # xodimlar: ish soatlari, kunlik faol vaqt, javob tezligi
    per = defaultdict(lambda: {"answers": 0, "clar": 0, "hours": [0] * 24, "weekdays": [0] * 7, "days": defaultdict(list),
                               "first_times": [], "weeks": Counter()})
    for r in staff_msgs:
        name = r.user.staff_name()
        lt = local(r.created_at)
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
            per[name]["first_times"].append(max(0.0, (at - q_at).total_seconds()))
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
            "within_15": round(100 * sum(1 for x in ft if x <= 900) / len(ft)) if ft else None,
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

    tasks = Counter(SupportTask.objects.filter(created_at__gte=start, created_at__lt=end).values_list("status", flat=True))
    return {
        **(info or {}), "unit": "s", "questions": len(questions), "answered_by_human": len(first), "answered_any": len(any_times),
        "first_median": _q(any_times, 0.5), "first_p90": _q(any_times, 0.9),
        "within_15": round(100 * sum(1 for x in any_times if x <= 900) / len(any_times)) if any_times else None,
        "within_60s": round(100 * sum(1 for x in any_times if x <= 60) / len(any_times)) if any_times else None,
        "human_median": _q(human_need, 0.5), "human_p90": _q(human_need, 0.9), "human_needed": len(human_need),
        "staff_median": _q(all_times, 0.5),
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


SPEED_BUCKETS = [(2, "≤2s"), (5, "2–5s"), (10, "5–10s"), (30, "10–30s"), (10 ** 9, ">30s")]


def speed(start, end, info=None):
    """Bot tezligi: savol Telegram'da yuborilgandan bot javobi yuborilguncha (soniya). Qayerda vaqt ketadi — navbat, OCR, AI, yuborish."""
    from .models import Settings
    rows = list(scoped(Message.objects.filter(kind=Message.QUESTION, created_at__gte=start, created_at__lt=end, answered_by="bot",
                                              answered_at__isnull=False))
                .values("id", "created_at", "answered_at", "stage", "photo_file_id", "group__title", "timing", "text"))
    def secs(r):
        return max(0.0, (r["answered_at"] - r["created_at"]).total_seconds())
    all_s = [secs(r) for r in rows]
    buckets = Counter(next(label for lim, label in SPEED_BUCKETS if v <= lim) for v in all_s)
    by = lambda key: defaultdict(list)  # noqa: E731
    stage, kind, group, hour, day = by(0), by(0), by(0), by(0), by(0)
    parts = defaultdict(list)
    for r, v in zip(rows, all_s):
        stage[r["stage"] or "—"].append(v)
        kind["photo" if r["photo_file_id"] else "text"].append(v)
        group[r["group__title"] or "—"].append(v)
        hour[local(r["created_at"]).hour].append(v)
        day[local(r["created_at"]).date().isoformat()].append(v)
        for k, ms in (r["timing"] or {}).items():
            if isinstance(ms, (int, float)):
                parts[k].append(ms / 1000)

    def pack(d, name):
        return sorted([{name: k, "n": len(v), "p50": _q(v, 0.5), "p90": _q(v, 0.9), "max": round(max(v), 1)} for k, v in d.items()],
                      key=lambda x: -x["n"])
    slow = sorted(zip(rows, all_s), key=lambda x: -x[1])[:15]
    s = Settings.load()
    return {
        **(info or {}), "answered": len(rows), "p50": _q(all_s, 0.5), "p90": _q(all_s, 0.9), "p99": _q(all_s, 0.99),
        "max": round(max(all_s), 1) if all_s else None,
        "within_5": round(100 * sum(1 for v in all_s if v <= 5) / len(all_s)) if all_s else None,
        "within_3": round(100 * sum(1 for v in all_s if v <= 3) / len(all_s)) if all_s else None,
        "buckets": [{"label": label, "n": buckets.get(label, 0)} for _lim, label in SPEED_BUCKETS],
        "by_stage": pack(stage, "stage"), "by_kind": pack(kind, "kind"), "by_group": pack(group, "group")[:20],
        "by_hour": [{"hour": h, "n": len(hour.get(h, [])), "p50": _q(hour.get(h, []), 0.5), "p90": _q(hour.get(h, []), 0.9)} for h in range(24)],
        "by_day": [{"date": k, "n": len(v), "p50": _q(v, 0.5), "p90": _q(v, 0.9)} for k, v in sorted(day.items())],
        "parts": {k: {"avg": round(sum(v) / len(v), 2), "p90": _q(v, 0.9)} for k, v in parts.items() if v},
        "slowest": [{"id": r["id"], "secs": round(v, 1), "stage": r["stage"], "photo": bool(r["photo_file_id"]),
                     "group": r["group__title"] or "", "text": (r["text"] or "")[:80], "timing": r["timing"] or {},
                     "at": r["created_at"]} for r, v in slow],
        "workers": s.workers, "cpu": os.cpu_count(),
    }

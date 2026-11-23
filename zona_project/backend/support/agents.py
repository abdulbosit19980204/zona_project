"""Agent (savol beruvchi) tahlili: savollari, natijalari, mavzulari, kim javob berdi va tavsiyalar —
nimani o'rgatish kerak (bir mavzuni qayta-qayta so'raydi), qayerda yordam kerak (hal bo'lmagan mavzular)."""
from collections import Counter, defaultdict

from .explore import _q_metrics, _q_rows
from .models import Message
from .workload import local


def detail(user, start, end, info=None):
    qs = Message.objects.filter(kind=Message.QUESTION, user=user, created_at__gte=start, created_at__lt=end).exclude(stage="dup") \
        .exclude(status=Message.IGNORED)
    rows, _names = _q_rows(qs)
    items = [v for _k, v in rows]
    m = _q_metrics(items)
    topics = defaultdict(lambda: {"n": 0, "no": 0, "unanswered": 0, "bot": 0})
    staff = Counter()
    daily = Counter()
    for k, v in rows:
        t = topics[k["topic"]]
        t["n"] += 1
        t["no"] += v["res"] == Message.NO
        t["unanswered"] += not v["done"]
        t["bot"] += v["bot"]
        if k["staff"] and k["staff"] != "—":
            staff[k["staff"]] += 1
        daily[k["day"]] += 1
    photo_only = qs.filter(text="").exclude(photo_file_id="").count()
    out = []
    n = m["count"] or 0
    if n >= 4 and (m["bot_share"] or 0) >= 50:
        out.append({"kind": "plus", "code": "bot_ok", "v": m["bot_share"]})
    if n >= 4 and (m["rate"] or 0) >= 80:
        out.append({"kind": "plus", "code": "resolve", "v": m["rate"]})
    if n >= 4 and m["unanswered"] / n >= 0.3:
        out.append({"kind": "minus", "code": "unanswered", "v": round(100 * m["unanswered"] / n)})
    if n >= 4 and photo_only / n >= 0.5:
        out.append({"kind": "minus", "code": "photo_only", "v": round(100 * photo_only / n)})
    for t, v in sorted(topics.items(), key=lambda x: -x[1]["n"]):
        if v["n"] >= 3 and t != "Turi aniqlanmagan":
            out.append({"kind": "train", "code": "repeat", "topic": t, "n": v["n"]})
    for t, v in sorted(topics.items(), key=lambda x: -(x[1]["no"] + x[1]["unanswered"])):
        if v["no"] + v["unanswered"] >= 2:
            out.append({"kind": "help", "code": "unsolved_topic", "topic": t, "n": v["no"] + v["unanswered"]})
    recent = [{"id": q.pk, "at": q.created_at, "text": (q.text or q.problem or "")[:200], "status": q.status,
               "resolution": q.resolution, "stage": q.stage, "photo": bool(q.photo_file_id),
               "link": q.group.message_link(q.message_id) if q.group_id else "", "group": q.group.title if q.group_id else ""}
              for q in qs.select_related("group").order_by("-created_at")[:60]]
    sp = user.staff_person if user.staff_person_id else None
    who = {"name": (sp.name if sp else "") or user.real_name or user.name, "username": user.username,
           "role": sp.get_role_display() if sp else user.position, "project": sp.project.name if sp and sp.project_id else user.department,
           "territory": sp.territory if sp else "", "supervisor": "", "phone": (sp.phone if sp else "") or user.phone}
    if sp:
        from .engine import supervisor_of
        sv = supervisor_of(user)
        who["supervisor"] = sv.name if sv else ""
    return {**(info or {}), "id": user.pk, "who": who, "metrics": m, "photo_only": photo_only,
            "topics": [{"topic": t, **v} for t, v in sorted(topics.items(), key=lambda x: -x[1]["n"])[:15]],
            "staff": [{"name": s, "n": c} for s, c in staff.most_common(8)],
            "daily": [{"date": d, "n": c} for d, c in sorted(daily.items())],
            "insights": out[:14], "recent": recent,
            "hours": [sum(1 for k, _v in rows if k["hour"] == f"{h:02d}") for h in range(24)],
            "first_seen": local(user.first_seen).date().isoformat() if user.first_seen else None}

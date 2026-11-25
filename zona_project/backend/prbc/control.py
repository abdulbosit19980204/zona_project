"""Savol vazifalarini to'liq nazorat (SLA): muddat, ikki tomonlama holat va muddati o'tganlar.

- sla_window(): vazifa boshlanishi va muddati — ish vaqtida (standart Du–Sha 09:00–18:00, Toshkent) sla_minutes daqiqa.
  Ish vaqtidan tashqari kelgan savolning muddati keyingi ish kuni boshidan hisoblanadi.
- push_status(): savol holati -> PRBC vazifasi. Savol hal bo'ldi -> Done; xodim javob yozdi / "jarayonda" -> In Progress;
  savol egasi "hal bo'lmadi" dedi (vazifa yopilgandan keyin) -> In Progress (qayta ochiladi). Har o'zgarish — PRBC'da izoh.
- watch_overdue(): muddati o'tgan ochiq vazifa — PRBC'da bitta izoh va ustuvorlik "shoshilinch" (bir marta).
- untasked()/backfill(): odamga uzatilgan, hal bo'lmagan, lekin vazifasi yo'q savollar — vazifa navbatiga.

Hammasi prbc_worker'da ishlaydi (bot PRBC'ni kutmaydi). PRBC'da webhook yo'q — holat davriy so'rov bilan."""
import logging
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from .client import Client, PrbcError
from .models import Change, Connection, Task

log = logging.getLogger("prbc")
TZ = ZoneInfo("Asia/Tashkent")
OPEN = ("new", "in_progress", "review", "")
STATUS_TTL = 6 * 3600
BACKFILL_DAYS = 7


# ------------------------------------------------------------------ muddat (ish vaqti bo'yicha)
def _days(conn):
    return set(conn.work_days or [0, 1, 2, 3, 4, 5])


def _work_bounds(conn, day):
    a = min(int(conn.work_start or 0), 22)
    b = max(int(conn.work_end or 24), a + 1)
    start = datetime.combine(day, dtime(a, 0), TZ)
    end = datetime.combine(day, dtime(23, 59), TZ) if b >= 24 else datetime.combine(day, dtime(b, 0), TZ)
    return start, end


def next_work_moment(conn, at):
    """`at` ish vaqtida bo'lsa — o'zi; bo'lmasa — keyingi ish vaqti boshi."""
    at = at.astimezone(TZ)
    for i in range(15):
        day = (at + timedelta(days=i)).date()
        if day.weekday() not in _days(conn):
            continue
        start, end = _work_bounds(conn, day)
        if i == 0 and at >= end:
            continue
        return max(at, start) if i == 0 else start
    return at


def sla_window(conn, at=None, minutes=None):
    """(boshlanish, muddat) — ish vaqtida `minutes` (standart sla_minutes) daqiqa; kun oxiridan oshsa — ertasiga davom."""
    minutes = int(minutes if minutes is not None else conn.sla_minutes or 10)
    start = next_work_moment(conn, at or timezone.now())
    cur, left = start, minutes
    for _ in range(30):
        _s, end = _work_bounds(conn, cur.date())
        room = (end - cur).total_seconds() / 60
        if left <= room:
            return start, cur + timedelta(minutes=left)
        left -= max(0, room)
        cur = next_work_moment(conn, end + timedelta(minutes=1))
    return start, cur + timedelta(minutes=left)


# ------------------------------------------------------------------ PRBC statuslari (loyiha bo'yicha)
def status_map(conn, client, refresh=False):
    """{"36": {"new": 171, "in_progress": 172, "done": 174, ...}, "none": {...}} — /task-statuses/ dan (6 soat kesh)."""
    cache = dict(conn.statuses or {})
    fresh = cache.get("_at") and (timezone.now().timestamp() - float(cache["_at"])) < STATUS_TTL
    if fresh and not refresh:
        return cache
    out = {"_at": timezone.now().timestamp()}
    try:
        for s in client.pages("/task-statuses/", {"page_size": 200}):
            key = str(s.get("project") or "none")
            cat = s.get("category") or ""
            row = out.setdefault(key, {})
            if cat and (cat not in row or s.get("is_default")):
                row[cat] = s.get("id")
    except PrbcError as e:
        log.warning("task statuses: %s", e)
        return cache
    Connection.objects.filter(pk=conn.pk).update(statuses=out)
    conn.statuses = out
    return out


def status_id(conn, client, project, category):
    m = status_map(conn, client)
    sid = (m.get(str(project or "none")) or {}).get(category)
    if sid is None:
        m = status_map(conn, client, refresh=True)
        sid = (m.get(str(project or "none")) or {}).get(category)
    return sid


def set_status(conn, client, t, category, note=""):
    """PRBC vazifasini `category` holatiga o'tkazadi (+ izoh). Qaytaradi: yangilangan Task yoki None (rad etildi)."""
    from .tasks import _full, _mirror
    sid = status_id(conn, client, t.project_id, category)
    if not sid:
        log.warning("status %s not found for project %s", category, t.project_id)
        return None
    try:
        client.patch(f"/tasks/{t.prbc_id}/", {"status": sid})
    except PrbcError as e:
        log.info("status %s -> %s refused: %s", t.code, category, e)
        sync = {**(t.sync or {}), "status_error": f"{category}: {e}"[:300]}
        Task.objects.filter(pk=t.pk).update(sync=sync)
        return None
    if note:
        try:
            client.comment(t.prbc_id, note)
        except PrbcError as e:
            log.info("status note %s: %s", t.code, e)
    data = _full(client, {"id": t.prbc_id})
    if not data.get("status"):
        Task.objects.filter(pk=t.pk).update(status_category=category, checked_at=timezone.now())
        t.status_category = category
        return t
    return _mirror(data, kind=t.kind)


# ------------------------------------------------------------------ savol -> vazifa holati
def _staff_touched(q):
    """Xodim savolga javob yozdimi / reaksiya qo'ydimi / "jarayonda" belgiladimi."""
    from support.models import Message
    if q.resolution == Message.WORK:
        return True
    return Message.objects.filter(kind=Message.STAFF, question=q).exists() or bool(q.answered_by)


def _when(dt):
    return timezone.localtime(dt).strftime("%d.%m %H:%M") if dt else ""


def push_status(conn=None, client=None, limit=40):
    """Biz yaratgan vazifalar: savol holati PRBC'ga. Qaytaradi: o'zgartirilgan vazifalar soni."""
    from support.models import Message
    conn = conn or Connection.get()
    if not conn.sync_status:
        return 0
    client = client or Client(conn)
    n = 0
    qs = (Task.objects.filter(kind=Task.OURS, support_task__message__isnull=False)
          .select_related("support_task__message").order_by("-id"))
    for t in qs.filter(status_category__in=OPEN)[:limit]:
        q = t.support_task.message
        sync = dict(t.sync or {})
        if q.resolution == Message.YES and not (q.resolved_by or "").startswith("prbc:"):
            who = q.resolved_by or "savol egasi"
            note = (f"✅ Savol hal bo'ldi ({who}, {_when(q.resolved_at)}). Vazifa avtomatik yopildi — "
                    f"guruhdagi savol holatidan.")
            done = set_status(conn, client, t, "done", note)
            if done:
                Task.objects.filter(pk=t.pk).update(sync={**sync, "pushed": "done", "pushed_at": timezone.now().isoformat()})
                Change.objects.create(kind=Change.TASK, actor="zona", data={"task": t.prbc_id},
                                      text=f"Bajarildi (savol hal bo'ldi): {t.code} — {t.title}"[:500])
                n += 1
            continue
        if sync.get("assignee_why") == "standart ijrochi" and not sync.get("reassigned"):
            r = Message.objects.filter(question=q, kind=Message.STAFF).select_related("user").order_by("created_at").first()
            pid = _prbc_of_tg(r.user, conn) if r else None
            if pid and pid not in {p_["id"] for p_ in t.people or [] if p_.get("role") == "assignee"}:
                try:
                    t = reassign(conn, client, t, pid, f"👤 Ijrochi: {r.user.name} — savolga u javob yozdi.")
                    sync = {**sync, "reassigned": pid}
                    Task.objects.filter(pk=t.pk).update(sync={**(t.sync or {}), **sync})
                    n += 1
                except PrbcError as e:
                    log.info("reassign %s: %s", t.code, e)
                    sync = {**sync, "reassigned": -1}
                    Task.objects.filter(pk=t.pk).update(sync=sync)
        if t.status_category == "new" and _staff_touched(q) and sync.get("pushed") != "in_progress":
            who = q.answered_by or "xodim"
            if set_status(conn, client, t, "in_progress", f"⏳ Ish boshlandi: {who} savolga javob yozdi ({_when(timezone.now())})."):
                Task.objects.filter(pk=t.pk).update(sync={**sync, "pushed": "in_progress"})
                n += 1
    # yopilgan vazifa — savol egasi keyin "hal bo'lmadi" dedi: qayta ochiladi (bir marta har javob uchun)
    since = timezone.now() - timedelta(days=3)
    for t in qs.filter(status_category="done", completed_at__gte=since)[:limit]:
        q = t.support_task.message
        sync = dict(t.sync or {})
        stamp = q.resolved_at.isoformat() if q.resolved_at else ""
        if q.resolution == Message.NO and q.resolved_at and t.completed_at and q.resolved_at > t.completed_at \
                and sync.get("reopened_for") != stamp:
            note = f"❌ Savol egasi: hal bo'lmadi ({_when(q.resolved_at)}). Vazifa qayta ochildi."
            if set_status(conn, client, t, "in_progress", note):
                start, due = sla_window(conn)
                try:
                    client.patch(f"/tasks/{t.prbc_id}/", {"due_at": due.isoformat()})
                except PrbcError:
                    pass
                Task.objects.filter(pk=t.pk).update(due_at=due, report={}, completed_at=None,
                                                    sync={**sync, "reopened_for": stamp, "pushed": "in_progress",
                                                          "overdue_noted": False})
                n += 1
    return n


def watch_overdue(conn=None, client=None, limit=20):
    """Muddati o'tgan ochiq vazifa — PRBC'da izoh va ustuvorlik "shoshilinch" (bir marta)."""
    conn = conn or Connection.get()
    if not conn.overdue_alert:
        return 0
    client = client or Client(conn)
    n = 0
    now = timezone.now()
    for t in Task.objects.filter(kind=Task.OURS, status_category__in=OPEN, due_at__lt=now).order_by("due_at")[:limit]:
        sync = dict(t.sync or {})
        if sync.get("overdue_noted"):
            continue
        late = int((now - t.due_at).total_seconds() // 60)
        try:
            client.patch(f"/tasks/{t.prbc_id}/", {"priority": 4})
            client.comment(t.prbc_id, f"⏰ Muddat o'tdi ({late} daqiqa kechikdi; me'yor — {conn.sla_minutes} daqiqa). "
                                      f"Iltimos, hal qiling yoki holatni yangilang.")
        except PrbcError as e:
            log.info("overdue %s: %s", t.code, e)
            if e.status in (401, 403, 404):
                sync["overdue_noted"] = True
                Task.objects.filter(pk=t.pk).update(sync=sync)
            continue
        Task.objects.filter(pk=t.pk).update(sync={**sync, "overdue_noted": True})
        n += 1
    return n


# ------------------------------------------------------------------ vazifasi yo'q ochiq savollar
def untasked(days=BACKFILL_DAYS):
    """Odamga uzatilgan (yoki "hal bo'lmadi"), hal bo'lmagan, vazifasi yo'q jonli savollar."""
    from django.db.models import Q
    from support.models import Message
    since = timezone.now() - timedelta(days=days)
    return (Message.objects.filter(kind=Message.QUESTION, source="live", created_at__gte=since, task__isnull=True)
            .exclude(group__creates_tasks=False)
            .filter(Q(status=Message.ESCALATED) | Q(resolution__in=[Message.NO, Message.WORK]))
            .exclude(resolution=Message.YES).exclude(status__in=[Message.IGNORED, Message.CLOSED])
            .select_related("user", "group", "entry", "entry__responsible").order_by("created_at"))


def backfill(days=BACKFILL_DAYS, dry=False, actor=""):
    """Vazifasiz ochiq savollar -> vazifa navbati (worker bir necha soniyada PRBC'da ochadi). Qaytaradi: soni."""
    from support import tasks as st_tasks
    from support.models import Media, SupportTask
    from support.engine import Decision, _person
    rows = list(untasked(days)[:100])
    if dry:
        return len(rows)
    n = 0
    for q in rows:
        e = q.entry
        d = Decision("", e, 0, "", True, [_person(e.responsible)] if e is not None and e.responsible_id else [])
        _need, assignee, reason = st_tasks.decide_task(q, d)
        title = (e.title if e is not None else (q.problem or q.text or q.ocr_text or "Savol").strip().splitlines()[0])[:120]
        text, link = st_tasks.build_text(q, title, assignee)
        media = list(Media.objects.filter(message=q).exclude(path="").values_list("id", flat=True)[:10])
        SupportTask.objects.create(message=q, entry=e, assignee=assignee, title=title, text=text, link=link,
                                   media_ids=media, reason=(reason or "backfill")[:200], created_by=actor[:150] or "backfill")
        n += 1
    return n


def control_summary(conn=None):
    """Nazorat paneli: ochiq, muddati o'tgan, 5 daqiqa ichida tugaydigan, bugun bajarilgan, me'yorda %, o'rtacha vaqt."""
    conn = conn or Connection.get()
    now = timezone.now()
    ours = Task.objects.filter(kind=Task.OURS)
    open_ = ours.filter(status_category__in=OPEN)
    today = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    week = ours.filter(status_category="done", completed_at__gte=now - timedelta(days=7))
    mins, ok = [], 0
    for c, s, due in week.values_list("completed_at", "prbc_created_at", "due_at"):
        if c and s:
            mins.append((c - s).total_seconds() / 60)
        if c and due and c <= due:
            ok += 1
    mins.sort()
    return {
        "open": open_.count(), "overdue": open_.filter(due_at__lt=now).count(),
        "due_soon": open_.filter(due_at__gte=now, due_at__lt=now + timedelta(minutes=5)).count(),
        "in_progress": open_.filter(status_category="in_progress").count(),
        "done_today": ours.filter(status_category="done", completed_at__gte=today).count(),
        "done_week": len(week), "on_time_pct": round(100 * ok / len(week)) if week else None,
        "median_minutes": round(mins[len(mins) // 2]) if mins else None,
        "untasked": untasked().count(), "sla_minutes": conn.sla_minutes,
    }


# ------------------------------------------------------------------ ijrochi: vazifa kimga tegishli
GENERIC = {"it_stargroup"}  # umumiy akkauntlar — ular javob yozsa ham aniq ijrochi emas


def _prbc_of_tg(user, conn):
    """Telegram foydalanuvchi -> PRBC user id (bog'langan shaxs, qo'lda moslash, zona xodimi)."""
    from .models import Person
    from .tasks import assignee_ids_for
    if user is None or (user.username or "").lower() in GENERIC:
        return None
    pid = Person.objects.filter(tg_user=user, prbc_user__isnull=False).exclude(status=Person.LEFT) \
        .values_list("prbc_user", flat=True).first()
    if pid and pid != 168:
        return int(pid)
    ids = assignee_ids_for(user.username, conn) if user.username else []
    return ids[0] if ids else None


def _member_ids(m, conn):
    from .tasks import assignee_ids_for
    if m is None:
        return []
    names = [m.telegram] if getattr(m, "telegram", "") and not getattr(m, "is_team", False) else []
    if getattr(m, "is_team", False) and hasattr(m, "contacts"):
        names += [c.telegram for c in m.contacts.exclude(telegram="").order_by("order", "id")]
    for n in names:
        if (n or "").lstrip("@").lower() in GENERIC:
            continue
        ids = assignee_ids_for(n, conn)
        if ids:
            return ids
    return []


def group_answerer(group, conn, days=30):
    """Shu guruhda savollarga eng ko'p javob yozgan xodim (umumiy akkauntsiz) -> PRBC user id."""
    import collections
    from support.models import Message, TgUser
    if group is None:
        return None
    since = timezone.now() - timedelta(days=days)
    cnt = collections.Counter(Message.objects.filter(group=group, kind=Message.STAFF, created_at__gte=since,
                                                     user__isnull=False).values_list("user_id", flat=True))
    for uid, _n in cnt.most_common(6):
        pid = _prbc_of_tg(TgUser.objects.filter(pk=uid).first(), conn)
        if pid:
            return pid
    return None


def pick_assignees(conn, st, q):
    """Vazifa kimga tegishli — (PRBC id'lar, sabab). Tartib: savolga javob yozgan xodim -> mavzu mas'uli (bilim bazasi)
    -> toifa mas'uli (aksiya, to'lov, login...) -> guruh ijrochisi (sozlama) -> guruhda ko'p javob beradigan -> standart."""
    from support.engine import category_owner
    from support.models import Message
    from .tasks import assignee_ids_for
    if q is not None:
        for r in Message.objects.filter(question=q, kind=Message.STAFF).select_related("user").order_by("created_at")[:5]:
            pid = _prbc_of_tg(r.user, conn)
            if pid:
                return [pid], f"savolga javob yozgan: {r.user.name}"
    if st is not None and st.entry_id and st.entry.responsible_id:
        ids = _member_ids(st.entry.responsible, conn)
        if ids:
            return ids, f"mavzu mas'uli: {st.entry.responsible.name}"
    if st is not None and st.assignee and st.assignee.lstrip("@").lower() not in GENERIC:
        ids = assignee_ids_for(st.assignee, conn)
        if ids:
            return ids, f"mas'ul: @{st.assignee.lstrip('@')}"
    if q is not None and q.category:
        owner = category_owner(q.category)
        ids = _member_ids(owner, conn) if owner is not None else []  # xodim (Member) yoki jamoa a'zosi (ContactOwner)
        if ids:
            return ids, f"toifa mas'uli ({q.category}): {getattr(owner, 'name', '')}"
    if q is not None and q.group_id:
        pid = (conn.group_assignees or {}).get(str(q.group_id))
        if str(pid or "").isdigit():
            return [int(pid)], f"guruh ijrochisi ({q.group.title})"
        pid = group_answerer(q.group, conn)
        if pid:
            return [pid], f"guruhda ko'p javob beradi ({q.group.title})"
    ids = [int(x) for x in conn.task_default_assignees or []]
    return ids, "standart ijrochi"


def reassign(conn, client, t, new_id, note=""):
    """PRBC vazifa ijrochisini almashtiradi: yangisi qo'shiladi, eski ijrochi(lar) olib tashlanadi."""
    from .tasks import _full, _mirror
    data = _full(client, {"id": t.prbc_id})
    rows = [a for a in data.get("assignees") or [] if a.get("role") == "assignee"]
    if any((a.get("user") or {}).get("id") == new_id for a in rows):
        return t
    try:
        client.post(f"/tasks/{t.prbc_id}/assignees/", {"user_id": new_id, "role": "assignee"})
    except PrbcError as e:
        if e.status != 400:
            raise
        client.post(f"/tasks/{t.prbc_id}/assignees/", {"user": new_id, "role": "assignee"})
    for a in rows:
        try:
            client.request("DELETE", f"/tasks/{t.prbc_id}/assignees/{a['id']}/")
        except PrbcError as e:
            log.info("remove assignee %s from %s: %s", a.get("id"), t.code, e)
    if note:
        try:
            client.comment(t.prbc_id, note)
        except PrbcError:
            pass
    return _mirror(_full(client, {"id": t.prbc_id}), kind=t.kind)

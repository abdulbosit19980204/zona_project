"""PRBC integratsiyasi API (/api/prbc/...). Faqat Zona administratori."""
from datetime import timedelta

from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from zona.api import zona_api
from zona.crypto import encrypt
from zona.permissions import IsZonaAdmin

from . import people, tasks
from .client import Client, PrbcError, items_of
from .models import Change, Connection, Person, SyncRun, Task

ADMIN = [IsZonaAdmin]
EDITABLE = ["enabled", "base_url", "phone", "lifecycle_project", "task_project", "task_default_assignees", "sync_minutes",
            "auto_left", "comment_devices", "task_watchers", "close_on_done", "notify_done", "notify_created",
            "attach_files", "assignee_map", "watch_self", "outlet_lookup", "sla_minutes", "task_priority", "work_start",
            "work_end", "work_days", "sync_status", "overdue_alert"]


def _actor(request):
    return request.user.get_username() if request.user and request.user.is_authenticated else ""


def connection_payload(c):
    alive = bool(c.worker_beat and timezone.now() - c.worker_beat < timedelta(seconds=90))
    return {**{f: getattr(c, f) for f in EDITABLE}, "password_set": bool(c.password_enc), "organization": c.organization,
            "me": c.me, "last_sync_at": c.last_sync_at, "last_ok_at": c.last_ok_at, "last_error": c.last_error,
            "sync_requested": c.sync_requested, "worker_alive": alive, "worker_beat": c.worker_beat,
            "ready": not not_ready(c), "not_ready": not_ready(c), "task_all_escalated": _support_flag(),
            "named": _named([*(c.task_default_assignees or []), *(c.task_watchers or []),
                             *(c.assignee_map or {}).values()])}


def _support_flag():
    from support.models import Settings
    return bool(Settings.load().task_all_escalated)


def parse_map(v):
    """Telegram username -> PRBC user id: {"xusniddin": 15} yoki "xusniddin=15, said=7" matni."""
    if isinstance(v, str):
        pairs = [x.split("=", 1) for x in v.replace("\n", ",").split(",") if "=" in x]
        v = {a: b for a, b in pairs}
    out = {}
    for k, val in (v or {}).items() if isinstance(v, dict) else []:
        k, val = str(k).strip().lstrip("@").lower(), str(val).strip()
        if k and val.isdigit():
            out[k[:64]] = int(val)
    return dict(list(out.items())[:50])


def _named(ids):
    """PRBC user id -> ism (sozlamalarda tanlangan ijrochi va kuzatuvchilarni ko'rsatish uchun)."""
    ids = [int(x) for x in ids if str(x).isdigit()]
    return {str(k): v for k, v in Person.objects.filter(prbc_user__in=ids).values_list("prbc_user", "full_name")}


@zona_api(["GET", "PATCH"], ADMIN)
def connection(request):
    c = Connection.get()
    if request.method == "PATCH":
        d = request.data
        for f in EDITABLE:
            if f in d:
                v = d[f]
                if f in ("lifecycle_project", "task_project"):
                    v = int(v) if str(v or "").isdigit() else None
                elif f == "sync_minutes":
                    v = max(5, min(int(v or 30), 1440))
                elif f == "sla_minutes":
                    v = max(1, min(int(v or 10), 1440))
                elif f == "task_priority":
                    v = max(0, min(int(v or 0), 4))
                elif f in ("work_start", "work_end"):
                    v = max(0, min(int(v or 0), 24))
                elif f == "work_days":
                    v = sorted({int(x) for x in (v or []) if str(x).isdigit() and 0 <= int(x) <= 6})
                elif f in ("task_default_assignees", "task_watchers"):
                    v = [int(x) for x in (v or []) if str(x).isdigit()][:20]
                elif f in ("enabled", "auto_left", "comment_devices", "close_on_done", "notify_done", "notify_created",
                           "attach_files", "watch_self", "outlet_lookup", "sync_status", "overdue_alert"):
                    v = bool(v)
                elif f == "assignee_map":
                    v = parse_map(v)
                else:
                    v = str(v or "").strip()[:200]
                setattr(c, f, v)
        if d.get("password"):
            c.password_enc = encrypt(str(d["password"]))
            c.access_enc = c.refresh_enc = ""  # yangi parol — yangi seans
            c.access_until = None
        if c.enabled and c.phone and c.password_enc and c.last_error.startswith("PRBC ulanishi yoqilmagan"):
            c.last_error = ""  # eski "yoqilmagan" xatosi endi ahamiyatsiz
        c.save()
        if "task_all_escalated" in d:
            from support.models import Settings
            Settings.objects.filter(pk=Settings.load().pk).update(task_all_escalated=bool(d["task_all_escalated"]))
        Change.objects.create(kind=Change.UPDATED, text="PRBC sozlamalari o'zgartirildi", actor=_actor(request),
                              data={k: ("••••" if k == "password" else v) for k, v in d.items() if k in EDITABLE + ["password"]})
    return Response(connection_payload(c))


@zona_api(["POST"], ADMIN)
def test(request):
    """Kirish + profil + ochiq manbalar (vazifalar, xodimlar ro'yxati, HR) + loyihalar ro'yxati."""
    c = Connection.get()
    client = Client(c)
    try:
        client.login()
        me = client.profile() or {}
    except PrbcError as e:
        return Response({"ok": False, "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    emp = me.get("employee") if isinstance(me.get("employee"), dict) else {}
    c.me = {"id": me.get("id"), "full_name": me.get("full_name") or emp.get("full_name") or me.get("phone", ""),
            "position": me.get("position") or emp.get("position", "")}
    org = me.get("organization") or emp.get("organization")
    c.organization = org.get("id") if isinstance(org, dict) else (org if isinstance(org, int) else c.organization)
    c.save(update_fields=["me", "organization", "updated_at"])
    checks = {}
    for key, path in (("tasks", "/tasks/"), ("roster", "/tasks/assignable-users/"), ("hr", "/hr/employees/"),
                      ("hierarchy", "/hierarchy/tree/")):
        try:
            data = client.get(path, {"page": 1} if key == "tasks" else None)
            checks[key] = {"ok": True, "count": (data.get("count") if isinstance(data, dict) and "count" in data else len(items_of(data)))}
        except PrbcError as e:
            checks[key] = {"ok": False, "detail": str(e)[:200]}
    projects = []
    try:
        projects = tasks.load_projects(c, client)
    except PrbcError:
        pass
    return Response({"ok": True, "me": c.me, "organization": c.organization, "checks": checks, "projects": projects})


@zona_api(["POST"], ADMIN)
def sync(request):
    c = Connection.get()
    problem = not_ready(c)
    if problem:  # worker'ga yuborib, keyin umumiy xato ko'rsatish o'rniga — aniq sabab darhol
        return Response({"detail": problem}, status=status.HTTP_400_BAD_REQUEST)
    Connection.objects.filter(pk=1).update(sync_requested=True, last_error="")
    return Response(connection_payload(Connection.get()))


def not_ready(c):
    if not c.phone:
        return "PRBC telefon raqami kiritilmagan: Ulanish bo'limida kiriting va «Saqlash»ni bosing."
    if not c.password_enc:
        return "PRBC paroli kiritilmagan: Ulanish bo'limida kiriting va «Saqlash»ni bosing."
    if not c.enabled:
        return "PRBC ulanishi o'chiq: Ulanish bo'limida «Ulanish yoqilgan»ni yoqing va «Saqlash»ni bosing."
    return ""


def person_payload(p):
    def ref(obj, label):
        return {"id": obj.pk, "label": label} if obj else None
    return {"id": p.pk, "prbc_user": p.prbc_user, "tab_number": p.tab_number, "full_name": p.full_name, "position": p.position,
            "department": p.department, "company": p.company, "phone": p.phone, "email": p.email, "status": p.status,
            "hired_on": p.hired_on, "left_on": p.left_on, "left_reason": p.left_reason, "hire_task": p.hire_task,
            "leave_task": p.leave_task, "in_roster": p.in_roster, "sources": p.sources, "link_manual": p.link_manual,
            "left_applied": p.left_applied, "last_seen": p.last_seen, "agent_code": p.agent_code, "code_manual": p.code_manual,
            "links": {"staff_person": ref(p.staff_person, p.staff_person and f"{p.staff_person.name or 'Vakansiya'} · {p.staff_person.territory}"),
                      "member": ref(p.member, p.member and p.member.name),
                      "inv_employee": ref(p.inv_employee, p.inv_employee and p.inv_employee.full_name),
                      "tg_user": ref(p.tg_user, p.tg_user and (p.tg_user.name + (f" @{p.tg_user.username}" if p.tg_user.username else "")))}}


@zona_api(["GET"], ADMIN)
def overview(request):
    by_status = dict(Person.objects.values_list("status").annotate(n=Count("id")))
    agg = Person.objects.aggregate(
        n_staff=Count("id", filter=Q(staff_person__isnull=False)), n_member=Count("id", filter=Q(member__isnull=False)),
        n_inv=Count("id", filter=Q(inv_employee__isnull=False)), n_tg=Count("id", filter=Q(tg_user__isnull=False)),
        n_unlinked=Count("id", filter=Q(staff_person__isnull=True, member__isnull=True, inv_employee__isnull=True, tg_user__isnull=True)))
    linked = {k[2:]: v for k, v in agg.items()}
    since = timezone.now() - timedelta(days=30)
    left_members = Person.objects.filter(status=Person.LEFT, member__isnull=False).select_related("member")
    return Response({
        "connection": connection_payload(Connection.get()),
        "people": {"total": sum(by_status.values()), **by_status}, "linked": linked,
        "month": {"left": Change.objects.filter(kind=Change.LEFT, at__gte=since).count(),
                  "new": Change.objects.filter(kind=Change.NEW, at__gte=since).count()},
        "left_members": [{"person": p.full_name, "member": p.member.name, "member_id": p.member_id, "left_on": p.left_on}
                         for p in left_members[:50]],
        "runs": [{"id": r.id, "started_at": r.started_at, "finished_at": r.finished_at, "ok": r.ok, "stats": r.stats,
                  "error": r.error} for r in SyncRun.objects.all()[:10]],
    })


@zona_api(["GET"], ADMIN)
def people_list(request):
    qs = Person.objects.select_related("staff_person", "member", "inv_employee", "tg_user")
    st = request.query_params.get("status")
    if st:
        qs = qs.filter(status__in=st.split(","))
    if request.query_params.get("unlinked"):
        qs = qs.filter(staff_person__isnull=True, member__isnull=True, inv_employee__isnull=True, tg_user__isnull=True)
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(position__icontains=q) | Q(department__icontains=q) | Q(phone__icontains=q)
                       | Q(tab_number__icontains=q) | Q(agent_code__icontains=q) | Q(name_key__icontains=" ".join(people.name_tokens(q))))
    total = qs.count()
    page = max(1, int(request.query_params.get("page") or 1))
    order = "-left_on" if st and "left" in st else "full_name"
    rows = qs.order_by(order, "full_name")[(page - 1) * 100: page * 100]
    return Response({"total": total, "page": page, "items": [person_payload(p) for p in rows]})


@zona_api(["POST"], ADMIN)
def person_link(request, pk):
    """Qo'lda bog'lash yoki uzish: {field: staff_person|member|inv_employee|tg_user, id: <id>|null}."""
    from inventory.models import Employee
    from support.models import TgUser
    from zona.models import Member, StaffPerson
    p = Person.objects.filter(pk=pk).first()
    models = {"staff_person": StaffPerson, "member": Member, "inv_employee": Employee, "tg_user": TgUser}
    field = request.data.get("field")
    if not p or field not in models:
        return Response({"detail": "Topilmadi"}, status=status.HTTP_404_NOT_FOUND)
    obj = models[field].objects.filter(pk=request.data.get("id")).first() if request.data.get("id") else None
    if obj and Person.objects.filter(**{field: obj}).exclude(pk=p.pk).exists():
        return Response({"detail": "Bu yozuv boshqa PRBC xodimiga bog'langan."}, status=status.HTTP_400_BAD_REQUEST)
    setattr(p, field, obj)
    p.link_manual = True
    p.save()
    Change.objects.create(person=p, kind=Change.LINKED, actor=_actor(request),
                          text=f"Qo'lda {'bog' + chr(39) + 'landi' if obj else 'uzildi'}: {p.full_name} — {field}")
    return Response(person_payload(p))


@zona_api(["PATCH"], ADMIN)
def person_edit(request, pk):
    """Agent kodini qo'lda kiritish: {agent_code}. Bo'sh qiymat — avtomatik (PRBC/1C yoki kontakt o'rni kodi)."""
    p = Person.objects.select_related("staff_person", "member", "inv_employee", "tg_user").filter(pk=pk).first()
    if not p:
        return Response({"detail": "Topilmadi"}, status=status.HTTP_404_NOT_FOUND)
    if "agent_code" in request.data:
        code = " ".join(str(request.data.get("agent_code") or "").split())[:80]
        old = p.agent_code
        p.agent_code, p.code_manual = code, bool(code)
        if not code and p.staff_person_id:
            p.agent_code = p.staff_person.territory[:80]
        p.save(update_fields=["agent_code", "code_manual", "updated_at"])
        Change.objects.create(person=p, kind=Change.UPDATED, actor=_actor(request),
                              text=f"Agent kodi: {p.full_name} — {old or '—'} → {p.agent_code or '—'}"[:500])
    return Response(person_payload(p))


@zona_api(["POST"], ADMIN)
def person_left(request, pk):
    p = Person.objects.filter(pk=pk).first()
    if not p:
        return Response({"detail": "Topilmadi"}, status=status.HTTP_404_NOT_FOUND)
    if request.data.get("revert"):
        people.revert_left(p, _actor(request))
    else:
        if p.status != Person.LEFT:
            p.status, p.left_on = Person.LEFT, p.left_on or timezone.localdate()
            p.left_reason = p.left_reason or f"Qo'lda belgilandi ({_actor(request)})"
            p.save()
            Change.objects.create(person=p, kind=Change.LEFT, actor=_actor(request), text=f"Bo'shagan (qo'lda): {p.full_name}")
        if not p.left_applied:
            people.apply_left(p, actor=_actor(request))
    p.refresh_from_db()
    return Response(person_payload(p))


@zona_api(["GET"], ADMIN)
def link_candidates(request):
    """Qo'lda bog'lash uchun bizdagi yozuvlar: ?field=staff_person&q=ism"""
    from inventory.models import Employee
    from support.models import TgUser
    from zona.models import Member, StaffPerson
    field, q = request.query_params.get("field"), (request.query_params.get("q") or "").strip()
    spec = {"staff_person": (StaffPerson.objects.all(), "name", lambda o: f"{o.name or 'Vakansiya'} · {o.territory} · {o.project.name}"),
            "member": (Member.objects.filter(is_team=False), "name", lambda o: f"{o.name} · {o.role}"),
            "inv_employee": (Employee.objects.all(), "full_name", lambda o: f"{o.full_name} · {o.position}"),
            "tg_user": (TgUser.objects.all(), "name", lambda o: f"{o.name} @{o.username}" if o.username else o.name)}
    if field not in spec:
        return Response([])
    qs, attr, label = spec[field]
    if q:
        qs = qs.filter(**{f"{attr}__icontains": q})
    return Response([{"id": o.pk, "label": label(o)} for o in qs.order_by(attr)[:30]])


@zona_api(["GET"], ADMIN)
def changes(request):
    qs = Change.objects.select_related("person")
    kind = request.query_params.get("kind")
    if kind:
        qs = qs.filter(kind__in=kind.split(","))
    return Response([{"id": c.id, "at": c.at, "kind": c.kind, "text": c.text, "actor": c.actor,
                      "person": c.person_id} for c in qs[:300]])


def _question_info(t):
    st = t.support_task if t.support_task_id else None
    q = st.message if st and st.message_id else None
    if q is None:
        return {"asker": "", "group": "", "q_text": "", "q_resolution": "", "q_link": ""}
    return {"asker": q.user.name if q.user_id else "", "group": q.group.title if q.group_id else "",
            "q_text": (q.problem or q.text or q.ocr_text or "")[:300], "q_resolution": q.resolution,
            "q_link": q.group.message_link(q.message_id) if q.group_id else ""}


def task_payload(t, conn, full=False):
    open_ = t.status_category in tasks.OPEN
    d = {"id": t.id, "prbc_id": t.prbc_id, "code": t.code, "title": t.title, "kind": t.kind, "status": t.status_name,
         "category": t.status_category, "project": t.project_name, "assignee": t.assignee, "due_at": t.due_at,
         "updated_at": t.prbc_updated_at, "created_at": t.prbc_created_at, "created_by": t.created_by, "person": t.person_id,
         "person_name": t.person.full_name if t.person_id else "", "url": tasks.task_url(conn, t),
         "people": t.people, "watchers": t.watchers, "completed_at": t.completed_at, "completed_by": t.completed_by,
         "spent_minutes": t.spent_minutes, "overdue": bool(open_ and t.due_at and t.due_at < timezone.now()),
         "on_time": (t.report or {}).get("on_time"), "has_report": bool(t.report), "checked_at": t.checked_at,
         "question": t.support_task.message_id if t.support_task_id else None,
         "files": int((t.sync or {}).get("files") or 0), "notified": (t.sync or {}).get("notified") or [],
         "due_in": int((t.due_at - timezone.now()).total_seconds()) if open_ and t.due_at else None,
         "pushed": (t.sync or {}).get("pushed") or "", "status_error": (t.sync or {}).get("status_error") or "",
         **_question_info(t)}
    if full:
        d["report"] = t.report
    return d


@zona_api(["GET", "POST"], ADMIN)
def task_list(request):
    conn = Connection.get()
    if request.method == "POST":
        d = request.data
        title = str(d.get("title") or "").strip()
        if not title:
            return Response({"detail": "Sarlavha kiriting."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            watchers = d.get("watcher_ids")  # yuborilmasa — sozlamadagi kuzatuvchilar (Kamoliddin aka)
            t = tasks.create(title=title, description=str(d.get("description") or ""),
                             assignee_ids=[int(x) for x in d.get("assignee_ids") or [] if str(x).isdigit()],
                             watcher_ids=None if watchers is None else [int(x) for x in watchers if str(x).isdigit()],
                             project=int(d["project"]) if str(d.get("project") or "").isdigit() else None,
                             priority=int(d["priority"]) if str(d.get("priority") or "").isdigit() else None,
                             due_at=d.get("due_at") or None, actor=_actor(request), conn=conn)
        except PrbcError as e:
            return Response({"detail": f"PRBC: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(task_payload(t, conn), status=status.HTTP_201_CREATED)
    qs = Task.objects.select_related("person", "support_task__message__user", "support_task__message__group")
    p = request.query_params
    if p.get("kind"):
        qs = qs.filter(kind__in=p["kind"].split(","))
    if p.get("open"):
        qs = qs.filter(status_category__in=tasks.OPEN)
    if p.get("done"):
        qs = qs.filter(status_category="done")
    if p.get("overdue"):
        qs = qs.filter(status_category__in=tasks.OPEN, due_at__lt=timezone.now())
    if p.get("assignee"):
        qs = qs.filter(Q(assignee__icontains=p["assignee"]) | Q(people__icontains=p["assignee"]))
    if p.get("q"):
        qs = qs.filter(Q(title__icontains=p["q"]) | Q(code__icontains=p["q"]))
    return Response([task_payload(t, conn) for t in qs[:300]])


@zona_api(["GET"], ADMIN)
def task_detail(request, pk):
    """Bitta vazifa to'liq: ijrochilar, kuzatuvchi va bajarilgan bo'lsa — hisobot (izohlar, chek-list, tarix)."""
    t = Task.objects.select_related("person", "support_task").filter(pk=pk).first()
    if not t:
        return Response({"detail": "Topilmadi"}, status=status.HTTP_404_NOT_FOUND)
    return Response(task_payload(t, Connection.get(), full=True))


@zona_api(["GET"], ADMIN)
def task_stats(request):
    """Ijrochilar bo'yicha nazorat: ?days=30 (0 — hammasi)."""
    days = int(request.query_params.get("days") or 30)
    since = timezone.now() - timedelta(days=days) if days > 0 else None
    rows = tasks.stats(since)
    total = {k: sum(r[k] for r in rows) for k in ("open", "overdue", "late")}
    qs = Task.objects.filter(kind__in=[Task.OURS, Task.HIRE, Task.LEAVE])
    if since:
        qs = qs.filter(tasks.since_q(since))
    total.update(total=qs.count(), done=qs.filter(status_category="done").count(),
                 open=qs.filter(status_category__in=tasks.OPEN).count(),
                 cancelled=qs.filter(status_category="cancelled").count(),
                 overdue=qs.filter(status_category__in=tasks.OPEN, due_at__lt=timezone.now()).count())
    return Response({"rows": rows, "total": total, "groups": tasks.group_stats(since)})


@zona_api(["GET"], ADMIN)
def projects(request):
    """PRBC loyihalari (keshdan; ?refresh=1 yoki kesh bo'sh bo'lsa — PRBC'dan qayta o'qiladi)."""
    c = Connection.get()
    if request.query_params.get("refresh") or not c.projects:
        if not (c.phone and c.password_enc):
            return Response(c.projects or [])
        try:
            tasks.load_projects(c, Client(c))
        except PrbcError as e:
            if not c.projects:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(c.projects)


@zona_api(["GET", "PATCH"], ADMIN)
def group_projects(request):
    """Telegram guruh -> PRBC loyiha. Savol qaysi guruhdan kelsa, vazifa shu loyihada ochiladi
    (bog'lanmagan guruh — standart loyiha). PATCH {group_id: project_id | null, ...}."""
    from support.models import Group
    c = Connection.get()
    if request.method == "PATCH":
        cur = {str(k): v for k, v in (c.group_projects or {}).items()}
        owners = {str(k): v for k, v in (c.group_assignees or {}).items()}
        valid = {p["id"] for p in c.projects or [] if p.get("id")}
        for k, v in (request.data or {}).items():
            k = str(k)
            if k.startswith("tasks:") and k[6:].isdigit():  # guruhdan vazifa ochiladimi
                Group.objects.filter(pk=int(k[6:])).update(creates_tasks=bool(v))
                continue
            if k.startswith("owner:") and k[6:].isdigit():  # guruh ijrochisi (PRBC user id; bo'sh — avtomatik)
                if str(v or "").isdigit() and int(v):
                    owners[k[6:]] = int(v)
                else:
                    owners.pop(k[6:], None)
                continue
            if not k.isdigit():
                continue
            if v in (None, "", 0, "0"):
                cur.pop(str(k), None)
            elif str(v).isdigit() and (not valid or int(v) in valid):
                cur[str(k)] = int(v)
        c.group_projects, c.group_assignees = cur, owners
        c.save(update_fields=["group_projects", "group_assignees", "updated_at"])
        Change.objects.create(kind=Change.UPDATED, text="Guruh → PRBC loyiha bog'lanishi o'zgartirildi",
                              actor=_actor(request), data=request.data)
    from . import control as ctl
    names = {p["id"]: p["name"] for p in c.projects or []}
    pool = {int(x) for x in [*(c.task_default_assignees or []), *(c.assignee_map or {}).values(),
                             *(c.group_assignees or {}).values()] if str(x).isdigit()}
    pool |= set(Person.objects.filter(member__isnull=False, prbc_user__isnull=False).values_list("prbc_user", flat=True))
    people_ = dict(Person.objects.filter(prbc_user__in=pool).exclude(status=Person.LEFT).values_list("prbc_user", "full_name"))
    rows = []
    groups = Group.objects.filter(is_active=True).annotate(n=Count("messages", filter=Q(messages__kind="question"))).order_by("-n", "title")
    for g in groups:
        pid = (c.group_projects or {}).get(str(g.pk))
        sug = tasks.suggest_project(g.title, c.projects or []) if not pid else None
        owner = (c.group_assignees or {}).get(str(g.pk))
        auto = None if owner else ctl.group_answerer(g, c)
        rows.append({"id": g.pk, "title": g.title or str(g.chat_id), "questions": g.n, "project": pid,
                     "project_name": names.get(pid, f"#{pid}" if pid else ""),
                     "suggested": sug, "suggested_name": names.get(sug, "") if sug else "",
                     "creates_tasks": g.creates_tasks, "owner": owner, "owner_name": people_.get(owner, ""),
                     "auto_owner": auto, "auto_owner_name": people_.get(auto) or (
                         Person.objects.filter(prbc_user=auto).values_list("full_name", flat=True).first() if auto else "") or ""})
    return Response({"default": c.task_project, "default_name": names.get(c.task_project, ""), "groups": rows,
                     "people": sorted([{"id": k, "name": v} for k, v in people_.items()], key=lambda x: x["name"])})


@zona_api(["GET"], ADMIN)
def assignable(request):
    """Vazifaga qo'yish mumkin bo'lgan PRBC xodimlari (oxirgi sinxronlashdan)."""
    qs = Person.objects.filter(prbc_user__isnull=False, in_roster=True).exclude(status=Person.LEFT)
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(position__icontains=q))
    return Response([{"id": p.prbc_user, "name": p.full_name, "position": p.position} for p in qs[:50]])


@zona_api(["GET"], ADMIN)
def outlet_status(request):
    """Mijoz arizasining PRBC'dagi holati — bot guruhda beradigan javobning o'zi (panelda tekshirish uchun).
    ?q=STIR / JShShIR / 1C kodi (UZ-...)."""
    from . import outlets
    q = (request.query_params.get("q") or "")[:300]
    ids = outlets.find_ids(q)
    if not ids:
        return Response({"detail": "STIR (9 raqam), JShShIR (14 raqam) yoki 1C kodini (UZ-…) yozing."},
                        status=status.HTTP_400_BAD_REQUEST)
    c = Connection.get()
    if not c.phone or not c.password_enc:
        return Response({"detail": "PRBC ulanishi sozlanmagan."}, status=status.HTTP_400_BAD_REQUEST)
    client = outlets.Client(c)
    client.timeout = outlets.TIMEOUT
    found = outlets.lookup(ids, client=client)
    if not found:
        return Response({"detail": "PRBC javob bermadi — keyinroq urinib ko'ring."}, status=status.HTTP_502_BAD_GATEWAY)
    return Response({"ids": ids, "found": sum(len(r.get("requests") or []) + len(r.get("attachments") or []) for r in found.values()),
                     "text": outlets.card(found, "uz"), "text_ru": outlets.card(found, "ru"), "bot_enabled": c.enabled and c.outlet_lookup})


# ====================================================================== nazorat (SLA)
@zona_api(["GET"], ADMIN)
def control(request):
    """Nazorat paneli: xulosa + ochiq vazifalar (muddat bo'yicha) + bugun bajarilganlar + vazifasiz savollar."""
    from . import control as ctl
    conn = Connection.get()
    rel = ("person", "support_task__message__user", "support_task__message__group")
    open_ = (Task.objects.filter(kind=Task.OURS, status_category__in=ctl.OPEN).select_related(*rel)
             .order_by(F("due_at").asc(nulls_last=True), "id")[:200])
    today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    done = (Task.objects.filter(kind=Task.OURS, status_category="done", completed_at__gte=today - timedelta(days=1))
            .select_related(*rel).order_by("-completed_at")[:50])
    pending = [{"id": q.id, "text": (q.problem or q.text or q.ocr_text or "")[:200], "asker": q.user.name if q.user_id else "",
                "group": q.group.title if q.group_id else "", "created_at": q.created_at, "status": q.status,
                "link": q.group.message_link(q.message_id) if q.group_id else ""} for q in ctl.untasked()[:50]]
    return Response({"summary": ctl.control_summary(conn), "open": [task_payload(t, conn) for t in open_],
                     "done": [task_payload(t, conn) for t in done], "untasked": pending,
                     "worker_alive": connection_payload(conn)["worker_alive"]})


@zona_api(["POST"], ADMIN)
def task_set_status(request, pk):
    """Paneldan: {category: in_progress|done|cancelled|new} — PRBC'da holat + izoh (kim o'zgartirdi)."""
    from . import control as ctl
    t = Task.objects.filter(pk=pk, kind=Task.OURS).first()
    if not t:
        return Response({"detail": "Topilmadi"}, status=status.HTTP_404_NOT_FOUND)
    cat = str(request.data.get("category") or "")
    labels = {"in_progress": "jarayonda", "done": "bajarildi", "cancelled": "bekor qilindi", "new": "yangi"}
    if cat not in labels:
        return Response({"detail": "Noto'g'ri holat."}, status=status.HTTP_400_BAD_REQUEST)
    conn = Connection.get()
    try:
        upd = ctl.set_status(conn, Client(conn), t, cat, f"🔄 Holat: {labels[cat]} — {_actor(request) or 'panel'} (Foydali paneli).")
    except PrbcError as e:
        return Response({"detail": f"PRBC: {e}"}, status=status.HTTP_400_BAD_REQUEST)
    if upd is None:
        t.refresh_from_db()
        return Response({"detail": "PRBC holatni o'zgartirmadi: " + ((t.sync or {}).get("status_error") or "sabab noma'lum")},
                        status=status.HTTP_400_BAD_REQUEST)
    Change.objects.create(kind=Change.TASK, actor=_actor(request), data={"task": t.prbc_id},
                          text=f"{t.code}: holat → {labels[cat]}"[:500])
    return Response(task_payload(upd, conn))


@zona_api(["POST"], ADMIN)
def backfill(request):
    """Vazifasiz ochiq savollarga vazifa ochish: {days?: 7, dry?: true} -> {count}."""
    from . import control as ctl
    days = max(1, min(int(request.data.get("days") or ctl.BACKFILL_DAYS), 30))
    dry = bool(request.data.get("dry"))
    n = ctl.backfill(days, dry=dry, actor=_actor(request))
    if n and not dry:
        Change.objects.create(kind=Change.TASK, actor=_actor(request), text=f"{n} ta ochiq savolga vazifa navbatga qo'yildi")
    return Response({"count": n, "dry": dry})

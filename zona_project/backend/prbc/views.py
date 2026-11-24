"""PRBC integratsiyasi API (/api/prbc/...). Faqat Zona administratori."""
from datetime import timedelta

from django.db.models import Count, Q
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
            "attach_files", "assignee_map", "watch_self"]


def _actor(request):
    return request.user.get_username() if request.user and request.user.is_authenticated else ""


def connection_payload(c):
    alive = bool(c.worker_beat and timezone.now() - c.worker_beat < timedelta(seconds=90))
    return {**{f: getattr(c, f) for f in EDITABLE}, "password_set": bool(c.password_enc), "organization": c.organization,
            "me": c.me, "last_sync_at": c.last_sync_at, "last_ok_at": c.last_ok_at, "last_error": c.last_error,
            "sync_requested": c.sync_requested, "worker_alive": alive, "worker_beat": c.worker_beat,
            "ready": not not_ready(c), "not_ready": not_ready(c),
            "named": _named([*(c.task_default_assignees or []), *(c.task_watchers or []),
                             *(c.assignee_map or {}).values()])}


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
                elif f in ("task_default_assignees", "task_watchers"):
                    v = [int(x) for x in (v or []) if str(x).isdigit()][:20]
                elif f in ("enabled", "auto_left", "comment_devices", "close_on_done", "notify_done", "notify_created",
                           "attach_files", "watch_self"):
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
        projects = [{"id": p.get("id"), "name": p.get("name"), "open": p.get("open_count")}
                    for p in client.pages("/task-projects/", max_pages=5)]
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
         "files": int((t.sync or {}).get("files") or 0), "notified": (t.sync or {}).get("notified") or []}
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
    qs = Task.objects.select_related("person", "support_task")
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
def assignable(request):
    """Vazifaga qo'yish mumkin bo'lgan PRBC xodimlari (oxirgi sinxronlashdan)."""
    qs = Person.objects.filter(prbc_user__isnull=False, in_roster=True).exclude(status=Person.LEFT)
    q = (request.query_params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(position__icontains=q))
    return Response([{"id": p.prbc_user, "name": p.full_name, "position": p.position} for p in qs[:50]])

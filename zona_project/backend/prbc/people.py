"""Xodimlarni PRBC'dan aktual saqlash.

Manbalar (har biri ixtiyoriy — qaysi biri ochiq bo'lsa, o'shandan foydalaniladi):
1. "Yangi xodim: …" / "Ishdan bo'shash: …" vazifalari — PRBC Kadrlar moduli ularni 1C'dagi yozuv bo'yicha avtomatik
   yaratadi; tavsifida Xodim, Lavozim, Bo'lim, Korxona, Tabel raqami, Ishga kirish sanasi / Oxirgi ish kuni bor.
   1C'da bekor qilinsa vazifa ham bekor bo'ladi — shunda bo'shash qaytariladi.
2. GET /tasks/assignable-users/ — PRBC'dagi faol xodimlar (user id, ism, lavozim).
3. GET /hr/employees/ — HR moduli ochiq bo'lsa: is_active=false — bo'shagan.

Bo'shash faqat ANIQ belgi bo'yicha qo'yiladi (bo'shash vazifasi yoki HR is_active=false); ro'yxatda ko'rinmay qolish
bo'shash emas (ruxsat olib qo'yilgan bo'lishi mumkin).
"""
import logging
import re
from datetime import date, datetime, timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .client import Client, LoginError, PrbcError, items_of
from .models import Change, Connection, Person, SyncRun, Task

log = logging.getLogger("prbc")

HIRE_PREFIX, LEAVE_PREFIX = "Yangi xodim", "Ishdan bo'shash"
TITLE_RE = re.compile(r"^\s*(Yangi xodim|Ishdan bo['ʻʼ‘’`]shash)\s*:\s*(.+?)\s*(?:[—–-]{1,2}\s*(.+))?\s*$")
FIELD_RE = re.compile(r"^\s*([^:\n]{2,40}?)\s*:\s*(.+?)\s*$", re.M)
DETAILS_PER_RUN = 300

# ----------------------------------------------------------------------------- normallashtirish
APOS = "'ʻʼ‘’`´"
CYR = {"а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
       "й": "y", "к": "k", "қ": "k", "л": "l", "м": "m", "н": "n", "о": "o", "ў": "o", "п": "p", "р": "r", "с": "s",
       "т": "t", "у": "u", "ф": "f", "х": "h", "ҳ": "h", "ц": "s", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ь": "",
       "ы": "i", "э": "e", "ю": "yu", "я": "ya"}
SUFFIX = {"ogli", "ugli", "ogly", "oglu", "qizi", "kizi", "kyzy", "ovich", "ovna", "evich", "evna"}


def phone9(value):
    d = re.sub(r"\D", "", str(value or ""))
    return d[-9:] if len(d) >= 9 else ""


def name_tokens(name):
    """«NE’MATOV JAHONGIR MO‘MINJON O‘G‘LI» va «Жахонгир Неъматов» -> bir xil tokenlar to'plami."""
    s = str(name or "").lower()
    s = "".join(CYR.get(ch, ch) for ch in s)
    for a in APOS:
        s = s.replace(a, "")
    s = s.replace("x", "h").replace("q", "k").replace("w", "v").replace("kh", "h")
    toks = [t for t in re.split(r"[^a-z]+", s) if len(t) > 1]
    return [t for t in toks if t not in SUFFIX]


def name_key(name):
    return " ".join(sorted(name_tokens(name)))[:200]


def same_person(a, b):
    """Familiya + ism ikkalasi ham mos keladi (otasining ismi yozilmagan bo'lsa ham)."""
    ta, tb = name_tokens(a), name_tokens(b)
    if len(ta) < 2 or len(tb) < 2:
        return False
    core = set(ta[:2]) if len(ta) <= len(tb) else set(tb[:2])
    return core <= set(ta) and core <= set(tb)


def parse_date(value):
    value = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_lifecycle(title, description=""):
    """Vazifa sarlavhasi + tavsifidan: {"kind": hire|leave, "name", "position", "fields": {...}, "date"}."""
    m = TITLE_RE.match(title or "")
    if not m:
        return None
    kind = "hire" if m.group(1).lower().startswith("yangi") else "leave"
    fields = {k.strip(): v.strip() for k, v in FIELD_RE.findall(description or "")}
    name = fields.get("Xodim") or m.group(2)
    when = parse_date(fields.get("Ishga kirish sanasi") if kind == "hire" else fields.get("Oxirgi ish kuni"))
    return {"kind": kind, "name": name.strip(), "position": (fields.get("Lavozim") or m.group(3) or "").strip(),
            "department": fields.get("Bo'lim", ""), "company": fields.get("Korxona", "").strip('"'),
            "tab_number": fields.get("Tabel raqami", ""), "date": when, "fields": fields}


# ----------------------------------------------------------------------------- yordamchilar
def _dt(value):
    return parse_datetime(value) if isinstance(value, str) else value


def _log(person, kind, text, actor="prbc", **data):
    Change.objects.create(person=person, kind=kind, text=text[:500], data=data, actor=actor)


def _person_fields(item):
    """Har xil javob shakllaridan: id, ism, lavozim, telefon, email, faolmi."""
    user = item.get("user") if isinstance(item.get("user"), dict) else {}
    pid = item.get("user_id") or user.get("id") or item.get("id")
    name = item.get("full_name") or user.get("full_name") or item.get("name") or ""
    return {"prbc_user": int(pid) if str(pid or "").isdigit() else None, "full_name": str(name).strip(),
            "position": str(item.get("position") or user.get("position") or "").strip(),
            "phone": str(item.get("phone") or user.get("phone") or "").strip(),
            "email": str(item.get("email") or user.get("email") or "").strip(),
            "is_active": item.get("is_active", True) is not False, "agent_code": _code_of(item, user)}


CODE_KEYS = ("agent_code", "agentCode", "sales_agent_code", "sales_code", "territory_code", "territory", "route_code")


def _code_of(*boxes):
    """1C/PRBC javobidagi agent kodi (bor bo'lsa): "SR2 Tashkent", "Toshkent K1"..."""
    for box in boxes:
        for key in CODE_KEYS:
            v = box.get(key) if isinstance(box, dict) else None
            if isinstance(v, dict):
                v = v.get("code") or v.get("name")
            if v and isinstance(v, (str, int)):
                return str(v).strip()[:80]
    return ""


def find_person(name="", phone="", tab="", prbc_user=None):
    if prbc_user:
        p = Person.objects.filter(prbc_user=prbc_user).first()
        if p:
            return p
    if tab:
        p = Person.objects.filter(tab_number=tab).first()
        if p:
            return p
    key = phone9(phone)
    if key:
        hits = [p for p in Person.objects.exclude(phone="") if phone9(p.phone) == key][:2]
        if len(hits) == 1:
            return hits[0]
    if name:
        hits = [p for p in Person.objects.filter(name_key=name_key(name))[:2]]
        if len(hits) == 1:
            return hits[0]
        loose = [p for p in Person.objects.all() if same_person(p.full_name, name)][:2]
        if len(loose) == 1:
            return loose[0]
    return None


def _update(p, values, stats):
    changed = {}
    for k, v in values.items():
        if v not in (None, "") and getattr(p, k) != v:
            changed[k] = [getattr(p, k), v]
            setattr(p, k, v)
    if changed:
        if "full_name" in changed:
            p.name_key = name_key(p.full_name)
        p.save()
        if p.pk and set(changed) - {"last_seen", "in_roster", "sources", "raw"}:
            stats["updated"] += 1
            _log(p, Change.UPDATED, f"{p.full_name}: " + ", ".join(k for k in changed if k not in ("last_seen", "raw")),
                 fields={k: v for k, v in changed.items() if k not in ("raw", "last_seen")})
    return changed


# ----------------------------------------------------------------------------- 1) faol xodimlar ro'yxati
def sync_roster(client, stats):
    """PRBC'da vazifaga qo'yiladigan faol xodimlar. Qaytaradi: ko'rilgan user id'lar (None — manba yopiq)."""
    try:
        data = client.get("/tasks/assignable-users/")
    except PrbcError as e:
        if isinstance(e, LoginError):
            raise  # kirib bo'lmadi (parol yo'q / noto'g'ri) — butun sinxronlash xato
        stats["sources"]["assignable"] = f"yopiq: {e}"[:200]
        return None
    rows = [_person_fields(i) for i in items_of(data) if isinstance(i, dict)]
    rows = [r for r in rows if r["prbc_user"] and r["full_name"]]
    stats["sources"]["assignable"] = len(rows)
    now, seen = timezone.now(), set()
    for r in rows:
        seen.add(r["prbc_user"])
        p = find_person(r["full_name"], r["phone"], prbc_user=r["prbc_user"])
        if p is None:
            p = Person.objects.create(prbc_user=r["prbc_user"], full_name=r["full_name"], name_key=name_key(r["full_name"]),
                                      position=r["position"], phone=r["phone"], email=r["email"], in_roster=True,
                                      agent_code=r["agent_code"], last_seen=now, sources=["prbc"])
            stats["new"] += 1
            _log(p, Change.NEW, f"Yangi: {p.full_name}" + (f" — {p.position}" if p.position else ""))
            continue
        _update(p, {"prbc_user": p.prbc_user or r["prbc_user"], "full_name": r["full_name"], "position": r["position"],
                    "phone": r["phone"], "email": r["email"], "in_roster": True, "last_seen": now,
                    "sources": sorted({*p.sources, "prbc"}),
                    **({} if p.code_manual else {"agent_code": r["agent_code"]})}, stats)
    Person.objects.filter(in_roster=True).exclude(prbc_user__in=seen).update(in_roster=False)
    return seen


def sync_hr(client, stats):
    """HR moduli ochiq bo'lsa: is_active=false bo'lgan xodimlar — bo'shagan."""
    try:
        data = client.get("/hr/employees/")
    except PrbcError as e:
        if isinstance(e, LoginError):
            raise  # kirib bo'lmadi (parol yo'q / noto'g'ri) — butun sinxronlash xato
        stats["sources"]["hr"] = f"yopiq: {e}"[:200]
        return
    rows = [_person_fields(i) for i in items_of(data) if isinstance(i, dict)]
    stats["sources"]["hr"] = len(rows)
    for r in rows:
        if r["is_active"] or not r["full_name"]:
            continue
        p = find_person(r["full_name"], r["phone"])
        if p and p.status != Person.LEFT and not p.leave_task:
            p.status, p.left_reason = Person.LEFT, "PRBC HR: akkaunt faol emas"
            p.left_on = p.left_on or timezone.localdate()
            p.save()
            stats["left"] += 1
            _log(p, Change.LEFT, f"Bo'shagan: {p.full_name} (PRBC HR — faol emas)")


# ----------------------------------------------------------------------------- 2) Kadrlar vazifalari
def detect_lifecycle_project(client, conn):
    if conn.lifecycle_project:
        return conn.lifecycle_project
    for prefix in (LEAVE_PREFIX, HIRE_PREFIX):
        try:
            for it in client.pages("/tasks/", {"search": prefix, "ordering": "-created_at"}, max_pages=1):
                if TITLE_RE.match(it.get("title") or "") and (it.get("project") or {}).get("id"):
                    conn.lifecycle_project = it["project"]["id"]
                    conn.save(update_fields=["lifecycle_project", "updated_at"])
                    return conn.lifecycle_project
        except PrbcError:
            return None
    return None


def _status(it):
    st = it.get("status") or {}
    return (st.get("name") or "")[:60], (st.get("category") or "")[:20]


def sync_lifecycle(client, conn, stats):
    project = detect_lifecycle_project(client, conn)
    since = (conn.lifecycle_cursor - timedelta(days=1)) if conn.lifecycle_cursor else None
    newest, details = conn.lifecycle_cursor, 0
    for prefix in (LEAVE_PREFIX, HIRE_PREFIX):
        params = {"search": prefix, "ordering": "-updated_at", "include_archived": 1}
        if project:
            params["project"] = project
        stop = (lambda it: bool(since) and (_dt(it.get("updated_at")) or timezone.now()) < since)
        try:
            for it in client.pages("/tasks/", params, stop=stop):
                if not TITLE_RE.match(it.get("title") or ""):
                    continue
                upd = _dt(it.get("updated_at"))
                newest = max(filter(None, [newest, upd]), default=None)
                t = Task.objects.filter(prbc_id=it["id"]).first()
                name, cat = _status(it)
                if t and t.prbc_updated_at == upd and t.fields:
                    continue
                if details >= DETAILS_PER_RUN:
                    stats["lifecycle_pending"] = True
                    continue
                try:
                    full = client.get(f"/tasks/{it['id']}/")
                    details += 1
                except PrbcError as e:
                    stats.setdefault("errors", []).append(f"{it.get('code')}: {e}"[:200])
                    continue
                info = parse_lifecycle(full.get("title"), full.get("description"))
                if not info:
                    continue
                t, _ = Task.objects.update_or_create(prbc_id=it["id"], defaults={
                    "code": it.get("code", ""), "title": (it.get("title") or "")[:300],
                    "kind": Task.HIRE if info["kind"] == "hire" else Task.LEAVE, "status_name": name, "status_category": cat,
                    "project_id": (it.get("project") or {}).get("id"), "project_name": ((it.get("project") or {}).get("name") or "")[:200],
                    "assignee": ((it.get("primary_assignee") or {}).get("full_name") or "")[:200], "due_at": _dt(it.get("due_at")),
                    "prbc_created_at": _dt(full.get("created_at")), "prbc_updated_at": upd,
                    "fields": {**info["fields"], "_date": info["date"].isoformat() if info["date"] else ""}})
                apply_lifecycle(t, info, stats)
        except PrbcError as e:
            if isinstance(e, LoginError):
                raise  # kirib bo'lmadi (parol yo'q / noto'g'ri) — butun sinxronlash xato
            stats["sources"]["lifecycle"] = f"yopiq: {e}"[:200]
            return
    stats["sources"]["lifecycle"] = "ok"
    if newest and not stats.get("lifecycle_pending"):
        conn.lifecycle_cursor = newest
        conn.save(update_fields=["lifecycle_cursor", "updated_at"])


def apply_lifecycle(t, info, stats):
    """Kadrlar vazifasi -> xodim holati (yangi / bo'shayapti / bo'shagan / bekor qilingan -> qaytarildi)."""
    p = find_person(info["name"], tab=info["tab_number"])
    cancelled = t.status_category == "cancelled"
    if p is None:
        if cancelled:
            return
        p = Person.objects.create(full_name=info["name"], name_key=name_key(info["name"]), position=info["position"],
                                  department=info["department"][:200], company=info["company"][:200],
                                  tab_number=info["tab_number"], sources=["1c"])
        stats["new"] += 1
        _log(p, Change.NEW, f"Yangi (1C): {p.full_name}" + (f" — {p.position}" if p.position else ""), task=t.code)
    _update(p, {"tab_number": p.tab_number or info["tab_number"], "position": info["position"],
                "department": info["department"][:200], "company": info["company"][:200],
                "sources": sorted({*p.sources, "1c"})}, stats)
    t.person = p
    t.save(update_fields=["person", "updated_at"])
    today = timezone.localdate()
    if info["kind"] == "hire":
        if cancelled:
            return
        newer_leave = p.left_on and info["date"] and p.left_on < info["date"]
        p.hired_on, p.hire_task = info["date"] or p.hired_on, t.code
        if p.status != Person.ACTIVE and (newer_leave or not p.leave_task):  # qayta ishga kirdi
            p.status, p.left_on, p.left_reason, p.leave_task = Person.ACTIVE, None, "", ""
            stats["returned"] += 1
            _log(p, Change.RETURNED, f"Qayta ishga kirdi: {p.full_name}", task=t.code)
        p.save()
        return
    # bo'shash
    if cancelled:
        if p.leave_task == t.code and p.status != Person.ACTIVE:
            p.status, p.left_on, p.left_reason, p.leave_task = Person.ACTIVE, None, "", ""
            p.save()
            stats["returned"] += 1
            _log(p, Change.RETURNED, f"Bo'shash bekor qilindi (1C): {p.full_name}", task=t.code)
        return
    if p.hired_on and info["date"] and p.hired_on > info["date"]:
        return  # eski bo'shash — keyin qayta ishga kirgan
    status = Person.LEFT if (info["date"] is None or info["date"] <= today) else Person.LEAVING
    if p.status == status and p.leave_task == t.code:
        return
    p.status, p.left_on, p.leave_task = status, info["date"] or today, t.code
    p.left_reason = f"1C: ishdan bo'shatildi ({t.code})"
    p.save()
    stats["left" if status == Person.LEFT else "leaving"] += 1
    _log(p, Change.LEFT if status == Person.LEFT else Change.LEAVING,
         f"{'Bo' + chr(39) + 'shagan' if status == Person.LEFT else 'Bo' + chr(39) + 'shayapti'}: {p.full_name}"
         + (f", oxirgi ish kuni {p.left_on:%d.%m.%Y}" if p.left_on else ""), task=t.code)


def promote_leaving(stats):
    """Oxirgi ish kuni kelganlar: leaving -> left."""
    for p in Person.objects.filter(status=Person.LEAVING, left_on__lte=timezone.localdate()):
        p.status = Person.LEFT
        p.save(update_fields=["status", "updated_at"])
        stats["left"] += 1
        _log(p, Change.LEFT, f"Bo'shagan: {p.full_name} (oxirgi ish kuni o'tdi)")


# ----------------------------------------------------------------------------- 3) bizdagi yozuvlar bilan bog'lash
def _unique(candidates):
    return candidates[0] if len(candidates) == 1 else None


def _match(p, objects, name_attr, phone_attr=None):
    key = phone9(p.phone)
    if key and phone_attr:
        hit = _unique([o for o in objects if phone9(getattr(o, phone_attr, "")) == key])
        if hit:
            return hit
    return _unique([o for o in objects if same_person(getattr(o, name_attr, ""), p.full_name)])


def link_people(stats):
    from inventory.models import Employee
    from support.models import TgUser
    from zona.models import Member, StaffPerson

    staff = list(StaffPerson.objects.filter(is_vacancy=False).exclude(name=""))
    members = list(Member.objects.filter(is_team=False))
    employees = list(Employee.objects.all())
    tgs = list(TgUser.objects.exclude(real_name="", phone=""))
    taken = {f: set(Person.objects.exclude(**{f"{f}__isnull": True}).values_list(f"{f}_id", flat=True))
             for f in ("staff_person", "member", "inv_employee", "tg_user")}
    for p in Person.objects.filter(link_manual=False).exclude(status=Person.LEFT, left_applied=True):
        changed = []
        for field, objs, name_attr, phone_attr in (("staff_person", staff, "name", "phone"), ("member", members, "name", "phone"),
                                                   ("inv_employee", employees, "full_name", "phone"),
                                                   ("tg_user", tgs, "real_name", "phone")):
            if getattr(p, f"{field}_id"):
                continue
            hit = _match(p, objs, name_attr, phone_attr)
            if hit and hit.pk not in taken[field]:
                setattr(p, field, hit)
                taken[field].add(hit.pk)
                changed.append(field)
        if changed:
            p.save()
            stats["linked"] += len(changed)
            _log(p, Change.LINKED, f"Bog'landi: {p.full_name} — " + ", ".join(changed))


def sync_codes(stats):
    """Agent kodi: PRBC/1C'da bo'lmasa — bog'langan kontakt o'rnining hudud kodi (StaffPerson.territory)."""
    n = 0
    for p in Person.objects.filter(code_manual=False, agent_code="", staff_person__isnull=False)             .exclude(staff_person__territory="").select_related("staff_person"):
        p.agent_code = p.staff_person.territory[:80]
        p.save(update_fields=["agent_code", "updated_at"])
        n += 1
    stats["codes"] = n


# ----------------------------------------------------------------------------- 4) bo'shashni qo'llash va qaytarish
@transaction.atomic
def apply_left(p, actor="prbc"):
    """Bo'shagan xodim: kontaktdagi o'rni vakansiya bo'ladi (tarixga yoziladi), inventar xodimi nofaol.
    Mas'ul (Member) o'zgartirilmaydi — u ro'yxatda «bo'shagan mas'ul» sifatida ko'rsatiladi."""
    from zona.models import Event
    undo, done = {}, []
    sp = p.staff_person
    if sp and not sp.is_vacancy:
        undo["staff"] = {"id": sp.pk, "name": sp.name, "phone": sp.phone, "email": sp.email, "telegram": sp.telegram,
                         "since": sp.since.isoformat() if sp.since else ""}
        sp.remember_holder(p.left_reason or "Ishdan bo'shadi (PRBC)", p.left_on)
        sp.name = sp.phone = sp.email = sp.telegram = ""
        sp.since, sp.is_vacancy = None, True
        sp.save()
        Event.objects.create(kind=Event.MOVED, actor=actor, subject=f"{sp.project.name}: {sp.territory}"[:200],
                             from_name=undo["staff"]["name"][:80], to_name="Vakansiya",
                             text=f"Ishdan bo'shadi (PRBC{', ' + p.leave_task if p.leave_task else ''})"[:200])
        done.append("kontakt o'rni bo'shatildi")
    emp = p.inv_employee
    if emp and emp.is_active:
        undo["employee"] = {"id": emp.pk}
        emp.is_active = False
        emp.note = (f"{emp.note}\n" if emp.note else "") + f"PRBC: ishdan bo'shagan {p.left_on:%d.%m.%Y}" if p.left_on else emp.note
        emp.save()
        done.append("inventar xodimi nofaol")
    if p.member_id:
        Event.objects.create(kind=Event.EDITED, actor=actor, subject=p.member.name[:200],
                             text="Mas'ul ishdan bo'shagan (PRBC) — vazifalarini boshqa xodimga o'tkazing"[:200])
        done.append("mas'ul belgilandi")
    p.left_applied, p.undo = True, undo
    p.save(update_fields=["left_applied", "undo", "updated_at"])
    _log(p, Change.APPLIED, f"Bo'shash qo'llandi: {p.full_name}" + (" — " + ", ".join(done) if done else ""), actor=actor, undo=undo)
    return done


@transaction.atomic
def revert_left(p, actor):
    """Xato bo'lsa: kontakt o'rni va inventar xodimi avvalgi holiga qaytadi, xodim «ishlayapti» bo'ladi."""
    from inventory.models import Employee
    from zona.models import StaffPerson
    undo = p.undo or {}
    s = undo.get("staff")
    if s:
        sp = StaffPerson.objects.filter(pk=s["id"], is_vacancy=True, name="").first()
        if sp:
            sp.name, sp.phone, sp.email, sp.telegram = s["name"], s["phone"], s["email"], s["telegram"]
            sp.since = date.fromisoformat(s["since"]) if s.get("since") else None
            sp.is_vacancy = False
            if sp.history and sp.history[0].get("name") == s["name"]:
                sp.history = sp.history[1:]
            sp.save()
    e = undo.get("employee")
    if e:
        Employee.objects.filter(pk=e["id"]).update(is_active=True)
    p.status, p.left_applied, p.undo, p.left_reason = Person.ACTIVE, False, {}, ""
    p.left_on, p.leave_task = None, ""
    p.save()
    _log(p, Change.REVERTED, f"Qaytarildi: {p.full_name} (ishlayapti)", actor=actor)


def comment_devices(client, stats):
    """Bo'shash vazifasiga xodimdagi qurilmalar ro'yxati (bir marta) — IT nimani qaytarib olishini biladi."""
    from inventory.models import Item
    for t in Task.objects.filter(kind=Task.LEAVE, devices_commented=False, person__inv_employee__isnull=False) \
            .exclude(status_category__in=["done", "cancelled"]).select_related("person__inv_employee"):
        items = list(Item.objects.filter(employee=t.person.inv_employee, is_deleted=False).select_related("device_type", "branch"))
        if items:
            lines = [f"Inventarizatsiya bo'yicha xodimda {len(items)} ta qurilma bor (qaytarib olish kerak):"]
            for i in items[:40]:
                desc = " ".join(x for x in [i.device_type.name if i.device_type_id else "", i.brand, i.model] if x)
                lines.append(f"• {desc}" + (f", inv. {i.inv_number}" if i.inv_number else "") + (f", S/N {i.serial}" if i.serial else "")
                             + (f" ({i.branch.name})" if i.branch_id else ""))
            try:
                client.comment(t.prbc_id, "\n".join(lines))
            except PrbcError as e:
                stats.setdefault("errors", []).append(f"{t.code} izoh: {e}"[:200])
                continue
            stats["devices_commented"] += 1
            _log(t.person, Change.TASK, f"{t.code}: qurilmalar ro'yxati izoh qilib qo'shildi ({len(items)} ta)")
        t.devices_commented = True
        t.save(update_fields=["devices_commented", "updated_at"])


# ----------------------------------------------------------------------------- umumiy sinxronlash
def run(conn=None, client=None):
    conn = conn or Connection.get()
    client = client or Client(conn)
    run_ = SyncRun.objects.create()
    stats = {"new": 0, "updated": 0, "left": 0, "leaving": 0, "returned": 0, "linked": 0, "applied": 0,
             "devices_commented": 0, "sources": {}}
    try:
        sync_roster(client, stats)
        sync_hr(client, stats)
        sync_lifecycle(client, conn, stats)
        promote_leaving(stats)
        link_people(stats)
        sync_codes(stats)
        if conn.auto_left:
            for p in Person.objects.filter(status=Person.LEFT, left_applied=False):
                apply_left(p)
                stats["applied"] += 1
        if conn.comment_devices:
            comment_devices(client, stats)
        run_.ok = True
        conn.last_ok_at, conn.last_error = timezone.now(), ""
    except PrbcError as e:
        run_.error = str(e)[:2000]
        conn.last_error = str(e)[:2000]
        log.warning("prbc sync failed: %s", e)
    except Exception as e:  # noqa: BLE001 — sinxronlash xatosi workerni to'xtatmasin
        log.exception("prbc sync crashed")
        run_.error = f"{type(e).__name__}: {e}"[:2000]
        conn.last_error = run_.error
    run_.finished_at, run_.stats = timezone.now(), stats
    run_.save()
    conn.last_sync_at, conn.sync_requested = timezone.now(), False
    conn.save(update_fields=["last_sync_at", "last_ok_at", "last_error", "sync_requested", "updated_at"])
    return run_

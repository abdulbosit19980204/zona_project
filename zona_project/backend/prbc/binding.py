"""«Bu raqam boshqa PRBC akkauntiga bog'langan» — bitta odamda ikkita PRBC akkaunti.

Sabab: xodim 1C ga kiritilgach PRBC Kadrlar moduli unga akkaunt (A: login ``hr_…``, 1C, «Kutilmoqda», Telegramsiz,
Kirish telefoni — 1C dagi raqam) ochadi. Xodim keyin PRBC botiga o'zi kiradi — PRBC yangi bo'sh akkaunt (B: login
``tg_<telegram id>``) ochadi; B da «📱 Поделиться номером» bosilganda raqam A da band bo'lgani uchun xato chiqadi.

Bot (support guruhidagi savol bo'yicha) A va B ni topadi, G1–G7 xavfsizlik shartlarini tekshiradi va — panelda
ruxsat berilgan bo'lsa — 1C xodimini A dan uzib B ga bog'laydi, A dagi raqamni bo'shatadi (buzmasdan). Ruxsat o'chiq
bo'lsa yoki biror shart bajarilmasa — PRBC'da hech narsa o'zgarmaydi, javobda nima topilgani va admin qadamlari
yoziladi, savol mutaxassisga o'tadi. Har amal AccessLog'ga (oldin → keyin) yoziladi va panelda ortga qaytariladi.

PRBC endpointlari (prbc.uz frontend va OpenAPI sxemasidan):
  GET  /auth/admin/users/, /auth/admin/users/{id}/          — akkauntlar (phone = Kirish telefoni)
  PATCH /auth/admin/users/{id}/profile/ {phone}             — Kirish telefoni
  POST /auth/admin/users/{id}/active/ {is_active}           — bloklash / qayta yoqish
  GET  /hr/persons/?search=                                 — 1C xodimlari (employee = bog'langan PRBC xodimi)
  POST /hr/persons/{id}/unlink/                             — «Bog'lanishni uzish»
  POST /hr/persons/{id}/link/ {employee}                    — 1C xodimini PRBC xodimiga bog'lash
"""
import logging
import re
from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .access import IT, TEST, Result, _log, _t, connection, fold, make_client
from .actions import allowed
from .client import PrbcError, items_of
from .people import phone9, same_person

log = logging.getLogger(__name__)

CORE = ("bind_unlink_old", "bind_free_phone", "bind_link_new")   # uchalasi bo'lmasa — muammo hal bo'lmaydi
EXTRA = ("bind_set_phone", "bind_archive_old")                   # ixtiyoriy, alohida ruxsat
ORDER = CORE + EXTRA
REVERSIBLE_ACTIONS = ORDER
MAX_ASK = 3            # raqamni tugma orqali so'rash chegarasi
B_MAX_AGE_DAYS = 30    # B akkaunt «yangi» hisoblanadi
B_ROLES = {"employee"}  # B da bundan boshqa rol bo'lsa — u ishlatilgan akkaunt

# ------------------------------------------------------------------ savolni tanish
_RAW = re.compile(
    r"belongs\s+to\s+another\s+(prbc\s+)?account"
    r"|(number|phone)\s+(is\s+)?(already\s+)?(taken|in\s+use|linked\s+to\s+another)"
    r"|this\s+number\s+belongs")
_FOLD = re.compile(
    r"привязан\w*\s+к\s+друг\w*\s+учетн"
    r"|друг\w*\s+учетн\w*\s+запис\w*\s+прбц"
    r"|бошка\s+(\w+\s+){0,2}(аккаунт|акаунт|учетн|хисоб)\w*\s*(га\s+)?(богла|бириктир)"
    r"|(номер|рака\w*|телефон\w*)\s+(уже\s+)?(занят|банд|бошка\s+аккаунт)")
_CTX = re.compile(r"прбц|бот|аккаунт|акаунт|учетн|поделит|хисоб|рег|кир")
_PHONE = re.compile(r"(?:\+?\s*998[\s\-()]*)?\(?\d{2}\)?[\s\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")


def is_binding_question(text, ocr=""):
    """«Этот номер привязан к другой учётной записи PRBC» / «This number belongs to another PRBC account» / «raqam
    boshqa akkauntga bog'langan» — matnda yoki skrinshotda (OCR)."""
    for s in (text or "", ocr or ""):
        raw = s.lower()
        if _RAW.search(raw):
            return True
        f = fold(s)
        m = _FOLD.search(f)
        if m and (m.group(0).startswith(("привязан", "друг", "бошка")) or _CTX.search(f)):
            return True
    return False


def phones_in(*texts):
    """Matn/skrinshotdagi telefon raqamlari (oxirgi 9 raqam) — faqat qidiruv uchun, tasdiqlangan emas."""
    out = []
    for t in texts:
        for m in _PHONE.findall(t or ""):
            p = phone9(m)
            if p and p not in out:
                out.append(p)
    return out


def fmt_phone(p):
    p = phone9(p)
    return f"+998 {p[:2]} {p[2:5]} {p[5:7]} {p[7:]}" if p else ""


def user_link(uid):
    return f"https://prbc.uz/settings?tab=users&user={uid}"


# ------------------------------------------------------------------ PRBC o'qish
def load_users(client):
    return items_of(client.get("/auth/admin/users/"))


def detail(client, uid):
    return client.get(f"/auth/admin/users/{uid}/")


def is_old_kind(u):
    """A turi: 1C dan kelgan (Kadrlar ochgan) akkaunt — login hr_…, Telegram bog'lanmagan."""
    return str(u.get("username") or "").startswith("hr_") or (u.get("source") == "web" and not u.get("telegram_id"))


def person_of(client, employee_id, name):
    """1C xodimi (HR person) — shu PRBC xodimiga bog'langan. Ism bo'yicha qidiriladi, employee id bilan tekshiriladi."""
    if not employee_id:
        return None
    for q in (name, " ".join((name or "").split()[:2])):
        if not q:
            continue
        rows = items_of(client.get("/hr/persons/", {"search": q}))
        p = next((x for x in rows if (x.get("employee") or {}).get("id") == employee_id), None)
        if p:
            return p
    return None


def person_by_id(client, pid, name):
    for q in (name, " ".join((name or "").split()[:2])):
        if not q:
            continue
        p = next((x for x in items_of(client.get("/hr/persons/", {"search": q})) if x.get("id") == pid), None)
        if p:
            return p
    return None


def works(p):
    """1C xodimi ishlaydi: bo'shatilmagan, PRBC rejasi «faol»."""
    if not p:
        return False
    jobs = p.get("employments") or []
    hired = any((j.get("status") == "hired" and not j.get("dismissal_date")) for j in jobs) if jobs else True
    return hired and (p.get("planned_state") or "active") in ("active", "scheduled_start", "not_created")


def _age_days(u):
    dt = parse_datetime(str(u.get("date_joined") or ""))
    return (timezone.now() - dt).days if dt else 9999


# ------------------------------------------------------------------ shartlar
GATES = {
    "G1": ("Raqam xodimning o'zi tasdiqlagan Telegram raqami", "Номер — собственный подтверждённый номер Telegram"),
    "G2": ("Eski akkauntda (A) Telegram bog'lanmagan", "У старого аккаунта (A) нет Telegram"),
    "G3": ("A — 1C dan kelgan va «Kutilmoqda» (hech qachon ishlatilmagan)", "A пришёл из 1С и «Ожидает» (не использовался)"),
    "G4": ("A ga bog'langan 1C xodimi ishlaydi (bo'shatilmagan)", "Сотрудник 1С, связанный с A, работает (не уволен)"),
    "G5": ("Yangi akkaunt (B) bo'sh: 1C ga bog'lanmagan, yangi ochilgan", "Новый аккаунт (B) пустой: без 1С, недавно создан"),
    "G6": ("Raqam bo'yicha faqat bitta akkaunt", "По номеру найден только один аккаунт"),
    "G7": ("A va B dagi ism bir odamniki", "Имя в A и B — одного человека"),
}


@dataclass
class Pair:
    b: dict = None                 # yangi (Telegram'li) akkaunt
    a: dict = None                 # eski (1C) akkaunt
    a_detail: dict = None
    b_detail: dict = None
    person: dict = None            # A ga bog'langan 1C xodimi
    b_person: dict = None          # B ga allaqachon bog'langan 1C xodimi (bo'lsa — B bo'sh emas)
    phone: str = ""                # 9 raqam
    verified: bool = False         # G1: xodim o'z kontaktini bot tugmasi orqali yubordi
    by: str = ""                   # A qanday topildi: phone / name
    many: int = 0                  # raqam bo'yicha nechta akkaunt
    gates: list = field(default_factory=list)   # [(kod, ok, izoh)]

    def failed(self):
        return [g for g in self.gates if not g[1]]


def find_pair(client, users, tg_id=None, b_id=None, phone="", verified=False, name="", strict_name=True):
    """A/B juftligini topadi va G1–G7 ni tekshiradi (faqat o'qish)."""
    pr = Pair(phone=phone9(phone), verified=verified)
    if b_id:
        pr.b = next((u for u in users if u.get("id") == b_id), None)
    elif tg_id:
        pr.b = next((u for u in users if u.get("telegram_id") == tg_id), None)
    if pr.phone:
        hits = [u for u in users if phone9(u.get("phone")) == pr.phone and (not pr.b or u.get("id") != pr.b.get("id"))]
        pr.many = len(hits)
        if len(hits) == 1:
            pr.a, pr.by = hits[0], "phone"
    if pr.a is None and not pr.phone:
        who = (pr.b or {}).get("full_name") or (pr.b or {}).get("telegram_full_name") or name
        hits = [u for u in users if is_old_kind(u) and u.get("status") == "pending" and not u.get("telegram_id")
                and same_person(u.get("full_name") or "", who)]
        pr.many = len(hits)
        if len(hits) == 1:
            pr.a, pr.by = hits[0], "name"
    if pr.a is not None:
        pr.a_detail = detail(client, pr.a["id"])
        pr.person = person_of(client, pr.a.get("employee_id"), pr.a.get("full_name"))
    if pr.b is not None:
        pr.b_detail = detail(client, pr.b["id"])
        pr.b_person = person_of(client, pr.b.get("employee_id"), pr.b.get("full_name") or pr.a and pr.a.get("full_name"))
    check(pr, name, strict_name)
    return pr


def check(pr, name="", strict_name=True):
    a, b, ad, bd = pr.a or {}, pr.b or {}, pr.a_detail or {}, pr.b_detail or {}
    g = []
    g.append(("G1", pr.verified and pr.by == "phone" and phone9(ad.get("phone") or a.get("phone")) == pr.phone,
              "" if pr.verified else "raqam bot tugmasi orqali tasdiqlanmagan"))
    g.append(("G2", bool(a) and not a.get("telegram_id"), "A da boshqa Telegram bor" if a.get("telegram_id") else ""))
    old = bool(a) and is_old_kind(a) and a.get("status") == "pending" and set(a.get("role_codes") or []) <= B_ROLES
    g.append(("G3", old, "" if old else f"A holati: {a.get('status') or '—'}, login {str(a.get('username') or '')[:3]}…"))
    p = pr.person
    g.append(("G4", bool(p) and works(p), "A ga 1C xodimi bog'lanmagan" if not p else
              ("" if works(p) else "1C xodimi bo'shatilgan / bloklangan — raqam boshqa odamga o'tgan bo'lishi mumkin")))
    roles = set(b.get("role_codes") or [])
    fresh = bool(b) and str(b.get("username") or "").startswith("tg_") and not bd.get("hr_managed") \
        and not pr.b_person and not b.get("is_superuser") and roles <= B_ROLES and _age_days(b) <= B_MAX_AGE_DAYS
    why = ("B topilmadi" if not b else "B ga 1C xodimi allaqachon bog'langan" if pr.b_person or bd.get("hr_managed")
           else f"B {_age_days(b)} kun oldin ochilgan" if _age_days(b) > B_MAX_AGE_DAYS
           else "B da qo'shimcha rollar bor" if not roles <= B_ROLES else "")
    g.append(("G5", fresh, why))
    g.append(("G6", bool(a) and pr.many == 1, f"{pr.many} ta akkaunt" if pr.many != 1 else ""))
    nb = b.get("full_name") or b.get("telegram_full_name") or name
    same = bool(a) and (same_person(a.get("full_name") or "", nb) or same_person(a.get("full_name") or "", name))
    g.append(("G7", same or not strict_name, "" if same else "ism mos emas"))
    pr.gates = g
    return g


# ------------------------------------------------------------------ yozish (har biri tekshiriladi)
class StepFailed(PrbcError):
    pass


def _verify(cond, what):
    if not cond:
        raise StepFailed(f"PRBC'dan qayta o'qilganda kutilgan holat chiqmadi: {what}")


def do_unlink(client, pr):
    p = pr.person
    client.post(f"/hr/persons/{p['id']}/unlink/")
    now = person_by_id(client, p["id"], p.get("full_name"))
    _verify(now is not None and (now.get("employee") or {}).get("id") != pr.a.get("employee_id"), "1C xodimi A dan uzilmadi")
    return ({"person": p["id"], "person_name": p.get("full_name"), "employee": pr.a.get("employee_id"), "user": pr.a["id"]},
            {"person": p["id"], "employee": None})


def do_free_phone(client, pr):
    old = (pr.a_detail or {}).get("phone") or pr.a.get("phone") or ""
    client.patch(f"/auth/admin/users/{pr.a['id']}/profile/", {"phone": ""})
    _verify(not phone9(detail(client, pr.a["id"]).get("phone")), "A dagi Kirish telefoni bo'shamadi")
    return {"phone": old, "user": pr.a["id"]}, {"phone": "", "user": pr.a["id"]}


def do_link(client, pr):
    p = pr.person
    client.post(f"/hr/persons/{p['id']}/link/", {"employee": pr.b["employee_id"]})
    now = person_by_id(client, p["id"], p.get("full_name"))
    _verify(now is not None and (now.get("employee") or {}).get("id") == pr.b["employee_id"], "1C xodimi B ga bog'lanmadi")
    return ({"person": p["id"], "person_name": p.get("full_name"), "employee": None},
            {"person": p["id"], "employee": pr.b["employee_id"], "user": pr.b["id"]})


def do_set_phone(client, pr):
    old = (pr.b_detail or {}).get("phone") or ""
    client.patch(f"/auth/admin/users/{pr.b['id']}/profile/", {"phone": "+998" + pr.phone})
    _verify(phone9(detail(client, pr.b["id"]).get("phone")) == pr.phone, "B ga raqam yozilmadi")
    return {"phone": old, "user": pr.b["id"]}, {"phone": "+998" + pr.phone, "user": pr.b["id"]}


def do_archive(client, pr):
    client.post(f"/auth/admin/users/{pr.a['id']}/active/", {"is_active": False})
    _verify(detail(client, pr.a["id"]).get("is_active") is False, "A bloklanmadi")
    return {"is_active": True, "user": pr.a["id"]}, {"is_active": False, "user": pr.a["id"]}


DO = {"bind_unlink_old": do_unlink, "bind_free_phone": do_free_phone, "bind_link_new": do_link,
      "bind_set_phone": do_set_phone, "bind_archive_old": do_archive}


def undo(client, action, before, after):
    """Bitta amalni teskari bajaradi (rollback va panel «Ortga qaytarish»). Qaytaradi: qisqa matn."""
    if action == "bind_unlink_old":
        p = person_by_id(client, before["person"], before.get("person_name"))
        if p and (p.get("employee") or {}).get("id"):
            raise PrbcError("1C xodimi hozir boshqa akkauntga bog'langan — avval «yangi akkauntga bog'lash»ni qaytaring")
        client.post(f"/hr/persons/{before['person']}/link/", {"employee": before["employee"]})
        return "1C xodimi eski akkauntga qayta bog'landi"
    if action == "bind_link_new":
        client.post(f"/hr/persons/{after['person']}/unlink/")
        return "1C xodimi yangi akkauntdan uzildi"
    if action in ("bind_free_phone", "bind_set_phone"):
        client.patch(f"/auth/admin/users/{before['user']}/profile/", {"phone": before.get("phone") or ""})
        return f"Kirish telefoni qaytarildi: {fmt_phone(before.get('phone')) or '—'}"
    if action == "bind_archive_old":
        client.post(f"/auth/admin/users/{before['user']}/active/", {"is_active": True})
        return "Eski akkaunt qayta yoqildi"
    raise PrbcError("noma'lum amal")


def revert(entry, actor="", client=None):
    """Panel: AccessLog yozuvini ortga qaytarish. Qaytaradi: (ok, matn)."""
    if entry.action not in REVERSIBLE_ACTIONS or not entry.ok or not entry.reversible:
        return False, "Bu yozuvni ortga qaytarib bo'lmaydi"
    if entry.reverted_at:
        return False, "Allaqachon qaytarilgan"
    client = client or make_client()
    if client is None:
        return False, "PRBC ulanishi yoqilmagan"
    u = {"id": entry.prbc_user, "full_name": entry.name}
    try:
        text = undo(client, entry.action, entry.before or {}, entry.after or {})
    except PrbcError as e:
        _log("panel", u, "revert", False, f"{entry.action}: {e}", before=entry.after, after=entry.before)
        return False, f"PRBC: {e}"
    entry.reverted_at, entry.reverted_by = timezone.now(), actor[:150]
    entry.save(update_fields=["reverted_at", "reverted_by"])
    _log("panel", u, "revert", True, f"qaytarildi ({actor}): {text}", before=entry.after, after=entry.before,
         question=entry.question)
    return True, text


# ------------------------------------------------------------------ matnlar
DID = {
    "bind_unlink_old": ("1C xodimi eski akkauntdan uzildi", "Сотрудник 1С отвязан от старого аккаунта"),
    "bind_free_phone": ("eski akkauntdagi raqam bo'shatildi", "номер в старом аккаунте освобождён"),
    "bind_link_new": ("1C xodimi Telegram'dagi akkauntingizga bog'landi", "сотрудник 1С привязан к вашему аккаунту в Telegram"),
    "bind_set_phone": ("raqam akkauntingizga yozildi", "номер записан в ваш аккаунт"),
    "bind_archive_old": ("bo'sh qolgan eski akkaunt bloklandi", "пустой старый аккаунт заблокирован"),
}
NEED = {
    "bind_unlink_old": ("/staff → «Bog'lanishni uzish» (eski akkauntdan)", "/staff → «Отвязать» (от старого аккаунта)"),
    "bind_free_phone": ("eski akkauntda Kirish telefonini bo'shatish", "очистить телефон входа в старом аккаунте"),
    "bind_link_new": ("1C xodimini yangi (Telegram'li) akkauntga bog'lash", "привязать сотрудника 1С к новому аккаунту (с Telegram)"),
    "bind_set_phone": ("xodim PRBC botida raqamni qayta yuboradi", "сотрудник заново отправляет номер в боте PRBC"),
    "bind_archive_old": ("bo'sh eski akkauntni bloklash (ixtiyoriy)", "заблокировать пустой старый аккаунт (по желанию)"),
}
HEAD = ("🔎 PRBC: «raqam boshqa akkauntga bog'langan» — tekshirdim.", "🔎 PRBC: «номер привязан к другой учётной записи» — проверил.")
ASK_CONTACT = ("📱 Raqamingizni tasdiqlash kerak. Pastdagi tugmani bosib botga o'ting va «📱 Raqamni yuborish» ni bosing "
               "(raqam Telegram'dan o'zi olinadi).",
               "📱 Нужно подтвердить ваш номер. Нажмите кнопку ниже, перейдите в бот и нажмите «📱 Отправить номер» "
               "(номер возьмётся из Telegram сам).")
DONE = ("✅ Akkauntingiz 1C ma'lumotlaringiz bilan bog'landi. PRBC ilovasini to'liq yopib qayta oching.",
        "✅ Ваш аккаунт связан с данными 1С. Полностью закройте и заново откройте PRBC.")


def _gate_lines(pr, lang):
    out = []
    for code, ok, why in pr.gates:
        label = _t(lang, *GATES[code])
        out.append(f"{'✅' if ok else '❌'} {code}. {label}" + (f" — {why}" if why and not ok else ""))
    return out


def admin_card(pr, tg_id=None):
    """Mutaxassis uchun: kim, raqam, A/B havolalari, bajarilmagan shartlar."""
    a, b = pr.a or {}, pr.b or {}
    rows = [f"Xodim: {a.get('full_name') or b.get('full_name') or b.get('telegram_full_name') or '—'}",
            f"Telegram ID: {tg_id or b.get('telegram_id') or '—'}",
            f"Raqam: {fmt_phone(pr.phone) or '—'}" + (" (tasdiqlangan)" if pr.verified else " (tasdiqlanmagan)")]
    if a:
        rows.append(f"A (1C, eski): {user_link(a['id'])}")
    if b:
        rows.append(f"B (Telegram, yangi): {user_link(b['id'])}")
    bad = [f"{c} — {why or GATES[c][0]}" for c, ok, why in pr.gates if not ok]
    if bad:
        rows.append("Bajarilmagan: " + "; ".join(bad))
    return "\n".join(rows)


# ------------------------------------------------------------------ asosiy oqim
def verified_phone(question):
    """Shu savol bo'yicha xodim bot tugmasi orqali yuborgan (o'z) raqami — AccessLog «bind_contact»."""
    if not question:
        return "", 0
    from .models import AccessLog
    rows = list(AccessLog.objects.filter(question=question, action="bind_contact").order_by("-at")[:10])
    ok = next((r for r in rows if r.ok and (r.after or {}).get("phone")), None)
    return (ok.after["phone"] if ok else ""), sum(1 for r in rows if not r.ok)


def asks_so_far(question):
    if not question:
        return 0
    from .models import AccessLog
    return AccessLog.objects.filter(question=question, action="bind_ask").count()


def record_contact(question, tg_id, contact, name=""):
    """Bot shaxsiy chatida kelgan kontakt: G1 — contact.user_id == tg_id. Qaytaradi: True (qabul qilindi)."""
    own = bool(contact) and contact.get("user_id") == tg_id
    phone = "+998" + phone9(contact.get("phone_number")) if own and phone9((contact or {}).get("phone_number")) else ""
    _log("bot", {"id": None, "full_name": name}, "bind_contact", bool(phone),
         "Raqam tasdiqlandi (o'z kontakti)" if phone else "Boshqa odamning kontakti yoki raqamsiz — qabul qilinmadi",
         after={"phone": phone, "tg_id": tg_id} if phone else {"tg_id": tg_id}, question=question)
    return bool(phone)


def handle(text, ocr="", tg_id=None, username="", name="", lang="uz", question=None, client=None, conn=None,
           dry=False, force=False, b_id=None, phone=""):
    """Savol «raqam boshqa akkauntga bog'langan» bo'lsa — tekshiradi va ruxsat berilgan amallarni bajaradi.

    Qaytaradi: Result (kind: answer / escalate / contact — raqam tugma orqali kerak) yoki None (bu savol emas / o'chiq).
    dry — panel sinovi: PRBC'ga yozilmaydi. phone — sinovda kiritilgan raqam (tasdiqlangan deb olinadi)."""
    conn = conn or connection()
    if conn is None or not getattr(conn, "bind_bot", True):
        return None
    if not force and not is_binding_question(text, ocr):
        return None
    try:
        client = client or make_client(conn)
        users = load_users(client)
    except PrbcError as e:
        log.warning("PRBC bog'lash tekshiruvi: %s", e)
        return None
    acts = {k: allowed(conn, k) for k in ORDER}
    can_fix = all(acts[k] for k in CORE)
    ver, bad_contacts = (phone9(phone), 0) if dry and phone else verified_phone(question)
    ver = phone9(ver)
    strict = getattr(conn, "bind_strict_name", True)
    seen = phones_in(text, ocr)
    if not ver and can_fix and not dry and bad_contacts < MAX_ASK and asks_so_far(question) < MAX_ASK and tg_id:
        _log("bot", {"id": None, "full_name": name}, "bind_ask", True, "Raqam tugma orqali so'raldi", question=question)
        return Result("contact", "\n".join([_t(lang, *HEAD), "", _t(lang, *ASK_CONTACT)]),
                      note="Raqam bog'lash: tasdiqlangan raqam so'raldi")
    try:
        pr = find_pair(client, users, tg_id=tg_id, b_id=b_id, phone=ver or (seen[0] if seen else ""),
                       verified=bool(ver), name=name, strict_name=strict)
    except PrbcError as e:
        log.warning("PRBC bog'lash: %s", e)
        return None
    if not (can_fix or dry):  # faqat aniqlash: raqam so'ralmagan — G1 tekshirilmaydi (o'zgarish yo'q)
        pr.gates = [g for g in pr.gates if g[0] != "G1"]
    lines = [_t(lang, *HEAD)] + _gate_lines(pr, lang)
    card = admin_card(pr, tg_id)
    who = pr.a or pr.b or {"id": None, "full_name": name}
    if pr.failed():
        lines += ["", _t(lang, "PRBC'da hech narsa o'zgartirilmadi. ", "В PRBC ничего не изменено. ") + _t(lang, *IT)]
        if dry:
            lines.append(_t(lang, *TEST))
        else:
            _log("bot", who, "escalate", False, "Raqam bog'lash: shartlar bajarilmadi\n" + card, question=question)
        return Result("escalate", "\n".join(lines), note="Raqam bog'lash — mutaxassis:\n" + card,
                      planned=[{"key": k, "text": NEED[k][0]} for k in CORE])
    planned, done, plan = [], [], [k for k in ORDER if acts[k]] if can_fix else []
    for k in ORDER:
        if k not in plan or dry:
            mark = "🧪" if dry and acts[k] else ("⚠️" if k in EXTRA else "❌")
            planned.append({"key": k, "text": NEED[k][0], "enabled": acts[k]})
            if dry or k in CORE:  # ixtiyoriy amal o'chiq bo'lsa — xodimga yozilmaydi (panel ro'yxatida bor)
                lines.append(f"{mark} " + _t(lang, "kerak: ", "нужно: ") + _t(lang, *NEED[k]))
    if dry or not plan:
        lines += ["", (_t(lang, *TEST) if dry else
                       _t(lang, "Avtomatik o'zgartirish o'chiq — mutaxassis bajaradi. ",
                          "Автоматическое изменение выключено — сделает специалист. ") + _t(lang, *IT))]
        if not dry:
            _log("bot", who, "escalate", True, "Raqam bog'lash: shartlar joyida, amallar o'chiq\n" + card, question=question)
        return Result("escalate" if not dry else "answer", "\n".join(lines), note="Raqam bog'lash:\n" + card,
                      planned=planned)
    try:
        for k in plan:
            before, after = DO[k](client, pr)
            e = _log("bot", who, k, True, _t(lang, *DID[k]), before=before, after=after, question=question,
                     reversible=True)
            done.append((k, before, after, e))
    except PrbcError as err:
        rolled = rollback(client, done, who, question)
        lines += ["", _t(lang, f"⚠️ PRBC xato berdi ({err}) — qilingan o'zgarishlar ortga qaytarildi.",
                       f"⚠️ PRBC вернул ошибку ({err}) — сделанные изменения отменены.")
                  if rolled else _t(lang, f"⚠️ PRBC xato berdi ({err}) — o'zgarishlarni qaytarib bo'lmadi, mutaxassis "
                                         "ko'radi.", f"⚠️ PRBC вернул ошибку ({err}) — изменения не отменились, "
                                                     "посмотрит специалист."), _t(lang, *IT)]
        _log("bot", who, "escalate", False, f"Raqam bog'lash: {err}\n" + card, question=question)
        return Result("escalate", "\n".join(lines), note=f"Raqam bog'lash xatosi: {err}\n" + card)
    lines += [f"🔧 {_t(lang, *DID[k])}" for k, *_ in done]
    if "bind_set_phone" not in plan:
        lines.append(_t(lang, "📱 Endi PRBC botida «📱 Поделиться номером» ni qayta bosing.",
                          "📱 Теперь снова нажмите «📱 Поделиться номером» в боте PRBC."))
    lines += ["", _t(lang, *DONE)]
    return Result("answer", "\n".join(lines), note="Raqam bog'lash bajarildi:\n" + card, fixed=[k for k, *_ in done])


def rollback(client, done, who, question):
    """Yarim holat qolmasin: bajarilganlarini teskari tartibda qaytaradi. Qaytaradi: hammasi qaytdimi."""
    ok = True
    for k, before, after, entry in reversed(done):
        try:
            text = undo(client, k, before, after)
            if entry is not None:
                entry.reverted_at, entry.reverted_by = timezone.now(), "bot (rollback)"
                entry.save(update_fields=["reverted_at", "reverted_by"])
            _log("bot", who, "revert", True, f"rollback: {text}", before=after, after=before, question=question)
        except PrbcError as e:
            ok = False
            _log("bot", who, "revert", False, f"rollback {k}: {e}", before=after, after=before, question=question)
    return ok


# ------------------------------------------------------------------ panel: sinov, bitta odam, nazorat
def simulate(query="", phone="", tg_id=None, lang="uz", client=None, conn=None):
    """Bot nima yozardi va nima qilardi — PRBC'ga tegilmaydi. B: Telegram ID yoki F.I.Sh. (tg_ akkaunt)."""
    client = client or make_client(conn)
    users = load_users(client)
    b_id = None
    if not tg_id and query:
        b = _find(users, query, want_tg=True)
        b_id = b["id"] if b else None
    r = handle("", tg_id=tg_id, name=query, lang=lang, client=client, conn=conn or connection(), dry=True, force=True,
               b_id=b_id, phone=phone)
    if r is None:
        return {"kind": "none", "text": "PRBC javob bermadi yoki bog'lash tekshiruvi o'chiq", "planned": []}
    return {"kind": r.kind, "text": r.text, "planned": r.planned, "note": r.note}


def _find(users, query, want_tg):
    q = (query or "").strip()
    if q.isdigit():
        n = int(q)
        return next((u for u in users if u.get("id") == n or u.get("telegram_id") == n), None)
    hits = [u for u in users if same_person(u.get("full_name") or u.get("telegram_full_name") or "", q)
            and str(u.get("username") or "").startswith("tg_") == want_tg]
    return hits[0] if len(hits) == 1 else None


def check_one(query, client=None, conn=None):
    """Bitta odam: F.I.Sh. yoki telefon → A/B juftligi va G1–G7 (G1 — panelda tekshirilmaydi)."""
    client = client or make_client(conn)
    users = load_users(client)
    q = (query or "").strip()
    p = phone9(q) if sum(ch.isdigit() for ch in q) >= 9 else ""
    if p:
        owner = [u for u in users if phone9(u.get("phone")) == p]
        a = next((u for u in owner if is_old_kind(u)), owner[0] if owner else None)
        b = next((u for u in users if a and u.get("id") != a.get("id") and str(u.get("username") or "").startswith("tg_")
                  and same_person(a.get("full_name") or "", u.get("full_name") or u.get("telegram_full_name") or "")), None)
    else:
        b = _find(users, q, want_tg=True)
        a = None
    pr = find_pair(client, users, b_id=b["id"] if b else None, phone=p or (phone9((a or {}).get("phone")) if a else ""),
                   verified=False, name=q)
    return {"a": _brief(pr.a), "b": _brief(pr.b), "phone": fmt_phone(pr.phone), "by": pr.by, "many": pr.many,
            "gates": [{"code": c, "ok": ok, "label": GATES[c][0], "why": why} for c, ok, why in pr.gates],
            "card": admin_card(pr)}


def _brief(u):
    if not u:
        return None
    return {"id": u["id"], "name": u.get("full_name") or u.get("telegram_full_name") or "", "status": u.get("status"),
            "login": str(u.get("username") or "")[:3], "telegram": bool(u.get("telegram_id")),
            "phone": fmt_phone(u.get("phone")), "joined": u.get("date_joined"), "position": u.get("position") or "",
            "link": user_link(u["id"])}


def scan(conn=None, client=None):
    """Davriy nazorat — faqat hisobot: «1C, Kutilmoqda, Telegramsiz» (A) va «tg_, 1C siz» (B) akkauntlar bir xil
    F.I.Sh. bilan. PRBC o'zgarmaydi."""
    from .models import Connection
    conn = conn or connection()
    client = client or make_client(conn)
    if client is None:
        return None
    users = load_users(client)
    olds = [u for u in users if is_old_kind(u) and u.get("status") == "pending" and not u.get("telegram_id")]
    news = [u for u in users if str(u.get("username") or "").startswith("tg_") and u.get("status") != "disabled"
            and _age_days(u) <= 90]
    rows = []
    for a in olds:
        for b in news:
            if same_person(a.get("full_name") or "", b.get("full_name") or b.get("telegram_full_name") or ""):
                rows.append({"a": _brief(a), "b": _brief(b)})
    rep = {"at": timezone.now().isoformat(), "pairs": len(rows), "rows": rows[:200], "old_pending": len(olds)}
    Connection.objects.filter(pk=1).update(bind_report=rep)
    return rep

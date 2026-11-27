"""«Yangi tochka» (PRBC → Заявки на точки) ruxsatlari: bot tekshiradi, to'g'rilaydi, yetmagan ma'lumotni xodimdan so'raydi.

Belgi: ilovada «Для вашей организации ещё не включено ни одно подключение к 1С» va «+» tugmasi yo'q. PRBC tugmani
bazaning ``can_create_outlet`` belgisidan chizadi: baza yoniq + «Integratsiyalar» moduli ruxsati yaratishga imkon beradi
(Xodim; Ko'ruvchi yarata olmaydi) + xodim shu bazada 1C savdo vakiliga (pozivnoyga) biriktirilgan. Hisob faol, rol va
asosiy bo'lim — kirish va so'rovlar yo'nalishi uchun.

Bot nima qiladi (savolda yoki worker nazoratida):
* faol emas — tegmaydi, IT'ga (HR qarori);
* rol yo'q — Employee (butun tashkilot bo'yicha); «Integratsiyalar» ruxsati yo'q yoki Ko'ruvchi — Xodim;
* asosiy bo'lim yo'q — bitta bo'limi bo'lsa o'sha asosiy, umuman yo'q bo'lsa guruh nomiga teng bo'lim (aniq bitta bo'lsa);
* pozivnoy yo'q — xodimdan so'raydi, 1C ro'yxatidan topadi, baza (food/nonfood) pozivnoy topilgan baza; boshqa xodimga
  biriktirilgan bo'lsa — tegmaydi, IT'ga. ``food_copy`` (test baza) hech qachon ishlatilmaydi.

Xavfsizlik: hech narsa o'chirilmaydi va pasaytirilmaydi (admin/tekshiruvchi darajasiga tegilmaydi). Pozivnoylar API'si
butun ro'yxatni qabul qiladi — har gal to'liq ro'yxat yangidan o'qiladi, bitta qator qo'shiladi va saqlangandan keyin
qolgan qatorlar o'zgarmagani tekshiriladi (o'zgargan bo'lsa — eski ro'yxat qaytariladi). Har bir amal AccessLog'da."""
import logging
import re
from dataclasses import dataclass, field

from django.utils import timezone

from .client import Client, PrbcError, items_of

log = logging.getLogger("prbc")

BASES = ("food", "nonfood")  # ishchi bazalar; food_copy — test nusxa
CREATE_LEVELS = ("employee", "reviewer", "admin")
TIMEOUT = 15
MAX_SCAN_FIXES = 150  # bitta nazoratda ko'pi bilan shuncha o'zgarish (kutilmagan holatda ommaviy yozuv bo'lmasin)
MAX_OPTIONS = 6

# loyiha -> baza (pozivnoy ikkala bazada bir xil nomda bo'lsa tanlash uchun; asosiy qoida — pozivnoy qaysi bazada)
FOOD_HINTS = ("MDLZ", "МДЛЗ", "MONDELEZ", "МОНДЕЛЕЗ", "HEINZ", "ХАЙНЦ", "PRO TARGET")
NONFOOD_HINTS = ("LOREAL", "L'OREAL", "ЛОРЕАЛ", "BIC", "SILVER", "СХЗ", "J&J", "JOHNSON", "JOHSON", "COSMOPROF", "EVELIN",
                 "EVELINE", "VIVIENNE", "VIVINSABO", "SABO")


# ------------------------------------------------------------------ matnni bir xil ko'rinishga keltirish
_LAT2 = [("o'", "у"), ("g'", "г"), ("sh", "ш"), ("ch", "ч"), ("ya", "я"), ("yu", "ю"), ("yo", "ё"), ("ts", "ц"),
         ("zh", "ж")]
_LAT1 = dict(zip("abvgdezijklmnoprstufhxqcwy", "абвгдезижклмнопрстуфхxкквй"))
_LAT1["x"] = "х"
_CYR = str.maketrans({"ё": "е", "ў": "у", "қ": "к", "ғ": "г", "ҳ": "х", "ъ": "", "ь": "", "й": "й"})
_APOS = re.compile(r"[ʻʼ‘’`´]")


def fold(text, spaces=True):
    """Lotin/kirill, o'zbek/rus yozuvini bitta kirill ko'rinishga: «Qarshi K-3» va «Карши К3» -> «карши к 3» / «каршик3»."""
    s = _APOS.sub("'", (text or "").lower())
    for a, b in _LAT2:
        s = s.replace(a, b)
    s = "".join(_LAT1.get(ch, ch) for ch in s).translate(_CYR)
    s = re.sub(r"[^0-9а-я]+", " ", s).strip()
    return s if spaces else s.replace(" ", "")


# ------------------------------------------------------------------ savolni tanish
SCREEN = re.compile(r"ни одно подключени|не включено ни одно|заявок пока нет")
_NEW = re.compile(
    r"(янги|нов\w*|нев|нью)\s+(точк|нукт|клиент|мижоз|дукон|магазин|тт\b|т т\b)"
    r"|(точк|нукт|клиент|мижоз|дукон)\w*\s+(к[уо]ш|добав|созда|очиш|яратиш|киритиш|ачиш)"
    r"|(к[уо]ш|добав|созда|очиш|яратиш|киритиш)\w*\s+(янги\s+)?(точк|нукт|клиент|мижоз)"
    r"|заявк\w*\s+на\s+точк")
_NEG = re.compile(
    r"к[уо]ш\w*\s*(олм|булм|бол?м)|к[уо]шилм|к[уо]шолм|очилм|очолм|булм|чикм|\bйук\b|\bйок\b|ишлам"
    r"|не\s+мог|не\s+получ|\bнет\b|не\s+работ|не\s+активн|не\s+откр|не\s+показ|не\s+выход|не\s+доступ|недоступ"
    r"|не\s+созда|не\s+добавл|функци|кнопк|тугма|рухсат|доступ|ни\s+одно")


def is_access_question(text, ocr=""):
    """Savol «yangi tochka qo'sha olmayapman» turidami: ekran yozuvi yoki matn (yangi tochka/mijoz + qo'sha olmayapman)."""
    if SCREEN.search(fold(ocr)) or SCREEN.search(fold(text)):
        return True
    f = fold(text)
    return bool(_NEW.search(f) and _NEG.search(f))


def screen_shown(text, ocr=""):
    return bool(SCREEN.search(fold(ocr)) or SCREEN.search(fold(text)))


# ------------------------------------------------------------------ PRBC holati
def connection():
    from .models import Connection
    c = Connection.objects.filter(pk=1).first()
    if not c or not c.enabled or not c.phone or not c.password_enc:
        return None
    return c


def make_client(conn=None):
    conn = conn or connection()
    if conn is None:
        return None
    cl = Client(conn)
    cl.timeout = TIMEOUT
    return cl


def active(u):
    return bool(u.get("is_active")) and u.get("employee_active") is not False and (u.get("status") or "active") == "active"


def is_tp(u):
    p = (u.get("position") or "").lower()
    return "торговый представитель" in p or "savdo vakili" in p


def text_base(text):
    """Xodim bazani o'zi yozgan bo'lsa (variantlar so'ralganda): «nonfood» / «food»."""
    t = (text or "").lower()
    if re.search(r"non\s*-?\s*food|нон\s*-?\s*фу+д", t):
        return "nonfood"
    if re.search(r"(?<![a-zа-я])(food|фу+д)(?![a-zа-я])", t):
        return "food"
    return ""


def _hint(*texts):
    t = " ".join(x or "" for x in texts).upper()
    food, non = any(h in t for h in FOOD_HINTS), any(h in t for h in NONFOOD_HINTS)
    if food and not non:
        return "food"
    if non and not food:
        return "nonfood"
    return ""


@dataclass
class State:
    """PRBC'dan bir marta o'qilgan holat (faqat GET): foydalanuvchilar, ruxsatlar, bazalar, pozivnoylar."""
    client: object
    org: int = 0
    users: list = field(default_factory=list)
    seats: dict = field(default_factory=dict)       # user id -> level
    conns: dict = field(default_factory=dict)       # code -> connection
    maps: dict = field(default_factory=dict)        # code -> {user id: row}
    nodes: list = field(default_factory=list)       # tashkilot bo'limlari (tekis)
    _reps: dict = field(default_factory=dict)       # code -> 1C savdo vakillari (keraklida o'qiladi)

    @classmethod
    def load(cls, client):
        st = cls(client)
        conns = items_of(client.get("/integrations/connections/"))
        st.conns = {x.get("code"): x for x in conns if x.get("code") in BASES and x.get("is_enabled")}
        if not st.conns:
            raise PrbcError("PRBC'da yoqilgan food/nonfood bazasi topilmadi")
        st.org = int(next(iter(st.conns.values())).get("organization") or 0)
        st.users = items_of(client.get("/auth/admin/users/"))
        roster = client.get(f"/admin/organization-modules/{st.org}/integration-access/")
        st.seats = {p["id"]: p.get("level") or "none" for p in roster.get("members") or []}
        for code, x in st.conns.items():
            mp = client.get(f"/integrations/connections/{x['id']}/employee-mappings/")
            st.maps[code] = {r["employee_user_id"]: r for r in mp.get("rows") or []}
            if not st.nodes:
                st.nodes = mp.get("nodes") or []
        return st

    def reps(self, code):
        if code not in self._reps:
            g = self.client.get(f"/integrations/connections/{self.conns[code]['id']}/refs/", {"groups": "employees"})
            items = (((g or {}).get("groups") or {}).get("employees") or {}).get("items") or []
            self._reps[code] = [r for r in items if r.get("guid") and r.get("active", True)]
        return self._reps[code]

    def user(self, uid):
        return next((u for u in self.users if u.get("id") == uid), None)

    def mapping(self, uid):
        for code in BASES:
            r = self.maps.get(code, {}).get(uid)
            if r:
                return code, r
        return None, None

    def holder(self, code, guid):
        return next((r for r in self.maps.get(code, {}).values() if r.get("external_guid") == guid), None)


# ------------------------------------------------------------------ kimni tekshiramiz
_MENTION = re.compile(r"@([A-Za-z0-9_]{4,32})")


def find_target(st, tg_id=None, username="", text=""):
    """Savoldagi @username (boshqa xodim haqida yozilgan bo'lsa) yoki savol beruvchining o'zi (Telegram ID / username)."""
    own = (username or "").lstrip("@").lower()
    for m in _MENTION.findall(text or ""):
        if m.lower() == own:
            continue
        u = next((x for x in st.users if (x.get("telegram_username") or "").lower() == m.lower()), None)
        if u and is_tp(u):  # IT xodimi / mas'ul belgilangan bo'lsa (@StargroupSaid) — u tekshirilmaydi
            return u
    if tg_id:
        u = next((x for x in st.users if x.get("telegram_id") == tg_id and active(x)), None) \
            or next((x for x in st.users if x.get("telegram_id") == tg_id), None)
        if u:
            return u
    if own:
        return next((x for x in st.users if (x.get("telegram_username") or "").lower() == own), None)
    return None


# ------------------------------------------------------------------ pozivnoy (1C savdo vakili) qidirish
def _rep_keys(name):
    full = fold(name, spaces=False)
    bare = fold(re.sub(r"^\s*[\d.,]+\s*", "", name or ""), spaces=False)  # «2.3 Карши К-3» -> «каршик3»
    return full, bare


def find_reps(st, text, hint=""):
    """Matndagi pozivnoy -> [(baza, vakil)]. To'liq nom («2.3 Карши К-3») yoki kodsiz qismi («Qarshi K3») bo'yicha."""
    f = fold(text, spaces=False)
    if not f:
        return []
    words = f" {fold(text)} "
    hits = []
    for code in st.conns:
        try:
            reps = st.reps(code)
        except PrbcError as e:
            log.warning("PRBC 1C vakillari (%s): %s", code, e)
            continue
        for r in reps:
            full, bare = _rep_keys(r.get("name"))
            score = 0
            if len(full) >= 4 and full in f:
                score = 2
            elif 2 <= len(full) < 4 and re.search(r"\d", full) and f" {fold(r.get('name'))} " in words:
                score = 2  # qisqa nom («ТП1») — faqat alohida so'z sifatida
            elif len(bare) >= 4 and re.search(r"\d", bare) and bare in f:
                score = 1
            if score:
                hits.append((score, len(full), code, r))
    if not hits:
        return []
    best = max(h[0] for h in hits)
    hits = [h for h in hits if h[0] == best]
    longest = max(h[1] for h in hits)
    hits = [h for h in hits if h[1] == longest]  # «K-31» yozilsa «K-3» ham mos kelmasin
    if hint and len({h[2] for h in hits}) > 1:
        same = [h for h in hits if h[2] == hint]
        if same:
            hits = same
    out, seen = [], set()
    for _s, _l, code, r in hits:
        if (code, r["guid"]) not in seen:
            seen.add((code, r["guid"]))
            out.append((code, r))
    return out


# ------------------------------------------------------------------ yozish (har biri tekshiriladi va jurnalga yoziladi)
def _log(source, u, action, ok, text, before=None, after=None, question=None):
    from .models import AccessLog
    try:
        AccessLog.objects.create(source=source, prbc_user=u.get("id") if u else None,
                                 name=((u or {}).get("full_name") or "")[:200], action=action, ok=ok, text=text[:2000],
                                 before=before or {}, after=after or {}, question=question)
    except Exception:  # noqa: BLE001 — jurnal yozilmasa ham ish to'xtamasin
        log.exception("AccessLog")


def grant_seat(st, uids):
    """«Integratsiyalar» moduli: Xodim darajasi (faqat ruxsati yo'q yoki Ko'ruvchi bo'lganlarga)."""
    uids = [i for i in uids if st.seats.get(i, "none") not in CREATE_LEVELS]
    if not uids:
        return []
    r = st.client.post(f"/admin/organization-modules/{st.org}/integration-access/",
                       {"level": "employee", "user_ids": uids, "include_subtree": False})
    got = {p["id"]: p.get("level") for p in (r or {}).get("members") or []}
    done = [i for i in uids if got.get(i) in CREATE_LEVELS] if got else uids
    for i in done:
        st.seats[i] = got.get(i, "employee")
    return done


def add_role(st, u):
    st.client.post(f"/auth/admin/users/{u['id']}/roles/", {"role_code": "employee", "organization_id": st.org})
    u["role_codes"] = list(u.get("role_codes") or []) + ["employee"]


def fix_node(st, u, group_title=""):
    """Asosiy bo'lim: bitta bo'limi bo'lsa — o'sha; umuman yo'q bo'lsa — guruh nomiga aniq teng bitta bo'lim. Qaytaradi: nom."""
    d = st.client.get(f"/auth/admin/users/{u['id']}/")
    rows = d.get("assignments") or []
    if len(rows) == 1:
        a = rows[0]
        st.client.post(f"/auth/admin/users/{u['id']}/nodes/{a['id']}/primary/")
        return a.get("hierarchy_node_name") or a.get("node_name") or a.get("name") or ""
    if rows or not group_title:
        return ""
    title = fold(group_title, spaces=False)
    same = [n for n in st.nodes if n.get("is_active", True) and fold(n.get("name"), spaces=False) == title]
    if len(same) != 1:
        return ""
    st.client.post(f"/auth/admin/users/{u['id']}/nodes/", {"hierarchy_node_id": same[0]["id"], "is_primary": True})
    return same[0].get("name") or ""


class MappingConflict(PrbcError):
    pass


def add_mapping(st, code, u, rep):
    """Pozivnoy biriktirish: to'liq ro'yxat yangidan o'qiladi, bitta qator qo'shiladi, saqlangach qolganlari tekshiriladi."""
    cid = st.conns[code]["id"]
    path = f"/integrations/connections/{cid}/employee-mappings/"
    rows = st.client.get(path).get("rows") or []
    pairs = [{"user_id": r["employee_user_id"], "external_guid": r["external_guid"]} for r in rows]
    if any(p["user_id"] == u["id"] for p in pairs):
        raise MappingConflict("xodim bu bazada allaqachon biriktirilgan")
    other = next((r for r in rows if r["external_guid"] == rep["guid"]), None)
    if other:
        raise MappingConflict(f"pozivnoy {other.get('employee_name') or other['employee_user_id']} ga biriktirilgan")
    new = {"user_id": u["id"], "external_guid": rep["guid"]}
    res = st.client.request("PUT", path, body={"rows": pairs + [new]})
    after = {(r["employee_user_id"], r["external_guid"]) for r in (res or {}).get("rows") or []}
    expect = {(p["user_id"], p["external_guid"]) for p in pairs + [new]}
    if after != expect:
        try:  # kutilmagan natija — avvalgi ro'yxat qaytariladi
            st.client.request("PUT", path, body={"rows": pairs})
        except PrbcError:
            log.exception("PRBC pozivnoylar ro'yxatini qaytarib bo'lmadi")
        raise PrbcError(f"pozivnoylar ro'yxati kutilganidek saqlanmadi ({len(after)} ≠ {len(expect)})")
    st.maps.setdefault(code, {})[u["id"]] = {"employee_user_id": u["id"], "external_guid": rep["guid"],
                                             "external_name": rep.get("name") or "", "employee_name": u.get("full_name")}
    return len(pairs)


# ------------------------------------------------------------------ tekshirish
def checks(st, u):
    """Shartlar: [(kalit, holat, matn)] — holat: ok / bad. Bo'lim tugmaga ta'sir qilmaydi (faqat ogohlantirish)."""
    code, row = st.mapping(u["id"])
    seat = st.seats.get(u["id"], "none")
    return [
        ("active", "ok" if active(u) else "bad", u.get("status") or ""),
        ("role", "ok" if u.get("role_codes") else "bad", ", ".join(u.get("role_codes") or [])),
        ("node", "ok" if u.get("primary_node_id") else "bad", u.get("primary_node_name") or ""),
        ("seat", "ok" if seat in CREATE_LEVELS else "bad", seat),
        ("mapping", "ok" if row else "bad", f"{row.get('external_name')} ({code})" if row else ""),
    ]


def issues(st, u):
    return [k for k, s, _v in checks(st, u) if s != "ok"]


# ------------------------------------------------------------------ matnlar
def _t(lang, uz, ru):
    return ru if lang == "ru" else uz


LABEL = {
    "active": ("PRBC hisobi faol", "Аккаунт PRBC активен"),
    "role": ("Rol", "Роль"),
    "node": ("Asosiy bo'lim", "Основной отдел"),
    "seat": ("«Integratsiyalar» ruxsati", "Доступ к модулю «Интеграции»"),
    "mapping": ("1C pozivnoy (savdo vakili)", "Позывной 1С (торговый представитель)"),
}
LEVEL = {"employee": ("Xodim", "Сотрудник"), "viewer": ("Ko'ruvchi", "Наблюдатель"), "admin": ("Administrator", "Администратор"),
         "reviewer": ("Tekshiruvchi", "Проверяющий"), "none": ("yo'q", "нет")}


def _line(lang, key, mark, value=""):
    icon = {"ok": "✅", "fixed": "🔧", "bad": "❌", "warn": "⚠️"}[mark]
    label = _t(lang, *LABEL[key])
    if key == "seat" and value in LEVEL:
        value = _t(lang, *LEVEL[value])
    return f"{icon} {label}" + (f": {value}" if value else "")


def _head(lang, u):
    return _t(lang, f"🔎 PRBC «Yangi tochka» ruxsatlarini tekshirdim — {u.get('full_name')}:",
              f"🔎 Проверил доступ к «Новой точке» в PRBC — {u.get('full_name')}:")


REOPEN = ("👉 PRBC ilovasini yopib qayta oching — «Заявки на точки»da baza tanlovi va «+» tugmasi chiqadi. "
          "Chiqmasa — shu xabarga javob yozing.",
          "👉 Закройте и заново откройте приложение PRBC — в «Заявках на точки» появятся выбор базы и кнопка «+». "
          "Если не появилась — ответьте на это сообщение.")
ASK = ("❓ Pozivnoyingizni yozing — 1C dagi savdo vakili nomi (masalan: 2.3 Карши К-3). Bilmasangiz, supervayzeringizdan "
       "so'rang. Shu xabarga javob qilib yozing.",
       "❓ Напишите ваш позывной — название торгового представителя в 1С (например: 2.3 Карши К-3). Если не знаете — "
       "спросите у супервайзера. Ответьте на это сообщение.")
PICK = ("❓ Bir nechta mos pozivnoy topildi — qaysi biri sizniki? To'liq nomini yozing:",
        "❓ Нашлось несколько подходящих позывных — какой ваш? Напишите полное название:")
IT = ("IT mutaxassisi ko'rib chiqadi.", "Посмотрит IT-специалист.")


@dataclass
class Result:
    kind: str            # answer / ask / escalate
    text: str
    note: str = ""
    fixed: list = field(default_factory=list)


# ------------------------------------------------------------------ botdagi savol
def handle(text, ocr="", tg_id=None, username="", group_title="", lang="uz", asked=False, question=None, client=None,
           conn=None):
    """Savol «yangi tochka qo'sha olmayapman» bo'lsa — tekshiradi, kerak bo'lsa to'g'rilaydi yoki pozivnoy so'raydi.

    Qaytaradi: Result yoki None (savol bu turda emas, bot o'chiq, PRBC javob bermadi yoki hammasi joyida va ekran
    yozuvi ko'rsatilmagan — oddiy javob oqimi davom etadi)."""
    from . import outlets
    conn = conn or connection()
    if conn is None or not getattr(conn, "access_bot", True):
        return None
    screen = screen_shown(text, ocr)
    if not screen and not is_access_question(text, ocr):
        return None
    if not screen and outlets.find_ids(text):
        return None  # aniq mijoz (STIR / 1C kodi) haqida — arizaning holati (outlets) javob beradi
    try:
        client = client or make_client(conn)
        st = State.load(client)
    except PrbcError as e:
        log.warning("PRBC ruxsat tekshiruvi: %s", e)
        return None
    u = find_target(st, tg_id, username, text)
    if u is None:
        msg = _t(lang, "🔎 PRBC'da Telegram hisobingizga bog'langan foydalanuvchi topilmadi — ruxsatlarni tekshirib "
                       "bo'lmadi. " + IT[0],
                 "🔎 В PRBC не найден пользователь, привязанный к вашему Telegram — проверить доступ не получилось. " + IT[1])
        _log("bot", None, "escalate", False, f"PRBC foydalanuvchisi topilmadi (tg {tg_id}, @{username})", question=question)
        return Result("escalate", msg, note="PRBC ruxsatlari: foydalanuvchi topilmadi")
    return _run(st, u, text, lang, asked, screen, group_title, question, getattr(conn, "access_autofix", True))


def _run(st, u, text, lang, asked, screen, group_title, question, autofix):  # noqa: C901 — ketma-ket shartlar
    lines, fixed, problems, ask = [], [], [], ""
    if not active(u):
        lines.append(_line(lang, "active", "bad", u.get("status") or ""))
        body = "\n".join([_head(lang, u), *lines, "",
                          _t(lang, "Hisob PRBC'da faol emas — uni HR / IT faollashtiradi. " + IT[0],
                             "Аккаунт в PRBC не активен — его активирует HR / IT. " + IT[1])])
        _log("bot", u, "escalate", False, f"faol emas ({u.get('status')})", question=question)
        return Result("escalate", body, note="PRBC ruxsatlari: hisob faol emas")
    lines.append(_line(lang, "active", "ok"))

    def attempt(key, fn, value_ok):
        """Bitta tuzatish: muvaffaqiyat — 🔧, xato — ❌ va IT'ga."""
        try:
            v = fn()
            if v is False:
                return False
            fixed.append(key)
            lines.append(_line(lang, key, "fixed", v if isinstance(v, str) and v else value_ok))
            _log("bot", u, key, True, f"{key}: {v if isinstance(v, str) else value_ok}", question=question)
            return True
        except PrbcError as e:
            problems.append(f"{key}: {e}")
            lines.append(_line(lang, key, "bad", _t(lang, "berib bo'lmadi", "не удалось выдать")))
            _log("bot", u, key, False, f"{key}: {e}", question=question)
            return False

    # rol
    if u.get("role_codes"):
        lines.append(_line(lang, "role", "ok", ", ".join(u["role_codes"])))
    elif autofix:
        attempt("role", lambda: add_role(st, u) or "Employee", "Employee")
    else:
        problems.append("role")
        lines.append(_line(lang, "role", "bad", _t(lang, "yo'q", "нет")))
    # bo'lim (tugmaga ta'sir qilmaydi — topilmasa ogohlantirish)
    if u.get("primary_node_id"):
        lines.append(_line(lang, "node", "ok", u.get("primary_node_name") or ""))
    else:
        done = False
        if autofix:
            try:
                name = fix_node(st, u, group_title)
                if name:
                    done = True
                    fixed.append("node")
                    lines.append(_line(lang, "node", "fixed", name))
                    _log("bot", u, "node", True, f"asosiy bo'lim: {name}", question=question)
            except PrbcError as e:
                _log("bot", u, "node", False, str(e), question=question)
        if not done:
            lines.append(_line(lang, "node", "warn", _t(lang, "yo'q (tugmaga ta'sir qilmaydi, IT biriktiradi)",
                                                       "нет (на кнопку не влияет, IT назначит)")))
            _log("bot", u, "node", False, "asosiy bo'lim yo'q — avtomatik aniqlab bo'lmadi", question=question)
    # «Integratsiyalar» ruxsati
    seat = st.seats.get(u["id"], "none")
    if seat in CREATE_LEVELS:
        lines.append(_line(lang, "seat", "ok", seat))
    elif autofix:
        attempt("seat", lambda: "employee" if grant_seat(st, [u["id"]]) else False, "employee")
        if "seat" not in fixed and not any(p.startswith("seat") for p in problems):
            problems.append("seat: PRBC darajani o'zgartirmadi")
            lines.append(_line(lang, "seat", "bad", seat))
    else:
        problems.append("seat")
        lines.append(_line(lang, "seat", "bad", seat))
    # pozivnoy
    code, row = st.mapping(u["id"])
    if row:
        lines.append(_line(lang, "mapping", "ok", f"{row.get('external_name')} ({code})"))
    else:
        hint = text_base(text) or _hint(u.get("primary_node_path"), u.get("primary_node_name"), group_title)
        found = find_reps(st, text, hint)
        free = [(c, r) for c, r in found if not st.holder(c, r["guid"])]
        if len(found) == 1 and not free:
            c, r = found[0]
            h = st.holder(c, r["guid"])
            problems.append(f"mapping: «{r.get('name')}» ({c}) {h.get('employee_name')} ga biriktirilgan")
            lines.append(_line(lang, "mapping", "bad", _t(
                lang, f"«{r.get('name')}» ({c}) boshqa xodimga biriktirilgan — {h.get('employee_name')}",
                f"«{r.get('name')}» ({c}) уже закреплён за другим сотрудником — {h.get('employee_name')}")))
        elif len(free) == 1 and autofix:
            c, r = free[0]
            try:
                add_mapping(st, c, u, r)
                fixed.append("mapping")
                lines.append(_line(lang, "mapping", "fixed", f"{r.get('name')} ({c})"))
                _log("bot", u, "mapping", True, f"pozivnoy: {r.get('name')} ({c})",
                     after={"base": c, "guid": r["guid"], "name": r.get("name")}, question=question)
            except PrbcError as e:
                problems.append(f"mapping: {e}")
                lines.append(_line(lang, "mapping", "bad", f"{r.get('name')} ({c}) — {e}"))
                _log("bot", u, "mapping", False, f"{r.get('name')} ({c}): {e}", question=question)
        elif len(free) == 1:
            c, r = free[0]
            problems.append(f"mapping: {r.get('name')} ({c}) — avtomatik tuzatish o'chiq")
            lines.append(_line(lang, "mapping", "bad", _t(lang, f"yo'q (topildi: {r.get('name')}, {c})",
                                                          f"нет (найден: {r.get('name')}, {c})")))
        elif len(free) > 1 and not asked:
            lines.append(_line(lang, "mapping", "bad", _t(lang, "yo'q", "нет")))
            ask = _t(lang, *PICK) + "\n" + "\n".join(f"• {r.get('name')} ({c})" for c, r in free[:MAX_OPTIONS])
        elif not asked:
            lines.append(_line(lang, "mapping", "bad", _t(lang, "yo'q", "нет")))
            ask = _t(lang, *ASK)
        else:
            what = ", ".join(f"{r.get('name')} ({c})" for c, r in free[:MAX_OPTIONS])
            problems.append("mapping: " + (f"bir nechta mos: {what}" if free else "yozilgan pozivnoy 1C ro'yxatida topilmadi"))
            lines.append(_line(lang, "mapping", "bad", _t(
                lang, "yozgan pozivnoyingiz 1C ro'yxatida aniq topilmadi" if not free else f"aniq emas: {what}",
                "указанный позывной не найден в списке 1С" if not free else f"неоднозначно: {what}")))

    head = _head(lang, u)
    if ask and not problems:
        body = "\n".join([head, *lines, "", ask])
        _log("bot", u, "ask", True, "pozivnoy so'raldi" + (f" (variantlar: {len(free)})" if free else ""), question=question)
        return Result("ask", body, note="PRBC ruxsatlari: pozivnoy so'raldi", fixed=fixed)
    if problems or ask:
        body = "\n".join([head, *lines, "", _t(lang, *IT)])
        note = "PRBC ruxsatlari: " + "; ".join(problems or ["pozivnoy kerak"])
        _log("bot", u, "escalate", False, note, question=question)
        return Result("escalate", body, note=note[:300], fixed=fixed)
    if not screen and not any(k in ("seat", "mapping") for k in fixed):
        # tugmaga ta'sir qiladigan narsa yo'q edi (rol/bo'lim tuzatilgan bo'lsa ham) va ekran yozuvi ko'rsatilmagan —
        # savol boshqa narsa haqida bo'lishi mumkin («tochka qo'shdim, ProTarget'da chiqmayapti»): oddiy javob
        _log("bot", u, "check", True, "tugma shartlari joyida" + (f"; to'g'rilandi: {', '.join(fixed)}" if fixed else "")
             + " — oddiy javob", question=question)
        return None
    _log("bot", u, "check", True, "to'g'rilandi: " + ", ".join(fixed) if fixed else "hammasi joyida", question=question)
    return Result("answer", "\n".join([head, *lines, "", _t(lang, *REOPEN)]),
                  note="PRBC ruxsatlari: " + (("to'g'rilandi — " + ", ".join(fixed)) if fixed else "hammasi joyida"),
                  fixed=fixed)


def diagnose_text(query, lang="uz", client=None):
    """Panel: bitta xodimni (ism, @username yoki PRBC id) tekshirish — faqat o'qish, hech narsa o'zgarmaydi."""
    client = client or make_client()
    if client is None:
        return {"error": "PRBC ulanishi yoqilmagan"}
    st = State.load(client)
    q = (query or "").strip().lstrip("@")
    fq = fold(q, spaces=False)
    found = [u for u in st.users if (q.isdigit() and u.get("id") == int(q))
             or (u.get("telegram_username") or "").lower() == q.lower()
             or (fq and len(fq) >= 3 and fq in fold(u.get("full_name"), spaces=False))][:10]
    out = []
    for u in found:
        out.append({"id": u["id"], "name": u.get("full_name"), "position": u.get("position") or "",
                    "telegram": u.get("telegram_username") or "",
                    "checks": [{"key": k, "ok": s == "ok", "value": v} for k, s, v in checks(st, u)]})
    return {"items": out}


# ------------------------------------------------------------------ doimiy nazorat (worker)
def scan(conn=None, client=None, autofix=None):
    """Barcha faol savdo vakillari: 4 shart. Yoqilgan bo'lsa — ruxsat, rol va (bitta bo'limli) asosiy bo'lim beriladi.
    Pozivnoyni bot taxmin qilmaydi — ro'yxatda ko'rinadi, xodim so'raganda bot o'zidan so'raydi."""
    from .models import Connection
    conn = conn or Connection.get()
    client = client or make_client(conn)
    autofix = conn.access_autofix if autofix is None else autofix
    st = State.load(client)
    tps = [u for u in st.users if is_tp(u)]
    act = [u for u in tps if active(u)]
    writes = 0
    fixed = {}
    if autofix:
        need = [u["id"] for u in act if st.seats.get(u["id"], "none") not in CREATE_LEVELS][:MAX_SCAN_FIXES]
        if need:
            before = {i: st.seats.get(i, "none") for i in need}
            try:
                done = grant_seat(st, need)
                writes += len(done)
                for i in done:
                    fixed.setdefault(i, []).append("seat")
                    _log("scan", st.user(i), "seat", True, f"«Integratsiyalar»: {before[i]} → employee",
                         before={"level": before[i]}, after={"level": st.seats.get(i)})
            except PrbcError as e:
                _log("scan", None, "seat", False, f"{len(need)} xodimga ruxsat berib bo'lmadi: {e}")
        for u in act:
            if writes >= MAX_SCAN_FIXES:
                break
            if not u.get("role_codes"):
                try:
                    add_role(st, u)
                    writes += 1
                    fixed.setdefault(u["id"], []).append("role")
                    _log("scan", u, "role", True, "rol: Employee")
                except PrbcError as e:
                    _log("scan", u, "role", False, str(e))
            if not u.get("primary_node_id"):
                try:
                    name = fix_node(st, u)
                    if name:
                        writes += 1
                        u["primary_node_id"], u["primary_node_name"] = -1, name
                        fixed.setdefault(u["id"], []).append("node")
                        _log("scan", u, "node", True, f"asosiy bo'lim: {name}")
                except PrbcError as e:
                    _log("scan", u, "node", False, str(e))
    rows, counts = [], {"tp": len(tps), "active": len(act), "ok": 0, "role": 0, "node": 0, "seat": 0, "mapping": 0,
                        "fixed": sum(len(v) for v in fixed.values())}
    for u in act:
        bad = issues(st, u)
        for k in bad:
            if k in counts:
                counts[k] += 1
        if not bad:
            counts["ok"] += 1
        if bad or u["id"] in fixed:
            rows.append({"id": u["id"], "name": u.get("full_name") or "", "position": u.get("position") or "",
                         "node": u.get("primary_node_name") or "", "telegram": u.get("telegram_username") or "",
                         "issues": bad, "fixed": fixed.get(u["id"], [])})
    rows.sort(key=lambda r: (-len(r["issues"]), r["name"]))
    now = timezone.now()
    report = {"at": now.isoformat(), "autofix": bool(autofix), "counts": counts, "rows": rows[:500]}
    Connection.objects.filter(pk=1).update(access_report=report, access_scan_at=now, access_scan_requested=False)
    return report


def scan_due(conn):
    if conn.access_scan_requested:
        return True
    if not conn.access_scan_minutes:
        return False
    return conn.access_scan_at is None or (timezone.now() - conn.access_scan_at).total_seconds() >= conn.access_scan_minutes * 60

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

from .actions import allowed
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
def _log(source, u, action, ok, text, before=None, after=None, question=None, reversible=False):
    from .models import AccessLog
    try:
        return AccessLog.objects.create(source=source, prbc_user=u.get("id") if u else None,
                                        name=((u or {}).get("full_name") or "")[:200], action=action, ok=ok,
                                        text=text[:2000], before=before or {}, after=after or {}, question=question,
                                        reversible=reversible)
    except Exception:  # noqa: BLE001 — jurnal yozilmasa ham ish to'xtamasin
        log.exception("AccessLog")
        return None


def asks_so_far(question):
    """Shu savolda bot pozivnoyni necha marta so'radi (qayta so'rash chegarasi uchun)."""
    if not question:
        return 0
    from .models import AccessLog
    return AccessLog.objects.filter(question=question, action="ask").count()


# ------------------------------------------------------------------ yozish: har biri {before, after} qaytaradi
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


def do_seat(st, u):
    before = st.seats.get(u["id"], "none")
    if not grant_seat(st, [u["id"]]):
        raise PrbcError("PRBC darajani o'zgartirmadi")
    return {"level": before}, {"level": st.seats.get(u["id"], "employee")}


def detail(st, u):
    if "_detail" not in u:
        u["_detail"] = st.client.get(f"/auth/admin/users/{u['id']}/") or {}
    return u["_detail"]


def do_role(st, u):
    before = list(u.get("role_codes") or [])
    st.client.post(f"/auth/admin/users/{u['id']}/roles/", {"role_code": "employee", "organization_id": st.org})
    u.pop("_detail", None)
    ra = next((r for r in detail(st, u).get("role_assignments") or [] if r.get("role_code") == "employee"), {})
    u["role_codes"] = before + ["employee"]
    return {"roles": before}, {"role": "employee", "assignment_id": ra.get("id")}


def group_node(st, group_title):
    """Telegram guruh nomiga aniq mos (harf/belgi farqisiz) bitta faol PRBC bo'limi yoki None."""
    if not group_title:
        return None
    title = fold(group_title, spaces=False)
    same = [n for n in st.nodes if n.get("is_active", True) and fold(n.get("name"), spaces=False) == title]
    return same[0] if len(same) == 1 else None


def node_plan(st, u, group_title):
    """Bo'lim bo'yicha nima kerak: (amal, bo'lim nomi) — amal: add / primary / ""."""
    rows = detail(st, u).get("assignments") or []
    has_primary = bool(u.get("primary_node_id")) or any(a.get("is_primary") for a in rows)
    node = group_node(st, group_title)
    if node is not None:
        mine = next((a for a in rows if a.get("hierarchy_node_id") == node["id"]), None)
        if mine is None:
            return "add", node, not has_primary
        if not has_primary:
            return "primary", mine, True
        return "", None, False
    if not has_primary and len(rows) == 1:
        return "primary", rows[0], True
    return "", None, False


def do_node(st, u, plan):
    kind, obj, primary = plan
    rows = detail(st, u).get("assignments") or []
    before = {"assignments": [{"id": a.get("id"), "node": a.get("hierarchy_node_name"), "primary": a.get("is_primary")}
                              for a in rows]}
    if kind == "add":
        st.client.post(f"/auth/admin/users/{u['id']}/nodes/", {"hierarchy_node_id": obj["id"], "is_primary": primary})
        u.pop("_detail", None)
        new = next((a for a in detail(st, u).get("assignments") or [] if a.get("hierarchy_node_id") == obj["id"]), {})
        name = obj.get("name") or ""
        after = {"assignment_id": new.get("id"), "node_id": obj["id"], "node": name, "primary": primary}
    else:
        st.client.post(f"/auth/admin/users/{u['id']}/nodes/{obj['id']}/primary/")
        name = obj.get("hierarchy_node_name") or ""
        after = {"primary_of": obj["id"], "node": name}
    if primary:
        u["primary_node_id"], u["primary_node_name"] = obj.get("hierarchy_node_id") or obj.get("id"), name
    return before, after


class MappingConflict(PrbcError):
    pass


def _mapping_path(st, code):
    return f"/integrations/connections/{st.conns[code]['id']}/employee-mappings/"


def _put_checked(st, path, pairs):
    """To'liq ro'yxatni saqlaydi va natijani tekshiradi; farq bo'lsa — avvalgi ro'yxat qaytariladi."""
    res = st.client.request("PUT", path, body={"rows": pairs})
    got = {(r["employee_user_id"], r["external_guid"]) for r in (res or {}).get("rows") or []}
    want = {(p["user_id"], p["external_guid"]) for p in pairs}
    return got == want, got


def add_mapping(st, code, u, rep):
    """Pozivnoy biriktirish: to'liq ro'yxat yangidan o'qiladi, bitta qator qo'shiladi, saqlangach qolganlari tekshiriladi."""
    path = _mapping_path(st, code)
    rows = st.client.get(path).get("rows") or []
    pairs = [{"user_id": r["employee_user_id"], "external_guid": r["external_guid"]} for r in rows]
    if any(p["user_id"] == u["id"] for p in pairs):
        raise MappingConflict("xodim bu bazada allaqachon biriktirilgan")
    other = next((r for r in rows if r["external_guid"] == rep["guid"]), None)
    if other:
        raise MappingConflict(f"pozivnoy {other.get('employee_name') or other['employee_user_id']} ga biriktirilgan")
    new = {"user_id": u["id"], "external_guid": rep["guid"]}
    ok, got = _put_checked(st, path, pairs + [new])
    if not ok:
        try:  # kutilmagan natija — avvalgi ro'yxat qaytariladi
            st.client.request("PUT", path, body={"rows": pairs})
        except PrbcError:
            log.exception("PRBC pozivnoylar ro'yxatini qaytarib bo'lmadi")
        raise PrbcError(f"pozivnoylar ro'yxati kutilganidek saqlanmadi ({len(got)} ≠ {len(pairs) + 1})")
    st.maps.setdefault(code, {})[u["id"]] = {"employee_user_id": u["id"], "external_guid": rep["guid"],
                                             "external_name": rep.get("name") or "", "employee_name": u.get("full_name")}
    return ({"base": code, "mapped": None, "rows": len(pairs)},
            {"base": code, "guid": rep["guid"], "name": rep.get("name") or "", "rows": len(pairs) + 1})


def refresh_refs(st, code):
    """1C ma'lumotnomalarini yangilash (savdo vakillari) — baza uchun soatiga bir marta."""
    from django.core.cache import cache
    key = f"prbc-refresh-refs-{code}"
    if cache.get(key):
        return False
    cache.set(key, 1, 3600)
    st.client.post(f"/integrations/connections/{st.conns[code]['id']}/refresh-refs/?groups=employees")
    st._reps.pop(code, None)
    return True


# ------------------------------------------------------------------ ortga qaytarish (panel)
def revert(entry, actor="", client=None):
    """AccessLog yozuvidagi o'zgarishni qaytaradi; natija ham jurnalga yoziladi. Qaytaradi: (ok, matn)."""
    if entry.action not in REVERSIBLE_ACTIONS or not entry.ok or not entry.reversible:
        return False, "Bu yozuvni ortga qaytarib bo'lmaydi"
    if entry.reverted_at:
        return False, "Allaqachon qaytarilgan"
    client = client or make_client()
    if client is None:
        return False, "PRBC ulanishi yoqilmagan"
    st = State.load(client)
    uid, a, b = entry.prbc_user, entry.after or {}, entry.before or {}
    u = st.user(uid) or {"id": uid, "full_name": entry.name}
    try:
        if entry.action in ("task_seat", "chat_seat"):
            from . import modules
            text = modules.revert(entry, client, st.org)
        elif entry.action == "seat":
            lvl = b.get("level") or "none"
            client.post(f"/admin/organization-modules/{st.org}/integration-access/",
                        {"level": lvl, "user_ids": [uid], "include_subtree": False})
            text = f"«Integratsiyalar»: {a.get('level')} → {lvl}"
        elif entry.action == "role":
            if not a.get("assignment_id"):
                return False, "Rol yozuvi id'si saqlanmagan"
            client.post(f"/auth/admin/users/{uid}/roles/{a['assignment_id']}/remove/")
            text = "Employee roli olib tashlandi"
        elif entry.action == "node":
            if not a.get("assignment_id"):
                return False, "Asosiy bo'lim belgisini avtomatik qaytarib bo'lmaydi — PRBC'da qo'lda tanlang"
            client.post(f"/auth/admin/users/{uid}/nodes/{a['assignment_id']}/remove/", {"confirm": True})
            text = f"Bo'limdan chiqarildi: {a.get('node')}"
        else:  # mapping
            code = a.get("base")
            if code not in st.conns:
                return False, f"{code} bazasi topilmadi"
            path = _mapping_path(st, code)
            rows = client.get(path).get("rows") or []
            pairs = [{"user_id": r["employee_user_id"], "external_guid": r["external_guid"]} for r in rows]
            keep = [p for p in pairs if not (p["user_id"] == uid and p["external_guid"] == a.get("guid"))]
            if len(keep) == len(pairs):
                return False, "Bu pozivnoy allaqachon biriktirilmagan"
            ok, _got = _put_checked(st, path, keep)
            if not ok:
                client.request("PUT", path, body={"rows": pairs})
                return False, "PRBC ro'yxatni kutilganidek saqlamadi — o'zgarish bekor qilindi"
            text = f"Pozivnoy olib tashlandi: {a.get('name')} ({code})"
    except PrbcError as e:
        _log("panel", u, "revert", False, f"{entry.action}: {e}", before=a, after=b)
        return False, f"PRBC: {e}"
    entry.reverted_at, entry.reverted_by = timezone.now(), actor[:150]
    entry.save(update_fields=["reverted_at", "reverted_by"])
    _log("panel", u, "revert", True, f"qaytarildi ({actor}): {text}", before=a, after=b, question=entry.question)
    return True, text


REVERSIBLE_ACTIONS = ("seat", "role", "node", "mapping", "task_seat", "chat_seat")


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


def suggest(st, reply, hint="", limit=8):
    """Noto'liq pozivnoy («sr1») -> o'xshash bo'sh variantlar [(baza, vakil)] (javobdagi raqamli so'z nomning ichida)."""
    toks = [t for t in fold(reply).split() if len(t) >= 2 and (re.search(r"\d", t) or len(t) >= 4)]
    if not toks:
        return []
    out = []
    for code in st.conns:
        if hint and code != hint:
            continue
        try:
            reps = st.reps(code)
        except PrbcError:
            continue
        for r in reps:
            name = fold(r.get("name"), spaces=False)
            if all(t in name for t in toks) and not st.holder(code, r["guid"]):
                out.append((code, r))
    out.sort(key=lambda x: (len(x[1].get("name") or ""), x[1].get("name") or ""))
    return out[: limit + 1]


# ------------------------------------------------------------------ matnlar
def _t(lang, uz, ru):
    return ru if lang == "ru" else uz


LABEL = {
    "active": ("PRBC hisobi faol", "Аккаунт PRBC активен"),
    "role": ("Rol", "Роль"),
    "node": ("Bo'lim", "Отдел"),
    "seat": ("«Integratsiyalar» ruxsati", "Доступ к модулю «Интеграции»"),
    "mapping": ("1C pozivnoy (savdo vakili)", "Позывной 1С (торговый представитель)"),
    "telegram_sync": ("Telegram ma'lumoti PRBC'da", "Данные Telegram в PRBC"),
}
LEVEL = {"employee": ("Xodim", "Сотрудник"), "viewer": ("Ko'ruvchi", "Наблюдатель"), "admin": ("Administrator", "Администратор"),
         "reviewer": ("Tekshiruvchi", "Проверяющий"), "none": ("yo'q", "нет")}


def _lv(lang, v):
    return _t(lang, *LEVEL[v]) if v in LEVEL else v


def _line(lang, key, mark, value=""):
    icon = {"ok": "✅", "fixed": "🔧", "bad": "❌", "warn": "⚠️", "plan": "🧪"}[mark]
    label = _t(lang, *LABEL[key])
    if key == "seat" and value in LEVEL:
        value = _lv(lang, value)
    return f"{icon} {label}" + (f": {value}" if value else "")


def _head(lang, u):
    return _t(lang, f"🔎 PRBC «Yangi tochka» ruxsatlarini tekshirdim — {u.get('full_name')}:",
              f"🔎 Проверил доступ к «Новой точке» в PRBC — {u.get('full_name')}:")


REOPEN = ("👉 PRBC ilovasini yopib qayta oching — «Заявки на точки»da baza tanlovi va «+» tugmasi chiqadi. "
          "Chiqmasa — shu xabarga javob yozing.",
          "👉 Закройте и заново откройте приложение PRBC — в «Заявках на точки» появятся выбор базы и кнопка «+». "
          "Если не появилась — ответьте на это сообщение.")
ASK = ("❓ Pozivnoyingizni to'liq yozing — 1C dagi savdo vakili nomi (masalan: 2.3 Карши К-3). Bilmasangiz, "
       "supervayzeringizdan so'rang. Shu xabarga javob qilib yozing.",
       "❓ Напишите ваш позывной полностью — название торгового представителя в 1С (например: 2.3 Карши К-3). Если не "
       "знаете — спросите у супервайзера. Ответьте на это сообщение.")
PICK = ("❓ Pozivnoy to'liq emas yoki bir nechtasiga mos keldi. Qaysi biri sizniki — to'liq nomini aynan yozing:",
        "❓ Позывной неполный или подходит к нескольким. Какой ваш — напишите полное название точно:")
TOO_MANY = ("❓ «{v}» ga juda ko'p pozivnoy mos keladi. Hudud va kodi bilan to'liq yozing (masalan: 2.3 Карши К-3).",
            "❓ Под «{v}» подходит слишком много позывных. Напишите полностью, с регионом и кодом (например: 2.3 Карши К-3).")
NOT_FOUND = ("❓ «{v}» 1C ro'yxatida topilmadi. Pozivnoyni aynan 1C dagidek to'liq yozing (masalan: 2.3 Карши К-3).",
             "❓ «{v}» не найден в списке 1С. Напишите позывной полностью, точно как в 1С (например: 2.3 Карши К-3).")
IT = ("IT mutaxassisi ko'rib chiqadi.", "Посмотрит IT-специалист.")
OFF = ("avtomatik o'zgartirish o'chiq — mutaxassis bajaradi", "автоматическое изменение выключено — сделает специалист")
TEST = ("🧪 Sinov: PRBC'da hech narsa o'zgarmadi.", "🧪 Тест: в PRBC ничего не изменено.")
MAX_ASK = 3


@dataclass
class Result:
    kind: str            # answer / ask / escalate
    text: str
    note: str = ""
    fixed: list = field(default_factory=list)
    planned: list = field(default_factory=list)  # ruxsat o'chiq yoki sinov: bajarilishi kerak bo'lgan amallar


# ------------------------------------------------------------------ botdagi savol
def handle(text, ocr="", tg_id=None, username="", group_title="", lang="uz", asked=False, question=None, client=None,
           conn=None, dry=False, target=None, force=False):
    """Savol «yangi tochka qo'sha olmayapman» bo'lsa — tekshiradi, ruxsat berilgan amallarni bajaradi, yetmagan
    ma'lumotni (pozivnoy) so'raydi. Ruxsat berilmagan amal — faqat aniqlanadi va javobda yoziladi, savol mutaxassisga.

    dry — panel sinovi: hech narsa yozilmaydi, bot nima qilishi ko'rsatiladi. target — PRBC user (panelda tanlangan).
    Qaytaradi: Result yoki None (savol bu turda emas, bot o'chiq, PRBC javob bermadi yoki tugma shartlari joyida va
    ekran yozuvi ko'rsatilmagan — oddiy javob oqimi davom etadi)."""
    from . import outlets
    conn = conn or connection()
    if conn is None or not getattr(conn, "access_bot", True):
        return None
    screen = screen_shown(text, ocr)
    if not force:
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
    u = st.user(target) if target else find_target(st, tg_id, username, text)
    if u is None:
        msg = _t(lang, "🔎 PRBC'da Telegram hisobingizga bog'langan foydalanuvchi topilmadi — ruxsatlarni tekshirib "
                       "bo'lmadi. " + IT[0],
                 "🔎 В PRBC не найден пользователь, привязанный к вашему Telegram — проверить доступ не получилось. " + IT[1])
        if not dry:
            _log("bot", None, "escalate", False, f"PRBC foydalanuvchisi topilmadi (tg {tg_id}, @{username})", question=question)
        return Result("escalate", msg, note="PRBC ruxsatlari: foydalanuvchi topilmadi")
    run = Run(st, u, conn, text, lang, asked, screen or force, group_title, question, dry)
    run.tg_id, run.username = tg_id, (username or "").lstrip("@")
    return run.go()


class Run:
    """Bitta savol bo'yicha tekshiruv: shartlar ketma-ket, har biri — joyida / bajarildi / kerak (ruxsat o'chiq)."""

    def __init__(self, st, u, conn, text, lang, asked, screen, group_title, question, dry):
        self.st, self.u, self.conn, self.text, self.lang = st, u, conn, text, lang
        self.asked, self.screen, self.group_title, self.question, self.dry = asked, screen, group_title, question, dry
        self.lines, self.fixed, self.planned, self.problems, self.ask = [], [], [], [], ""
        self.tg_id, self.username = None, ""

    def t(self, uz, ru):
        return _t(self.lang, uz, ru)

    def log(self, action, ok, text, **kw):
        if not self.dry:
            _log("bot", self.u, action, ok, text, question=self.question, **kw)

    def can(self, key):
        return not self.dry and allowed(self.conn, key)

    def act(self, key, fn, did_uz, did_ru, need_uz, need_ru, blocking=True):
        """Ruxsat bo'lsa — bajaradi (🔧 + nima qilindi), bo'lmasa — 🧪/❌ «kerak: …» (mutaxassisga)."""
        if self.can(key):
            try:
                before, after = fn()
                self.fixed.append(key)
                self.lines.append(_line(self.lang, key, "fixed", self.t(did_uz, did_ru)))
                self.log(key, True, did_uz, before=before, after=after, reversible=key in REVERSIBLE_ACTIONS)
                return True
            except PrbcError as e:
                self.problems.append(f"{key}: {e}")
                self.lines.append(_line(self.lang, key, "bad", self.t(f"{need_uz} — PRBC xato berdi", f"{need_ru} — ошибка PRBC")))
                self.log(key, False, f"{need_uz}: {e}")
                return False
        mark = "plan" if self.dry and allowed(self.conn, key) else ("bad" if blocking else "warn")
        self.planned.append((key, need_uz))
        tail = "" if mark == "plan" else f" ({self.t(*OFF)})"
        self.lines.append(_line(self.lang, key, mark, self.t(f"kerak: {need_uz}", f"нужно: {need_ru}") + tail))
        return False

    def go(self):  # noqa: C901 — ketma-ket shartlar
        st, u, lang = self.st, self.u, self.lang
        if not active(u):
            self.lines.append(_line(lang, "active", "bad", u.get("status") or ""))
            body = "\n".join([_head(lang, u), *self.lines, "",
                              self.t("Hisob PRBC'da faol emas — uni HR / IT faollashtiradi. " + IT[0],
                                     "Аккаунт в PRBC не активен — его активирует HR / IT. " + IT[1])])
            self.log("escalate", False, f"faol emas ({u.get('status')})")
            return Result("escalate", body, note="PRBC ruxsatlari: hisob faol emas")
        self.lines.append(_line(lang, "active", "ok"))
        # Telegram username o'zgargan (PRBC'dagi nusxa eski) — faqat o'zi yozgan bo'lsa; tugmaga ta'sir qilmaydi
        old = (u.get("telegram_username") or "").lstrip("@")
        if (self.tg_id and u.get("telegram_id") == self.tg_id and self.username
                and old.lower() != self.username.lower()):
            def sync():
                st.client.post(f"/auth/admin/users/{u['id']}/telegram-sync/")
                return {"telegram_username": old}, {"telegram_username": self.username}
            self.act("telegram_sync", sync, f"@{old or '—'} → @{self.username} (yangilandi)",
                     f"@{old or '—'} → @{self.username} (обновлено)", f"@{old or '—'} → @{self.username}",
                     f"@{old or '—'} → @{self.username}", blocking=False)
        # rol
        if u.get("role_codes"):
            self.lines.append(_line(lang, "role", "ok", ", ".join(u["role_codes"])))
        else:
            self.act("role", lambda: do_role(st, u), "Employee berildi", "выдана Employee",
                     "Employee roli", "роль Employee")
        # bo'lim: guruhga mos bo'lim (tugmaga ta'sir qilmaydi — bloklamaydi)
        try:
            plan = node_plan(st, u, self.group_title)
        except PrbcError as e:
            plan = ("", None, False)
            log.warning("PRBC bo'limlar (%s): %s", u.get("id"), e)
        if plan[0]:
            name = plan[1].get("name") or plan[1].get("hierarchy_node_name") or ""
            star = self.t(" (asosiy)", " (основной)") if plan[2] else ""
            if plan[0] == "add":
                did = (f"{name} bo'limiga qo'shildi{star}", f"добавлен в отдел {name}{star}")
                need = (f"{name} bo'limiga qo'shish{star}", f"добавить в отдел {name}{star}")
            else:
                did = (f"{name} asosiy bo'lim qilindi", f"{name} назначен основным отделом")
                need = (f"{name} ni asosiy bo'lim qilish", f"сделать {name} основным отделом")
            self.act("node", lambda: do_node(st, u, plan), *did, *need, blocking=False)
        elif u.get("primary_node_id"):
            self.lines.append(_line(lang, "node", "ok", u.get("primary_node_name") or ""))
        else:
            self.lines.append(_line(lang, "node", "warn", self.t("asosiy bo'lim yo'q (tugmaga ta'sir qilmaydi)",
                                                                 "нет основного отдела (на кнопку не влияет)")))
        # «Integratsiyalar» ruxsati
        seat = st.seats.get(u["id"], "none")
        if seat in CREATE_LEVELS:
            self.lines.append(_line(lang, "seat", "ok", seat))
        else:
            self.act("seat", lambda: do_seat(st, u),
                     f"{_lv('uz', seat)} → Xodim (berildi)", f"{_lv('ru', seat)} → Сотрудник (выдан)",
                     f"{_lv('uz', seat)} → Xodim", f"{_lv('ru', seat)} → Сотрудник")
        # pozivnoy
        self.mapping()
        return self.result()

    def mapping(self):  # noqa: C901
        st, u, lang = self.st, self.u, self.lang
        code, row = st.mapping(u["id"])
        if row:
            self.lines.append(_line(lang, "mapping", "ok", f"{row.get('external_name')} ({code})"))
            return
        hint = text_base(self.text) or _hint(u.get("primary_node_path"), u.get("primary_node_name"), self.group_title)
        found = find_reps(st, self.text, hint)
        reply = (self.text or "").strip().splitlines()[-1] if self.asked else ""
        if not found and self.asked and self.can("refresh_refs"):
            for c in list(st.conns):  # yangi savdo vakili bo'lishi mumkin — ma'lumotnoma bir marta yangilanadi
                try:
                    if refresh_refs(st, c):
                        self.log("refresh_refs", True, f"{c}: 1C ma'lumotnomalari yangilandi")
                except PrbcError as e:
                    self.log("refresh_refs", False, f"{c}: {e}")
            found = find_reps(st, self.text, hint)
        free = [(c, r) for c, r in found if not st.holder(c, r["guid"])]
        n_ask = asks_so_far(self.question)
        if len(found) == 1 and not free:
            c, r = found[0]
            h = st.holder(c, r["guid"])
            self.problems.append(f"mapping: «{r.get('name')}» ({c}) {h.get('employee_name')} ga biriktirilgan")
            self.lines.append(_line(lang, "mapping", "bad", self.t(
                f"«{r.get('name')}» ({c}) boshqa xodimga biriktirilgan — {h.get('employee_name')}",
                f"«{r.get('name')}» ({c}) уже закреплён за другим сотрудником — {h.get('employee_name')}")))
            return
        if len(free) == 1:
            c, r = free[0]
            if not self.act("mapping", lambda: add_mapping(st, c, u, r),
                            f"{r.get('name')} ({c} bazasi) biriktirildi", f"{r.get('name')} (база {c}) закреплён",
                            f"{r.get('name')} ({c} bazasi) biriktirish", f"закрепить {r.get('name')} (база {c})"):
                return
            return
        # aniq topilmadi: variantlar bilan qayta so'rash (MAX_ASK martagacha)
        if len(free) > 1:
            options = free
        elif reply:
            options = suggest(st, reply, hint)
        else:
            options = []
        self.lines.append(_line(lang, "mapping", "bad", self.t("yo'q", "нет")))
        if n_ask < MAX_ASK:
            if options and len(options) <= 8:
                self.ask = self.t(*PICK) + "\n" + "\n".join(f"• {r.get('name')} ({c})" for c, r in options)
            elif options:
                self.ask = self.t(*TOO_MANY).format(v=reply[:40])
            elif reply:
                self.ask = self.t(*NOT_FOUND).format(v=reply[:40])
            else:
                self.ask = self.t(*ASK)
            return
        what = ", ".join(f"{r.get('name')} ({c})" for c, r in options[:MAX_OPTIONS])
        self.problems.append("mapping: " + (f"aniq emas: {what}" if options else "yozilgan pozivnoy 1C ro'yxatida topilmadi")
                             + f" ({MAX_ASK} marta so'raldi)")

    def result(self):
        u, lang, head = self.u, self.lang, _head(self.lang, self.u)
        blocking = [k for k, _n in self.planned if k in ("seat", "mapping", "role")]
        test = ["", self.t(*TEST)] if self.dry else []
        if self.ask and not self.problems:
            body = "\n".join([head, *self.lines, "", self.ask, *test])
            self.log("ask", True, "pozivnoy so'raldi: " + self.ask.splitlines()[0][:150])
            return Result("ask", body, note="PRBC ruxsatlari: pozivnoy so'raldi", fixed=self.fixed, planned=self.planned)
        if self.problems or blocking:
            need = [n for k, n in self.planned if k in ("seat", "mapping", "role")]
            parts = self.problems + ([f"kerak: {', '.join(need)}"] if need else [])
            body = "\n".join([head, *self.lines, "", self.t(*IT), *test])
            note = "PRBC ruxsatlari: " + "; ".join(parts)
            self.log("escalate", False, note)
            return Result("escalate", body, note=note[:300], fixed=self.fixed, planned=self.planned)
        if not self.screen and not any(k in ("seat", "mapping") for k in self.fixed):
            # tugmaga ta'sir qiladigan narsa yo'q edi va ekran yozuvi ko'rsatilmagan — savol boshqa narsa haqida
            # bo'lishi mumkin («tochka qo'shdim, ProTarget'da chiqmayapti»): oddiy javob
            self.log("check", True, "tugma shartlari joyida" + (f"; bajarildi: {', '.join(self.fixed)}" if self.fixed else "")
                     + " — oddiy javob")
            if not self.dry:
                return None
        self.log("check", True, "bajarildi: " + ", ".join(self.fixed) if self.fixed else "hammasi joyida")
        return Result("answer", "\n".join([head, *self.lines, "", self.t(*REOPEN), *test]),
                      note="PRBC ruxsatlari: " + (("bajarildi — " + ", ".join(self.fixed)) if self.fixed else "hammasi joyida"),
                      fixed=self.fixed, planned=self.planned)


def find_people(st, query):
    q = (query or "").strip().lstrip("@")
    fq = fold(q, spaces=False)
    return [u for u in st.users if (q.isdigit() and u.get("id") == int(q))
            or (u.get("telegram_username") or "").lower() == q.lower()
            or (fq and len(fq) >= 3 and fq in fold(u.get("full_name"), spaces=False))][:10]


def diagnose_text(query, lang="uz", client=None):
    """Panel: bitta xodimni (ism, @username yoki PRBC id) tekshirish — faqat o'qish, hech narsa o'zgarmaydi."""
    client = client or make_client()
    if client is None:
        return {"error": "PRBC ulanishi yoqilmagan"}
    st = State.load(client)
    out = []
    for u in find_people(st, query):
        out.append({"id": u["id"], "name": u.get("full_name"), "position": u.get("position") or "",
                    "telegram": u.get("telegram_username") or "",
                    "checks": [{"key": k, "ok": s == "ok", "value": v} for k, s, v in checks(st, u)]})
    return {"items": out}


def simulate(user_id, text="", group_title="", lang="uz", client=None, conn=None, mod="outlet"):
    """Panel sinovi: bot shu xodimga shu savolda nima yozardi va nima qilardi — PRBC'da hech narsa o'zgarmaydi."""
    conn = conn or connection()
    if mod in ("task", "chat"):
        from . import modules
        r = modules.handle(text or "PRBC", "", lang=lang, client=client, conn=conn, dry=True, target=int(user_id), mod=mod)
        if r is None:
            return {"kind": "none", "text": "Ruxsati bor — bot aralashmaydi (odatdagi javob)", "planned": []}
        from .actions import CATALOG
        titles = {a["key"]: a["title"] for a in CATALOG}
        return {"kind": r.kind, "text": r.text, "note": r.note, "planned": [
            {"key": k, "title": titles.get(k, k), "need": n, "enabled": allowed(conn, k)} for k, n in r.planned]}
    r = handle(text or "yangi tochka qo'sha olmayapman", "", group_title=group_title, lang=lang, client=client,
               conn=conn, dry=True, target=int(user_id), force=True, asked=bool(text and "\n" in text))
    if r is None:
        return {"kind": "none", "text": "Bot bu savolga aralashmaydi (odatdagi javob)", "planned": []}
    from .actions import CATALOG
    titles = {a["key"]: a["title"] for a in CATALOG}
    return {"kind": r.kind, "text": r.text, "note": r.note,
            "planned": [{"key": k, "title": titles.get(k, k), "need": n, "enabled": allowed(conn, k)} for k, n in r.planned]}


# ------------------------------------------------------------------ doimiy nazorat (worker) — faqat hisobot
def scan(conn=None, client=None, autofix=None):
    """Barcha faol savdo vakillari: 4 shart — faqat hisobot, PRBC'da hech narsa o'zgarmaydi. O'zgarish faqat xodim
    savol berganda va amal ruxsat etilganda (savoldan kelib chiqib)."""
    from .models import Connection
    conn = conn or Connection.get()
    client = client or make_client(conn)
    st = State.load(client)
    tps = [u for u in st.users if is_tp(u)]
    act = [u for u in tps if active(u)]
    rows, counts = [], {"tp": len(tps), "active": len(act), "ok": 0, "role": 0, "node": 0, "seat": 0, "mapping": 0,
                        "fixed": 0}
    for u in act:
        bad = issues(st, u)
        for k in bad:
            if k in counts:
                counts[k] += 1
        if not bad:
            counts["ok"] += 1
        else:
            rows.append({"id": u["id"], "name": u.get("full_name") or "", "position": u.get("position") or "",
                         "node": u.get("primary_node_name") or "", "telegram": u.get("telegram_username") or "",
                         "issues": bad, "fixed": []})
    rows.sort(key=lambda r: (-len(r["issues"]), r["name"]))
    now = timezone.now()
    report = {"at": now.isoformat(), "autofix": False, "counts": counts, "rows": rows[:500]}
    Connection.objects.filter(pk=1).update(access_report=report, access_scan_at=now, access_scan_requested=False)
    return report


def scan_due(conn):
    if conn.access_scan_requested:
        return True
    if not conn.access_scan_minutes:
        return False
    return conn.access_scan_at is None or (timezone.now() - conn.access_scan_at).total_seconds() >= conn.access_scan_minutes * 60

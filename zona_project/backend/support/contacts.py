"""Kontakt qidiruvi: "L'Oréal ROPi", "Jizzax supervayzeri nomeri", "Jizzax SVR MDLZ", "Saidabror telefoni".

Manba — mas'uliyat platformasidagi Kontaktlar (dala tuzilmasi: brend, yo'nalish, hudud, rol) va Xodimlar.
Ma'lumotlar ruscha kirill, o'zbek lotin/kirill va yangi alifboda bo'lishi mumkin — hammasi bir xil ko'rinishga keltiriladi,
shahar va rollar uchun sinonimlar ishlatiladi. Telefon raqamlari faqat ruxsat etilgan xodimlarga (shaxsiy chatda) beriladi.
"""
import functools
import html
import re
from dataclasses import dataclass, field

from zona.models import Member, StaffPerson
from zona.search.normalize import fold

from .engine import _damerau1

STOP = {"nomer", "nomeri", "nomerini", "raqam", "raqami", "raqamini", "telefon", "telefoni", "telefonini", "tel", "kontakt",
        "kontakti", "kontaktini", "topib", "top", "ber", "bering", "beringchi", "menga", "kerak", "kim", "kimdir", "qaysi",
        "ning", "ini", "ni", "va", "bilan", "uchun", "iltimos", "nomerini", "kontaktlar", "hamma", "barcha", "jami", "list",
        "nomer", "номер", "телефон", "контакт", "дай", "дайте", "найди", "найдите", "скинь", "скиньте", "мне", "нужен",
        "нужна", "кто", "пожалуйста", "у", "по", "и", "the", "phone", "number", "of", "please", "send"}
ROLE = {
    "ROP": {"rop", "rahbar", "rahbari", "rahbarini", "boshliq", "boshlig", "head", "rukovoditel", "руководитель", "роп"},
    "RSM": {"rsm", "рсм"}, "ASM": {"asm", "асм"}, "KAM": {"kam", "кам"},
    "SVR": {"svr", "sv", "supervayzer", "supervayzeri", "supervayzerini", "supervizor", "supervisor", "supervaizer",
            "супервайзер", "супервайзера", "свр", "сврлар", "supervayzerlar"},
    "TP": {"tp", "agent", "agenti", "agentlar", "torgoviy", "torgovy", "тп", "агент", "торговый", "savdo", "vakil", "vakili"},
    "MER": {"mer", "merch", "merchandayzer", "merchendayzer", "мерч", "мерчендайзер", "мрч"},
}
BRAND = {"L'Oréal": {"loreal", "loreall", "лореаль", "лореал", "mny", "maybelline", "garnier"},
         "Heinz": {"heinz", "hayns", "xayns", "хайнц", "heynz"}, "BIC": {"bic", "бик", "bik"},
         "JJ": {"jj", "johnson", "jnj", "джонсон", "жж", "jonson"}}
# shahar/hudud sinonimlari: lotin (eski/yangi), kirill, ruscha -> bitta kalit
PLACE = {
    "toshkent": {"toshkent", "tashkent", "ташкент", "тошкент", "tash", "таш"},
    "fargona": {"fargona", "fergana", "фергана", "фарғона", "fv", "vodiy", "долина", "ферганская"},
    "jizzax": {"jizzax", "jizzakh", "jizzak", "джиззак", "джизак", "жиззах"},
    "samarqand": {"samarqand", "samarkand", "самарканд", "самарқанд"},
    "buxoro": {"buxoro", "bukhara", "buhara", "бухара", "бухоро"},
    "qarshi": {"qarshi", "karshi", "карши", "қарши"},
    "andijon": {"andijon", "andijan", "андижан", "андижон"},
    "namangan": {"namangan", "наманган"}, "navoiy": {"navoiy", "navoi", "навои", "навоий"},
    "nukus": {"nukus", "нукус"}, "xorazm": {"xorazm", "horezm", "khorezm", "хорезм", "хоразм", "urganch"},
    "termiz": {"termiz", "termez", "термез", "термиз"}, "qoqon": {"qoqon", "kokand", "коканд", "қўқон"},
    "janub": {"janub", "yug", "юг", "южный"}, "garb": {"garb", "zapad", "запад", "sw"},
    "janubigarb": {"janubigarb", "yugozapad", "юго-запад", "югозапад"},
}


@functools.lru_cache(maxsize=16384)
def _norm(word):
    w = fold(word).replace("dzh", "j").replace("dj", "j")
    return re.sub(r"[^a-z0-9]", "", w)


_TABLES = {}


def _aliases(name):
    """Sinonimlar bir marta normallashtiriladi (har so'rovda qayta emas)."""
    if name not in _TABLES:
        table = {"ROLE": ROLE, "BRAND": BRAND, "PLACE": PLACE}[name]
        _TABLES[name] = [(_norm(w), key) for key, words in table.items() for w in words]
    return _TABLES[name]


@functools.lru_cache(maxsize=16384)
def _lookup_named(name, token):
    t = _norm(token)
    for n, key in _aliases(name):
        if t == n or (len(t) >= 5 and len(n) >= 5 and _damerau1(t, n)) or (len(t) >= 4 and n.startswith(t) and len(n) - len(t) <= 4):
            return key
    return None


def _lookup(table, token):
    name = "ROLE" if table is ROLE else "BRAND" if table is BRAND else "PLACE"
    return _lookup_named(name, token)


@dataclass
class Query:
    roles: set = field(default_factory=set)
    brands: set = field(default_factory=set)
    places: set = field(default_factory=set)
    names: list = field(default_factory=list)

    @property
    def empty(self):
        return not (self.roles or self.brands or self.places or self.names)


SUFFIXES = ("larining", "larini", "lariga", "lari", "ining", "ning", "ini", "iga", "ni", "ga", "si", "i")


def _variants(tok):
    """So'z va o'zbekcha qo'shimchasiz shakli: ropini -> rop, supervayzerini -> supervayzer."""
    out = [tok]
    for suf in SUFFIXES:
        if tok.endswith(suf) and len(tok) - len(suf) >= 2:
            out.append(tok[: -len(suf)])
    return out


def parse(text):
    q = Query()
    stop = {_norm(x) for x in STOP}
    for raw in re.findall(r"[\w'ʻʼ’\-]+", text or ""):
        tok = raw.strip("-'ʻʼ’").lower()
        if not tok or len(_norm(tok)) < 2 or any(_norm(v) in stop for v in _variants(tok)):
            continue
        for v in _variants(tok):
            role, brand, place = _lookup(ROLE, v), _lookup(BRAND, v), _lookup(PLACE, v)
            if role:
                q.roles.add(role)
                break
            if brand:
                q.brands.add(brand)
                break
            if place:
                q.places.add(place)
                break
        else:
            q.names.append(_norm(tok))
    return q


@functools.lru_cache(maxsize=8192)
def _place_keys(*values):
    keys = set()
    for v in values:
        for tok in re.findall(r"[\w'ʻʼ’\-]+", v or ""):
            k = _lookup(PLACE, tok)
            if k:
                keys.add(k)
    return keys


def _name_ok(names, full_name):
    parts = [_norm(x) for x in re.findall(r"\w+", full_name or "")]
    return all(any(n == p or (len(n) >= 4 and p.startswith(n)) or (len(n) >= 5 and _damerau1(n, p)) for p in parts) for n in names)


def search(text):
    """-> (barcha natijalar, Query)."""
    q = parse(text)
    return search_query(q), q


def search_query(q):
    if q.empty:
        return []
    out = []
    for p in StaffPerson.objects.filter(is_vacancy=False).exclude(name="").select_related("project", "unit", "manager"):
        if q.roles and p.role not in q.roles:
            continue
        if q.brands and p.project.name not in q.brands:
            continue
        if q.places and not q.places <= _place_keys(p.unit.title if p.unit_id else "", p.region, p.city, p.territory):
            continue
        if q.names and not _name_ok(q.names, p.name):
            continue
        out.append({"kind": "staff", "name": p.name, "role": p.get_role_display(), "role_code": p.role, "brand": p.project.name,
                    "unit": p.unit.title if p.unit_id else "", "place": ", ".join(x for x in (p.city, p.territory) if x),
                    "phone": p.phone, "telegram": p.telegram.lstrip("@"), "manager": p.manager.name if p.manager_id else "",
                    "via": ""})
    if q.names and not (q.roles or q.brands or q.places):
        for m in Member.objects.filter(is_team=False):
            if _name_ok(q.names, m.name):
                out.append({"kind": "member", "name": m.name, "role": m.role, "role_code": "", "brand": "StarGroup", "unit": "",
                            "place": m.location, "phone": m.phone, "telegram": m.telegram.lstrip("@"), "manager": "", "via": ""})
    if not out and q.roles & MANAGERS and not q.names:  # tanilmagan so'z (masalan, MDLZ) bo'lsa — taxmin qilmaymiz
        out = _fallback(q)
    order = {"ROP": 0, "RSM": 1, "ASM": 2, "KAM": 3, "SVR": 4, "MER": 5, "TP": 6, "": 7}
    out.sort(key=lambda r: (order.get(r["role_code"], 7), r["brand"], r["name"]))
    return out


MANAGERS = {"ROP", "RSM", "ASM", "KAM", "SVR"}
LEVEL = {"ROP": 0, "RSM": 1, "ASM": 2, "KAM": 3, "SVR": 4}


def _row(p, via=""):
    return {"kind": "staff", "name": p.name, "role": p.get_role_display(), "role_code": p.role, "brand": p.project.name,
            "unit": p.unit.title if p.unit_id else "", "place": ", ".join(x for x in (p.city, p.territory) if x),
            "phone": p.phone, "telegram": p.telegram.lstrip("@"), "manager": p.manager.name if p.manager_id else "", "via": via}


def _fallback(q):
    """To'g'ridan-to'g'ri topilmasa: 1) hududdagi xodimlarning rahbari (Jizzax supervayzeri = Jizzaxdagi agentlarning SVR'i);
    2) brendda so'ralgan lavozim yo'q bo'lsa — o'sha brenddagi eng yuqori rahbarlar (masalan, ROP o'rniga RSM/ASM)."""
    people = list(StaffPerson.objects.filter(is_vacancy=False).exclude(name="").select_related("project", "unit", "manager__manager__manager"))
    found = {}
    if q.places:
        for p in people:
            if q.brands and p.project.name not in q.brands:
                continue
            if not q.places <= _place_keys(p.unit.title if p.unit_id else "", p.region, p.city, p.territory):
                continue
            cur, seen = p.manager, set()
            while cur and cur.pk not in seen:
                if cur.role in q.roles and cur.name:
                    found[cur.pk] = _row(cur, "hudud")
                    break
                seen.add(cur.pk)
                cur = cur.manager
    if not found and q.brands and not q.places:
        brand_people = [p for p in people if p.project.name in q.brands and p.role in MANAGERS]
        if brand_people:
            top = min(LEVEL[p.role] for p in brand_people)
            for p in brand_people:
                if LEVEL[p.role] == top:
                    found[p.pk] = _row(p, "yuqori")
    return list(found.values())


def card_html(r):
    esc = html.escape
    lines = [f"👤 <b>{esc(r['name'])}</b>", f"💼 {esc(r['role'])} · {esc(r['brand'])}"]
    if r["unit"] or r["place"]:
        lines.append("📍 " + esc(" · ".join(x for x in (r["unit"], r["place"]) if x)))
    if r["phone"]:
        lines.append(f"📞 <code>{esc(r['phone'])}</code>")
    if r["telegram"]:
        lines.append(f"✈️ @{esc(r['telegram'])}")
    if r["manager"]:
        lines.append(f"👔 Rahbari: {esc(r['manager'])}")
    if r.get("via") == "hudud":
        lines.append("<i>ℹ️ Shu hududdagi xodimlarning rahbari</i>")
    elif r.get("via") == "yuqori":
        lines.append("<i>ℹ️ So'ralgan lavozim bu brendda yo'q — eng yuqori rahbar</i>")
    return "\n".join(lines)


def vcard(r):
    phone = re.sub(r"[^\d+]", "", r["phone"] or "")
    return ("BEGIN:VCARD\nVERSION:3.0\n"
            f"FN:{r['name']}\nORG:StarGroup;{r['brand']}\nTITLE:{r['role']}\n"
            + (f"TEL;TYPE=CELL:{phone}\n" if phone else "")
            + (f"NOTE:{' · '.join(x for x in (r['unit'], r['place']) if x)}\n" if (r['unit'] or r['place']) else "")
            + "END:VCARD")


def describe(q):
    bits = sorted(q.brands) + sorted(q.roles) + sorted(q.places) + q.names
    return ", ".join(bits)


# ====================================================================== aqlli rejim: turli usullar, ≤ 15 soniya
def _relaxed(q, limit=8):
    """Qat'iy shartlar bilan topilmasa: har bir xodim mos kelgan shartlar bo'yicha baholanadi, eng yaqinlari qaytadi."""
    scored = []
    for p in StaffPerson.objects.filter(is_vacancy=False).exclude(name="").select_related("project", "unit", "manager"):
        score, total = 0, 0
        if q.roles:
            total += 3
            score += 3 if p.role in q.roles else 0
        if q.brands:
            total += 3
            score += 3 if p.project.name in q.brands else 0
        if q.places:
            keys = _place_keys(p.unit.title if p.unit_id else "", p.region, p.city, p.territory)
            total += 2 * len(q.places)
            score += 2 * len(q.places & keys)
        for n in q.names:
            total += 2
            score += 2 if _name_ok([n], p.name) else 0
        if total and score * 2 >= total:  # kamida yarmi mos
            scored.append((score / total, p))
    scored.sort(key=lambda x: (-x[0], LEVEL.get(x[1].role, 9), x[1].name))
    return [_row(p, "yaqin") for _sc, p in scored[:limit]]


AI_SCHEMA = {
    "type": "object",
    "properties": {"brands": {"type": "array", "items": {"type": "string"}}, "roles": {"type": "array", "items": {"type": "string"}},
                   "places": {"type": "array", "items": {"type": "string"}}, "names": {"type": "array", "items": {"type": "string"}}},
    "required": ["brands", "roles", "places", "names"], "additionalProperties": False,
}


def _ai_parse(text, timeout):
    """AI so'rovni tushunib, faqat bizning lug'atdagi qiymatlarni qaytaradi (brend, lavozim kodi, hudud kaliti, ism)."""
    import concurrent.futures

    from zona.ai import service as ai
    from zona.models import AITaskConfig, StaffProject
    brands = list(StaffProject.objects.values_list("name", flat=True))
    system = ("Sen kontakt qidiruv so'rovini tahlil qilasan. Faqat quyidagi qiymatlardan tanla, boshqasini qo'shma:\n"
              f"brands: {brands}\nroles: {sorted(ROLE)} (ROP-bo'lim rahbari, RSM/ASM-hudud menejeri, SVR-supervayzer, "
              f"TP-agent/savdo vakili, MER-merchandayzer, KAM-kalit mijozlar)\nplaces: {sorted(PLACE)}\n"
              "names — so'rovdagi odam ismi/familiyasi (lotin), bo'lmasa bo'sh. So'rov o'zbek (lotin/kirill), rus yoki aralash.")

    def call():
        data, _meta = ai.run(AITaskConfig.SUPPORT, None, f"Kontakt qidiruvi: {text[:80]}", system, text[:300], AI_SCHEMA)
        return data

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        data = ex.submit(call).result(timeout=timeout)
    q = Query()
    q.brands = {b for b in data.get("brands") or [] if b in brands}
    q.roles = {r for r in data.get("roles") or [] if r in ROLE}
    q.places = {x for x in data.get("places") or [] if x in PLACE}
    q.names = [_norm(n) for n in data.get("names") or [] if len(_norm(n)) >= 2][:3]
    return q


def smart_search(text, deadline=15.0):
    """-> (natijalar, Query, usul). Usullar: aniq -> rahbar/hudud bo'yicha (search ichida) -> eng yaqin -> AI tushunishi.
    Umumiy vaqt deadline soniyadan oshmaydi (AI'ga qolgan vaqt beriladi)."""
    import time
    t0 = time.monotonic()
    results, q = search(text)
    if results:
        return results, q, "aniq"
    if not q.empty:
        near = _relaxed(q)
        if near:
            return near, q, "yaqin"
    from .models import Settings
    left = deadline - (time.monotonic() - t0) - 1.0
    if Settings.load().ai_enabled and left > 2:
        try:
            aq = _ai_parse(text, min(left, 10.0))
            if not aq.empty:
                res = search_query(aq) or _relaxed(aq)
                if res:
                    return res, aq, "ai"
                return [], aq, "ai"
        except Exception:  # noqa: BLE001 — AI band/vaqt tugadi: oddiy natija bilan qaytamiz
            pass
    return [], q, "topilmadi"

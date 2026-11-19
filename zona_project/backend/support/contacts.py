"""Kontakt qidiruvi: "L'Oréal ROPi", "Jizzax supervayzeri nomeri", "Jizzax SVR MDLZ", "Saidabror telefoni".

Manba — mas'uliyat platformasidagi Kontaktlar (dala tuzilmasi: brend, yo'nalish, hudud, rol) va Xodimlar.
Ma'lumotlar ruscha kirill, o'zbek lotin/kirill va yangi alifboda bo'lishi mumkin — hammasi bir xil ko'rinishga keltiriladi,
shahar va rollar uchun sinonimlar ishlatiladi. Telefon raqamlari faqat ruxsat etilgan xodimlarga (shaxsiy chatda) beriladi.
"""
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


def _norm(word):
    w = fold(word).replace("dzh", "j").replace("dj", "j")
    return re.sub(r"[^a-z0-9]", "", w)


def _lookup(table, token):
    t = _norm(token)
    for key, words in table.items():
        for w in words:
            n = _norm(w)
            if t == n or (len(t) >= 5 and len(n) >= 5 and _damerau1(t, n)) or (len(t) >= 4 and n.startswith(t) and len(n) - len(t) <= 4):
                return key
    return None


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
    """-> (barcha natijalar, Query). Natija: {"kind", "name", "role", "brand", "unit", "place", "phone", "telegram", "manager"}."""
    q = parse(text)
    if q.empty:
        return [], q
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
                    "phone": p.phone, "telegram": p.telegram.lstrip("@"), "manager": p.manager.name if p.manager_id else ""})
    if q.names and not (q.roles or q.brands or q.places):
        for m in Member.objects.filter(is_team=False):
            if _name_ok(q.names, m.name):
                out.append({"kind": "member", "name": m.name, "role": m.role, "role_code": "", "brand": "StarGroup", "unit": "",
                            "place": m.location, "phone": m.phone, "telegram": m.telegram.lstrip("@"), "manager": ""})
    order = {"ROP": 0, "RSM": 1, "ASM": 2, "KAM": 3, "SVR": 4, "MER": 5, "TP": 6, "": 7}
    out.sort(key=lambda r: (order.get(r["role_code"], 7), r["brand"], r["name"]))
    return out, q


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

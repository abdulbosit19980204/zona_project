"""Sahifadan nusxa olingan matndan (Ctrl+A, Ctrl+C) jamoa tuzilmasini ajratish — AI'siz.

Claude artifact kabi sahifalarni server ocha olmaydi, lekin foydalanuvchi sahifani brauzerda ochib,
matnini nusxalab joylashi mumkin. Matn odatda shunday bloklardan iborat:

    РУКОВОДИТЕЛЬ ОТДЕЛА ПРОДАЖ          <- yuqori rahbar: lavozim sarlavhasi, ism, "joy · telefon"
    Bilalov Zamir Ramilevich
    Heinz · Узбекистан

    Ташкент                             <- yo'nalish sarlavhasi (keyin "14 чел." bo'lishi mumkin)
    14 чел.
    RSM Valiyeva Elvira · Ташкент · +998 ...   <- yo'nalish rahbari bir qatorda (ixtiyoriy)
    Xalikov Valijon Lutfullayevich      <- guruh rahbari: ism, rol, "hudud · shahar · telefon"
    СВР
    SVR Tash 1 · Ташкент · +998 77 729 99 44
    ТП                                  <- xodim: rol, ism, hudud, shahar, telefon
    Muxamadjanova Nilufar Shakirdjanovna
    SR2 Tashkent
    Ташкент
    +998 97 454 80 32

Bog'lanish: xodim -> shu yo'nalishdagi oxirgi guruh rahbari -> yo'nalish rahbari (RSM) -> yuqori rahbar.
"""
import re

PHONE = re.compile(r"\+?\d[\d\s()-]{7,}\d")
NO_PHONE = re.compile(r"^(нет телефона|no phone|telefon yo'q|—|-)$", re.I)
COUNT = re.compile(r"^\d+(\s*(чел\.?|сотр.*|kishi|people|позиц.*|команд.*|ta))?$", re.I)

ROLE_WORDS = {
    "TP": ["тп", "tp", "торговый представитель", "торговые представители", "savdo vakili", "sales rep", "агент"],
    "SVR": ["свр", "svr", "супервайзер", "supervisor", "supervayzer", "sv"],
    "RSM": ["rsm", "рсм", "региональный менеджер"],
    "ASM": ["asm", "асм"],
    "ROP": ["роп", "rop", "руководитель отдела продаж"],
    "MER": ["мерч", "mr", "mer", "мерчендайзер", "merchandiser", "merch"],
    "KAM": ["kam", "кам"],
}
WORD_ROLE = {w: r for r, words in ROLE_WORDS.items() for w in words}
TITLE_ROLE = [  # yuqori rahbar sarlavhalari
    (re.compile(r"отдела продаж|head of sales|savdo bo'limi", re.I), "ROP"),
    (re.compile(r"area sales|асм|\basm\b", re.I), "ASM"),
    (re.compile(r"regional|региональн|\brsm\b", re.I), "RSM"),
    (re.compile(r"national|country|директор|director", re.I), "ROP"),
]
VACANCY = re.compile(r"^(вакансия|vakansiya|vacancy)$", re.I)
ROLE_VACANCY = re.compile(r"^(.+?)\s*[—–-]\s*(вакансия|vakansiya|vacancy)$", re.I)
HEADER = re.compile(r"(?:структура\s+(?:полевой\s+)?команды|команда|team structure|jamoasi)\s*[:—-]?\s*(.+)$", re.I)


def _role_of(line):
    return WORD_ROLE.get(line.strip().lower().rstrip(".:"))


def _is_phone(line):
    return bool(NO_PHONE.match(line.strip())) or bool(PHONE.fullmatch(line.strip()))


def _phone_in(line):
    m = PHONE.search(line)
    return m.group(0).strip() if m else ""


MARKS = re.compile(r"[\s●○•★☆✓✔*·]+$")


def _clean(name):
    return MARKS.sub("", name).strip()


def _is_name(line):
    s = _clean(line)
    if not s or len(s) > 90 or re.search(r"\d|·|@|/", s) or _role_of(s) or VACANCY.match(s):
        return False
    words = [w for w in re.split(r"\s+", s) if w]
    return 2 <= len(words) <= 7 and all(w.lstrip("(")[:1].isupper() for w in words[:2])


def _info(line):
    """'SVR Tash 1 · Ташкент · +998 ...' -> (hudud, shahar, telefon)."""
    parts = [p.strip() for p in line.split("·") if p.strip()]
    phone = ""
    rest = []
    for p in parts:
        if not phone and (PHONE.fullmatch(p) or NO_PHONE.match(p)):
            phone = "" if NO_PHONE.match(p) else p
        else:
            rest.append(p)
    territory = rest[0] if len(rest) >= 2 else ""
    city = rest[1] if len(rest) >= 2 else (rest[0] if rest else "")
    return territory, city, phone


def looks_like(text):
    """Matn shu formatga o'xshaydimi (kamida 3 ta telefonli xodim bloki)."""
    return len(PHONE.findall(text)) >= 3


def from_text(text, name="", source_url=""):
    from .staff_io import StaffImportError, _person, empty, slug

    lines = [re.sub(r"\s+", " ", ln).strip() for ln in str(text).replace("\r", "").split("\n")]
    lines = [ln for ln in lines if ln]
    if not lines:
        raise StaffImportError("Matn bo'sh.")
    title = name
    if not title:
        for ln in lines[:15]:
            m = HEADER.search(ln)
            if m:
                title = m.group(1).strip(" .")
                break
    if not title:
        raise StaffImportError("Jamoa nomini kiriting (matndan aniqlanmadi).")
    doc = empty(title, source_url)
    people = doc["people"]
    seq = [0]

    def add(**kw):
        seq[0] += 1
        p = _person(key=f"t{seq[0]}", **kw)
        people.append(p)
        return p["key"]

    leader = None
    unit = ""
    rsm = None
    head = None
    last_end = 0  # oxirgi tanilgan blokdan keyingi qator

    def open_unit(i):
        """Blokdan oldingi "erkin" qatorlardan yo'nalish nomi (son qatorlari tashlanadi)."""
        nonlocal unit, rsm, head
        free = [ln for ln in lines[last_end:i] if not COUNT.match(ln)]
        if free and leader is not None:
            # bloklar orasida — birinchi qator sarlavha; umumiy ko'rinishdan keyin — oxirgi sarlavhasimon qator
            if len(people) > 1:
                t = free[0]
            else:
                t = next((x for x in reversed(free[-3:]) if "·" not in x), free[-1])
            if len(t) <= 80 and not _is_phone(t):
                key = slug(t, f"u{len(doc['units']) + 1}")
                if all(u["key"] != key for u in doc["units"]):
                    doc["units"].append({"key": key, "title": t})
                if key != unit:
                    unit, rsm, head = key, None, None

    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        nxt = lines[i + 1] if i + 1 < n else ""
        nxt2 = lines[i + 2] if i + 2 < n else ""

        # 1) yuqori rahbar: uzun lavozim sarlavhasi (katta harflar) + ism + "joy · telefon"
        if leader is None and ln.upper() == ln and len(ln) > 6 and _is_name(nxt) and "·" in nxt2:
            role = next((r for rx, r in TITLE_ROLE if rx.search(ln)), "ROP")
            territory, city, phone = _info(nxt2)
            leader = add(name=_clean(nxt), role=role, position=role, city=city, phone=phone)
            i, last_end = i + 3, i + 3
            continue

        # 2) yo'nalish rahbari bir qatorda: "RSM Ism Familiya · Shahar · +998 ..."
        m = re.match(r"^([A-Za-zА-Яа-я]{2,5})\s+(.+?)\s*·\s*(.+)$", ln)
        if m and _role_of(m.group(1)) in ("RSM", "ASM", "SVR") and _is_name(m.group(2)) and _phone_in(m.group(3)):
            open_unit(i)
            territory, city, phone = _info(m.group(3))
            rsm = add(name=_clean(m.group(2)), role=_role_of(m.group(1)), city=city, phone=phone,
                      unit=unit, manager=leader or "")
            head = None
            i, last_end = i + 1, i + 1
            continue

        # 3) guruh rahbari: ism (yoki "Вакансия") + rol + "hudud · shahar · telefon"
        role_line = ROLE_VACANCY.match(ln)
        if "·" in nxt2 and (_role_of(nxt) or (role_line and VACANCY.match(nxt))) and (_is_name(ln) or role_line):
            open_unit(i)
            vacancy = bool(role_line)
            role = _role_of(role_line.group(1)) if role_line else _role_of(nxt)
            territory, city, phone = _info(nxt2)
            head = add(name="" if vacancy else _clean(ln), role=role or "SVR", territory=territory, city=city, phone=phone, vacancy=vacancy, unit=unit,
                       manager=rsm or leader or "")
            i, last_end = i + 3, i + 3
            continue

        # 4) xodim: rol + ism (yoki "Вакансия") + 1-2 qator (hudud, shahar) + telefon
        role = _role_of(ln) or ("TP" if VACANCY.match(ln) else None)
        if role and (_is_name(nxt) or VACANCY.match(nxt)):
            j = next((k for k in (i + 3, i + 4, i + 2) if k < n and _is_phone(lines[k])), None)
            extra = lines[i + 2:j] if j else []
            if j and (extra or j == i + 2):
                if last_end < i:
                    open_unit(i)
                vacancy = bool(VACANCY.match(nxt)) or bool(VACANCY.match(ln))
                territory = extra[0] if extra else ""
                city = extra[1] if len(extra) >= 2 else ""
                phone = "" if NO_PHONE.match(lines[j]) else lines[j]
                add(name="" if vacancy else _clean(nxt), role=role, territory=territory,
                    city=city, phone=phone, vacancy=vacancy, unit=unit, manager=head or rsm or leader or "")
                i, last_end = j + 1, j + 1
                continue
        i += 1

    if len(people) < 2:
        raise StaffImportError(
            "Matndan xodimlar ajratilmadi. Sahifani brauzerda oching, sahifa ichiga bir marta bosing, "
            "Ctrl+A va Ctrl+C bosib, matnni shu yerga to'liq joylang.")
    # ishlatilmagan yo'nalishlarni olib tashlash
    used = {p["unit"] for p in people}
    doc["units"] = [u for u in doc["units"] if u["key"] in used]
    # matnda yo'q maydonlar (region, lavozim, izoh, telegram) bazadagi qiymatni o'chirmaydi
    doc["keep_empty"] = ["region", "position", "note", "telegram"]
    return {title: doc}

"""Savol beruvchi agent (dala xodimi) kartochkasi: agent kodi ("SR2 Tashkent", "Toshkent K1"...), loyiha, yo'nalish,
shahar, supervayzer, telefon, 1C tabel raqami.

IT supportga (vazifa, mas'ulga ko'rsatma, admin kartasi) savol uzatilganda qo'shiladi — ijrochi agentni qayta
so'ramasdan topadi. Faqat lokal bazadan o'qiydi (tarmoq so'rovi yo'q) — botni sekinlashtirmaydi."""
import re

# Telegram ismidagi agent kodi: "Toshkent K1", "SR2 Tashkent", "Х-07", "TP 12", "agent 3"
CODE_RE = re.compile(r"(?<![\w])(?:SR|K|К|X|Х|TP|ТП)\s?-?\s?\d{1,3}(?![\w])|\bagent\s?\d{1,3}\b|агент\s?\d{1,3}", re.I)


def code_from_name(*names):
    """Ismda kod bo'lsa — ismning o'zi (kod odatda shahar bilan birga yoziladi: "Toshkent K1")."""
    for n in names:
        n = " ".join((n or "").split())
        if n and CODE_RE.search(n):
            return n[:60]
    return ""


def _prbc_person(user, sp):
    try:
        from prbc.models import Person
    except ImportError:  # prbc ilovasi o'rnatilmagan
        return None
    qs = Person.objects.exclude(status=Person.LEFT)
    p = qs.filter(tg_user=user).first() if user is not None else None
    if p is None and sp is not None:
        p = qs.filter(staff_person=sp).first()
    return p


def info(user):
    """Agent ma'lumotlari (dict) yoki None — savol beruvchi dala xodimi/PRBC xodimi sifatida tanilmasa."""
    if user is None:
        return None
    sp = user.staff_person if user.staff_person_id else None
    p = _prbc_person(user, sp)
    code = ((p.agent_code if p else "") or (sp.territory if sp else "")
            or code_from_name(getattr(user, "real_name", ""), user.name))
    if sp is None and p is None and not code:
        return None
    d = {
        "name": (sp.name if sp else "") or (p.full_name if p else "") or getattr(user, "real_name", "") or user.name,
        "code": code,
        "role": sp.get_role_display() if sp else "",
        "position": (sp.position if sp else "") or (p.position if p else "") or getattr(user, "position", ""),
        "project": sp.project.name if sp and sp.project_id else "",
        "unit": sp.unit.title if sp and sp.unit_id else "",
        "place": ", ".join(x for x in dict.fromkeys([sp.city, sp.region] if sp else []) if x),
        "supervisor": "",
        "phone": (sp.phone if sp else "") or (p.phone if p else "") or getattr(user, "phone", ""),
        "department": (p.department if p else "") or getattr(user, "department", ""),
        "company": p.company if p else "",
        "tab_number": p.tab_number if p else "",
    }
    if sp is not None and sp.manager_id:
        m = sp.manager
        d["supervisor"] = " ".join(x for x in [m.name, f"({m.phone})" if m.phone else ""] if x)
    return d


LABELS = [("code", "Agent kodi"), ("role", "Rol"), ("position", "Lavozim"), ("project", "Loyiha"), ("unit", "Yo'nalish"),
          ("place", "Hudud"), ("supervisor", "Supervayzer"), ("phone", "Telefon"), ("department", "Bo'lim"),
          ("company", "Korxona"), ("tab_number", "Tabel raqami")]


def lines(user, esc=None):
    """Kartochka satrlari: "Agent kodi: SR2 Tashkent" ... esc — HTML uchun (html.escape)."""
    d = info(user)
    if not d:
        return []
    e = esc or (lambda x: x)
    out = []
    for key, label in LABELS:
        if d.get(key) and not (key == "position" and d["position"] == d["role"]):
            out.append(f"{label}: {e(str(d[key]))}")
    return out


def short(user):
    """Bir qatorda: "SR2 Tashkent · Heinz · Toshkent · SV: Aliyev (+99890...)"."""
    d = info(user)
    if not d:
        return ""
    bits = [d["code"], d["project"], d["place"] or d["unit"], f"SV: {d['supervisor']}" if d["supervisor"] else "",
            d["phone"]]
    return " · ".join(b for b in bits if b)

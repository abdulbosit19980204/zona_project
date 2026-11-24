"""Boshlang'ich katalog (shablondan) va nomlarni moslashtirish yordamchilari."""
import json
import re
from pathlib import Path

CATALOG = Path(__file__).resolve().parent / "data" / "catalog.json"
TEMPLATE = Path(__file__).resolve().parent / "data" / "template.xlsx"
CATALOG_RU = Path(__file__).resolve().parent / "data" / "catalog_ru.json"

CONDITION_BY_LABEL = {"ishlayapti": "ok", "ta'mirga muhtoj": "repair", "ishlamaydi": "broken",
                      "ishlatilmayapti (zaxirada)": "spare", "zaxirada": "spare", "topilmadi": "missing"}
STATUS_BY_LABEL = {"rejada": "planned", "jarayonda": "active", "yakunlandi": "done"}

# Xodimlar tuzilmasidagi (rus tilidagi) shahar nomlari -> filial kodi
CITY_ALIASES = {
    "андижан": "AND", "бухара": "BUX", "фергана": "FRG", "наманган": "NAM", "навои": "NAV", "навоий": "NAV",
    "нукус": "NS", "карши": "QSH", "коканд": "QQN", "самарканд": "SAM", "термез": "TRM", "ташкент": "TSH",
    "таш. обл": "TSH", "ташкентская область": "TSH", "хорезм": "URG", "ургенч": "URG", "сергели": "TSH",
    "чиланзар": "TSH", "шахонтохур": "TSH", "яшнабод": "TSH", "олмазор": "TSH", "мирабад- яккасарай": "TSH",
}


def load_catalog():
    return json.loads(CATALOG.read_text(encoding="utf-8"))


def norm(text):
    """Taqqoslash uchun: kichik harf, apostrof turlari bir xil, ortiqcha bo'shliqsiz."""
    t = str(text or "").strip().lower()
    t = re.sub(r"[ʻʼ’‘`´]", "'", t)
    return re.sub(r"\s+", " ", t)


def name_key(text):
    """Ismni taqqoslash kaliti: harf katta-kichikligi, nuqta/vergul va ortiqcha bo'shliqlar hisobga olinmaydi."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w']+", " ", norm(text))).strip()


def phone_key(text):
    """Telefonning oxirgi 9 raqami (+998 / 8 / bo'shliqlardan qat'i nazar)."""
    d = re.sub(r"\D", "", str(text or ""))
    return d[-9:] if len(d) >= 9 else ""


class EmployeeIndex:
    """Mavjud xodimlarni qayta yaratmaslik uchun qidiruv (import, Xodimlar tuzilmasidan olish).

    Mos keladi: (1) ism + shu filial; (2) ism + telefon yoki Telegram; (3) shu ismli yagona xodim, agar ikkala
    tomonning birida filial ko'rsatilmagan bo'lsa. Nofaol xodimlar ham topiladi (qayta faollashtiriladi).
    """

    def __init__(self, qs=None):
        from .models import Employee
        self.by_name_branch, self.by_name = {}, {}
        for e in (qs if qs is not None else Employee.objects.all()).order_by("-is_active", "id"):
            self.add(e)

    def add(self, e):
        n = name_key(e.full_name)
        self.by_name_branch.setdefault((n, e.branch_id), e)
        bucket = self.by_name.setdefault(n, [])
        if e not in bucket:
            bucket.append(e)

    def find(self, name, branch_id=None, phone="", telegram=""):
        n = name_key(name)
        if not n:
            return None
        e = self.by_name_branch.get((n, branch_id))
        if e:
            return e
        cands = self.by_name.get(n, [])
        pk, tg = phone_key(phone), str(telegram or "").lstrip("@").lower()
        for c in cands:
            if (pk and phone_key(c.phone) == pk) or (tg and c.telegram.lower() == tg):
                return c
        if len(cands) == 1 and (cands[0].branch_id is None or branch_id is None):
            return cands[0]
        return None


def seed_catalog(apps=None, force=False):
    """Bo'sh jadvallarni shablon katalogi bilan to'ldiradi. Mavjud yozuvlarga tegmaydi (faqat yo'qlarini qo'shadi)."""
    get = (lambda name: apps.get_model("inventory", name)) if apps else None
    if get is None:
        from . import models as m
        Org, Branch, Location, DeviceType = m.Org, m.Branch, m.Location, m.DeviceType
    else:
        Org, Branch, Location, DeviceType = get("Org"), get("Branch"), get("Location"), get("DeviceType")
    cat = load_catalog()
    added = 0
    if force or not Org.objects.exists():
        for i, o in enumerate(cat["orgs"]):
            _, c = Org.objects.get_or_create(name=o["name"], defaults={"code": o["code"], "order": i})
            added += c
    if force or not Location.objects.exists():
        for i, name in enumerate(cat["locations"]):
            _, c = Location.objects.get_or_create(name=name, defaults={"order": i})
            added += c
    if force or not DeviceType.objects.exists():
        for i, d in enumerate(cat["device_types"]):
            _, c = DeviceType.objects.get_or_create(name=d["name"], defaults={
                "group": d["group"], "description": d["description"], "serial_hint": d["serial_hint"],
                "extra_hint": d["extra_hint"], "brands": d["brands"], "order": i})
            added += c
    if force or not Branch.objects.exists():
        for i, b in enumerate(cat["branches"]):
            _, c = Branch.objects.get_or_create(code=b["code"], defaults={
                "name": b["name"], "region": b["region"], "note": b["note"], "order": i})
            added += c
    if apps is None:  # migratsiyalarda tarjima 0004 da (0002 paytida ruscha maydonlar hali yo'q)
        fill_russian()
    return added


def fill_russian(apps=None):
    """Ruscha nom va yordamlarni faqat BO'SH maydonlarga yozadi (qo'lda kiritilganlarga tegmaydi)."""
    if apps:
        DeviceType, Location = apps.get_model("inventory", "DeviceType"), apps.get_model("inventory", "Location")
    else:
        from .models import DeviceType, Location
    ru = json.loads(CATALOG_RU.read_text(encoding="utf-8"))
    filled = 0
    for d in DeviceType.objects.all():
        tr = ru["device_types"].get(d.name)
        if not tr:
            continue
        changed = [f for f, v in tr.items() if v and not getattr(d, f, "")]
        for f in changed:
            setattr(d, f, tr[f])
        if changed:
            d.save(update_fields=changed)
            filled += 1
    for loc in Location.objects.all():
        if not loc.name_ru and ru["locations"].get(loc.name):
            loc.name_ru = ru["locations"][loc.name]
            loc.save(update_fields=["name_ru"])
            filled += 1
    return filled

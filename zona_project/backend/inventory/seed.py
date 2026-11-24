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

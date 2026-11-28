"""Ma'lumotlarni avtomatik tarjima qilish (AI): xodim bitta tilda yozadi, qolgan tillarga AI o'giradi.

Har bir tarjima qilinadigan yozuvda `i18n` JSON maydoni bor:
    {"src": {"title": "<asl matn>"}, "uz": {"title": "..."}, "ru": {"title": "..."}, "en": {"title": "..."}}
`src` — tarjima qaysi asl matndan qilinganini eslab qoladi. Asl matn o'zgarsa, eski tarjimalar
yaroqsiz bo'ladi (ko'rsatilmaydi) va yozuv qayta tarjima navbatiga tushadi.

Saqlangandan keyin tarjima fonda (alohida oqimda) bajariladi; tugagach mijozlarga
WebSocket orqali {"type": "state"} yuboriladi — ular tuzilmani qayta yuklaydi.
"""
import json
from pathlib import Path
import logging
import os
import re
import threading

from django.conf import settings
from django.core.cache import cache
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import AITaskConfig, Authority, Department, EdgeCase, Member, Process, System, Task, TaskFallback, Team, Zone

log = logging.getLogger(__name__)

LANGS = ("uz", "ru", "en")
FIELDS = {
    Department: ("name", "description"),
    System: ("name",),
    Zone: ("name", "description"),
    Team: ("name", "description"),
    Member: ("role", "trigger", "does", "excludes", "escalation", "duties"),
    Process: ("name", "description"),
    Task: ("title", "note", "rule"),
    TaskFallback: ("condition",),
    EdgeCase: ("situation", "then_text"),
    Authority: ("title", "scope"),
}
# Ro'yxat maydonlari: i18n da qatorlar "\n" bilan birlashtirilgan matn sifatida saqlanadi
LIST_FIELDS = {"duties"}
MEMORY_FILE = Path(__file__).resolve().parent / "data" / "translations.json"
BATCH_CHARS = 3500
BATCH_ITEMS = 40
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")


def fields_of(obj):
    fields = FIELDS.get(type(obj), ())
    # odam ismi tarjima qilinmaydi, jamoa nomi ("Supervayzerlar") esa tarjima qilinadi
    if isinstance(obj, Member) and obj.is_team:
        fields = ("name",) + fields
    return fields


def _text(obj, field):
    value = getattr(obj, field)
    if field in LIST_FIELDS:
        return "\n".join(str(x).strip() for x in (value or []) if str(x).strip())
    return (value or "").strip()


def _valid(obj, field):
    """Tarjimalar hozirgi asl matnga tegishlimi."""
    data = obj.i18n or {}
    return bool(_text(obj, field)) and (data.get("src") or {}).get(field) == _text(obj, field)


def current(obj, field, lang):
    """Maydonning `lang` tilidagi ko'rinishi (tarjima bo'lmasa — asl matn)."""
    if lang in LANGS and _valid(obj, field):
        value = ((obj.i18n or {}).get(lang) or {}).get(field)
        if value:
            return value.split("\n") if field in LIST_FIELDS else value
    return getattr(obj, field)


def public(obj):
    """API uchun: {"uz": {...}, "ru": {...}, "en": {...}} — faqat yaroqli tarjimalar."""
    data = obj.i18n or {}
    out = {}
    for field in fields_of(obj):
        if _valid(obj, field):
            for lang in LANGS:
                value = (data.get(lang) or {}).get(field)
                if value:
                    out.setdefault(lang, {})[field] = value
    return out


def variants(obj, field):
    """Qidiruv uchun: asl matn va barcha yaroqli tarjimalar bitta satrda."""
    parts = [_text(obj, field)]
    if _valid(obj, field):
        data = obj.i18n or {}
        parts += [(data.get(lang) or {}).get(field) or "" for lang in LANGS]
    return " ".join(dict.fromkeys(p for p in parts if p))


def pending_fields(obj):
    data = obj.i18n or {}
    out = []
    for field in fields_of(obj):
        if not _text(obj, field):
            continue
        if not _valid(obj, field) or any(not (data.get(lang) or {}).get(field) for lang in LANGS):
            out.append(field)
    return out


def localize(obj, lang):
    """Obyekt maydonlarini (xotirada) tanlangan tilga almashtiradi — eksport kabi joylar uchun."""
    for field in fields_of(obj):
        setattr(obj, field, current(obj, field, lang))
    return obj


def request_lang(request):
    raw = ""
    if request is not None:
        raw = request.headers.get("X-Lang") or request.headers.get("Accept-Language") or ""
    lang = raw.split(",")[0].strip().lower()[:2]
    return lang if lang in LANGS else None


def keep_source(obj, attrs, lang):
    """Foydalanuvchi o'z tilidagi ko'rinishni o'zgartirmay qaytarsa, asl matn o'zgarmaydi.

    Masalan, rus tilidagi interfeysda vazifaning faqat mas'uli o'zgartirildi: sarlavha rus tarjimasi
    holida qaytadi — uni asl matn sifatida yozib qo'ysak, boshqa tillardagi tarjimalar behuda yangilanardi.
    """
    if obj is None or not lang:
        return attrs
    for field in fields_of(obj):
        if field in LIST_FIELDS and isinstance(attrs.get(field), list):
            new = "\n".join(str(x).strip() for x in attrs[field] if str(x).strip())
            cur = current(obj, field, lang)
            if new != _text(obj, field) and isinstance(cur, list) and new == "\n".join(cur):
                attrs[field] = getattr(obj, field)
            continue
        if field in attrs and isinstance(attrs[field], str):
            new = attrs[field].strip()
            if new != _text(obj, field) and new == (current(obj, field, lang) or "").strip():
                attrs[field] = getattr(obj, field)
    return attrs


# ------------------------------------------------------------------ fon jarayoni
_lock = threading.Lock()
_state = {"running": False, "again": False, "last_error": "", "last_run": None, "translated": 0, "version": 0}
# Bir nechta backend jarayoni (gunicorn worker'lar) bo'lsa: bir vaqtda faqat bittasi tarjima qiladi (AI takror
# chaqirilmasin), qidiruv indeksi versiyasi va holat — umumiy keshda (Redis). Lokalda kesh jarayon ichida.
_RUN_KEY, _AGAIN_KEY, _VER_KEY, _INFO_KEY = ("zona:translate:run", "zona:translate:again",
                                             "zona:translate:version", "zona:translate:info")
_RUN_TTL = 1800  # jarayon o'lib qolsa qulf shuncha vaqtda o'zi ochiladi


def _note(**kw):
    """Holatni (oxirgi xato, vaqt, soni) jarayon ichida va umumiy keshda yangilaydi."""
    _state.update(kw)
    cache.set(_INFO_KEY, {k: _state[k] for k in ("last_error", "last_run", "translated")}, None)


def enabled():
    return AITaskConfig.objects.filter(task=AITaskConfig.TRANSLATE, enabled=True, provider__isnull=False,
                                       provider__is_active=True).exclude(model="").exists()


def status():
    pending = sum(len(pending_fields(o)) for model in FIELDS for o in model.objects.all())
    info = cache.get(_INFO_KEY) or {}
    return {"enabled": enabled(), "running": _state["running"] or bool(cache.get(_RUN_KEY)), "pending": pending,
            "last_error": info.get("last_error", _state["last_error"]),
            "last_run": info.get("last_run", _state["last_run"]),
            "translated": info.get("translated", _state["translated"])}


def version():
    """Tarjima qo'shilganda o'zgaradi (qidiruv indeksi shunga qarab yangilanadi) — barcha jarayonlar uchun bitta."""
    return (cache.get(_VER_KEY) or 0, _state["version"])


def schedule():
    """Saqlangan yozuvlarni fonda tarjima qilish (tranzaksiya yakunlangach)."""
    if not getattr(settings, "ZONA_TRANSLATE_ASYNC", True) or not enabled():
        return
    transaction.on_commit(start)


def start():
    with _lock:
        if _state["running"]:
            _state["again"] = True
            return False
        _state["running"] = True
        _state["again"] = False
    threading.Thread(target=_worker, name="zona-translate", daemon=True).start()
    return True


def _worker():
    try:
        while True:
            # «yana bir aylanish kerak» belgisi QULFDAN OLDIN qo'yiladi: qulf band bo'lsa, egasi uni ochgach
            # belgini ko'radi va yana aylanadi — so'rov yo'qolmaydi
            cache.set(_AGAIN_KEY, 1, _RUN_TTL)
            if not cache.add(_RUN_KEY, os.getpid(), _RUN_TTL):
                with _lock:
                    _state["running"] = False
                return  # boshqa backend jarayoni tarjima qilyapti
            try:
                cache.delete(_AGAIN_KEY)
                translate_pending()
            except Exception as e:  # noqa: BLE001 — fon oqimi hech qachon yiqilmasin
                log.exception("Tarjima xatosi")
                _note(last_error=str(e)[:300])
            finally:
                cache.delete(_RUN_KEY)
            with _lock:
                if not _state["again"] and not cache.get(_AGAIN_KEY):
                    _state["running"] = False
                    return
                _state["again"] = False
    finally:
        close_old_connections()


SYSTEM = """Sen professional tarjimonsan. {company} kompaniyasining (savdo va distribyutsiya) ichki
"mas'uliyat xaritasi" tizimidagi qisqa matnlarni tarjima qilasan: bo'limlar, jamoalar, lavozimlar, jarayonlar,
vazifalar (agent va supervayzerlar beradigan savol turlari), shartlar va izohlar.

Har bir element uchun:
- source: matn qaysi tilda yozilgan — "uz" (o'zbek, lotin yoki kirill), "ru", "en" yoki "other".
- uz: o'zbek tilida, LOTIN yozuvida (o', g', sh, ch; tutuq belgisi ').
- ru: rus tilida.
- en: ingliz tilida.

Qoidalar:
- Manba tildagi variant asl matnning o'zi bo'lsin (o'zbek kirillda yozilgan bo'lsa — lotinga o'gir).
- Ma'noni aniq saqla; qisqa, tabiiy, ish uslubida yoz. Sarlavhani sarlavha kabi, gapni gap kabi tarjima qil.
- Kishi ismlari, dastur va brend nomlari (1C, ProTarget, Telegram, Excel va h.k.), kodlar, raqamlar,
  qisqartmalar va formatni (yangi qatorlar, ro'yxat belgilari) o'zgartirma.
- Soha atamalari: agent — агент — sales agent; supervayzer — супервайзер — supervisor;
  marshrut — маршрут — route; klient/mijoz — клиент — client; tashrif — визит — visit;
  savdo nuqtasi — торговая точка — outlet; buyurtma — заказ — order.
- Faqat tarjima qaytar, izoh qo'shma. Har bir "id" ni o'zgartirmasdan qaytar."""

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "source": {"type": "string"},
                       "uz": {"type": "string"}, "ru": {"type": "string"}, "en": {"type": "string"}},
        "required": ["id", "source", "uz", "ru", "en"], "additionalProperties": False}}},
    "required": ["items"],
    "additionalProperties": False,
}


def translate_texts(texts, user=None):
    """[matn, ...] -> ({matn: {"uz": .., "ru": .., "en": ..}}, xato matni).

    AI xato bersa, shu paytgacha tarjima qilinganlar saqlanadi va xato qaytariladi."""
    from . import conf
    from .ai import service

    unique = list(dict.fromkeys(t for t in texts if t))
    out = {}
    for chunk in _chunks(unique):
        payload = {"items": [{"id": str(i), "text": t} for i, t in enumerate(chunk)]}
        try:
            data, _ = service.run(AITaskConfig.TRANSLATE, user, f"Tarjima: {len(chunk)} ta matn",
                                  SYSTEM.format(company=conf.get("COMPANY_NAME")),
                                  json.dumps(payload, ensure_ascii=False), SCHEMA)
        except Exception as e:  # noqa: BLE001 — AIError va tarmoq xatolari
            return out, str(e)[:300]
        for item in data.get("items") or []:
            try:
                text = chunk[int(item.get("id"))]
            except (TypeError, ValueError, IndexError):
                continue
            result = {lang: str(item.get(lang) or "").strip() for lang in LANGS}
            source = str(item.get("source") or "").lower()[:2]
            # foydalanuvchi yozgan matn o'z tilida o'zgarmaydi (o'zbek kirill — lotin tarjimasi qoladi)
            if source in LANGS and not (source == "uz" and _CYRILLIC.search(text)):
                result[source] = text
            if all(result.values()):
                out[text] = result
    return out, ""


def _chunks(texts):
    chunk, size = [], 0
    for t in texts:
        if chunk and (size + len(t) > BATCH_CHARS or len(chunk) >= BATCH_ITEMS):
            yield chunk
            chunk, size = [], 0
        chunk.append(t)
        size += len(t)
    if chunk:
        yield chunk


_memory_cache = {"mtime": None, "data": {}}


def memory():
    """Tarjima xotirasi: {asl matn: {"ru": .., "en": .., "uz"?: ..}} — repoda saqlanadi, AI'siz ishlaydi."""
    try:
        mtime = MEMORY_FILE.stat().st_mtime
    except OSError:
        return {}
    if _memory_cache["mtime"] != mtime:
        try:
            _memory_cache["data"] = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except ValueError:
            log.exception("Tarjima xotirasi o'qilmadi")
            _memory_cache["data"] = {}
        _memory_cache["mtime"] = mtime
    return _memory_cache["data"]


def _known(texts):
    """Ma'lum tarjimalar: xotira fayli + bazadagi boshqa yozuvlarning yaroqli tarjimalari (bir xil matn)."""
    mem = memory()
    want = set(texts)
    out = {}
    for t in want:
        m = mem.get(t)
        if m and m.get("ru") and m.get("en"):
            out[t] = {"uz": m.get("uz") or t, "ru": m["ru"], "en": m["en"]}
        elif "\n" in t:
            # ko'p qatorli matn (masalan, vazifalar ro'yxati) — har bir qator xotirada bo'lsa, qatorma-qator yig'iladi
            lines = t.split("\n")
            parts = [mem.get(ln) for ln in lines]
            if all(p and p.get("ru") and p.get("en") for p in parts):
                out[t] = {"uz": t, "ru": "\n".join(p["ru"] for p in parts), "en": "\n".join(p["en"] for p in parts)}
    missing = want - set(out)
    if missing:
        for model in FIELDS:
            for obj in model.objects.all():
                data = obj.i18n or {}
                for field, src in (data.get("src") or {}).items():
                    if src in missing and all((data.get(lang) or {}).get(field) for lang in LANGS):
                        out[src] = {lang: data[lang][field] for lang in LANGS}
    return out


def translate_pending(user=None, use_ai=True):
    """Tarjimasi yo'q yoki eskirgan barcha maydonlarni tarjima qiladi: avval tarjima xotirasidan,
    qolganini AI bilan (yoqilgan bo'lsa). Nechta maydon yangilanganini qaytaradi."""
    from .realtime import broadcast

    work = []  # (model, pk, field, text)
    for model in FIELDS:
        for obj in model.objects.all():
            for field in pending_fields(obj):
                work.append((model, obj.pk, field, _text(obj, field)))
    if not work:
        _note(last_error="")
        return 0
    done = 0
    translated = _known([w[3] for w in work])
    rest = [w[3] for w in work if w[3] not in translated]
    error = ""
    if rest and use_ai and enabled():
        more, error = translate_texts(rest, user)
        translated.update(more)
    by_obj = {}
    for model, pk, field, text in work:
        if text in translated:
            by_obj.setdefault((model, pk), []).append((field, text))
    for (model, pk), items in by_obj.items():
        with transaction.atomic():
            obj = model.objects.select_for_update().filter(pk=pk).first()
            if obj is None:
                continue
            data = dict(obj.i18n or {})
            src = dict(data.get("src") or {})
            changed = False
            for field, text in items:
                if _text(obj, field) != text:  # orada tahrirlangan — keyingi aylanishda tarjima bo'ladi
                    continue
                if src.get(field) != text:
                    # asl matn o'zgargan: eski tarjimalar o'chiriladi
                    for lang in LANGS:
                        (data.get(lang) or {}).pop(field, None)
                src[field] = text
                for lang in LANGS:
                    data[lang] = {**(data.get(lang) or {}), field: translated[text][lang]}
                changed = True
                done += 1
            if changed:
                data["src"] = src
                model.objects.filter(pk=pk).update(i18n=data)
    total = (cache.get(_INFO_KEY) or {}).get("translated", _state["translated"])
    if done:
        _state["version"] += 1
        try:
            cache.incr(_VER_KEY)
        except ValueError:  # birinchi marta (yoki kesh qayta ishga tushgan)
            cache.set(_VER_KEY, 1, None)
        broadcast("state", {"translated": done})
    _note(last_error=error, last_run=timezone.now().isoformat(), translated=total + done)
    return done

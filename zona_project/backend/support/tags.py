"""Savol teglari (turlari): aksiya, vizit, PRBC, ProTarget, 1C, marshrut... — bir savolda bir nechta bo'lishi mumkin.

Teg ro'yxati sozlamalarda (Tag): nomi, kalit so'zlari (oddiy so'z yoki "re:regex"), rangi. Savolga avtomatik qo'yiladi
(matn, rasmdagi matn, tanilgan mavzu sarlavhasi bo'yicha); xodim panelda qo'shib/olib tashlasa — `tags_locked`, keyin
avtomatik qayta yozilmaydi. Tahlilda (konstruktor, umumiy ko'rinish) — o'lchov sifatida.
"""
import re

from .models import Message, Tag

DEFAULT = [  # (kalit, nomi, kalit so'zlar)
    ("promo", "Aksiya / skidka", ["aksiya", "aksya", "akciya", "акци", "skidka", "skitka", "скидк", "bonus", "бонус", "limit", "лимит"]),
    ("visit", "Vizit", ["vizit", "визит", "tashrif", "visit"]),
    ("location", "Lokatsiya / geo", ["lokats", "lakats", "локац", "лакац", "geoloka", "геолока", "геотег", "joylashuv", "координат"]),
    ("prbc", "PRBC", ["prbc", "прбц", "мини-приложени", "mini app", "заявки на точки"]),
    ("protarget", "ProTarget", ["protarget", "pro target", "протаргет", "pro-target"]),
    ("1c", "1C", ["re:(?<![\\w])1[сc](?![\\w])", "dms"]),
    ("route", "Marshrut", ["marshrut", "marshurt", "маршрут"]),
    ("order", "Zakaz / buyurtma", ["zakaz", "заказ", "buyurtma", "корзин", "savat"]),
    ("client", "Klient / nuqta qo'shish", ["klient", "kilent", "клиент", "контрагент", "торговая точка", "savdo nuqta", "nuqta",
                                           "dokon", "do'kon", "магазин", "podkl", "подключ", "inn", "инн", "stir"]),
    ("moderation", "Moderatsiya", ["moderats", "модерац"]),
    ("delivery", "Dostavka", ["dostav", "dastav", "доставк", "доставщ"]),
    ("stock", "Sklad / ostatka", ["sklad", "склад", "ostat", "остат", "qoldiq"]),
    ("payment", "To'lov / perechisleniye", ["perechisl", "перечисл", "безнал", "beznal", "to'lov", "tolov", "оплат"]),
    ("login", "Kirish / parol / dostup", ["login", "логин", "parol", "парол", "dostup", "доступ", "kira olma", "kirolma", "akkaunt", "аккаунт"]),
    ("product", "Tovar / SKU", ["tovar", "товар", "sku", "mahsulot", "артикул", "shtrix", "штрих"]),
    ("price", "Narx", ["narx", "цена", "цены", "prays", "прайс"]),
    ("sync", "Sinxronlash / yangilash", ["sinxron", "синхрон", "obnov", "обнов", "yangila"]),
]


def seed():
    """Bo'sh bo'lsa — boshlang'ich teglar (mavjudlariga tegilmaydi)."""
    if Tag.objects.exists():
        return 0
    for i, (key, title, words) in enumerate(DEFAULT):
        Tag.objects.create(key=key, title=title, keywords=words, order=i)
    return len(DEFAULT)


_CACHE = {"key": None, "rules": []}


def _rules():
    from django.db.models import Max
    stamp = Tag.objects.aggregate(m=Max("updated_at"))["m"], Tag.objects.count()
    if _CACHE["key"] != stamp:
        rules = []
        for t in Tag.objects.filter(active=True):
            rx = []
            for w in t.keywords or []:
                w = str(w).strip()
                if not w:
                    continue
                try:
                    rx.append(re.compile(w[3:] if w.startswith("re:") else re.escape(w.lower()), re.I))
                except re.error:
                    continue
            if rx:
                rules.append((t.key, rx))
        _CACHE.update(key=stamp, rules=rules)
    return _CACHE["rules"]


def detect(*texts):
    blob = "\n".join(str(t or "") for t in texts).lower()
    if not blob.strip():
        return []
    return [key for key, rx in _rules() if any(r.search(blob) for r in rx)]


def apply(q, save=False):
    """Avtomatik teglar (qo'lda tahrirlangan bo'lsa — tegilmaydi)."""
    if q.tags_locked:
        return q
    q.tags = detect(q.text, q.ocr_text, q.alert_text, q.entry.title if q.entry_id else "", q.problem)
    if save:
        Message.objects.filter(pk=q.pk).update(tags=q.tags)
    return q


def backfill(batch=200):
    """Barcha savollarga avtomatik teglar (qo'lda tahrirlanganlardan tashqari). Qaytaradi: nechta yangilandi.

    Avval hammasi hisoblanadi (o'qish kursori yopiladi), keyin kichik paketlarda yoziladi — bot bir vaqtda
    yozayotgan bo'lsa ham SQLite "database is locked" bermasligi uchun; band bo'lsa — biroz kutib qayta uriniladi."""
    import time

    from django.db import OperationalError, transaction
    qs = Message.objects.filter(kind=Message.QUESTION, tags_locked=False).select_related("entry").only(
        "id", "text", "ocr_text", "alert_text", "problem", "tags", "tags_locked", "entry__title")
    todo = []
    for q in list(qs):
        new = detect(q.text, q.ocr_text, q.alert_text, q.entry.title if q.entry_id else "", q.problem)
        if new != (q.tags or []):
            q.tags = new
            todo.append(q)
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        for attempt in range(8):
            try:
                with transaction.atomic():
                    Message.objects.bulk_update(part, ["tags"])
                break
            except OperationalError:
                if attempt == 7:
                    raise
                time.sleep(1 + attempt)
    return len(todo)

"""Review navbatini serverda yopish (interfeysdan emas — har amal ro'yxatni rasmlar bilan qayta yuklab, prod'ni
sekinlashtiradi).

Qoida (DASTURCHILAR_REVIEW_NAVBAT.md, 2026-11-27):
1. ``claude_kind="same"`` (Standartga mos), maqsad standarti tasdiqlangan va savolda standart mavzusiga oid so'z bor
   -> ``dedupe.absorb`` (savol standartning savol ko'rinishi bo'ladi, yozuv arxivga).
2. Qolgan new/review yozuvlar -> ``runner.reject`` (o'chirilmaydi, status=rejected; qaytarish mumkin).
3. Tasdiqlangan yozuvlarga tegilmaydi.
"""
import re

from django.db import transaction
from django.utils import timezone

from .models import Entry

BY = "review navbatini yopish"
GREET = re.compile(r"📍[^\n]*|https?://\S+|@\w+|ассал\w*|assal\w*|салом|salom|алейк\w*|alayk\w*|aleyk\w*|alek\w*|"
                   r"здравствуйте|добрый день|доброе утро", re.I)


def topic(title):
    """Standart sarlavhasi -> savolda bo'lishi kerak bo'lgan mavzu so'zlari (regexlar)."""
    t = (title or "").lower()
    r = []
    if re.search(r"parol|kira|login", t):
        r.append(r"parol|kira|kirol|войт|парол|логин|login|obnov|обнов|yangilan")
    if re.search(r"geolok|geoteg|lokats|joylash|координ", t):
        r.append(r"lok|лок|lak|геот|geot|координ|joylash|сдвин|uzoq|далек")
    if re.search(r"vizit|визит|tashrif", t):
        r.append(r"vizit|визит|tashrif|vzit")
    if re.search(r"yetkazib|достав", t):
        r.append(r"достав|dostav|yetkaz|маршрут")
    if re.search(r"moderats|модерац", t):
        r.append(r"модерац|moderat|podkl|подключ|padkl|tasdiql|подтверд|qo.sh|добав")
    if re.search(r"aksiya|skidka|акци", t):
        r.append(r"aksiya|акци|skidka|скидк|bonus|бонус")
    if re.search(r"zakaz|заказ", t):
        r.append(r"zakaz|заказ|zakas")
    if not r and re.search(r"nuqta|тт|точк|klient", t):
        r.append(r"nuqta|tochk|точк|\bтт\b|magazin|магазин|do.kon|dukon|клиент|klient")
    if not r:
        w = [x[:5] for x in re.findall(r"[a-zа-яё']{5,}", t)]
        if w:
            r.append("|".join(map(re.escape, w)))
    return [re.compile(x, re.I) for x in r]


def plan(older_than_days=0, reject_rest=True):
    """-> {"absorb": {standart_id: [ids]}, "reject": [ids]} — hech narsa o'zgartirilmaydi."""
    from .engine import learnable_question
    queue = Entry.objects.filter(status__in=[Entry.NEW, Entry.REVIEW])
    if older_than_days:
        queue = queue.filter(created_at__lt=timezone.now() - timezone.timedelta(days=older_than_days))
    absorb_map, rejected = {}, []
    for e in queue.select_related("claude_target").order_by("id"):
        text = " ".join(GREET.sub(" ", " ".join([e.title, *(e.questions or [])[:3]])).split())
        tgt = e.claude_target
        if (e.claude_kind == "same" and tgt is not None and tgt.status == Entry.APPROVED and len(text) >= 12
                and learnable_question(text) and any(rx.search(text) for rx in topic(tgt.title))):
            absorb_map.setdefault(tgt.pk, []).append(e.pk)
        elif reject_rest:
            rejected.append(e.pk)
    return {"absorb": absorb_map, "reject": rejected}


def apply(p, by=BY):
    """Rejani bajaradi (bitta tranzaksiya). Qaytaradi: (standartga qo'shilgan, rad etilgan) soni."""
    from . import runner
    from .dedupe import absorb
    absorbed = rejected = 0
    with transaction.atomic():
        for tgt, ids in p["absorb"].items():
            absorbed += absorb(tgt, ids, by)
        for e in Entry.objects.filter(pk__in=p["reject"], status__in=[Entry.NEW, Entry.REVIEW]):
            runner.reject(e, by)
            rejected += 1
    return absorbed, rejected

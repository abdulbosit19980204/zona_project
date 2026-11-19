"""O'z-o'zini o'qitish: bot chatlardan o'rganib, javoblarini yaxshilab boradi.

1) Savol ko'rinishlari (xavfsiz, avtomatik): bot bilim bazasidagi javob bilan javob bergan, savol beruvchi 👎 bosmagan va
   xodim tuzatmagan bo'lsa — savolning shu yozilishi yozuvga qo'shiladi. Keyingi safar shunday savol AI'siz, darhol topiladi
   (tezlik ham oshadi). 👍 bosilsa — darhol qo'shiladi.
2) Xodim tuzatishi: bot javob bergan savolga xodim boshqa javob yozsa — AI eski javob va xodim tuzatishini birlashtirib
   yaxshilangan javob taklif qiladi. Ishonchli xodim (sozlamadagi daraja) tuzatgan bo'lsa — darhol qo'llanadi, aks holda
   tasdiqlashga tushadi. Eski holat har doim versiyalarda qoladi.
3) Ishonchli xodimning yangi javobi (bot bilmagan savol) — nomzod darhol tasdiqlanadi; boshqalarniki — tasdiqlashga.
4) Kunlik AI tahlili: 👎 olgan, ko'p ishlatiladigan yozuvlar va javobsiz savollar avtomatik ko'rib chiqiladi; faqat
   xavfsiz takliflar (yangi savol ko'rinishlari) o'zi qo'llanadi, qolganlari — "AI takliflari"da.
"""
import logging

from django.utils import timezone

from . import engine
from .models import AIJob, Entry, Message, Settings

log = logging.getLogger("support")
LEVELS = {"off": set(), "lead": {"L3", "LEAD"}, "l2": {"L2", "L3", "LEAD"}, "all": {"L1", "L2", "L3", "LEAD", ""}}


def trusted(user, s=None):
    s = s or Settings.load()
    if not user or not user.is_staff:
        return False
    return (user.staff_level() or "") in LEVELS.get(s.auto_approve_level, set())


def add_variant(entry, text):
    """Savolning yangi yozilishini yozuvga qo'shish (juda o'xshashi bo'lsa — qo'shilmaydi)."""
    t = " ".join((text or "").split())
    if not entry or len(t) < 8 or len(t) > 300 or not engine.substantive(t):
        return False
    variants = [entry.title, *(entry.questions or [])]
    if any(engine.similarity(t, v) >= 90 for v in variants):
        return False
    entry.questions = [*(entry.questions or []), t][-60:]
    Entry.objects.filter(pk=entry.pk).update(questions=entry.questions, updated_at=timezone.now())
    return True


def on_feedback(q):
    """👍 — savol shu javobga mos: yozilishini darhol o'rganamiz."""
    s = Settings.load()
    if s.self_learning and q.feedback > 0 and q.entry_id and not q.learned:
        add_variant(q.entry, q.text)
        Message.objects.filter(pk=q.pk).update(learned=True)


def tick(limit=300):
    """Soatlik: bir soatdan oshgan, e'tirozsiz bot javoblaridan savol ko'rinishlarini o'rganish."""
    s = Settings.load()
    if not s.self_learning:
        return 0
    now = timezone.now()
    qs = (Message.objects.filter(kind=Message.QUESTION, answered_by="bot", status=Message.ANSWERED, entry__isnull=False,
                                 learned=False, feedback__gte=0, created_at__lte=now - timezone.timedelta(hours=1),
                                 created_at__gte=now - timezone.timedelta(days=14), entry__status=Entry.APPROVED)
          .select_related("entry").order_by("id")[:limit])
    added, seen = 0, []
    for q in qs:
        seen.append(q.pk)
        if q.staff_replies.filter(kind=Message.STAFF).exists():
            continue  # xodim aralashgan — javob to'liq to'g'ri bo'lmagan bo'lishi mumkin
        added += add_variant(q.entry, q.text)
    Message.objects.filter(pk__in=seen).update(learned=True)
    return added


def on_correction(q, staff_user, staff_text):
    """Bot javobini xodim tuzatdi — yozuvni yaxshilash uchun AI tahlili (ishonchli xodim bo'lsa — avto qo'llash)."""
    from zona.ai import service as ai
    s = Settings.load()
    if not (s.self_learning and q.entry_id and ai.status().get("support")):
        return None
    return AIJob.objects.create(kind=AIJob.REVIEW_ENTRIES, created_by=f"avto: {staff_user.staff_name()} tuzatishi",
                                params={"ids": [q.entry_id], "auto": trusted(staff_user, s), "correction": {
                                    "question": (q.text or q.ocr_text or "")[:800], "bot": (q.answer_text or "")[:800],
                                    "staff": staff_text[:1500], "by": staff_user.staff_name()}})


def daily_review():
    """Kuniga bir marta: bilim bazasi va javobsiz savollar AI tahlili (agar AI sozlangan bo'lsa)."""
    from zona.ai import service as ai
    s = Settings.load()
    if not s.self_learning or not ai.status().get("support"):
        return False
    since = timezone.now() - timezone.timedelta(hours=24)
    if AIJob.objects.filter(created_by__startswith="avto: kunlik", created_at__gte=since).exists():
        return False
    if AIJob.objects.filter(status__in=[AIJob.QUEUED, AIJob.RUNNING]).exists():
        return False
    AIJob.objects.create(kind=AIJob.REVIEW_ENTRIES, created_by="avto: kunlik tahlil",
                         params={"scope": "priority", "limit": 24, "auto_safe": True})
    AIJob.objects.create(kind=AIJob.REVIEW_UNANSWERED, created_by="avto: kunlik tahlil", params={"days": 2})
    return True

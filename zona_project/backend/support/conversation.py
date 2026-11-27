"""Bitta mavzu — bitta suhbat. Odam savolni bir nechta xabarda yozadi: "do'konning lokatsiyasi noto'g'ri", keyin
lokatsiya, keyin rasmlar, keyin "hali ham shunday". Har bir xabar alohida savol emas — ochiq savolning davomi.

Qoida: shu odamning shu guruhdagi oxirgi ochiq savoli (oxirgi xabaridan `thread_window` daqiqa o'tmagan) bo'lsa,
yangi xabar unga biriktiriladi. Yangi savol faqat aniq belgisi bo'lsa ochiladi: salom bilan boshlangan aniq savol,
"yana bir savol", izohli yangi rasm yoki bazadagi boshqa mavzuga aniq mos kelgan matn.
"""
import re

from django.utils import timezone

from . import engine
from .models import Entry, Message, Settings

MAX_AGE_HOURS = 3  # savol shundan eski bo'lsa — davom emas, yangi suhbat

NEW_TOPIC = re.compile(
    r"(?<!\w)(yana bir savol|yana savol|boshqa savol|ikkinchi savol|yana bir narsa|"
    r"ещ[её] (один |1 )?вопрос|другой вопрос|новый вопрос|ещ[её] одно|"
    r"another question|one more question)(?!\w)", re.IGNORECASE)
GREET_START = re.compile(
    r"^\W*(assalomu?|asalomu?|assalom|salom|ассалому?|ассалом|салом|здравств\w*|добр\w+ (день|утро|вечер)|"
    r"привет|hello|hi)(?!\w)", re.IGNORECASE)

ATTACH, APPEND, ASK, REOPEN, REANSWER = "attach", "append", "ask", "reopen", "reanswer"


def _root(m):
    """Takror (dup) savollar asl savolga bog'langan — suhbat ildizi asl savol."""
    seen = 0
    while m is not None and m.kind == Message.QUESTION and m.stage == "dup" and m.question_id and seen < 5:
        m, seen = m.question, seen + 1
    return m


def open_root(bot, chat_id, user, window_min, now=None):
    """Shu odamning ochiq suhbati (savoli) yoki None."""
    if not window_min or user is None:
        return None
    now = now or timezone.now()
    last = (Message.objects.filter(bot=bot, chat_id=chat_id, user=user, kind__in=[Message.QUESTION, Message.INFO],
                                   created_at__gte=now - timezone.timedelta(minutes=window_min), created_at__lte=now)
            .select_related("question").order_by("-created_at").first())
    if last is None:
        return None
    root = _root(last if last.kind == Message.QUESTION else last.question)
    if root is None or root.kind != Message.QUESTION or root.user_id != user.pk:
        return None
    if root.created_at < now - timezone.timedelta(hours=MAX_AGE_HOURS):
        return None
    if root.status in (Message.IGNORED, Message.CLOSED) or root.resolution == Message.YES:
        return None
    return root


def topic_entry(text):
    """Matn bazadagi qaysi mavzuga aniq mos keladi (shablon yoki savol-javob), yoki None."""
    s = Settings.load()
    entries = list(Entry.objects.filter(status=Entry.APPROVED))
    templates = [e for e in entries if e.kind == Entry.TEMPLATE]
    e, _fields, _conf = engine.match_template(text, templates)
    if e:
        return e
    faqs = [e for e in entries if e.kind == Entry.FAQ or (e.kind == Entry.TEMPLATE and e.questions)]
    e, score = engine.match_faq(text, faqs)
    return e if e and score >= s.faq_threshold else None


def root_keys(root):
    """Suhbat obyekti: savol, OCR va qo'shimchalaridagi UZ-kod, zakaz, STIR (support.tasks.case_keys)."""
    from .tasks import _keys_of
    return _keys_of(root)


CASE_SCHEMA = {
    "type": "object",
    "properties": {"decision": {"type": "string", "enum": ["continue", "new_case"]},
                   "reason": {"type": "string"}},
    "required": ["decision", "reason"],
    "additionalProperties": False,
}
CASE_SYSTEM = """Sen Telegram support guruhidagi suhbatlarni ajratuvchisan. Bir agentning ochiq savoli (suhbat) va
uning yangi xabari beriladi. Qaror: "continue" — yangi xabar shu holat haqida (qo'shimcha, «hali ham», shu klient/zakaz,
shu muammoning yana bir skrinshoti, salom bilan boshlangan bo'lsa ham shu holat); "new_case" — boshqa klient/nuqta, boshqa
zakaz yoki boshqa muammo. Holat = bitta agent + bitta obyekt (klient/nuqta kodi, zakaz) + bitta muammo turi.
Noaniq bo'lsa — "continue". Qisqa sabab (o'zbekcha)."""


def ai_case(root, text, photo):
    """Noaniq holatda AI qarori: True — yangi holat, False — davom, None — AI ishlamadi (qoida qaror qiladi)."""
    s = Settings.load()
    if not s.ai_enabled or engine.ai_quota_left(s) <= 0 or engine.ai_down():
        return None
    from zona.ai import service as ai
    from zona.ai.providers import AIError, deadline
    from zona.models import AITaskConfig
    msg = (f"OCHIQ SUHBAT:\n{context(root, limit=12)}\n\nYANGI XABAR"
           f"{' (rasm bilan)' if photo else ''}:\n{(text or '')[:800]}")
    try:
        with deadline(8):
            data, _meta = ai.run(AITaskConfig.SUPPORT, None, "suhbat: davommi", CASE_SYSTEM, msg, CASE_SCHEMA)
    except (AIError, Exception):  # noqa: BLE001 — AI xatosi suhbatni to'xtatmasin
        return None
    return str(data.get("decision")) == "new_case"


def new_topic(text, root, photo=False, use_ai=True):
    """Bu xabar yangi holatmi (True) yoki ochiq suhbatning davomi (False).

    Holat = bitta agent + bitta obyekt (UZ-kod, zakaz, STIR) + bitta muammo (egasi, 2026-11-27). Tez qoidalar:
    mazmunsiz -> davom; «yana bir savol» -> yangi; obyekt kalitlari kesishsa -> davom, farq qilsa -> yangi;
    «hali ham / до сих пор» -> davom. Salom bilan boshlangan yoki izohli rasm (avval doim yangi edi) — noaniq: AI
    qaror qiladi, AI ishlamasa — avvalgi qoida."""
    from .resolution import NOT_YET
    from .tasks import case_keys, strip_greeting
    t = (text or "").strip()
    if not engine.substantive(t):
        return False  # lokatsiya, rasm, "hali ham", "нету его" — davom
    if NEW_TOPIC.search(t):
        return True
    mine, theirs = case_keys(t), root_keys(root)
    if mine and theirs:
        return not (mine & theirs)  # shu klient/zakaz — davom; boshqasi — yangi holat
    rest = strip_greeting(t) if GREET_START.match(t) else t
    if NOT_YET.search(rest) and not mine:
        return False  # «Assalomu alaykum, hali ham chiqmayapti» — shu holatning davomi
    if GREET_START.match(t) or photo:
        verdict = ai_case(root, t, photo) if use_ai else None
        if verdict is not None:
            return verdict
        return True  # AI'siz — avvalgi qoida: salom bilan aniq savol / izohli yangi rasm — yangi savol
    e = topic_entry(t)
    return e is not None and e.pk != root.entry_id and bool(root.entry_id or engine.substantive(root.text))


def action(root, text, photo, use_ai=True):
    """Davom xabari bilan nima qilinadi: "" — davom emas (oddiy savol sifatida), yoki ATTACH/APPEND/ASK/REOPEN/REANSWER."""
    if not (text or "").strip() and not photo:
        return ""
    if new_topic(text, root, bool(photo), use_ai=use_ai):
        return ""
    if root.status == Message.NEW:
        return ASK if root.stage == "ask" else APPEND
    if root.status in (Message.ESCALATED, Message.DRAFTED):
        return ATTACH  # mutaxassis kutilmoqda — xabar suhbatga qo'shiladi, bot qayta "qabul qilindi" yozmaydi
    if root.status == Message.ANSWERED:
        from .resolution import NOT_YET
        unhappy = engine.substantive(text) or bool(NOT_YET.search(text or ""))
        if root.answered_by == "bot":
            if photo:
                return ""  # bot javobidan keyin yangi ekran — o'z mantig'i (boshqa ekran — alohida javob)
            return REANSWER if unhappy else ATTACH
        return REOPEN if unhappy else ATTACH
    return ""


def context(root, limit=20):
    """Suhbat matni (AI va panel uchun): savol, bot javobi, odamning qo'shimchalari, xodim javoblari — vaqt tartibida."""
    items = [(root.created_at, "Mijoz", root.text or ("(rasm)" if root.photo_file_id else ""))]
    if root.answered_by == "bot" and root.answer_text:
        items.append((root.answered_at or root.created_at, "Bot", root.answer_text[:700]))
    for m in root.staff_replies.order_by("created_at")[:limit]:
        if m.kind in (Message.INFO, Message.FEEDBACK, Message.QUESTION):
            who = "Mijoz"
        elif m.kind == Message.CLARIFY:
            who = "Xodim (aniqlashtirdi)"
        else:
            who = "Xodim"
        body = m.text or ("(rasm)" if m.photo_file_id else "")
        if body:
            items.append((m.created_at, who, body[:500]))
    items.sort(key=lambda x: x[0])
    return "\n".join(f"{who}: {body}" for _t, who, body in items)[-3500:]


def location_text(msg):
    """Telegram lokatsiya/joy xabari -> matn (suhbatda va AI uchun)."""
    venue = msg.get("venue") or {}
    loc = venue.get("location") or msg.get("location") or {}
    if not loc.get("latitude"):
        return ""
    lat, lon = loc["latitude"], loc["longitude"]
    bits = [x for x in (venue.get("title"), venue.get("address")) if x]
    bits.append(f"https://maps.google.com/?q={lat:.6f},{lon:.6f}")
    return "📍 Lokatsiya: " + ", ".join(bits)


def staff_target(bot, chat_id, staff_text, window_min, now=None):
    """Xodim reply qilmasdan yozdi: guruhda javob kutayotgan YAGONA savol bo'lsa (yoki savol egasi @username bilan
    tilga olingan bo'lsa) — o'sha savolga bog'lanadi. Aks holda None (taxmin qilinmaydi)."""
    if not window_min:
        return None
    now = now or timezone.now()
    waiting = list(Message.objects.filter(bot=bot, chat_id=chat_id, kind=Message.QUESTION, source="live",
                                          status__in=[Message.ESCALATED, Message.DRAFTED],
                                          created_at__gte=now - timezone.timedelta(minutes=window_min))
                   .exclude(stage="dup").select_related("user").order_by("-created_at")[:10])
    low = (staff_text or "").lower()
    named = [q for q in waiting if q.user_id and q.user.username and "@" + q.user.username.lower() in low]
    if len(named) == 1:
        return named[0]
    users = {q.user_id for q in waiting}
    if len(users) == 1 and waiting and not named:
        return waiting[0]  # bitta odam kutyapti — uning oxirgi savoli
    return None

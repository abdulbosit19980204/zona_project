"""Savol yopildimi — aniq holat: hal bo'ldi (yes) / hal bo'lmadi (no) / tasdiq so'raldi (asked) / noma'lum ("").

Manbalar:
- savol egasi "rahmat", "готово", "ishladi" yozdi -> hal bo'ldi (bot xabarga 👍 qo'yadi);
  "ishlamadi", "не помогло" (javobga reply) -> hal bo'lmadi, savol yana xodimga o'tadi;
- xodim javob berganidan (yoki vazifa ochilganidan) keyin bot savol egasidan "hal bo'ldimi?" deb so'raydi (tugmalar);
- bot javobi ostidagi 👍/👎;
- paneldan xodim belgilaydi.
"""
import html
import logging
import re
from zoneinfo import ZoneInfo

from django.db.models import Q
from django.utils import timezone

from .models import MODE_LIVE, Message, Settings, SupportTask

log = logging.getLogger("support")
TZ = ZoneInfo("Asia/Tashkent")
YES, NO, ASKED = Message.YES, Message.NO, Message.ASKED

THANKS = re.compile(
    r"(?<!\w)(rahmat\w*|raxmat\w*|rahmet\w*|raxmet\w*|tashakkur\w*|рахмат\w*|рахмет\w*|ташаккур\w*|спасибо|спс|пасиб\w*|"
    r"благодар\w*|thanks?|thank you|thx|готово|получилось|заработал\w*|работает|решено|решилось|"
    r"bo'ldi|boldi|bo‘ldi|bo’ldi|ishladi|ishlayapti|hal bo'ldi|zo'r|zor|супер|отлично|класс)(?!\w)", re.IGNORECASE)
NOT_YET = re.compile(
    r"(?<!\w)(ishlamadi|ishlamayapti|bo'lmadi|bolmadi|bo‘lmadi|hal bo'lmadi|yordam bermadi|o'xshamadi|"
    r"не помогло|не работает|не получилось|не решено|не решилось|не вышло|всё ещё|все еще|до сих пор|"
    r"hali ham|haliyam|xaliyam|baribir)(?!\w)", re.IGNORECASE)

DONE_TEXT = {"uz": "✅ Rahmat! Savol yopildi.", "ru": "✅ Спасибо! Вопрос закрыт."}
AGAIN_TEXT = {"uz": "❌ Tushunarli — mutaxassis qayta ko'rib chiqadi.", "ru": "❌ Понятно — специалист посмотрит ещё раз."}


def feedback_kind(text):
    """Savol egasining qisqa xabari: "yes" (rahmat/готово/ishladi), "no" (ishlamadi/не помогло) yoki "" (boshqa)."""
    t = (text or "").strip()
    if not t or len(t) > 120 or "?" in t:
        return ""
    if len(re.findall(r"\w+", t)) > 8:
        return ""
    if NOT_YET.search(t):
        # "ishlamadi", "не помогло" — qisqa javob; uzunroq matn yangi muammo tavsifi bo'lishi mumkin
        return NO if len(re.findall(r"\w+", t)) <= 5 else ""
    if THANKS.search(t):
        return YES
    return ""


def target(bot, chat_id, user, reply_to, kind):
    """Qaysi savol haqida: reply qilingan zanjir (savol, javob, "hal bo'ldimi?" xabari); "rahmat" reply'siz bo'lsa —
    shu odamning oxirgi sutkadagi javob olgan/uzatilgan savoli. "ishlamadi" faqat zanjirga reply bo'lsa olinadi
    (aks holda bu yangi muammo bo'lishi mumkin — savol sifatida ishlanadi)."""
    q = None
    if reply_to:
        parent = Message.objects.filter(bot=bot, chat_id=chat_id, message_id=reply_to).first()
        if parent is not None:
            q = parent if parent.kind == Message.QUESTION else parent.question
        else:
            q = (Message.objects.filter(bot=bot, chat_id=chat_id, kind=Message.QUESTION)
                 .filter(Q(bot_reply_id=reply_to) | Q(confirm_msg_id=reply_to)).first())
        if q is not None and q.kind == Message.QUESTION and q.user_id == user.pk:
            return q
    if kind != YES:
        return None
    since = timezone.now() - timezone.timedelta(hours=24)
    return (Message.objects.filter(bot=bot, chat_id=chat_id, user=user, kind=Message.QUESTION, created_at__gte=since,
                                   status__in=[Message.ANSWERED, Message.ESCALATED, Message.DRAFTED])
            .exclude(resolution=YES).exclude(stage="dup").order_by("-created_at").first())


def mark(q, value, by):
    """Holatni yozish. "Hal bo'lmadi" — javob berilgan savol yana xodim kutayotganlar qatoriga qaytadi."""
    now = timezone.now()
    upd = {"resolution": value, "resolved_at": now if value in (YES, NO) else None, "resolved_by": (by or "")[:150]}
    if value == NO and q.status in (Message.ANSWERED, Message.CLOSED):
        upd["status"] = Message.ESCALATED
    Message.objects.filter(pk=q.pk).update(**upd)
    for k, v in upd.items():
        setattr(q, k, v)
    return q


def close_prompt(tg, q, value):
    """"Hal bo'ldimi?" xabari javobga aylanadi (tugmalarsiz)."""
    if not q.confirm_msg_id or tg is None:
        return
    lang = "ru" if q.lang == "ru" else "uz"
    try:
        tg.edit_text(q.chat_id, q.confirm_msg_id, (DONE_TEXT if value == YES else AGAIN_TEXT)[lang])
    except Exception as e:  # noqa: BLE001
        log.info("confirm prompt edit: %s", e)


def notify_unresolved(tg, q, admin_chat_id, text=""):
    if not admin_chat_id or tg is None:
        return
    who = html.escape(q.user.name if q.user_id else "")
    link = q.group.message_link(q.message_id) if q.group_id else ""
    body = (f"❌ <b>Hal bo'lmadi</b> — {who}" + (f" · {html.escape(q.group.title)}" if q.group_id else "")
            + f"\n<blockquote>{html.escape((q.problem or q.text or '')[:300])}</blockquote>"
            + (f"\n💬 {html.escape(text[:200])}" if text else ""))
    try:
        tg.send(admin_chat_id, body, buttons=[[{"text": "↗ Savolga o'tish", "url": link}]] if link else None)
    except Exception as e:  # noqa: BLE001
        log.info("unresolved notify: %s", e)


def _mention(u):
    if u.username:
        return "@" + html.escape(u.username)
    return f'<a href="tg://user?id={u.tg_id}">{html.escape(u.name or "foydalanuvchi")}</a>'


def prompt_text(q):
    if q.lang == "ru":
        return f"{_mention(q.user)}, ваш вопрос решён?"
    return f"{_mention(q.user)}, savolingiz bo'yicha muammo hal bo'ldimi?"


def prompt_buttons(q):
    yes, no = ("✅ Да, решён", "❌ Нет") if q.lang == "ru" else ("✅ Ha, hal bo'ldi", "❌ Yo'q")
    return [[{"text": yes, "callback_data": f"rs:{q.id}:1"}, {"text": no, "callback_data": f"rs:{q.id}:0"}]]


TASK_WAIT_HOURS = 2  # vazifa ochilgan, guruhda xodim javobi yo'q — shuncha vaqtdan keyin so'raladi
WORK_HOURS = (9, 20)  # kechasi odamlarni bezovta qilmaymiz (Toshkent vaqti)
ASK_WINDOW_HOURS = 3  # xodim javobidan keyin shu vaqt ichida so'raladi (keyin — kech, so'ralmaydi)


def due(now=None, s=None):
    """Tasdiq so'raladigan savollar: xodim javob bergan (confirm_after daqiqa o'tgan) yoki vazifa ochilgan
    (TASK_WAIT_HOURS o'tgan), holati noma'lum, savol egasi xodim emas, oxirgi 2 kun ichida."""
    s = s or Settings.load()
    now = now or timezone.now()
    base = (Message.objects.filter(kind=Message.QUESTION, source="live", resolution="", user__isnull=False,
                                   user__member__isnull=True, user__contact__isnull=True,
                                   created_at__gte=now - timezone.timedelta(days=2))
            .exclude(stage="dup").exclude(status__in=[Message.IGNORED, Message.NEW]))
    # eski savollar haqida so'ralmaydi (kecha javob berilgan savolga bugun "hal bo'ldimi?" — g'alati)
    staff = base.filter(status=Message.ANSWERED, answered_at__lte=now - timezone.timedelta(minutes=s.confirm_after or 0),
                        answered_at__gte=now - timezone.timedelta(hours=ASK_WINDOW_HOURS)).exclude(answered_by="bot")
    task_ids = SupportTask.objects.filter(created_at__lte=now - timezone.timedelta(hours=TASK_WAIT_HOURS),
                                          created_at__gte=now - timezone.timedelta(hours=24)).values_list("message_id", flat=True)
    tasked = base.filter(pk__in=task_ids)
    return (staff | tasked).distinct().select_related("user", "group").order_by("created_at")


def ask_pending(tg, s=None, now=None, limit=5):
    """Ishchi sikl chaqiradi: tasdiq so'rash vaqti kelgan savollarga "hal bo'ldimi?" (savolga reply, tugmalar bilan)."""
    s = s or Settings.load()
    if not s.confirm_resolution or tg is None:
        return 0
    now = now or timezone.now()
    hour = now.astimezone(TZ).hour
    if not (WORK_HOURS[0] <= hour < WORK_HOURS[1]):
        return 0
    n = 0
    for q in due(now, s)[:limit]:
        if q.group_id and q.group.effective_mode() != MODE_LIVE:
            continue
        try:
            sent = tg.send(q.chat_id, prompt_text(q), reply_to=q.message_id, buttons=prompt_buttons(q))
        except Exception as e:  # noqa: BLE001
            log.info("confirm ask failed q=%s: %s", q.pk, e)
            Message.objects.filter(pk=q.pk).update(resolution=ASKED)  # qayta-qayta urinib guruhni to'ldirmaymiz
            continue
        Message.objects.filter(pk=q.pk).update(resolution=ASKED, confirm_msg_id=(sent or {}).get("message_id"))
        n += 1
    return n


def problem_of(q, entry=None):
    """Savolning qisqa muammosi (jurnal va tahlil uchun): aniq matn; bo'lmasa tanilgan holat nomi; bo'lmasa rasm matni."""
    from .engine import substantive
    text = " ".join((q.text or "").split())
    if substantive(text):
        body = text
    elif entry is not None:
        body = entry.title + (f" — {text}" if text else "")
    elif text:
        body = text
    else:
        ocr = next((ln.strip() for ln in (q.ocr_text or "").splitlines() if len(ln.strip()) >= 12), "")
        body = ("Rasmli savol" + (f": {ocr}" if ocr else "")) if q.photo_file_id else ""
    return body[:297] + "…" if len(body) > 300 else body

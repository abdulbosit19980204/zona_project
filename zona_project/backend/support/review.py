"""Bot javoblarini baholash va tuzatish.

Guruhda: savol egasi 👍 / 👎 bosadi; admin va xodimlar "⚠️ Xato javob" (yoki 👎) bilan xato javobni belgilaydi.
Panelda — alohida ro'yxat: savol, skrinshotlar, guruhdagi havola, bot javobi; to'g'ri javob yoziladi va bitta tugma
bilan guruhdagi bot javobiga reply qilib yuboriladi, xohlasa bilim bazasiga ham (tasdiqlash navbatiga) tushadi.

Holatlar (Message.review): "" — baholanmagan; wrong — xato; check — tekshirish (👍 bosilgan — to'g'riligini tasdiqlash);
ok — to'g'ri deb tasdiqlandi; fixed — to'g'ri javob yozildi.
"""
import html
import logging

from django.utils import timezone

from .models import Message

log = logging.getLogger("support")
WRONG, CHECK, OK, FIXED = "wrong", "check", "ok", "fixed"
OPEN = (WRONG, CHECK)

NOTE = {
    "uz": "🤖 Avto-javob · test rejimi. Fikringiz muhim — 👍 / 👎 bosing, javoblarni shu asosda yaxshilaymiz.",
    "ru": "🤖 Автоответ · тестовый режим. Ваше мнение важно — нажмите 👍 / 👎, по нему мы улучшаем ответы.",
}


def note_html(lang):
    return f"\n\n<i>{html.escape(NOTE['ru' if lang == 'ru' else 'uz'])}</i>"


def buttons(q, settings):
    """Bot javobi ostidagi tugmalar: 👍 / 👎 (savol egasi) va ⚠️ Xato javob (admin / xodim)."""
    rows = []
    if settings.feedback_buttons:
        rows.append([{"text": "👍", "callback_data": f"fb:{q.id}:1"}, {"text": "👎", "callback_data": f"fb:{q.id}:-1"}])
    if settings.review_button:
        label = "⚠️ Неверный ответ" if q.lang == "ru" else "⚠️ Xato javob"
        rows.append([{"text": label, "callback_data": f"bad:{q.id}"}])
    return rows or None


def mark(q, value, by, note=""):
    """Holatni yozish. Xato belgisi kuchliroq: tekshirish (👍) xato belgisini yopmaydi."""
    if value == CHECK and q.review in (WRONG, FIXED, OK):
        return q
    upd = {"review": value, "review_by": (by or "")[:150], "review_at": timezone.now()}
    if note:
        upd["review_note"] = note[:300]
    Message.objects.filter(pk=q.pk).update(**upd)
    for k, v in upd.items():
        setattr(q, k, v)
    return q


def fix(q, text, by, tg=None, send=True, learn_kb=False):
    """To'g'ri javob: saqlanadi; send — guruhdagi bot javobiga (bo'lmasa savolga) reply qilib bot yuboradi;
    learn_kb — bilim bazasiga (tasdiqlash navbatiga, muhim deb)."""
    text = (text or "").strip()
    upd = {"fixed_text": text[:4000], "fixed_by": (by or "")[:150], "fixed_at": timezone.now(), "review": FIXED,
           "review_at": timezone.now()}
    if not q.review_by:
        upd["review_by"] = (by or "")[:150]
    sent_id = None
    if send and tg is not None and text:
        head = "✏️ Уточнённый ответ:" if q.lang == "ru" else "✏️ Aniqlashtirilgan javob:"
        body = f"<b>{head}</b>\n{html.escape(text)}"
        try:
            sent = tg.send(q.chat_id, body, reply_to=q.bot_reply_id or q.message_id)
            sent_id = (sent or {}).get("message_id")
        except Exception as e:  # noqa: BLE001
            log.warning("fix send failed q=%s: %s", q.pk, e)
            raise
        upd["fixed_msg_id"] = sent_id
    Message.objects.filter(pk=q.pk).update(**upd)
    for k, v in upd.items():
        setattr(q, k, v)
    entry = None
    if learn_kb and text:
        from .runner import learn
        entry, _new = learn(q, text, by or "admin", priority=True, source="panel")
    return q, entry

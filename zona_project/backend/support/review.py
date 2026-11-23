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


HIDDEN = {
    "uz": "♻️ Javob yangilanishga yuborildi — tez orada shu yerda to'g'ri javob yoziladi.",
    "ru": "♻️ Ответ отправлен на обновление — скоро здесь будет правильный ответ.",
}


def _lang(q):
    return "ru" if q.lang == "ru" else "uz"


def hide(tg, q):
    """Xodim/admin xato degan javob guruhda ko'rsatilmaydi: bot xabari "yangilanishga yuborildi" ga almashadi (tugmalarsiz).
    Asl javob bazada (answer_text) — panelda va xodimlarga ko'rinadi. Qaytaradi: yashirildimi."""
    if tg is None or not q.bot_reply_id or q.answer_hidden or q.answered_by != "bot":
        return False
    try:
        tg.edit_text(q.chat_id, q.bot_reply_id, f"<i>{html.escape(HIDDEN[_lang(q)])}</i>")
    except Exception as e:  # noqa: BLE001 — xabar o'chirilgan / juda eski bo'lishi mumkin
        log.info("hide answer failed q=%s: %s", q.pk, e)
        return False
    Message.objects.filter(pk=q.pk).update(answer_hidden=True)
    q.answer_hidden = True
    return True


def restore(tg, q, settings=None):
    """Javob aslida to'g'ri edi — guruhda qayta ko'rsatiladi (asl matn, 👍/👎 tugmalari bilan)."""
    if tg is None or not q.answer_hidden or not q.bot_reply_id:
        return False
    from .engine import to_html
    from .models import Settings
    s = settings or Settings.load()
    body = to_html(q.answer_text or "") + (note_html(q.lang) if s.answer_test_note else "")
    try:
        tg.edit_text(q.chat_id, q.bot_reply_id, body, buttons=buttons(q, s))
    except Exception as e:  # noqa: BLE001
        log.info("restore answer failed q=%s: %s", q.pk, e)
        return False
    Message.objects.filter(pk=q.pk).update(answer_hidden=False)
    q.answer_hidden = False
    return True


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
        if q.answer_hidden and q.bot_reply_id:
            # yashirilgan javob o'rniga — o'sha xabar to'g'ri javobga aylanadi (guruhda ortiqcha xabar chiqmaydi)
            try:
                tg.edit_text(q.chat_id, q.bot_reply_id, body)
                sent_id = q.bot_reply_id
                upd["answer_hidden"] = False
            except Exception as e:  # noqa: BLE001 — tahrirlab bo'lmasa, yangi xabar bilan
                log.info("fix edit failed q=%s: %s", q.pk, e)
        if sent_id is None:
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

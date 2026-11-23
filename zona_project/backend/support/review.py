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
    """Bot javobi ostidagi tugmalar: 👍 / 👎 (savol egasi) va ⚠️ Xato javob (har kim: javob yashiriladi, tuzatishga tushadi)."""
    rows = []
    if settings.feedback_buttons:
        rows.append([{"text": "👍", "callback_data": f"fb:{q.id}:1"}, {"text": "👎", "callback_data": f"fb:{q.id}:-1"}])
    if settings.review_button:
        label = "⚠️ Неверный ответ" if q.lang == "ru" else "⚠️ Xato javob"
        rows.append([{"text": label, "callback_data": f"bad:{q.id}"}])
    return rows or None


def mark(q, value, by, note=""):
    """Holatni yozish. Xato belgisi kuchliroq: tekshirish (👍) xato belgisini yopmaydi; tuzatilgan javobga 👍 — o'zgarmaydi."""
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


def shown_id(q):
    """Guruhda hozir ko'rinib turgan oxirgi javob xabari: tuzatilgan javob (bo'lsa) yoki botning javobi."""
    return q.fixed_msg_id or q.bot_reply_id


def _fixed_body(q, text, s):
    head = "✏️ Уточнённый ответ:" if q.lang == "ru" else "✏️ Aniqlashtirilgan javob:"
    return f"<b>{head}</b>\n{html.escape(text)}" + (note_html(q.lang) if s.answer_test_note else "")


def hide(tg, q):
    """Xato degan javob guruhda ko'rsatilmaydi: xabar "yangilanishga yuborildi" ga almashadi (tugmalarsiz).
    Tuzatilgan javob ham qayta xato deb belgilanishi mumkin — u ham yashiriladi (oxirgi ko'rinib turgan javob).
    Asl javob bazada (answer_text / fixed_text) — panelda va xodimlarga ko'rinadi. Qaytaradi: yashirildimi."""
    # bot javob bergan (keyin xodim ham javob yozgan bo'lishi mumkin — answered_by xodim nomiga almashadi);
    # mutaxassisga uzatilgan savoldagi "qabul qilindi" xabari yashirilmaydi
    bot_answered = bool((q.answer_text or "").strip()) and (q.answered_by == "bot" or q.status in (Message.ANSWERED, Message.CLOSED))
    if tg is None or not shown_id(q) or q.answer_hidden or not (bot_answered or q.fixed_msg_id):
        return False
    try:
        tg.edit_text(q.chat_id, shown_id(q), f"<i>{html.escape(HIDDEN[_lang(q)])}</i>")
    except Exception as e:  # noqa: BLE001 — xabar o'chirilgan / juda eski bo'lishi mumkin
        log.info("hide answer failed q=%s: %s", q.pk, e)
        return False
    Message.objects.filter(pk=q.pk).update(answer_hidden=True)
    q.answer_hidden = True
    return True


def restore(tg, q, settings=None):
    """Javob aslida to'g'ri edi — guruhda qayta ko'rsatiladi (oxirgi javob: tuzatilgan yoki asl, tugmalari bilan)."""
    if tg is None or not q.answer_hidden or not shown_id(q):
        return False
    from .engine import to_html
    from .models import Settings
    s = settings or Settings.load()
    if q.fixed_msg_id and (q.fixed_text or "").strip():
        body = _fixed_body(q, q.fixed_text, s)
    else:
        body = to_html(q.answer_text or "") + (note_html(q.lang) if s.answer_test_note else "")
    try:
        tg.edit_text(q.chat_id, shown_id(q), body, buttons=buttons(q, s))
    except Exception as e:  # noqa: BLE001
        log.info("restore answer failed q=%s: %s", q.pk, e)
        return False
    Message.objects.filter(pk=q.pk).update(answer_hidden=False)
    q.answer_hidden = False
    return True


def fix(q, text, by, tg=None, send=True, learn_kb=False):
    """To'g'ri javob: saqlanadi; send — guruhdagi bot javobiga (bo'lmasa savolga) reply qilib bot yuboradi;
    learn_kb — bilim bazasiga (tasdiqlash navbatiga, muhim deb). Tuzatilgan javobni yana tuzatish mumkin (kimdir
    adashgan yoki vazifalar o'zgargan): o'sha xabar yangilanadi. Tuzatilgan javob ostida ham 👍/👎 va ⚠️ Xato javob."""
    from .models import Settings
    s = Settings.load()
    text = (text or "").strip()
    upd = {"fixed_text": text[:4000], "fixed_by": (by or "")[:150], "fixed_at": timezone.now(), "review": FIXED,
           "review_at": timezone.now()}
    if not q.review_by:
        upd["review_by"] = (by or "")[:150]
    sent_id = None
    if send and tg is not None and text:
        body = _fixed_body(q, text, s)
        target = shown_id(q) if (q.answer_hidden or q.fixed_msg_id) else None
        if target:
            # yashirilgan javob (yoki oldingi tuzatish) o'rniga — o'sha xabar yangi javobga aylanadi (ortiqcha xabar yo'q)
            try:
                tg.edit_text(q.chat_id, target, body, buttons=buttons(q, s))
                sent_id = target
                upd["answer_hidden"] = False
            except Exception as e:  # noqa: BLE001 — tahrirlab bo'lmasa, yangi xabar bilan
                if "not modified" in str(e):  # matn o'zgarmagan — xabar allaqachon shu javob
                    sent_id = target
                    upd["answer_hidden"] = False
                else:
                    log.info("fix edit failed q=%s: %s", q.pk, e)
        if sent_id is None:
            try:
                sent = tg.send(q.chat_id, body, reply_to=q.bot_reply_id or q.message_id, buttons=buttons(q, s))
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

"""Savol yopildimi — aniq holat: hal bo'ldi (yes) / hal bo'lmadi (no) / tasdiq so'raldi (asked) / noma'lum ("").

Manbalar:
- savol egasi "rahmat", "готово", "ishladi" yozdi -> hal bo'ldi (bot xabarga 👍 qo'yadi);
  "ishlamadi", "не помогло" (javobga reply) -> hal bo'lmadi, savol yana xodimga o'tadi;
- xodim javob berganidan (yoki vazifa ochilganidan) keyin bot savol egasidan "hal bo'ldimi?" deb so'raydi (tugmalar);
- bot javobi ostidagi 👍/👎;
- paneldan xodim belgilaydi.

Savol ochiq qolmasin:
- xodim savolga reaksiya (istalgan emoji) qo'ysa — savolni qabul qildi (qisman javob); keyin savol egasidan so'raladi;
- "hal bo'ldimi?" xabarida xodim uchun ham tugmalar: "✅ Javob berildi" (ikkala tomonda ham yopiladi) va "⏳ Jarayonda";
- savol egasi belgilamasa — javob bergan xodimdan so'raladi (@belgilab); "hal bo'lmadi" / "jarayonda" — vaqt o'tib
  qayta so'raladi va xodim eslatiladi; ko'p marta eslatilsa ham ochiq qolsa — admin chatiga.
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
YES, NO, ASKED, WORK = Message.YES, Message.NO, Message.ASKED, Message.WORK

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
AGAIN_WHO = {"uz": "❌ Tushunarli — {who} qayta ko'rib chiqadi. Hal bo'lguncha qayta so'rab turamiz.",
             "ru": "❌ Понятно — {who} посмотрит ещё раз. Будем спрашивать, пока вопрос не решится."}


def again_text(q):
    """«Hal bo'lmadi»: kim qayta ko'radi — xodim belgilanadi (bildirishnoma boradi), bo'lmasa umumiy matn."""
    staff = staff_mentions(q)
    if staff:
        return AGAIN_WHO[_lang(q)].format(who=", ".join(staff))
    return html.escape(AGAIN_TEXT[_lang(q)])


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


ADMIN = "panel: "  # resolved_by shu bilan boshlansa — admin/xodim paneldan belgilagan: YAKUNIY qaror


def is_final(q):
    """Admin paneldan belgilagan — savol egasining keyingi tugmasi/xabari holatni o'zgartirmaydi."""
    return (q.resolved_by or "").startswith(ADMIN) and q.resolution in (YES, NO)


def admin_mark(q, value, actor, tg=None):
    """Admin qarori (savol egasining javobini kutmasdan): holat yoziladi, guruhdagi "hal bo'ldimi?" xabari yopiladi."""
    mark(q, value, ADMIN + (actor or "admin"))
    if value in (YES, NO) and tg is not None and q.confirm_msg_id:
        close_prompt(tg, q, value)
    return q


def mark(q, value, by):
    """Holatni yozish. "Hal bo'lmadi" — javob berilgan savol yana xodim kutayotganlar qatoriga qaytadi."""
    now = timezone.now()
    upd = {"resolution": value, "resolved_at": now if value in (YES, NO) else None, "resolved_by": (by or "")[:150]}
    if value == NO and q.status in (Message.ANSWERED, Message.CLOSED):
        upd["status"] = Message.ESCALATED
    if value in (NO, WORK) and not (by or "").startswith(ADMIN):
        # hal bo'lmadi / jarayonda — vaqt o'tib qayta so'raladi va xodim eslatiladi (savol ochiq qolib ketmasin)
        after = Settings.load().reask_after
        upd["next_ask_at"] = now + timezone.timedelta(minutes=after) if after else None
        upd["remind_count"] = 0
    else:  # hal bo'ldi / admin qarori / tozalandi — eslatmalar to'xtaydi
        upd["next_ask_at"] = None
    Message.objects.filter(pk=q.pk).update(**upd)
    for k, v in upd.items():
        setattr(q, k, v)
    return q


def _lang(q):
    return "ru" if q.lang == "ru" else "uz"


def close_prompt(tg, q, value):
    """"Hal bo'ldimi?" xabari javobga aylanadi (tugmalarsiz)."""
    close_prompts(tg, q, DONE_TEXT[_lang(q)] if value == YES else again_text(q))


def close_prompts(tg, q, text):
    """Savol egasiga va xodimga yuborilgan "hal bo'ldimi?" xabarlari — ikkalasi ham yopiladi (tugmalarsiz)."""
    if tg is None:
        return
    for mid in sorted({q.confirm_msg_id, q.staff_msg_id} - {None}):
        try:
            tg.edit_text(q.chat_id, mid, text)
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


LABELS = {
    "uz": {"yes": "✅ Ha, hal bo'ldi", "no": "❌ Yo'q", "done": "✅ Javob berildi", "work": "⏳ Jarayonda"},
    "ru": {"yes": "✅ Да, решён", "no": "❌ Нет", "done": "✅ Ответ дан", "work": "⏳ В работе"},
}


def prompt_buttons(q):
    """1-qator — savol egasi uchun, 2-qator — xodim uchun ("javob berildi" ikkala tomonda ham yopadi; "jarayonda")."""
    L = LABELS[_lang(q)]
    return [[{"text": L["yes"], "callback_data": f"rs:{q.id}:1"}, {"text": L["no"], "callback_data": f"rs:{q.id}:0"}],
            [{"text": L["done"], "callback_data": f"rs:{q.id}:a"}, {"text": L["work"], "callback_data": f"rs:{q.id}:w"}]]


STAFF_DONE = {"uz": "✅ Savol yopildi — javob berildi ({who}).", "ru": "✅ Вопрос закрыт — ответ дан ({who})."}
WORK_TEXT = {"uz": "⏳ Jarayonda — {who} ko'rib chiqyapti.", "ru": "⏳ В работе — вопросом занимается {who}."}


def press(tg, q, user, val, msg_id=None, admin_chat_id=None):
    """"Hal bo'ldimi?" tugmasi. Savol egasi: ✅ / ❌. Xodim: ✅ Javob berildi — savol ikkala tomonda ham yopiladi;
    ⏳ Jarayonda — keyinroq eslatiladi. Qaytaradi: (javob matni, ogohlantirish oynasimi)."""
    asker = q.user_id is not None and q.user_id == user.id
    staff = user.is_staff and not asker
    if not asker and not staff:
        return "Faqat savol egasi yoki xodim belgilaydi", True
    if val == "w" and not staff:
        return "«⏳ Jarayonda» — xodimlar uchun", True
    if val == "0" and not asker:
        return "«❌ Yo'q» — savol egasi uchun. Xodim: «✅ Javob berildi» yoki «⏳ Jarayonda»", True
    if is_final(q):  # admin allaqachon yopgan — qaror o'zgarmaydi
        close_prompt(tg, q, q.resolution)
        if asker and val == "0" and q.resolution == YES:
            notify_unresolved(tg, q, admin_chat_id, "savol egasi: hal bo'lmadi (siz yopgansiz)")
        return "Rahmat! Mutaxassis allaqachon belgilagan.", False
    if asker:
        value = NO if val == "0" else YES
        mark(q, value, "savol egasi")
        close_prompt(tg, q, value)
        if value == NO:
            notify_unresolved(tg, q, admin_chat_id)
        return "Rahmat!", False
    who = user.staff_name()
    Message.objects.filter(pk=q.pk).update(handler=user)
    q.handler = user
    if val == "w":
        mark(q, WORK, f"xodim: {who}")
        if tg is not None and msg_id:
            try:  # tugmalar qoladi: keyin shu xabarda "javob berildi" bosiladi
                tg.edit_text(q.chat_id, msg_id, html.escape(WORK_TEXT[_lang(q)].format(who=who)), buttons=prompt_buttons(q))
            except Exception as e:  # noqa: BLE001
                log.info("work prompt edit: %s", e)
        return "Belgilandi: jarayonda. Keyinroq eslatamiz.", False
    mark(q, YES, f"xodim: {who}")
    close_prompts(tg, q, html.escape(STAFF_DONE[_lang(q)].format(who=who)))
    return "Savol yopildi — rahmat!", False


def target_of(bot, chat_id, message_id):
    """Guruhdagi xabar qaysi savolga tegishli: savolning o'zi, zanjirdagi xabar yoki botning javob / so'rov xabari."""
    if not message_id:
        return None
    m = Message.objects.filter(bot=bot, chat_id=chat_id, message_id=message_id).select_related("question").first()
    if m is not None:
        return m if m.kind == Message.QUESTION else m.question
    return (Message.objects.filter(bot=bot, chat_id=chat_id, kind=Message.QUESTION)
            .filter(Q(bot_reply_id=message_id) | Q(confirm_msg_id=message_id) | Q(staff_msg_id=message_id)
                    | Q(fixed_msg_id=message_id)).first())


def accept(q, user, now=None, react=False):
    """Xodim savolni qabul qildi (reaksiya qo'ydi yoki javob yozdi). Reaksiya — qisman javob: savol "javob berildi"
    holatiga o'tadi va odatdagidek savol egasidan "hal bo'ldimi?" so'raladi. "Hal bo'lmadi" / "jarayonda" bo'lgan
    savolda xodim harakati — savol egasidan qayta so'raladi."""
    if q is None or q.kind != Message.QUESTION or q.status == Message.IGNORED or is_final(q):
        return q
    now = now or timezone.now()
    upd = {"handler": user, "accepted_at": now}
    if react and q.status in (Message.ESCALATED, Message.DRAFTED) and not q.answered_by:
        upd.update(status=Message.ANSWERED, stage="react", answered_by=user.staff_name()[:150], answered_at=now)
    if q.resolution in (NO, WORK) or (q.resolution == ASKED and (q.stage == "handoff" or not q.confirm_msg_id)):
        upd.update(resolution="", next_ask_at=None, remind_count=0)
    Message.objects.filter(pk=q.pk).update(**upd)
    for k, v in upd.items():
        setattr(q, k, v)
    return q


def _member_mention(m):
    if m is None or m.is_team:
        return ""
    from .models import TgUser
    u = TgUser.objects.filter(member=m).exclude(username="").first() or TgUser.objects.filter(member=m).first()
    if u is not None:
        return _mention(u)
    return "@" + html.escape(m.telegram.lstrip("@")) if m.telegram else ""


def staff_mentions(q, limit=2):
    """Kimni eslatish: savolni qabul qilgan / javob bergan xodim; bo'lmasa — vazifa ijrochisi yoki toifa / javob mas'uli."""
    from .models import TgUser
    out = []

    def add(x):
        if x and x not in out:
            out.append(x)
    if q.handler_id and q.handler.is_staff:
        add(_mention(q.handler))
    uids = (Message.objects.filter(question=q, kind=Message.STAFF, user__isnull=False).order_by("-created_at")
            .values_list("user", flat=True)[:5])
    for u in TgUser.objects.filter(pk__in=list(uids)).select_related("member", "contact"):
        if u.is_staff:
            add(_mention(u))
    if not out:
        task = SupportTask.objects.filter(message=q).exclude(assignee="").first()
        if task is not None:
            add("@" + html.escape(task.assignee.lstrip("@")))
    if not out:
        from .engine import category_owner
        add(_member_mention(category_owner(q.category)))
    if not out and q.entry_id and q.entry.responsible_id:
        add(_member_mention(q.entry.responsible))
    return out[:limit]


def elapsed(q, now=None):
    """Savol tushganidan beri: "45 daqiqa", "2 soat 10 daqiqa", "3 kun 4 soat" (ru — mos ravishda)."""
    secs = max(0, int(((now or timezone.now()) - q.created_at).total_seconds()))
    d, h, m = secs // 86400, secs % 86400 // 3600, secs % 3600 // 60
    ru = q.lang == "ru"
    if d:
        return f"{d} дн. {h} ч" if ru else f"{d} kun {h} soat"
    if h:
        return f"{h} ч {m} мин" if ru else f"{h} soat {m} daqiqa"
    return f"{max(1, m)} мин" if ru else f"{max(1, m)} daqiqa"


def _topic(q):
    t = " ".join((q.problem or q.text or "").split())
    return html.escape(t[:80] + ("…" if len(t) > 80 else ""))


def _staff_prompt(q, staff):
    a = _mention(q.user) if q.user_id else ""
    ago = elapsed(q)
    if q.stage == "handoff":  # so'rov xodimga uzatilgan — ish bajarildimi, xodimning o'zidan
        if q.lang == "ru":
            return (f"{', '.join(staff)}, запрос {a} «{_topic(q)}» ждёт уже {ago}. Выполнено? "
                    f"Нажмите «✅ Ответ дан» или «⏳ В работе».")
        return (f"{', '.join(staff)}, {a} so'rovi «{_topic(q)}» {ago}dan beri kutyapti. Bajarildimi? "
                f"«✅ Javob berildi» yoki «⏳ Jarayonda» ni bosing.")
    if q.lang == "ru":
        return (f"{', '.join(staff)}, по вопросу {a} ответ дан? Вопросу уже {ago}, автор ещё не отметил — "
                f"нажмите «✅ Ответ дан» или «⏳ В работе».")
    return (f"{', '.join(staff)}, {a} savoli bo'yicha javob berildimi? Savol tushganiga {ago} bo'ldi, savol egasi hali "
            f"belgilamadi — «✅ Javob berildi» yoki «⏳ Jarayonda» ni bosing.")


def _reask_text(q, staff):
    base = prompt_text(q)
    if staff:
        base += (f"\n{', '.join(staff)} — напоминание: вопрос не решён уже {elapsed(q)}." if q.lang == "ru"
                 else f"\n{', '.join(staff)} — eslatma: savol {elapsed(q)}dan beri hal bo'lmagan.")
    return base


def _work_text(q, staff):
    if q.lang == "ru":
        return (f"{', '.join(staff)}, ⏳ вопрос в работе уже {elapsed(q)} («{_topic(q)}»): решён? "
                f"Если ответ дан — нажмите «✅ Ответ дан».")
    return (f"{', '.join(staff)}, ⏳ jarayondagi savol «{_topic(q)}» — {elapsed(q)} bo'ldi: hal bo'ldimi? "
            f"Javob berilgan bo'lsa — «✅ Javob berildi» ni bosing.")


def notify_open(tg, q, admin_chat_id, staff):
    if not admin_chat_id or tg is None:
        return
    link = q.group.message_link(q.message_id) if q.group_id else ""
    state = {ASKED: "savol egasi belgilamadi", NO: "hal bo'lmadi", WORK: "jarayonda"}.get(q.resolution, q.resolution)
    body = (f"⏰ <b>Savol ochiq qolmoqda</b> — {elapsed(q)} ({state}, {q.remind_count} marta eslatildi)"
            + (f" · {html.escape(q.group.title)}" if q.group_id else "")
            + f"\n<blockquote>{html.escape((q.problem or q.text or '')[:300])}</blockquote>"
            + (f"\n👤 {', '.join(staff)}" if staff else "\n👤 mas'ul topilmadi"))
    try:
        tg.send(admin_chat_id, body, buttons=[[{"text": "↗ Savolga o'tish", "url": link}]] if link else None)
    except Exception as e:  # noqa: BLE001
        log.info("open notify: %s", e)


def followups(tg, s=None, now=None, limit=5, bot_id=None):
    """Ishchi sikl chaqiradi: savol egasi belgilamagan — xodimdan so'raladi; "hal bo'lmadi" — savol egasidan qayta
    so'raladi (xodim hali harakat qilmagan bo'lsa — u ham eslatiladi); "jarayonda" — xodim eslatiladi.
    "Hal bo'lmadi" / "jarayonda" — yechim chiqquncha qayta-qayta so'raladi (ish vaqtida; remind_max dan keyin admin
    chatiga bir marta xabar va oraliq 2 baravar uzayadi). Savol egasi belgilamagan savol — remind_max dan keyin
    admin hal qiladi (eslatish to'xtaydi)."""
    s = s or Settings.load()
    if not s.confirm_resolution or tg is None:
        return 0
    now = now or timezone.now()
    if not (WORK_HOURS[0] <= now.astimezone(TZ).hour < WORK_HOURS[1]):
        return 0
    qs = (Message.objects.filter(kind=Message.QUESTION, source="live", resolution__in=[ASKED, NO, WORK],
                                 next_ask_at__isnull=False, next_ask_at__lte=now,
                                 created_at__gte=now - timezone.timedelta(days=PERSIST_DAYS))
          .select_related("user", "group", "handler__member", "handler__contact", "entry", "bot").order_by("next_ask_at"))
    if bot_id:
        qs = qs.filter(bot_id=bot_id)
    n = 0
    for q in qs[:limit]:
        stop = {"next_ask_at": None}
        if q.group_id is None or q.group.effective_mode() != MODE_LIVE or is_final(q) or q.user_id is None:
            Message.objects.filter(pk=q.pk).update(**stop)
            continue
        if q.entry_id and q.entry.auto_close:  # ma'lumot xabari — auto_close_due() yopadi, eslatilmaydi
            Message.objects.filter(pk=q.pk).update(**stop)
            continue
        staff = staff_mentions(q)
        cap = max(1, s.remind_max)
        # savol ochiq qolmasin: yechim chiqquncha eslatiladi (ish vaqtida, oraliq uzayib boradi); remind_max da va
        # keyin har ADMIN_EVERY eslatmada admin chatiga — necha vaqtdan beri ochiqligi bilan (hafta o'tib ketmasin)
        if q.remind_count >= cap and (q.remind_count - cap) % ADMIN_EVERY == 0:
            notify_open(tg, q, q.bot.admin_chat_id, staff)
        if q.resolution == NO:
            acted = bool(q.resolved_at) and Message.objects.filter(question=q, kind=Message.STAFF,
                                                                   created_at__gt=q.resolved_at).exists()
            text, to_staff = _reask_text(q, [] if acted else staff), False
        elif staff:
            text, to_staff = (_staff_prompt(q, staff) if q.resolution == ASKED else _work_text(q, staff)), True
        else:  # kimdan so'rashni bilmaymiz — admin hal qiladi
            notify_open(tg, q, q.bot.admin_chat_id, staff)
            Message.objects.filter(pk=q.pk).update(**stop)
            continue
        try:
            sent = tg.send(q.chat_id, text, reply_to=q.message_id, buttons=prompt_buttons(q))
        except Exception as e:  # noqa: BLE001
            log.info("followup failed q=%s: %s", q.pk, e)
            Message.objects.filter(pk=q.pk).update(**stop)  # guruhni qayta-qayta urinish bilan to'ldirmaymiz
            continue
        mid = (sent or {}).get("message_id")
        drop_prompts(tg, q, keep=mid)
        every = s.reask_after or 120
        if q.remind_count + 1 >= cap:  # ko'p eslatilgan — oraliq uzayadi (guruh to'lib ketmasin), lekin to'xtamaydi
            every = min(every * 2, 480)
        upd = {"remind_count": q.remind_count + 1, "next_ask_at": now + timezone.timedelta(minutes=every)}
        upd["staff_msg_id" if to_staff else "confirm_msg_id"] = mid
        upd["confirm_msg_id" if to_staff else "staff_msg_id"] = None  # o'chirildi
        Message.objects.filter(pk=q.pk).update(**upd)
        n += 1
    return n


PERSIST_DAYS = 14  # rad etilgan savol shuncha kungacha qayta so'raladi (undan eskisi — admin ro'yxatida)
ADMIN_EVERY = 6  # remind_max dan keyin har 6-eslatmada admin chatiga yana xabar
TASK_WAIT_HOURS = 2  # vazifa ochilgan, guruhda xodim javobi yo'q — shuncha vaqtdan keyin so'raladi
WORK_HOURS = (9, 20)  # kechasi odamlarni bezovta qilmaymiz (Toshkent vaqti)
ASK_WINDOW_HOURS = 3  # xodim javobidan keyin shu vaqt ichida so'raladi (keyin — kech, so'ralmaydi)


def drop_prompts(tg, q, keep=None):
    """Savol bo'yicha botning oldingi "hal bo'ldimi?" xabarlari o'chiriladi (guruhda ochiq so'rov qolib ketmasin).
    O'chirib bo'lmasa (48 soatdan eski) — tugmalari olib tashlanadi."""
    if tg is None:
        return
    for mid in sorted({q.confirm_msg_id, q.staff_msg_id} - {None, keep}):
        try:
            tg.delete(q.chat_id, mid)
        except Exception as e:  # noqa: BLE001
            log.info("drop prompt q=%s: %s", q.pk, e)
            try:
                tg.edit_buttons(q.chat_id, mid)
            except Exception:  # noqa: BLE001
                pass


AUTO = "avto: ma'lumot xabari"


def auto_close_due(tg, now=None, limit=20, bot_id=None):
    """Ma'lumot xabarlari (yozuvda auto_close > 0, masalan, nuqta moderatsiyaga yuborildi): ko'rsatilgan daqiqadan
    keyin savol "hal bo'ldi" deb yopiladi, guruhdagi so'rov xabari (bo'lsa) o'chiriladi. Qaytaradi: nechta yopildi."""
    now = now or timezone.now()
    qs = (Message.objects.filter(kind=Message.QUESTION, entry__auto_close__gt=0, resolution__in=["", ASKED],
                                 created_at__gte=now - timezone.timedelta(days=3))
          .exclude(status=Message.IGNORED).select_related("entry"))
    if bot_id:
        qs = qs.filter(bot_id=bot_id)
    n = 0
    for q in qs.order_by("created_at")[:200]:
        if q.created_at > now - timezone.timedelta(minutes=q.entry.auto_close) or is_final(q):
            continue
        drop_prompts(tg, q)
        mark(q, YES, AUTO)
        Message.objects.filter(pk=q.pk).update(confirm_msg_id=None, staff_msg_id=None)
        n += 1
        if n >= limit:
            break
    return n


def staff_users(member):
    """Mas'ul (Member) ning Telegram foydalanuvchilari: o'zi, username bo'yicha, jamoa bo'lsa — a'zolari."""
    from .models import TgUser
    if member is None:
        return TgUser.objects.none()
    q = Q(member=member) | Q(contact__member=member)
    if member.telegram:
        q |= Q(username__iexact=member.telegram.lstrip("@"))
    return TgUser.objects.filter(q)


def queue_of(member, now=None):
    """Mas'ulning hozirgi yuklamasi: ochiq so'rovlari soni va odatdagi javob vaqti (oxirgi 14 kun, median, soniya)."""
    from statistics import median
    now = now or timezone.now()
    users = list(staff_users(member).values_list("pk", flat=True))
    since = now - timezone.timedelta(days=PERSIST_DAYS)
    open_q = (Message.objects.filter(kind=Message.QUESTION, source="live", created_at__gte=since)
              .filter(Q(handler_id__in=users) | Q(entry__responsible=member))
              .filter(Q(resolution__in=[ASKED, NO, WORK]) | Q(status=Message.ESCALATED, resolution=""))
              .exclude(status=Message.IGNORED).count())
    times = [max(0.0, (at - qat).total_seconds()) for at, qat in
             Message.objects.filter(kind=Message.STAFF, user_id__in=users, created_at__gte=since, question__isnull=False)
             .values_list("created_at", "question__created_at")[:500]]
    return open_q, (median(times) if times else None)


def _eta(secs, lang):
    m = max(10, min(240, int(round((secs or 1800) / 60.0 / 5)) * 5 or 10))
    if m >= 60:
        h = round(m / 60 * 2) / 2
        return (f"≈ {h:g} ч" if lang == "ru" else f"≈ {h:g} soat")
    return f"≈ {m} мин" if lang == "ru" else f"≈ {m} daqiqa"


def handoff_text(q, member, now=None, ask_first=""):
    """Agent so'rovni mas'ulning o'ziga yo'llagan ("aksiyani yoqing @Said"): "Saidabror yoqadi" deb takrorlamasdan —
    so'rov yetkazildi, uning hozirgi yuklamasi va taxminiy vaqt; bajarilgach "hal bo'ldimi?" so'ralishi."""
    now = now or timezone.now()
    ru = q.lang == "ru"
    n, med = queue_of(member, now)
    hour = now.astimezone(TZ).hour
    who = f"<b>{html.escape(member.name)}</b>"
    tgs = [t for t in [member.telegram.lstrip("@")] if t] if member.telegram else []
    tag = (" (" + " ".join("@" + html.escape(t) for t in tgs) + ")") if tgs else ""
    head = (f"✅ Запрос передан: {who}{tag}." if ru else f"✅ So'rovingiz {who}{tag}ga yetkazildi.")
    eta_secs = (med or 1800) * (1 + max(0, n - 1) / 3)
    if not (WORK_HOURS[0] <= hour < WORK_HOURS[1]):
        load = ("🌙 Сейчас нерабочее время — ответ будет в рабочее время (с 9:00)." if ru
                else "🌙 Hozir ish vaqti emas — ish vaqtida (9:00 dan) javob beriladi.")
    elif n >= 3:
        load = (f"⏳ Сейчас у него много запросов ({n} в очереди) — ответ {_eta(eta_secs, 'ru')}, немного позже обычного."
                if ru else f"⏳ Hozir unda so'rovlar ko'p ({n} ta navbatda) — {_eta(eta_secs, 'uz')} ichida, odatdagidan "
                           f"biroz kechroq javob beradi.")
    else:
        load = (f"⏱ Обычно отвечает {_eta(eta_secs, 'ru')}." if ru
                else f"⏱ Odatda {_eta(eta_secs, 'uz')} ichida javob beradi.")
    tail = ("Когда будет готово, спросим вас «вопрос решён?»." if ru
            else "Bajarilgach, sizdan «hal bo'ldimi?» deb so'raymiz.")
    need = ""
    if ask_first.strip():
        need = ("\n📎 Если ещё не написали: " if ru else "\n📎 Agar yozmagan bo'lsangiz: ") + html.escape(ask_first.strip()[:200])
    return f"{head}\n{load}{need}\n{tail}"


def track(q, handler=None, now=None, s=None):
    """Savol nazoratga olinadi: ask_staff_after daqiqadan keyin xodimdan "bajarildimi?" so'raladi, yechim chiqquncha
    eslatiladi (followups). Xodim javob yozsa / bajarsa — savol egasidan "hal bo'ldimi?" so'raladi."""
    s = s or Settings.load()
    if not s.confirm_resolution or q.resolution or q.user_id is None or q.user.is_staff:
        return q
    if q.entry_id and q.entry.auto_close:
        return q
    now = now or timezone.now()
    upd = {"resolution": ASKED, "next_ask_at": now + timezone.timedelta(minutes=s.ask_staff_after or 60), "remind_count": 0}
    if handler is not None:
        upd["handler"] = handler
    Message.objects.filter(pk=q.pk).update(**upd)
    for k, v in upd.items():
        setattr(q, k, v)
    return q


def due(now=None, s=None):
    """Tasdiq so'raladigan savollar: xodim javob bergan (confirm_after daqiqa o'tgan) yoki vazifa ochilgan
    (TASK_WAIT_HOURS o'tgan), holati noma'lum, savol egasi xodim emas, oxirgi 2 kun ichida."""
    s = s or Settings.load()
    now = now or timezone.now()
    base = (Message.objects.filter(kind=Message.QUESTION, source="live", resolution="", user__isnull=False,
                                   user__member__isnull=True, user__contact__isnull=True,
                                   created_at__gte=now - timezone.timedelta(days=2))
            .exclude(stage="dup").exclude(status__in=[Message.IGNORED, Message.NEW])
            .exclude(entry__auto_close__gt=0))  # ma'lumot xabari — so'ralmaydi, avtomatik yopiladi
    # eski savollar haqida so'ralmaydi (kecha javob berilgan savolga bugun "hal bo'ldimi?" — g'alati)
    staff = base.filter(status=Message.ANSWERED, answered_at__lte=now - timezone.timedelta(minutes=s.confirm_after or 0),
                        answered_at__gte=now - timezone.timedelta(hours=ASK_WINDOW_HOURS)).exclude(answered_by="bot")
    task_ids = SupportTask.objects.filter(created_at__lte=now - timezone.timedelta(hours=TASK_WAIT_HOURS),
                                          created_at__gte=now - timezone.timedelta(hours=24)).values_list("message_id", flat=True)
    tasked = base.filter(pk__in=task_ids)
    # xodim savolni qabul qildi (reaksiya qo'ydi, javob yozdi, "hal bo'lmadi" dan keyin harakat qildi) — savol egasidan
    accepted = base.filter(accepted_at__lte=now - timezone.timedelta(minutes=s.confirm_after or 0),
                           accepted_at__gte=now - timezone.timedelta(hours=ASK_WINDOW_HOURS))
    return (staff | tasked | accepted).distinct().select_related("user", "group").order_by("created_at")


def ask_pending(tg, s=None, now=None, limit=5, bot_id=None):
    """Ishchi sikl chaqiradi: tasdiq so'rash vaqti kelgan savollarga "hal bo'ldimi?" (savolga reply, tugmalar bilan).
    Savol egasi ask_staff_after daqiqada belgilamasa — followups() xodimdan so'raydi."""
    s = s or Settings.load()
    if not s.confirm_resolution or tg is None:
        return 0
    now = now or timezone.now()
    hour = now.astimezone(TZ).hour
    if not (WORK_HOURS[0] <= hour < WORK_HOURS[1]):
        return 0
    n = 0
    rows = due(now, s)
    if bot_id:
        rows = rows.filter(bot_id=bot_id)
    for q in rows[:limit]:
        if q.group_id and q.group.effective_mode() != MODE_LIVE:
            continue
        try:
            sent = tg.send(q.chat_id, prompt_text(q), reply_to=q.message_id, buttons=prompt_buttons(q))
        except Exception as e:  # noqa: BLE001
            log.info("confirm ask failed q=%s: %s", q.pk, e)
            Message.objects.filter(pk=q.pk).update(resolution=ASKED)  # qayta-qayta urinib guruhni to'ldirmaymiz
            continue
        later = now + timezone.timedelta(minutes=s.ask_staff_after) if s.ask_staff_after else None
        Message.objects.filter(pk=q.pk).update(resolution=ASKED, confirm_msg_id=(sent or {}).get("message_id"),
                                               next_ask_at=later, remind_count=0)
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
        from .ocr import main_message
        ocr = main_message(q.ocr_text or "")  # skrinshotdagi xato/holat xabari (holat qatori va menyusiz)
        body = ("Rasmdagi xabar: " + ocr) if ocr else ("Rasmli savol" if q.photo_file_id else "")
    return body[:297] + "…" if len(body) > 300 else body

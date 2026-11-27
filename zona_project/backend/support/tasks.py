"""PRBC vazifalari: haqiqiy savollar bo'yicha vazifa ochilishini ta'minlash.

Ikki rejim (Settings.task_mode):
- remind (standart, tavsiya): bot O'ZI mas'ul xodimga eslatadi — shaxsiy xabarda savol tafsiloti, havola va tayyor
  "/vazifa ..." buyrug'i; guruhda esa qisqa "@mas'ul, vazifa oching" eslatma. Vazifani xodim guruhda savolga reply qilib
  "/vazifa Sarlavha" yozib ochadi (PRBC boti guruhda ishlaydi). Hech kimning akkaunti ishlatilmaydi.
- account: ulangan Telegram akkaunt PRBC botiga "/vazifa @ijrochi matn" yuboradi (ban xavfi bor; PRBC boti bu buyruqni
  faqat guruhda qabul qiladi — shuning uchun tavsiya etilmaydi).

Qachon: jonli guruhdagi haqiqiy savol (aniqlashtirish/qo'shimcha ma'lumot/takror emas) va
  - bilim bazasidagi javob turida "vazifa yaratiladi" belgilangan, yoki
  - savol odamga uzatilgan / mas'ulga yo'naltirilgan va mas'ul tanlangan bo'limlarda (IT) yoki tanlangan xodim.
Bitta mavzuga bitta vazifa: shu odam 24 soat ichida shu mavzuda (shu javob turi yoki o'xshash matn) savol bergan va
vazifa yaratilgan bo'lsa — yangi savol mavjud vazifaga bog'lanadi.

Ban xavfini kamaytirish: vazifalar navbat bilan, orasida tanaffus (task_gap) va kunlik limit (task_daily_limit).
"""
import asyncio
import logging
import os
import re
import time

from django.utils import timezone

from zona.crypto import decrypt
from zona.models import Member

from .agent import lines as agent_lines
from .models import Entry, Media, Message, Settings, SupportTask

log = logging.getLogger("support")
DEDUPE_HOURS = 24


# ====================================================================== qaror: vazifa kerakmi
def targets(s):
    deps = set(s.task_departments or [])
    mems = set(s.task_members or [])
    return deps, mems


def _member_matches(m, deps, mems):
    return bool(m) and m.level != "EXT" and (m.id in mems or (m.department_id in deps))


def _tg_of(m, s):
    """Ijrochi: yakka xodim — o'zi; jamoa — sozlamadagi standart ijrochi yoki jamoaning birinchi a'zosi."""
    if not m:
        return s.task_default_assignee.lstrip("@")
    if not m.is_team and m.telegram:
        return m.telegram.lstrip("@")
    if s.task_default_assignee:
        return s.task_default_assignee.lstrip("@")
    c = m.contacts.exclude(telegram="").select_related("operator").order_by("order", "id").first()
    if c is not None and c.operator_id and c.operator.telegram:
        return c.operator.telegram.lstrip("@")  # umumiy akkaunt — uning asosiy operatori
    if c is not None:
        return c.telegram.lstrip("@")
    x = Member.objects.filter(member_of=m).exclude(telegram="").order_by("order", "id").first()
    return x.telegram.lstrip("@") if x else ""


CMD_RE = re.compile(r"^/\w+(@\w+)?\s*(@\w+\s*)*")
CODE_RE = re.compile(r"\bUZ-\d{6,}\b")
ORDER_RE = re.compile(r"(?:№|N[o°]?\s?|zakaz\s*|заказ[:\s]*№?\s*)(\d{5,})", re.I)


def operator_tg(username):
    """@IT_StarGroup kabi umumiy akkaunt -> asosiy operatorining Telegram'i (Xusniddin); boshqalar — o'zgarmaydi."""
    u = (username or "").lstrip("@")
    if not u:
        return u
    from zona.models import TeamContact
    c = TeamContact.objects.filter(telegram__iexact=u, operator__isnull=False).select_related("operator").first()
    return c.operator.telegram.lstrip("@") if c is not None and c.operator.telegram else u


def is_external(d):
    """Savolning asosiy mas'uli tashqi jamoami (level EXT: Pro-target) — toifa mas'uli yoki tanilgan yozuvning mas'uli."""
    if getattr(d, "owner", False) and d.responsible:
        return d.responsible[0].get("level") == "EXT"
    e = d.entry
    return bool(e is not None and e.responsible_id and e.responsible.level == "EXT")


def decide_task(q, d, s=None):
    """(kerakmi, ijrochi, sabab). d — engine.Decision."""
    s = s or Settings.load()
    if not s.tasks_enabled or q.kind != Message.QUESTION:
        return False, "", ""
    if q.group_id and (not q.group.creates_tasks or q.group.redirect_to_id or not q.group.is_active):
        # guruh sozlamasi: bu guruhdan vazifa ochilmaydi (VAZIFALAR — test guruhi), eski (yangi guruhga yo'naltirilgan)
        # yoki nofaol guruh
        return False, "", ""
    e = d.entry
    if is_external(d):
        # tashqi jamoa (Pro-target, EXT) mas'ul — PRBC vazifasi umuman ochilmaydi va boshqa xodimga ham tushirilmaydi
        # (egasining qoidasi, 2026-11-27)
        return False, "", "ext"
    if e is not None and e.creates_task:
        m = e.responsible if e.responsible_id else None
        if getattr(d, "owner", False) and d.responsible:  # toifa mas'uli (masalan, aksiya — operator) ustun
            m = Member.objects.filter(pk=d.responsible[0].get("id")).prefetch_related("contacts").first() or m
            return True, _tg_of(m, s), "entry"
        return True, (e.task_assignee.lstrip("@") or _tg_of(m, s)), "entry"
    deps, mems = targets(s)
    every = bool(getattr(s, "task_all_escalated", False))
    if not (deps or mems or every):
        return False, "", ""
    if not (d.needs_human or d.stage == "rule"):
        return False, "", ""
    from .engine import substantive
    if e is None and not substantive(CMD_RE.sub("", q.text or "")):
        return False, "", ""  # aniq savol ham, tanilgan holat ham yo'q (salomlashuv, suhbat) — vazifa ochilmaydi
    ids = [r.get("id") for r in d.responsible or [] if r.get("id")]
    if e is not None and e.responsible_id and not getattr(d, "owner", False):
        ids.insert(0, e.responsible_id)
    found = list(Member.objects.filter(id__in=ids).prefetch_related("contacts"))
    found.sort(key=lambda m: ids.index(m.id))
    for m in found:
        if _member_matches(m, deps, mems):
            return True, _tg_of(m, s), f"responsible:{m.name}"[:200]
    if every and d.needs_human:
        # odamga uzatilgan har savol — vazifa: mas'ul (IT bo'limida bo'lmasa ham) yoki standart ijrochi
        if found and found[0].level == "EXT":
            return False, "", "ext"  # birinchi mas'ul tashqi jamoa — boshqa xodimga tushirilmaydi
        m = next((x for x in found if x.level != "EXT"), None)
        if m is None:
            return False, "", "no-owner"  # mas'ul topilmadi — ijrochisiz vazifa ochilmaydi, savol odam navbatida
        return True, _tg_of(m, s), f"escalated:{m.name}"[:200]
    return False, "", ""


STIR_RE = re.compile(r"(?:stir|инн|inn|стир)\s*[:№-]?\s*(\d{9})\b", re.I)
PINFL_RE = re.compile(r"\b(\d{14})\b")


def case_keys(text):
    """Holat (case) obyekti: nuqta/klient kodi (UZ-…), zakaz raqami, STIR, JShShIR. Bitta holat = bitta agent + bitta
    obyekt + bitta muammo turi (egasi, 2026-11-27): 10 ta klientga aksiya — 10 ta vazifa."""
    t = text or ""
    keys = {m.group(0).upper().strip() for m in re.finditer(r"\bUZ-\d{6,}\b", t, re.I)}
    keys |= {"zakaz:" + m.group(1) for m in ORDER_RE.finditer(t)}
    keys |= {"stir:" + m.group(1) for m in STIR_RE.finditer(t)}
    keys |= {"pinfl:" + m.group(1) for m in PINFL_RE.finditer(t)}
    return keys


def _keys_of(m):
    if m is None:
        return set()
    ks = case_keys(f"{m.text or ''} {m.ocr_text or ''}")
    for i in Message.objects.filter(question=m, kind=Message.INFO).values_list("text", "ocr_text")[:10]:
        ks |= case_keys(" ".join(x or "" for x in i))
    return ks


def _same_topic(q, d):
    """Shu odamning 24 soat ichidagi SHU HOLATI bo'yicha vazifasi (mavjud vazifaga izoh) yoki None (yangi vazifa).

    - Ikkalasida obyekt kaliti (UZ-kod, zakaz, STIR) bor: kesishsa — bitta holat, farq qilsa — ALOHIDA vazifa.
    - Yangi xabar mazmunsiz davom («тоже самое», «nma boldi», «shu») — oxirgi ochiq vazifaga izoh.
    - Kalit yo'q: avvalgidek — shu yozuv (standart holat) yoki matn o'xshashligi ≥60."""
    from .engine import learnable_question, similarity
    since = timezone.now() - timezone.timedelta(hours=DEDUPE_HOURS)
    qs = SupportTask.objects.filter(created_at__gte=since, message__user=q.user, message__chat_id=q.chat_id) \
        .exclude(status=SupportTask.FAILED).select_related("message").order_by("-created_at")
    mine = _keys_of(q)
    text = CMD_RE.sub("", q.text or "").strip()
    for t in qs[:20]:
        theirs = _keys_of(t.message)
        if mine and theirs:
            if mine & theirs:
                return t
            continue  # boshqa klient / zakaz — alohida holat
        if not mine and not q.photo_file_id and not learnable_question(text):
            return t  # mazmunsiz davom xabari — oxirgi vazifaga izoh
        if mine and not theirs:
            continue  # yangi xabarda aniq obyekt bor, eskisida yo'q — alohida (AI aniqlashtiradi: 0e)
        if d.entry is not None and t.entry_id == d.entry.pk:
            return t
        if t.message and q.text and t.message.text and similarity(q.text, t.message.text) >= 60:
            return t
    return None


def build_text(q, title, assignee):
    """PRBC botiga yuboriladigan matn: /vazifa @ijrochi sarlavha + tafsilot + havola."""
    who = q.user.name if q.user else ""
    if q.user and q.user.username:
        who += f" (@{q.user.username})"
    lines = [f"/vazifa @{assignee} {title}".strip(), ""]
    body = (q.text or "").strip() or (q.ocr_text or "").strip()[:300]
    if body:
        lines.append(f"Savol: {body[:1500]}")
    lines.append(f"Kimdan: {who}" + (f" · {q.group.title}" if q.group_id else ""))
    card = agent_lines(q.user)
    if card:  # agent kodi, loyiha, hudud, supervayzer, telefon — ijrochi qayta so'ramasin
        lines += ["", "Agent ma'lumotlari:", *(f"• {x}" for x in card), ""]
    link = q.group.message_link(q.message_id) if q.group_id else ""
    if link:
        lines.append(f"Havola: {link}")
    if q.answer_text and q.status == Message.ANSWERED:
        lines.append(f"Bot javobi: {q.answer_text[:1500]}")
    return "\n".join(lines)[:3900], link


def maybe_create(q, d, tg=None):
    """Javobdan keyin chaqiriladi (jonli rejim). remind — darhol eslatadi (tg — bot klienti); account — navbatga qo'yadi."""
    try:
        from .engine import learnable_question
        if q.user_id and not q.photo_file_id and not learnable_question(CMD_RE.sub("", q.text or "")):
            # «Тут тоже самое», «nma boldi» — yangi holat emas: shu odamning ochiq vazifasiga izoh bo'ladi
            prev = _same_topic(q, d)
            if prev:
                SupportTask.objects.filter(pk=prev.pk).update(duplicates=[*prev.duplicates, q.pk][-50:])
                return prev
        need, assignee, reason = decide_task(q, d)
        if not need:
            return None
        assignee = operator_tg(assignee)  # umumiy akkaunt (@IT_StarGroup) — ijrochi uning asosiy operatori
        if not assignee and Settings.load().task_mode != "api":
            return None
        if hasattr(q, "task"):
            return q.task
        prev = _same_topic(q, d)
        if prev:
            SupportTask.objects.filter(pk=prev.pk).update(duplicates=[*prev.duplicates, q.pk][-50:])
            return prev
        title = (d.entry.title if d.entry is not None else (q.text or q.ocr_text or "Savol").strip().splitlines()[0])[:120]
        s = Settings.load()
        if s.task_mode == "api":  # PRBC API orqali: navbatga yoziladi, prbc_worker bir necha soniyada yaratadi
            text, link = build_text(q, title, assignee)
            media = list(Media.objects.filter(message=q).exclude(path="").values_list("id", flat=True)[:10])
            return SupportTask.objects.create(message=q, entry=d.entry, assignee=assignee, title=title, text=text,
                                              link=link, media_ids=media, reason=reason)
        if s.task_mode == "command":
            return post_command(q, d, title, assignee, reason, tg, s)
        if s.task_mode != "account":
            return remind(q, d, title, assignee, reason, tg, s)
        if not assignee:
            return SupportTask.objects.create(message=q, entry=d.entry, title=title, reason=reason, status=SupportTask.SKIPPED,
                                              error="Ijrochi topilmadi: Sozlamalar → PRBC vazifalari → standart ijrochini kiriting.")
        text, link = build_text(q, title, assignee)
        media = list(Media.objects.filter(message=q).exclude(path="").values_list("id", flat=True)[:10])
        return SupportTask.objects.create(message=q, entry=d.entry, assignee=assignee, title=title, text=text, link=link,
                                          media_ids=media, reason=reason)
    except Exception:  # noqa: BLE001 — vazifa xatosi javob berishni to'xtatmasin
        log.exception("task create failed for %s", q.pk)
        return None


# ====================================================================== buyruq: bot guruhda /vazifa@prbc_bot yozadi
TASK_OK = re.compile(r"(TASK-\d+|vazifa\w* yaratildi|задача .*создан)", re.I)


GREET_RE = re.compile(
    r"^\W*((assalomu?|assalom|asalom|ассало\w*|асало\w*|salom|салом)\W*(alay?kum|alekum|алей?кум|алайкум|алейкум)?|"
    r"(va\s*)?alay?kum\s*assalom|добр(ый|ое|ого)\s+(день|утро|вечер|дня)|здравствуй\w*|привет\w*|hayrli\s+(kun|tong)|"
    r"xayrli\s+(kun|tong)|хайрли\s+(кун|тонг))[\s,.!)]*(\w+\s*(aka|opa|ака|опа)[\s,.!]*)?", re.I)


def strip_greeting(text):
    """"Ассалом алейкум. Акция не работает" -> "Акция не работает" (vazifa sarlavhasida salomlashuv kerak emas)."""
    prev = None
    text = text or ""
    while prev != text:
        prev = text
        text = GREET_RE.sub("", text, count=1).strip()
    return text


def problem_text(q, title, entry=None):
    """Vazifa sarlavhasi: aniq yozilgan savol matni; bo'lmasa — tanilgan holat nomi (xom OCR emas). Oxirida — kimdan,
    rasmda topilgan UZ-kod va zakaz raqami (ijrochi tez topishi uchun)."""
    from .engine import learnable_question
    text = strip_greeting(" ".join(CMD_RE.sub("", (q.text or "").strip()).split()))
    if not learnable_question(text):
        # «Добрый день», «Кушиб беринг», «Nma boldi» — sarlavha emas: savol egasining keyingi mazmunli xabari yoki
        # skrinshotdagi asosiy xato
        nxt = next((strip_greeting(" ".join((i.text or "").split())) for i in
                    Message.objects.filter(question=q, kind=Message.INFO).order_by("id")[:5]
                    if learnable_question(i.text or "")), "") if q.pk else ""
        if nxt:
            text = nxt
        elif entry is not None:
            text = ""  # tanilgan holat nomi (pastda) — xom OCR'dan ishonchli
        else:
            # skrinshotdagi qizil xato qatori (ocr.red_text) — asosiy xato; xom OCR sarlavha bo'lmaydi
            main = " ".join((q.alert_text or "").split())
            text = main if learnable_question(main) else ""
    if text and learnable_question(text):
        body = text
    elif entry is not None:
        body = entry.title
    else:
        body = text or ("Rasmli savol" if q.photo_file_id else title)
    if len(body) > 160:
        body = body[:160].rsplit(" ", 1)[0] + "…"
    extra = []
    src = f"{q.text or ''} {q.ocr_text or ''}"
    code = CODE_RE.search(src)
    if code:
        extra.append(code.group(0))
    order = ORDER_RE.search(src)
    if order:
        extra.append(f"zakaz №{order.group(1)}")
    if q.user:
        extra.append(q.user.name[:40])
    return body + (f" ({', '.join(extra)})" if extra else "")


def post_command(q, d, title, assignee, reason, tg, s):
    """Savolga reply qilib "/vazifa@prbc_bot @ijrochi muammo" — PRBC vazifani yaratadi va savoldagi fayllarni o'zi oladi.
    PRBC javobi ("TASK-123 yaratildi") botga reply bo'lib keladi va capture_reply() orqali shu yerga yoziladi."""
    if assignee and tg is not None and prbc_silent():
        # PRBC bot buyruqlarimizga javob bermayapti (Bot-to-Bot o'chiq): ochiq guruhga buyruq yozilmaydi —
        # ko'rsatma faqat xodimga (shaxsiy xabar yoki admin chati)
        return remind(q, d, title, assignee, reason, tg, s, group=False)
    bot = (s.task_bot or "prbc_bot").lstrip("@")
    link = q.group.message_link(q.message_id) if q.group_id else ""
    text = f"/vazifa@{bot} @{assignee} {problem_text(q, title, d.entry)}" if assignee else ""
    t = SupportTask.objects.create(message=q, entry=d.entry, assignee=assignee, title=title, link=link, reason=reason,
                                   text=text, status=SupportTask.QUEUED)
    if not assignee or tg is None:
        t.status, t.error = SupportTask.SKIPPED, ("" if assignee else "Ijrochi topilmadi (Sozlamalar → PRBC vazifalari).")
        t.save(update_fields=["status", "error"])
        return t
    try:
        sent = tg.send(q.chat_id, text, reply_to=q.message_id, html=False)
        t.post_id = (sent or {}).get("message_id")
        t.status, t.sent_at, t.reply = SupportTask.SENT, timezone.now(), "PRBC javobi kutilmoqda…"
    except Exception as e:  # noqa: BLE001
        t.status, t.error = SupportTask.FAILED, f"{type(e).__name__}: {e}"[:500]
    t.save()
    return t


def prbc_silent(n=3):
    """Oxirgi n ta buyrug'imizga PRBC boti javob bermagan (va undan keyin birorta vazifa yaratilmagan) bo'lsa — True."""
    last = list(SupportTask.objects.filter(post_id__isnull=False).exclude(reply="PRBC javobi kutilmoqda…")
                .order_by("-id").values_list("reply", "created_at")[:n])
    if len(last) < n or any(TASK_OK.search(r or "") for r, _at in last):
        return False
    # sutkada bir marta baribir sinab ko'riladi (Bot-to-Bot yoqilsa — o'zi tiklanadi)
    return last[0][1] >= timezone.now() - timezone.timedelta(hours=24)


def check_unanswered(tg, wait=120):
    """PRBC bot buyrug'imizga javob bermasa (bot-to-bot o'chiq yoki botdan buyruq qabul qilmaydi) — guruhdagi buyruq
    o'chiriladi (savol beruvchilar uchun tushunarsiz xabar qolmaydi), tayyor buyruqli ko'rsatma esa mas'ulning o'ziga
    boradi: shaxsiy xabar, bo'lmasa admin chati. Ikkalasi ham bo'lmasa — guruhdagi xabar ko'rsatmaga aylanadi."""
    since = timezone.now() - timezone.timedelta(seconds=wait)
    for t in SupportTask.objects.filter(status=SupportTask.SENT, post_id__isnull=False, reply="PRBC javobi kutilmoqda…",
                                        sent_at__lte=since).select_related("message")[:5]:
        q = t.message
        if q is None:
            continue
        cmd = CMD_RE.sub("", t.text or "").strip() or t.title
        where = _notify_staff(tg, q, dm_text(q, cmd, t.assignee, t.link), t.assignee, t.link)
        if where:
            tg.delete(q.chat_id, t.post_id)
            t.reply = f"PRBC bot buyrug'iga javob bermadi — buyruq guruhdan o'chirildi, ko'rsatma: {where}"
        else:
            html_text = (f"🗂 <b>@{_esc(t.assignee)}</b>, bu savol bo'yicha vazifa oching — savolga <i>reply</i> qilib "
                         f"yuboring:\n<code>/vazifa {_esc(cmd)}</code>")
            try:
                tg.edit_text(q.chat_id, t.post_id, html_text)
                t.reply = "PRBC bot buyrug'iga javob bermadi — xabar mas'ulga ko'rsatmaga aylantirildi"
            except Exception as e:  # noqa: BLE001
                t.reply = f"PRBC javob bermadi; xabarni o'zgartirib bo'lmadi: {str(e)[:120]}"
        t.status = SupportTask.REMINDED
        t.error = "PRBC javob bermadi: @BotFather → @savolbopbot → Bot-to-Bot Communication Mode yoqilganini tekshiring"
        t.save(update_fields=["reply", "status", "error"])


def capture_reply(msg):
    """Guruhdagi bot xabari: PRBC botining bizning /vazifa xabarimizga javobi bo'lsa — natijani vazifaga yozamiz."""
    s = Settings.load()
    sender = (msg.get("from") or {}).get("username", "")
    if not sender or sender.lower() != (s.task_bot or "prbc_bot").lstrip("@").lower():
        return None
    parent = (msg.get("reply_to_message") or {}).get("message_id")
    if not parent:
        return None
    t = SupportTask.objects.filter(post_id=parent, message__chat_id=msg["chat"]["id"]).first()
    if not t:
        return None
    reply = (msg.get("text") or msg.get("caption") or "").strip()
    t.reply = reply[:2000]
    ok = bool(TASK_OK.search(reply))
    t.status = SupportTask.SENT if ok else SupportTask.FAILED
    t.error = "" if ok else "PRBC vazifa yaratmadi — javobini ko'ring"
    t.save(update_fields=["reply", "status", "error"])
    return t


# ====================================================================== eslatma (bot o'zi yozadi)
def _esc(x):
    import html
    return html.escape(x or "", quote=False)


def staff_chat_id(username):
    """Xodimning Telegram ID'si (bot unga shaxsiy yoza olishi uchun): guruhda yozgan bo'lsa yoki kontaktda saqlangan."""
    from zona.models import TeamContact

    from .models import TgUser
    u = (username or "").lstrip("@")
    if not u:
        return None
    tg = TgUser.objects.filter(username__iexact=u).values_list("tg_id", flat=True).first()
    if tg:
        return tg
    return TeamContact.objects.filter(telegram__iexact=u).exclude(telegram_id=None).values_list("telegram_id", flat=True).first()


def dm_text(q, title, assignee, link):
    who = _esc(q.user.name if q.user else "")
    if q.user and q.user.username:
        who += f" (@{_esc(q.user.username)})"
    body = _esc(((q.text or "").strip() or (q.ocr_text or "").strip())[:900])
    lines = ["🗂 <b>Vazifa ochish kerak</b>", "", f"<b>Mavzu:</b> {_esc(title)}", f"<b>Kimdan:</b> {who}"]
    if q.group_id:
        lines.append(f"<b>Guruh:</b> {_esc(q.group.title)}")
    card = agent_lines(q.user, _esc)
    if card:
        lines.append("<b>Agent:</b> " + " · ".join(card))
    if body:
        lines += ["", f"<blockquote>{body}</blockquote>"]
    lines += ["", "<b>Qanday ochiladi</b> — guruhdagi savolga <i>reply</i> qilib yozing:",
              f"<code>/vazifa {_esc(title)}</code>", "Bir nechta ijrochi bilan:",
              f"<code>/vazifa @{_esc(assignee)} @boshqa {_esc(title)}</code>"]
    if q.answer_text and q.status == Message.ANSWERED:
        lines += ["", f"<i>Bot javob bergan: {_esc(q.answer_text[:200])}…</i>"]
    return "\n".join(lines)


def group_hint(assignee, lang):
    if lang == "ru":
        return (f"🗂 <b>@{_esc(assignee)}</b>, по этому вопросу создайте задачу: ответьте на вопрос командой "
                f"<code>/vazifa Заголовок</code>")
    return (f"🗂 <b>@{_esc(assignee)}</b>, bu savol bo'yicha vazifa oching: savolga <i>reply</i> qilib "
            f"<code>/vazifa Sarlavha</code> yozing")


def _notify_staff(tg, q, html_text, assignee, link=""):
    """Ko'rsatmani xodimning o'ziga yetkazish: shaxsiy xabar (botni ochgan bo'lsa), bo'lmasa — bot admin chati.
    Qaytaradi: qayerga yuborildi ("shaxsiy xabar" / "admin chati") yoki "" (hech qayerga)."""
    buttons = [[{"text": "↗ Savolga o'tish", "url": link}]] if link else None
    chat = staff_chat_id(assignee)
    if chat:
        try:
            tg.send(chat, html_text, buttons=buttons)
            if q.photo_file_id and hasattr(tg, "copy"):
                tg.copy(chat, q.chat_id, q.message_id)
            return "shaxsiy xabar"
        except Exception:  # noqa: BLE001 — xodim botni ochmagan (403)
            pass
    admin = q.bot.admin_chat_id if q.bot_id else None
    if admin:
        try:
            tg.send(admin, html_text, buttons=buttons)
            return "admin chati"
        except Exception:  # noqa: BLE001
            pass
    return ""


def remind(q, d, title, assignee, reason, tg, s, group=None):
    """Bir mavzuga bir marta: mas'ulga shaxsiy xabar (tafsilot + havola + rasm nusxasi) va guruhda qisqa eslatma."""
    link = q.group.message_link(q.message_id) if q.group_id else ""
    t = SupportTask.objects.create(message=q, entry=d.entry, assignee=assignee, title=title, link=link, reason=reason,
                                   status=SupportTask.REMINDED, text=dm_text(q, title, assignee, link) if assignee else "")
    if not assignee or tg is None:
        t.error = "" if assignee else "Ijrochi topilmadi (Sozlamalar → PRBC vazifalari → jamoa savollari ijrochisi)."
        t.save(update_fields=["error"])
        return t
    notes = []
    if s.task_remind_dm:
        chat = staff_chat_id(assignee)
        try:
            if not chat:
                raise ValueError("xodim Telegram ID'si noma'lum")
            buttons = [[{"text": "↗ Savolga o'tish", "url": link}]] if link else None
            tg.send(chat, t.text, buttons=buttons)
            if q.photo_file_id and hasattr(tg, "copy"):
                tg.copy(chat, q.chat_id, q.message_id)
            notes.append("shaxsiy xabar yuborildi")
        except Exception as e:  # noqa: BLE001 — xodim botni ochmagan bo'lishi mumkin (403)
            notes.append(f"shaxsiy xabar yuborilmadi: {str(e)[:120]}")
    if group is False and not any(n == "shaxsiy xabar yuborildi" for n in notes) and q.bot_id and q.bot.admin_chat_id:
        try:  # guruhga yozilmaydi — shaxsiy xabar bormagan bo'lsa ko'rsatma admin chatiga
            tg.send(q.bot.admin_chat_id, t.text, buttons=[[{"text": "↗ Savolga o'tish", "url": link}]] if link else None)
            notes.append("ko'rsatma admin chatiga yuborildi")
        except Exception as e:  # noqa: BLE001
            notes.append(f"admin chatiga yuborilmadi: {str(e)[:120]}")
    if s.task_remind_group and group is not False:
        try:
            tg.send(q.chat_id, group_hint(assignee, q.lang), reply_to=q.message_id)
            notes.append("guruhda eslatildi")
        except Exception as e:  # noqa: BLE001
            notes.append(f"guruh eslatmasi yuborilmadi: {str(e)[:120]}")
    t.reply = "; ".join(notes)
    t.sent_at = timezone.now()
    t.save(update_fields=["reply", "sent_at"])
    return t


# ====================================================================== yuborish (MTProto, "account" rejimi)
def _paths(ids):
    from .runner import media_dir
    root = media_dir()
    out = []
    for m in Media.objects.filter(id__in=ids).exclude(path=""):
        p = os.path.join(root, m.path)
        if os.path.exists(p):
            out.append(p)
    return out


async def _find_bot(c, username):
    if username:
        return await c.get_entity(username.lstrip("@"))
    async for dlg in c.iter_dialogs(limit=300):
        ent = dlg.entity
        if getattr(ent, "bot", False) and "prbc" in ((getattr(ent, "username", "") or "") + (dlg.name or "")).lower():
            return ent
    raise ValueError("PRBC boti topilmadi: Sozlamalar → PRBC vazifalari'da bot username'ini kiriting.")


async def _send(session, api_id, api_hash, bot_username, text, files):
    from .history import _client
    c = _client(session, api_id, api_hash)
    await c.connect()
    try:
        if not await c.is_user_authorized():
            raise ValueError("Telegram akkaunt ulanmagan (Sozlamalar → Guruh tarixi).")
        bot = await _find_bot(c, bot_username)
        if files:
            cap = text if len(text) <= 1000 else ""
            sent = await c.send_file(bot, files if len(files) > 1 else files[0],
                                     caption=([cap] + [""] * (len(files) - 1)) if len(files) > 1 else cap)
            if isinstance(sent, list):
                sent = sent[-1]
            if len(text) > 1000:  # izoh chegarasi — buyruq alohida xabar bo'lib, fayllarga javob sifatida
                sent = await c.send_message(bot, text, reply_to=sent.id)
        else:
            sent = await c.send_message(bot, text)
        reply = ""
        for _ in range(10):  # PRBC botining javobini kutamiz (vazifa raqami / xato)
            await asyncio.sleep(1.5)
            msgs = await c.get_messages(bot, limit=3, min_id=sent.id)
            got = [m.message for m in msgs if m.message and not m.out]
            if got:
                reply = "\n".join(reversed(got))
                break
        return getattr(bot, "username", "") or "", reply
    finally:
        await c.disconnect()


FAIL_RE = re.compile(r"(xato|topilmadi|noto.g.ri|ruxsat|error|not found|не найден|ошибк|нет доступа|unknown|usage|"
                     r"works in your team|only in|guruhda ishlaydi|группе)", re.I)


def send_one(t):
    from .history import _creds
    s, api_id, api_hash = _creds()
    session = decrypt(s.mtproto_session_enc)
    if not session:
        raise ValueError("Telegram akkaunt ulanmagan (Sozlamalar → Guruh tarixi).")
    files = _paths(t.media_ids) if s.task_attach else []
    username, reply = asyncio.run(_send(session, api_id, api_hash, s.task_bot, t.text, files))
    if username and not s.task_bot:
        Settings.objects.filter(pk=s.pk).update(task_bot=username)  # topilgan botni eslab qolamiz
    return reply


def process_queue():
    """Navbatdagi bitta vazifani yuborish (runner oqimi chaqiradi). Qaytaradi: yuborildi/yo'q."""
    s = Settings.load()
    pending = SupportTask.objects.filter(status=SupportTask.QUEUED, attempts__lt=3)
    if s.task_mode != "account":
        return False  # eslatma rejimida akkaunt orqali hech narsa yuborilmaydi
    if not s.tasks_enabled:
        pending = pending.filter(reason="test")  # o'chiq bo'lsa ham sinov vazifasi yuboriladi
    since = timezone.now() - timezone.timedelta(days=1)
    if SupportTask.objects.filter(status=SupportTask.SENT, sent_at__gte=since).count() >= s.task_daily_limit:
        return False
    last = SupportTask.objects.filter(sent_at__isnull=False).order_by("-sent_at").values_list("sent_at", flat=True).first()
    if last and (timezone.now() - last).total_seconds() < s.task_gap:
        return False
    t = pending.order_by("created_at").first()
    if not t:
        return False
    t.attempts += 1
    try:
        reply = send_one(t)
        t.reply = reply[:2000]
        t.status = SupportTask.FAILED if reply and FAIL_RE.search(reply) else SupportTask.SENT
        t.error = "PRBC boti xato qaytardi — javobini ko'ring" if t.status == SupportTask.FAILED else ""
    except Exception as e:  # noqa: BLE001
        wait = getattr(e, "seconds", None)  # FloodWait — Telegram kutishni so'radi
        t.error = (f"Telegram {wait} soniya kutishni so'radi" if wait else f"{type(e).__name__}: {e}")[:500]
        t.status = SupportTask.QUEUED if t.attempts < 3 else SupportTask.FAILED
        if wait:
            time.sleep(min(int(wait), 300))
    t.sent_at = timezone.now()
    t.save()
    return t.status == SupportTask.SENT


def test_task(by, assignee=""):
    """Sinov vazifasi (o'ziga): format to'g'riligini tekshirish uchun."""
    s = Settings.load()
    who = (assignee or s.task_default_assignee or "").lstrip("@")
    if not who:
        raise ValueError("Sinov uchun ijrochi username'ini kiriting.")
    text = f"/vazifa @{who} Sinov vazifasi (Support bot)\n\nBu sinov: Support bot PRBC'da vazifa yarata olishini tekshirish."
    return SupportTask.objects.create(assignee=who, title="Sinov vazifasi", text=text, reason="test", created_by=by)


def entries_creating_tasks():
    return Entry.objects.filter(creates_task=True).count()

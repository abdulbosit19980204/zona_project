"""PRBC vazifalari: haqiqiy savollardan PRBC'da vazifa yaratish.

Yo'l: ulangan Telegram akkaunt (egasi, MTProto) PRBC botiga SHAXSIY chatda "/vazifa @ijrochi matn" yuboradi — guruhda
hech narsa ko'rinmaydi. Savoldagi fayllar shu xabarga biriktiriladi, xabar havolasi matnda bo'ladi.

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
    c = m.contacts.exclude(telegram="").order_by("order", "id").first()
    return c.telegram.lstrip("@") if c else ""


def decide_task(q, d, s=None):
    """(kerakmi, ijrochi, sabab). d — engine.Decision."""
    s = s or Settings.load()
    if not s.tasks_enabled or q.kind != Message.QUESTION:
        return False, "", ""
    e = d.entry
    if e is not None and e.creates_task:
        m = e.responsible if e.responsible_id else None
        return True, (e.task_assignee.lstrip("@") or _tg_of(m, s)), "entry"
    deps, mems = targets(s)
    if not (deps or mems):
        return False, "", ""
    if not (d.needs_human or d.stage == "rule"):
        return False, "", ""
    ids = [r.get("id") for r in d.responsible or [] if r.get("id")]
    if e is not None and e.responsible_id:
        ids.insert(0, e.responsible_id)
    for m in Member.objects.filter(id__in=ids).prefetch_related("contacts"):
        if _member_matches(m, deps, mems):
            return True, _tg_of(m, s), f"responsible:{m.name}"[:200]
    return False, "", ""


def _same_topic(q, d):
    """Shu odamning 24 soat ichidagi shu mavzudagi vazifasi (bitta mavzu — bitta vazifa)."""
    from .engine import similarity
    since = timezone.now() - timezone.timedelta(hours=DEDUPE_HOURS)
    qs = SupportTask.objects.filter(created_at__gte=since, message__user=q.user, message__chat_id=q.chat_id) \
        .exclude(status=SupportTask.FAILED).select_related("message")
    for t in qs[:20]:
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
    link = q.group.message_link(q.message_id) if q.group_id else ""
    if link:
        lines.append(f"Havola: {link}")
    if q.answer_text and q.status == Message.ANSWERED:
        lines.append(f"Bot javobi: {q.answer_text[:300]}")
    return "\n".join(lines)[:3900], link


def maybe_create(q, d):
    """Javobdan keyin chaqiriladi (jonli rejim). Navbatga qo'yadi; yuborish — fon oqimida."""
    try:
        need, assignee, reason = decide_task(q, d)
        if not need:
            return None
        if hasattr(q, "task"):
            return q.task
        prev = _same_topic(q, d)
        if prev:
            SupportTask.objects.filter(pk=prev.pk).update(duplicates=[*prev.duplicates, q.pk][-50:])
            return prev
        title = (d.entry.title if d.entry is not None else (q.text or q.ocr_text or "Savol").strip().splitlines()[0])[:120]
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


# ====================================================================== yuborish (MTProto)
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


FAIL_RE = re.compile(r"(xato|topilmadi|noto.g.ri|ruxsat|error|not found|не найден|ошибк|нет доступа|unknown|usage)", re.I)


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

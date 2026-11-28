"""Guruh tarixini o'qish va o'rganish (MTProto, Telethon).

Rasmiy bot guruhning eski xabarlarini o'qiy olmaydi, shuning uchun tarix egasining Telegram akkaunti orqali
(my.telegram.org dagi API ID/hash bilan) FAQAT O'QISH rejimida olinadi: hech narsa yozilmaydi, o'chirilmaydi.
Seans bazada shifrlangan. Xabarlar jonli rejimdagi mantiq bilan (yig'ish rejimi) qayta ishlanadi:
savollar yig'iladi, rasmlar o'qiladi, xodimlar javoblari (aniqlashtirishlar ajratilgan holda) bilim bazasiga nomzod bo'ladi.
"""
import asyncio
import concurrent.futures
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from zona.crypto import decrypt, encrypt

from .models import Bot, Group, HistoryJob, Message, Settings

log = logging.getLogger("support")
PHOTO_MAX_BYTES = 8 * 1024 * 1024
TZ = ZoneInfo("Asia/Tashkent")

# Akkaunt xavfsizligi (Telegram foydalanuvchi akkaunti): faqat o'qish, bir vaqtda bitta guruh, sahifalar orasida pauza,
# rasmlar bittadan; Telegram "kuting" (FloodWait) desa — aynan shuncha kutiladi, uzoq bo'lsa vazifa keyinga qoldiriladi.
# Kunlik "3 ta guruh" chegarasi o'rniga shu tezlik cheklovlari ishlaydi (Telegram aynan so'rovlar tezligini kuzatadi).
BATCH = 50              # shuncha xabardan keyin o'rganiladi va joy (cursor) saqlanadi — qayta ishga tushsa davom etadi
PAGE_WAIT = 1.5         # 100 talik sahifalar orasida (s)
PHOTO_GAP = {"day": 1.2, "night": 0.5}    # rasmlar orasida (s); kunduzi sekinroq — ish vaqtida xalaqit bermaslik
BATCH_REST = {"day": 3.0, "night": 0.5}   # har 50 xabardan keyin dam (s)
LONG_FLOOD = 600        # Telegram bundan uzoq kutishni so'rasa — vazifa shu vaqtdan keyinga qoldiriladi
GAP_BETWEEN_JOBS = 60   # guruhlar orasida tanaffus (s)


class NeedPassword(Exception):
    """Akkauntda ikki bosqichli himoya (2FA) yoqilgan — parol kerak."""


def available():
    """telethon o'rnatilganmi — import qilmasdan (import ~0.8 s; sozlamalar sahifasi har ochilishda kutmasin)."""
    import importlib.util
    try:
        return importlib.util.find_spec("telethon") is not None
    except (ImportError, ValueError):
        return False


def _run(coro_fn, *args):
    """Async funksiyani alohida oqimda o'z event loop'i bilan bajarish (ASGI/worker loop'iga xalaqit bermaydi)."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro_fn(*args))).result(timeout=600)


def _creds():
    s = Settings.load()
    api_hash = decrypt(s.api_hash_enc)
    if not s.api_id or not api_hash:
        raise ValueError("Avval Telegram API ID va API hash kiriting (my.telegram.org).")
    return s, int(s.api_id), api_hash


def _client(session, api_id, api_hash):
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    return TelegramClient(StringSession(session or ""), api_id, api_hash, device_model="Foydali support",
                          app_version="1.0", system_version="server")


# ====================================================================== kirish (paneldan)
def send_code(phone):
    s, api_id, api_hash = _creds()

    async def go():
        c = _client("", api_id, api_hash)
        await c.connect()
        try:
            r = await c.send_code_request(phone)
            return {"phone": phone, "hash": r.phone_code_hash, "session": c.session.save()}
        finally:
            await c.disconnect()

    pending = _run(go)
    s.mtproto_pending_enc = encrypt(__import__("json").dumps(pending))
    s.save(update_fields=["mtproto_pending_enc", "updated_at"])


def sign_in(code="", password=""):
    import json

    from telethon.errors import SessionPasswordNeededError
    s, api_id, api_hash = _creds()
    pending = json.loads(decrypt(s.mtproto_pending_enc) or "{}")
    if not pending:
        raise ValueError("Avval telefon raqamiga kod yuboring.")

    async def go():
        c = _client(pending["session"], api_id, api_hash)
        await c.connect()
        try:
            if pending.get("need_password"):
                if not password:
                    raise NeedPassword()
                await c.sign_in(password=password)
            else:
                try:
                    await c.sign_in(pending["phone"], code, phone_code_hash=pending["hash"])
                except SessionPasswordNeededError:
                    pending["need_password"], pending["session"] = True, c.session.save()
                    if not password:
                        raise NeedPassword() from None
                    await c.sign_in(password=password)
            me = await c.get_me()
            who = " ".join(x for x in (me.first_name, me.last_name) if x) + (f" (@{me.username})" if me.username else "")
            return c.session.save(), who
        finally:
            await c.disconnect()

    try:
        session, who = _run(go)
    except NeedPassword:
        s.mtproto_pending_enc = encrypt(json.dumps(pending))
        s.save(update_fields=["mtproto_pending_enc", "updated_at"])
        raise
    s.mtproto_session_enc, s.mtproto_user, s.mtproto_pending_enc = encrypt(session), who[:150], ""
    s.save(update_fields=["mtproto_session_enc", "mtproto_user", "mtproto_pending_enc", "updated_at"])
    return who


def logout():
    s = Settings.load()
    session = decrypt(s.mtproto_session_enc)
    if session and available():
        try:
            _s, api_id, api_hash = _creds()

            async def go():
                c = _client(session, api_id, api_hash)
                await c.connect()
                try:
                    await c.log_out()
                finally:
                    await c.disconnect()

            _run(go)
        except Exception:  # noqa: BLE001 — seans baribir o'chiriladi
            log.warning("mtproto logout failed", exc_info=True)
    s.mtproto_session_enc, s.mtproto_user, s.mtproto_pending_enc = "", "", ""
    s.save(update_fields=["mtproto_session_enc", "mtproto_user", "mtproto_pending_enc", "updated_at"])


# ====================================================================== tarixni o'qish
def _peer(chat_id):
    from telethon.tl.types import PeerChannel, PeerChat
    text = str(chat_id)
    if text.startswith("-100"):
        return PeerChannel(int(text[4:]))
    return PeerChat(abs(int(chat_id)))


def _plain_id(chat_id):
    text = str(chat_id)
    return int(text[4:]) if text.startswith("-100") else abs(int(chat_id))


async def _resolve(c, chat_id):
    """Guruhni topish. Yangi seansda Telethon keshida guruh bo'lmaydi ("Could not find the input entity") — shunda
    akkauntning dialoglari ko'rib chiqiladi (bu keshni ham to'ldiradi). Akkaunt guruhda bo'lmasa — tushunarli xato."""
    try:
        return await c.get_entity(_peer(chat_id))
    except (ValueError, TypeError):
        pass
    want = _plain_id(chat_id)
    async for d in c.iter_dialogs():
        if getattr(d.entity, "id", None) == want:
            return d.entity
    raise ValueError("Ulangan Telegram akkaunt bu guruhda emas (yoki guruh ko'rinmaydi). Akkauntni guruhga qo'shing va qayta urining.")


class Pause(Exception):
    """Vazifa to'xtatiladi va keyin shu joydan davom etadi (tungi oyna tugadi, uzoq FloodWait, bekor qilindi)."""

    def __init__(self, reason, until=None, cancel=False):
        super().__init__(reason)
        self.reason, self.until, self.cancel = reason, until, cancel


def is_night(now=None, s=None):
    """Tungi oyna (Toshkent vaqti), masalan 22:00–07:00 — og'ir o'qish shu vaqtga rejalashtiriladi."""
    s = s or Settings.load()
    h = (now or timezone.now()).astimezone(TZ).hour
    a, b = s.history_night_from % 24, s.history_night_to % 24
    return (a <= h or h < b) if a > b else (a <= h < b)


def next_night_start(now=None, s=None):
    s = s or Settings.load()
    now = (now or timezone.now()).astimezone(TZ)
    start = now.replace(hour=s.history_night_from % 24, minute=0, second=0, microsecond=0)
    if start <= now:
        start += timedelta(days=1)
    return start


def next_job(now=None):
    """Navbatdagi vazifa: vaqti kelgan (run_after); "faqat tunda" bo'lsa — tungi oynada."""
    s = Settings.load()
    now = now or timezone.now()
    night = is_night(now, s)
    for j in HistoryJob.objects.filter(status=HistoryJob.QUEUED).order_by("created_at", "id"):
        if j.run_after and j.run_after > now:
            continue
        if j.night_only and not night:
            continue
        return j
    return None


def _is_image(m):
    if getattr(m, "photo", None):
        return True
    doc = getattr(m, "document", None)
    return bool(doc and str(getattr(doc, "mime_type", "") or "").startswith("image/"))


async def _sender(m, senders):
    sid = m.sender_id or 0
    if sid not in senders:
        try:
            u = await m.get_sender()
        except Exception:  # noqa: BLE001
            u = None
        senders[sid] = {"id": sid, "username": getattr(u, "username", "") or "",
                        "first_name": getattr(u, "first_name", "") or getattr(u, "title", "") or "",
                        "last_name": getattr(u, "last_name", "") or "", "is_bot": bool(getattr(u, "bot", False))}
    return senders[sid]


def _flood_pause(e):
    return Pause(f"Telegram {e.seconds} s kutishni so'radi — keyin shu joydan davom etadi",
                 until=timezone.now() + timedelta(seconds=e.seconds + 60))


async def stream(session, api_id, api_hash, chat_id, start, end, cursor, photos, hooks):
    """Guruh xabarlarini ESKIDAN YANGIGA o'qiydi (start..end oralig'ida, cursor'dan keyin) va 50 tadan o'rganishga beradi.
    hooks: known(items) -> o'rganilgan message_id'lar, process(items, wait) -> None, phase() -> "day"/"night"
    (hammasi sinxron, Django — alohida oqimda). Faqat o'qish."""
    from telethon.errors import FloodWaitError
    c = _client(session, api_id, api_hash)
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        raise ValueError("Telegram akkaunt seansi tugagan — paneldan qayta ulaning.")
    loop = asyncio.get_running_loop()
    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="support-history-db")
    senders, batch = {}, []

    def call(name, *a):
        return loop.run_in_executor(ex, lambda: hooks[name](*a))

    async def download(m):
        while True:
            try:
                data = await c.download_media(m, file=bytes)
                return data if data and len(data) <= PHOTO_MAX_BYTES else None
            except FloodWaitError as e:
                if e.seconds > LONG_FLOOD:
                    raise
                await call("process", [], e.seconds)
                await asyncio.sleep(e.seconds + 1)
            except Exception:  # noqa: BLE001 — bitta rasm butun tarixni to'xtatmasin
                return None

    async def flush():
        nonlocal batch
        if not batch:
            return
        items, batch = batch, []
        known = await call("known", [it["message_id"] for it in items])
        mode = await call("phase")
        for it in items:  # rasm faqat hali o'rganilmagan xabar uchun yuklanadi (qayta ishga tushganda qayta yuklanmaydi)
            m = it.pop("_m")
            it["known"] = it["message_id"] in known
            if photos and not it["known"] and _is_image(m):
                if (getattr(getattr(m, "document", None), "size", 0) or 0) <= PHOTO_MAX_BYTES:
                    it["photo"] = await download(m)
                    await asyncio.sleep(PHOTO_GAP[mode])
        await call("process", items, 0)
        await asyncio.sleep(BATCH_REST[mode])

    try:
        entity = await _resolve(c, chat_id)
        last = cursor or 0
        while True:
            try:
                kw = {"offset_id": last} if last else {"offset_date": start}
                async for m in c.iter_messages(entity, reverse=True, wait_time=PAGE_WAIT, **kw):
                    if end and m.date > end:
                        break
                    if m.date < start:
                        continue
                    last = m.id
                    if m.action is not None:
                        continue  # xizmat xabarlari (qo'shildi, chiqdi...)
                    item = {"message_id": m.id, "_date": m.date, "text": m.message or "", "from": await _sender(m, senders),
                            "reply_to": getattr(m.reply_to, "reply_to_msg_id", None) if m.reply_to else None,
                            "photo": None, "media_group_id": str(m.grouped_id or ""), "_m": m}
                    geo = getattr(m, "geo", None)
                    if geo is not None and getattr(geo, "lat", None) is not None:
                        item["location"] = {"latitude": geo.lat, "longitude": geo.long}
                    batch.append(item)
                    if len(batch) >= BATCH:
                        await flush()
                break
            except FloodWaitError as e:  # Telegram "sekinroq" desa — kutib, aynan shu joydan davom
                if e.seconds > LONG_FLOOD:
                    raise
                await call("process", [], e.seconds)
                await asyncio.sleep(e.seconds + 1)
        await flush()
    except FloodWaitError as e:
        raise _flood_pause(e) from e
    finally:
        await c.disconnect()
        ex.shutdown(wait=False)


def run_job(job_id):
    from django.db import close_old_connections

    from .models import Entry
    from .runner import Handler, NullClient

    job = HistoryJob.objects.select_related("group__bot").get(pk=job_id)
    s, api_id, api_hash = _creds()
    session = decrypt(s.mtproto_session_enc)
    if not session:
        raise ValueError("Telegram akkaunt ulanmagan (Sozlamalar → Guruh tarixi).")
    group: Group = job.group
    bot: Bot = group.bot
    start = job.date_from or (job.created_at - timedelta(days=job.days))
    end = job.date_to
    p = dict(job.progress or {})
    if "before_q" not in p:  # birinchi ishga tushish; davom etganda hisoblar saqlanadi
        p = {"before_q": Message.objects.filter(group=group, kind=Message.QUESTION).count(),
             "before_e": Entry.objects.filter(source="history").count(), "messages": 0, "photos": 0, "processed": 0,
             "skipped": 0}
    p.update(stage="o'qilmoqda", flood_wait=0, paused="")
    job.status, job.error, job.progress = HistoryJob.RUNNING, "", p
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=["status", "error", "progress", "started_at"])
    handler = Handler(bot, NullClient(), history=True)

    def known(ids):
        close_old_connections()
        return set(Message.objects.filter(chat_id=group.chat_id, message_id__in=ids).values_list("message_id", flat=True))

    def phase():
        return "night" if is_night(None, s) else "day"

    def process(items, wait=0):
        """50 ta xabar — jonli rejimdagi mantiq bilan (yig'ish rejimi) o'rganiladi, keyin joy saqlanadi."""
        close_old_connections()
        for it in items:
            p["messages"] += 1
            if it.get("photo"):
                p["photos"] += 1
            if it.get("known"):
                p["skipped"] += 1  # avval o'rganilgan (qayta ishga tushish) — takrorlanmaydi
                continue
            if it["from"].get("is_bot"):
                continue
            msg = {"message_id": it["message_id"], "_date": it["_date"],
                   "chat": {"id": group.chat_id, "type": "supergroup", "title": group.title},
                   "from": it["from"], "text": it["text"]}
            if it.get("media_group_id"):
                msg["media_group_id"] = it["media_group_id"]
            if it.get("location"):
                msg["location"] = it["location"]
            if it["reply_to"]:
                msg["reply_to_message"] = {"message_id": it["reply_to"]}
            if it.get("photo"):
                handler.photo_bytes[it["message_id"]] = it["photo"]
            try:
                handler.on_group(msg)
            except Exception:  # noqa: BLE001
                log.exception("history message %s failed", it["message_id"])
            handler.photo_bytes.pop(it["message_id"], None)
            p["processed"] += 1
        upd = {}
        if items:
            upd["cursor"] = items[-1]["message_id"]
            p["reached"] = items[-1]["_date"].isoformat()
        p.update(stage="o'rganilmoqda", flood_wait=wait)
        HistoryJob.objects.filter(pk=job_id).update(progress=dict(p), **upd)
        if HistoryJob.objects.filter(pk=job_id, status=HistoryJob.CANCELED).exists():
            raise Pause("bekor qilindi", cancel=True)
        if job.night_only and not is_night(None, s):
            raise Pause("tungi oyna tugadi — kechqurun shu joydan davom etadi", until=next_night_start(None, s))

    try:
        asyncio.run(stream(session, api_id, api_hash, group.chat_id, start, end, job.cursor, job.photos,
                           {"known": known, "process": process, "phase": phase}))
    except Pause as e:
        close_old_connections()
        if e.cancel:
            HistoryJob.objects.filter(pk=job_id).update(progress={**p, "stage": "bekor qilindi"}, finished_at=timezone.now())
        else:
            HistoryJob.objects.filter(pk=job_id).update(status=HistoryJob.QUEUED, run_after=e.until,
                                                        progress={**p, "stage": "kutmoqda", "paused": e.reason})
        return p
    close_old_connections()
    stats = {**p, "stage": "tayyor", "paused": "",
             "questions": Message.objects.filter(group=group, kind=Message.QUESTION).count() - p["before_q"],
             "staff_answers": Message.objects.filter(group=group, kind=Message.STAFF, source="history").count(),
             "clarifications": Message.objects.filter(group=group, kind=Message.CLARIFY, source="history").count(),
             "candidates": Entry.objects.filter(source="history").count() - p["before_e"]}
    HistoryJob.objects.filter(pk=job_id).update(status=HistoryJob.DONE, progress=stats, finished_at=timezone.now())
    return stats


# ====================================================================== davom ettirish
RETRIES = 3  # kutilmagan xatodan keyin avtomatik qayta urinish (10, 20, 40 daqiqadan keyin)
NEEDS_PERSON = ("guruhda emas", "seans tugagan", "ulanmagan", "API ID", "Could not find the input entity")


def retry_later(job_id, err):
    """Vazifa xato bilan to'xtadi. Odam aralashuvi kerak bo'lsa (akkaunt guruhda emas, seans tugagan) — "Xato";
    aks holda joyidan (cursor) avtomatik davom etadi."""
    text = f"{type(err).__name__}: {err}"[:500]
    j = HistoryJob.objects.filter(pk=job_id).first()
    if j is None:
        return
    p = dict(j.progress or {})
    n = int(p.get("attempts") or 0)
    if any(k in text for k in NEEDS_PERSON) or n >= RETRIES:
        HistoryJob.objects.filter(pk=job_id).update(status=HistoryJob.FAILED, error=text, finished_at=timezone.now())
        return
    p.update(attempts=n + 1, stage="kutmoqda", paused=f"xato — {10 * 2 ** n} daqiqadan keyin joyidan davom etadi")
    HistoryJob.objects.filter(pk=job_id).update(status=HistoryJob.QUEUED, error=text, progress=p,
                                                run_after=timezone.now() + timedelta(minutes=10 * 2 ** n))


def continue_job(j, by=""):
    """To'xtagan vazifani davom ettirish. Xato/bekor qilingan — saqlangan joydan (cursor); tugagan — oxirgi o'rganilgan
    xabardan bugungacha (yangi vazifa). Shu guruhda navbatda/ishlayotgan vazifa bo'lsa — hech narsa qilinmaydi.
    Qaytaradi: davom etayotgan vazifa yoki None."""
    busy = HistoryJob.objects.filter(group_id=j.group_id, status__in=[HistoryJob.QUEUED, HistoryJob.RUNNING]).first()
    if busy is not None:
        return busy if busy.pk == j.pk else None
    if j.status in (HistoryJob.FAILED, HistoryJob.CANCELED):
        p = {**(j.progress or {}), "attempts": 0, "paused": ""}
        HistoryJob.objects.filter(pk=j.pk).update(status=HistoryJob.QUEUED, error="", finished_at=None, run_after=None,
                                                  progress=p)
        return HistoryJob.objects.get(pk=j.pk)
    if j.status == HistoryJob.DONE:
        start = j.date_from or (j.created_at - timedelta(days=j.days))
        return HistoryJob.objects.create(group_id=j.group_id, days=j.days, photos=j.photos, night_only=j.night_only,
                                         date_from=start, date_to=None, cursor=j.cursor, created_by=by or j.created_by)
    return None


def continue_groups(group_ids=None, by=""):
    """Har bir guruhning oxirgi vazifasini davom ettirish ("Hammasini davom ettirish")."""
    qs = HistoryJob.objects.order_by("group_id", "-created_at", "-id")
    if group_ids is not None:
        qs = qs.filter(group_id__in=group_ids)
    out, seen = [], set()
    for j in qs:
        if j.group_id in seen:
            continue
        seen.add(j.group_id)
        if j.status in (HistoryJob.QUEUED, HistoryJob.RUNNING):
            continue  # allaqachon davom etyapti
        r = continue_job(j, by)
        if r is not None and r.status == HistoryJob.QUEUED:
            out.append(r)
    return out

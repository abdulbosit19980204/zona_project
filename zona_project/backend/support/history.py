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

from django.utils import timezone

from zona.crypto import decrypt, encrypt

from .models import Bot, Group, HistoryJob, Message, Settings

log = logging.getLogger("support")
MAX_PHOTOS = 400
PHOTO_MAX_BYTES = 6 * 1024 * 1024


class NeedPassword(Exception):
    """Akkauntda ikki bosqichli himoya (2FA) yoqilgan — parol kerak."""


def available():
    try:
        import telethon  # noqa: F401
        return True
    except ImportError:
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


async def fetch(session, api_id, api_hash, chat_id, since, limit, photos, progress):
    """Guruh xabarlarini (eskidan yangiga) va kerakli rasmlarni oladi. Faqat o'qish."""
    from telethon.errors import FloodWaitError
    c = _client(session, api_id, api_hash)
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        raise ValueError("Telegram akkaunt seansi tugagan — paneldan qayta ulaning.")
    out, photo_count = [], 0
    try:
        entity = await c.get_entity(_peer(chat_id))
        senders = {}
        while True:
            try:
                async for m in c.iter_messages(entity, limit=limit, wait_time=1):
                    if m.date < since:
                        break
                    if m.action is not None:
                        continue  # xizmat xabarlari (qo'shildi, chiqdi...)
                    sid = m.sender_id or 0
                    if sid not in senders:
                        u = await m.get_sender()
                        senders[sid] = {"id": sid, "username": getattr(u, "username", "") or "",
                                        "first_name": getattr(u, "first_name", "") or getattr(u, "title", "") or "",
                                        "last_name": getattr(u, "last_name", "") or "", "is_bot": bool(getattr(u, "bot", False))}
                    item = {"message_id": m.id, "_date": m.date, "text": m.message or "", "from": senders[sid],
                            "reply_to": getattr(m.reply_to, "reply_to_msg_id", None) if m.reply_to else None,
                            "photo": None}
                    if photos and m.photo and photo_count < MAX_PHOTOS:
                        try:
                            data = await c.download_media(m, file=bytes)
                            if data and len(data) <= PHOTO_MAX_BYTES:
                                item["photo"] = data
                                photo_count += 1
                        except FloodWaitError as e:
                            await asyncio.sleep(min(e.seconds, 120) + 1)
                        except Exception:  # noqa: BLE001 — bitta rasm butun tarixni to'xtatmasin
                            pass
                    out.append(item)
                    if len(out) % 200 == 0:
                        await asyncio.to_thread(progress, len(out), photo_count)
                break
            except FloodWaitError as e:  # Telegram "sekinroq" desa — kutib, davom etamiz
                await asyncio.to_thread(progress, len(out), photo_count, e.seconds)
                await asyncio.sleep(min(e.seconds, 300) + 1)
                if e.seconds > 300:
                    break
    finally:
        await c.disconnect()
    out.reverse()  # eskidan yangiga: avval savol, keyin javob
    return out, photo_count


def run_job(job_id):
    from .runner import Handler, NullClient

    job = HistoryJob.objects.select_related("group__bot").get(pk=job_id)
    s, api_id, api_hash = _creds()
    session = decrypt(s.mtproto_session_enc)
    if not session:
        raise ValueError("Telegram akkaunt ulanmagan (Sozlamalar → Guruh tarixi).")
    group: Group = job.group
    bot: Bot = group.bot
    job.status, job.started_at, job.error = HistoryJob.RUNNING, timezone.now(), ""
    job.progress = {"stage": "o'qilmoqda", "messages": 0, "photos": 0}
    job.save()

    def progress(n, ph, wait=0):
        HistoryJob.objects.filter(pk=job_id).update(progress={"stage": "o'qilmoqda", "messages": n, "photos": ph,
                                                              "flood_wait": wait})

    since = timezone.now() - timedelta(days=job.days)
    items, photos = _run(fetch, session, api_id, api_hash, group.chat_id, since, s.history_max, job.photos, progress)

    before_q = Message.objects.filter(group=group, kind=Message.QUESTION).count()
    from .models import Entry
    before_e = Entry.objects.filter(source="history").count()
    handler = Handler(bot, NullClient(), history=True)
    done = 0
    for it in items:
        if it["from"].get("is_bot"):
            continue
        msg = {"message_id": it["message_id"], "_date": it["_date"],
               "chat": {"id": group.chat_id, "type": "supergroup", "title": group.title},
               "from": it["from"], "text": it["text"]}
        if it["reply_to"]:
            msg["reply_to_message"] = {"message_id": it["reply_to"]}
        if it["photo"]:
            handler.photo_bytes[it["message_id"]] = it["photo"]
        try:
            handler.on_group(msg)
        except Exception:  # noqa: BLE001
            log.exception("history message %s failed", it["message_id"])
        handler.photo_bytes.pop(it["message_id"], None)
        done += 1
        if done % 100 == 0:
            HistoryJob.objects.filter(pk=job_id).update(progress={"stage": "o'rganilmoqda", "messages": len(items),
                                                                  "photos": photos, "processed": done})
    stats = {
        "stage": "tayyor", "messages": len(items), "photos": photos, "processed": done,
        "questions": Message.objects.filter(group=group, kind=Message.QUESTION).count() - before_q,
        "staff_answers": Message.objects.filter(group=group, kind=Message.STAFF, source="history").count(),
        "clarifications": Message.objects.filter(group=group, kind=Message.CLARIFY, source="history").count(),
        "candidates": Entry.objects.filter(source="history").count() - before_e,
    }
    HistoryJob.objects.filter(pk=job_id).update(status=HistoryJob.DONE, progress=stats, finished_at=timezone.now())
    return stats

"""Bot jarayoni: har bir yoqilgan bot uchun alohida oqim, Telegram'dan long-polling.

Admin paneldagi o'zgarishlar (yoqish/o'chirish, rejim, token) qayta ishga tushirmasdan ~10 soniyada kuchga kiradi.
Xabar avval bazaga yoziladi, keyin qayta ishlanadi: jarayon qayta ishga tushsa ham savol yo'qolmaydi.
"""
import logging
import os
import threading
import time
from pathlib import Path

from django.conf import settings as dj_settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from zona import conf
from zona.crypto import decrypt

from . import engine, ocr
from .models import MODE_LIVE, MODE_OFF, MODE_SHADOW, Bot, Entry, EntryVersion, Group, Message, Settings
from .telegram import Client, TelegramError

log = logging.getLogger("support")
APPROVER_LEVELS = {"L2", "L3", "LEAD", "BIZ"}


def media_dir():
    base = os.environ.get("ZONA_SUPPORT_MEDIA") or str(Path(str(dj_settings.DATABASES["default"]["NAME"])).parent / "support-media")
    return Path(base)


def panel_url(path):
    base = (conf.get("FRONTEND_URL") or "").rstrip("/")
    return f"{base}{path}" if base.startswith("http") else ""


# ====================================================================== bitta yangilanishni qayta ishlash
class Handler:
    def __init__(self, bot: Bot, client: Client):
        self.bot = bot
        self.tg = client

    # ---------------------------------------------------------------- kirish nuqtasi
    def handle(self, upd):
        if "my_chat_member" in upd:
            return self.on_membership(upd["my_chat_member"])
        if "callback_query" in upd:
            return self.on_callback(upd["callback_query"])
        msg = upd.get("message")
        if not msg:
            return None
        chat = msg.get("chat") or {}
        sender = msg.get("from") or {}
        if sender.get("is_bot"):
            return None
        if chat.get("type") == "private":
            return self.on_private(msg)
        if chat.get("type") in ("group", "supergroup"):
            return self.on_group(msg)
        return None

    # ---------------------------------------------------------------- guruhga qo'shilish
    def on_membership(self, data):
        chat = data.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup"):
            return None
        status = (data.get("new_chat_member") or {}).get("status", "")
        group, _ = Group.objects.get_or_create(bot=self.bot, chat_id=chat["id"], defaults={"title": chat.get("title", "")})
        group.title = chat.get("title", group.title)
        group.is_active = status in ("member", "administrator")
        group.is_admin = status == "administrator"
        group.save()
        if self.bot.admin_chat_id:
            state = "qo'shildi" if group.is_active else "chiqarildi"
            self._safe_send(self.bot.admin_chat_id, f"ℹ️ Bot guruhga {state}: <b>{engine.html.escape(group.title)}</b>"
                                                    f"\nRejim: {group.get_mode_display()} (panelda o'zgartiriladi)")
        return group

    # ---------------------------------------------------------------- shaxsiy chat
    def on_private(self, msg):
        sender = msg["from"]
        user = engine.identify(sender["id"], sender.get("username", ""), _full_name(sender))
        text = (msg.get("text") or "").strip()
        if text.startswith("/id"):
            return self._safe_send(msg["chat"]["id"], f"Chat ID: <code>{msg['chat']['id']}</code>")
        if text.startswith("/start") or text.startswith("/admin"):
            if user.is_staff and user.staff_level() == "LEAD" and not self.bot.admin_chat_id:
                Bot.objects.filter(pk=self.bot.pk).update(admin_chat_id=msg["chat"]["id"])
                self.bot.admin_chat_id = msg["chat"]["id"]
                return self._safe_send(msg["chat"]["id"], "✅ Bu chat admin chat sifatida belgilandi: soya rejimidagi "
                                                          "javoblar va tasdiqlash so'rovlari shu yerga keladi.")
            hello = self.bot.welcome or ("Assalomu alaykum! Men support botman: guruhdagi savollarga javob beraman. "
                                         "Savolingizni guruhda yozing (rasm bilan ham bo'ladi).")
            return self._safe_send(msg["chat"]["id"], engine.html.escape(hello))
        return None

    # ---------------------------------------------------------------- guruh xabari
    def on_group(self, msg):
        chat, sender = msg["chat"], msg["from"]
        group, created = Group.objects.get_or_create(bot=self.bot, chat_id=chat["id"],
                                                     defaults={"title": chat.get("title", "")})
        if created or group.title != chat.get("title", group.title):
            group.title = chat.get("title", group.title)
        group.last_message_at = timezone.now()
        group.save()
        mode = group.effective_mode()
        user = engine.identify(sender["id"], sender.get("username", ""), _full_name(sender))
        text = (msg.get("text") or msg.get("caption") or "").strip()
        photo = _photo_id(msg)
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")

        if user.is_staff:
            return self.on_staff(msg, group, user, text, reply_to)
        if mode == MODE_OFF or not engine.is_question(text, bool(photo)):
            return None

        q, created = Message.objects.get_or_create(
            bot=self.bot, chat_id=chat["id"], message_id=msg["message_id"],
            defaults={"group": group, "user": user, "text": text[:4000], "photo_file_id": photo or "",
                      "reply_to_id": reply_to, "kind": Message.QUESTION})
        if not created:
            return q  # takroriy yangilanish
        self.process_question(q, mode)
        return q

    def process_question(self, q, mode):
        settings = Settings.load()
        if q.photo_file_id and settings.ocr_enabled:
            self._read_photo(q)
        raw = "\n".join(x for x in (q.text, q.ocr_text) if x).strip()
        q.lang = engine.detect_lang(q.text or q.ocr_text)
        if not raw:
            q.status = Message.IGNORED
            q.save()
            return q
        if mode == MODE_LIVE:
            self.tg.typing(q.chat_id)
        d = engine.decide(raw, q.lang, allow_unapproved=(mode == MODE_SHADOW))
        q.stage, q.entry, q.confidence = d.stage, d.entry, d.confidence
        q.answer_text = d.text
        if d.entry:
            Entry.objects.filter(pk=d.entry.pk).update(uses=d.entry.uses + 1, last_used_at=timezone.now())

        if mode == MODE_SHADOW:
            q.status = Message.DRAFTED
            q.save()
            self._send_draft(q, d)
            return q

        # jonli rejim
        if not d.needs_human and d.text:
            body = d.text
            line = engine.responsible_line(d.responsible, q.lang) if d.stage == "rule" else ""
            if line:
                body += "\n\n" + line
            sent = self._safe_send(q.chat_id, engine.to_html(body, settings.signature), reply_to=q.message_id,
                                   buttons=[[{"text": "👍", "callback_data": f"fb:{q.id}:1"},
                                             {"text": "👎", "callback_data": f"fb:{q.id}:-1"}]])
            if sent:
                q.status, q.answered_by, q.answered_at = Message.ANSWERED, "bot", timezone.now()
                q.bot_reply_id = sent.get("message_id")
            q.save()
            return q

        q.status = Message.ESCALATED
        q.save()
        ack = ("Ваш вопрос принят." if q.lang == "ru" else "Savolingiz qabul qilindi.")
        if d.responsible and d.responsible[0].get("telegram"):
            tags = " ".join("@" + t for t in d.responsible[0]["telegram"][:3])
            ack += (" Ответит: " if q.lang == "ru" else " Javob beradi: ") + tags
        sent = self._safe_send(q.chat_id, engine.html.escape(ack), reply_to=q.message_id)
        if sent:
            Message.objects.filter(pk=q.pk).update(bot_reply_id=sent.get("message_id"))
        self._send_draft(q, d, escalated=True)
        return q

    # ---------------------------------------------------------------- xodim javobi -> o'rganish
    def on_staff(self, msg, group, user, text, reply_to):
        if not text or not reply_to:
            return None
        q = Message.objects.filter(bot=self.bot, chat_id=msg["chat"]["id"], message_id=reply_to,
                                   kind=Message.QUESTION).first()
        if not q:
            return None
        staff_name = user.staff_name()
        a, created = Message.objects.get_or_create(
            bot=self.bot, chat_id=msg["chat"]["id"], message_id=msg["message_id"],
            defaults={"group": group, "user": user, "text": text[:4000], "kind": Message.STAFF, "question": q,
                      "reply_to_id": reply_to, "status": Message.CLOSED, "stage": "staff"})
        if not created:
            return a
        corrected = q.status == Message.ANSWERED and q.answered_by == "bot"
        if q.status != Message.ANSWERED or corrected:
            q.status, q.stage, q.answered_by, q.answered_at = Message.ANSWERED, "staff", staff_name, timezone.now()
            q.save()
        if Settings.load().learn_from_staff:
            entry = learn(q, text, staff_name, priority=corrected)
            self._send_candidate(entry, q, staff_name)
        return a

    # ---------------------------------------------------------------- tugmalar
    def on_callback(self, cb):
        data = cb.get("data") or ""
        sender = cb.get("from") or {}
        chat_id = ((cb.get("message") or {}).get("chat") or {}).get("id")
        user = engine.identify(sender["id"], sender.get("username", ""), _full_name(sender))
        kind, _, rest = data.partition(":")
        if kind == "fb":
            mid, _, val = rest.partition(":")
            q = Message.objects.filter(pk=int(mid or 0), bot=self.bot).select_related("entry").first()
            if not q or (q.user_id and q.user_id != user.id):
                return self.tg.answer_callback(cb["id"], "Baholash faqat savol egasi uchun")
            if q.feedback == 0:
                q.feedback = 1 if val == "1" else -1
                q.save(update_fields=["feedback"])
                if q.entry_id:
                    field = "likes" if q.feedback > 0 else "dislikes"
                    Entry.objects.filter(pk=q.entry_id).update(**{field: getattr(q.entry, field) + 1})
                if q.feedback < 0 and self.bot.admin_chat_id:
                    self._safe_send(self.bot.admin_chat_id, f"👎 Javob yoqmadi:\n❓ {engine.html.escape(q.text[:300])}\n"
                                                            f"💬 {engine.html.escape(q.answer_text[:500])}")
            return self.tg.answer_callback(cb["id"], "Rahmat!")

        # quyidagilar faqat admin chatidan va xodimlar uchun
        if chat_id != self.bot.admin_chat_id or not user.is_staff:
            return self.tg.answer_callback(cb["id"], "Ruxsat yo'q", alert=True)
        by = user.staff_name()
        if kind in ("send", "skip"):
            q = Message.objects.filter(pk=int(rest or 0), bot=self.bot).first()
            if not q:
                return self.tg.answer_callback(cb["id"], "Topilmadi")
            if kind == "send" and q.answer_text and q.status != Message.ANSWERED:
                sent = self._safe_send(q.chat_id, engine.to_html(q.answer_text, Settings.load().signature),
                                       reply_to=q.message_id)
                if sent:
                    q.status, q.answered_by, q.answered_at = Message.ANSWERED, f"bot ({by})", timezone.now()
                    q.bot_reply_id = sent.get("message_id")
                    q.save()
            elif kind == "skip":
                q.status = Message.CLOSED
                q.save(update_fields=["status"])
            self.tg.edit_buttons(chat_id, cb["message"]["message_id"])
            return self.tg.answer_callback(cb["id"], "Yuborildi" if kind == "send" else "Yopildi")
        if kind in ("ap", "rj"):
            if user.staff_level() not in APPROVER_LEVELS:
                return self.tg.answer_callback(cb["id"], "Tasdiqlash uchun L2/L3 yoki rahbar darajasi kerak", alert=True)
            e = Entry.objects.filter(pk=int(rest or 0)).first()
            if not e:
                return self.tg.answer_callback(cb["id"], "Topilmadi")
            approve(e, by) if kind == "ap" else reject(e, by)
            self.tg.edit_buttons(chat_id, cb["message"]["message_id"])
            return self.tg.answer_callback(cb["id"], "Tasdiqlandi ✅" if kind == "ap" else "Rad etildi")
        return self.tg.answer_callback(cb["id"])

    # ---------------------------------------------------------------- yordamchilar
    def _read_photo(self, q):
        try:
            data = self.tg.download(q.photo_file_id)
        except TelegramError as e:
            q.error = f"Rasm olinmadi: {e}"[:300]
            return
        day = timezone.localdate().isoformat()
        folder = media_dir() / day
        try:
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / f"{q.bot_id}_{q.chat_id}_{q.message_id}.jpg"
            path.write_bytes(data)
            q.photo_path = str(path)
        except OSError:
            pass
        q.ocr_text = ocr.read_text(data)

    def _send_draft(self, q, d, escalated=False):
        if not self.bot.admin_chat_id:
            return None
        esc = engine.html.escape
        who = q.user.name if q.user else "?"
        head = "🚨 Odamga uzatildi" if escalated else "🕶 Soya rejimi"
        parts = [f"{head} · <b>{esc(q.group.title if q.group else '')}</b>", f"👤 {esc(who)}:", f"❓ {esc(q.text[:700])}"]
        if q.ocr_text:
            parts.append(f"🖼 <i>{esc(q.ocr_text[:400])}</i>")
        if d.text:
            label = {"template": "Shablon", "faq": "Bazadan", "rule": "Qoida", "ai": "AI"}.get(d.stage, "Taklif")
            warn = " · ⚠️ tasdiqlanmagan" if d.unapproved else ""
            parts.append(f"— — —\n💬 <b>{label}</b> ({d.confidence}%){warn}:\n{esc(d.text[:1500])}")
        else:
            parts.append("— — —\n❔ Javob topilmadi")
        if d.note:
            parts.append(f"<i>{esc(d.note[:300])}</i>")
        line = engine.responsible_line(d.responsible, "uz")
        if line:
            parts.append(esc(line))
        buttons = []
        if d.text and not escalated:
            buttons.append({"text": "✅ Guruhga yuborish", "callback_data": f"send:{q.id}"})
        buttons.append({"text": "✖️ Yopish", "callback_data": f"skip:{q.id}"})
        return self._safe_send(self.bot.admin_chat_id, "\n".join(parts), buttons=[buttons])

    def _send_candidate(self, entry, q, staff_name):
        if not self.bot.admin_chat_id or not entry:
            return None
        esc = engine.html.escape
        star = "⭐ Ustuvor (bot javobi tuzatildi)\n" if entry.priority else ""
        text = (f"📚 <b>Yangi javob nomzodi</b>\n{star}❓ {esc(q.text[:600])}\n"
                + (f"🖼 <i>{esc(q.ocr_text[:300])}</i>\n" if q.ocr_text else "")
                + f"💬 {esc(entry.answer[:1500])}\n👤 {esc(staff_name)}")
        row = [{"text": "✅ Tasdiqlash", "callback_data": f"ap:{entry.id}"},
               {"text": "❌ Rad etish", "callback_data": f"rj:{entry.id}"}]
        url = panel_url(f"/support/review?entry={entry.id}")
        buttons = [row] + ([[{"text": "✏️ Panelda tahrirlash", "url": url}]] if url else [])
        return self._safe_send(self.bot.admin_chat_id, text, buttons=buttons)

    def _safe_send(self, chat_id, text, reply_to=None, buttons=None):
        try:
            return self.tg.send(chat_id, text, reply_to=reply_to, buttons=buttons)
        except TelegramError as e:
            log.warning("send failed chat=%s: %s", chat_id, e)
            Bot.objects.filter(pk=self.bot.pk).update(last_error=f"sendMessage: {e}"[:500])
            return None


# ====================================================================== bilim bazasi amallari
def learn(q, answer, staff_name, priority=False):
    """Xodim javobidan bilim bazasiga nomzod (status=new). Tasdiqlanmaguncha bot uni ishlatmaydi."""
    question = q.text.strip() or q.ocr_text.strip()[:300]
    if not question or len(answer.strip()) < 3:
        return None
    title = question.splitlines()[0][:190]
    return Entry.objects.create(kind=Entry.FAQ, title=title, questions=[question[:1000]], answer=answer.strip(),
                                status=Entry.NEW, source="staff", author=staff_name, priority=priority)


def snapshot(entry, editor, note=""):
    EntryVersion.objects.create(entry=entry, title=entry.title, questions=entry.questions, triggers=entry.triggers,
                                extract=entry.extract, answer=entry.answer, answer_ru=entry.answer_ru,
                                editor=editor or "", note=note[:200])


@transaction.atomic
def approve(entry, by):
    """Tasdiqlash. Kutayotgan tahrir bo'lsa — eski holat versiyaga yoziladi, tahrir qo'llanadi."""
    if entry.pending:
        snapshot(entry, by, "tahrir tasdiqlandi")
        for f in ("title", "questions", "triggers", "extract", "answer", "answer_ru"):
            if f in entry.pending:
                setattr(entry, f, entry.pending[f])
        entry.pending = None
    entry.status = Entry.APPROVED
    entry.approved_by, entry.approved_at = by or "", timezone.now()
    entry.priority = False
    entry.save()
    return entry


def reject(entry, by):
    if entry.pending and entry.status == Entry.APPROVED:
        entry.pending = None  # faqat tahrir rad etildi, tasdiqlangan javob qoladi
    else:
        entry.status = Entry.REJECTED
    entry.approved_by = by or ""
    entry.save()
    return entry


# ====================================================================== oqimlar
def _full_name(u):
    return " ".join(x for x in (u.get("first_name"), u.get("last_name")) if x)[:150]


def _photo_id(msg):
    if msg.get("photo"):
        return msg["photo"][-1]["file_id"]  # eng katta o'lcham
    doc = msg.get("document") or {}
    if str(doc.get("mime_type", "")).startswith("image/"):
        return doc.get("file_id")
    return None


class BotWorker(threading.Thread):
    def __init__(self, bot_id, token):
        super().__init__(name=f"support-bot-{bot_id}", daemon=True)
        self.bot_id, self.token = bot_id, token
        self.stop_event = threading.Event()

    def run(self):
        client = Client(self.token)
        backoff = 5
        while not self.stop_event.is_set():
            close_old_connections()
            try:
                bot = Bot.objects.get(pk=self.bot_id)
                if not bot.username:
                    me = client.get_me()
                    Bot.objects.filter(pk=bot.pk).update(username=me.get("username", ""), tg_id=me.get("id"))
                updates = client.get_updates(bot.last_update_id + 1 if bot.last_update_id else None)
                handler = Handler(bot, client)
                for upd in updates or []:
                    if self.stop_event.is_set():
                        break
                    try:
                        handler.handle(upd)
                    except Exception:  # noqa: BLE001 — bitta xabar butun botni to'xtatmasin
                        log.exception("update %s failed", upd.get("update_id"))
                    Bot.objects.filter(pk=bot.pk).update(last_update_id=upd["update_id"])
                    handler.bot.last_update_id = upd["update_id"]
                Bot.objects.filter(pk=bot.pk).update(last_ok_at=timezone.now(), last_error="")
                backoff = 5
            except Bot.DoesNotExist:
                return
            except TelegramError as e:
                msg = str(e)
                if e.code == 409:
                    msg = "Boshqa jarayon shu token bilan ishlayapti (409). Bitta joyda ishlating."
                elif e.code == 401:
                    msg = "Token noto'g'ri (401). Panelda yangilang."
                Bot.objects.filter(pk=self.bot_id).update(last_error=msg[:500])
                log.warning("bot %s: %s", self.bot_id, msg)
                self.stop_event.wait(e.retry_after or backoff)
                backoff = min(backoff * 2, 120)
            except Exception as e:  # noqa: BLE001
                log.exception("bot %s loop error", self.bot_id)
                Bot.objects.filter(pk=self.bot_id).update(last_error=f"{type(e).__name__}: {e}"[:500])
                self.stop_event.wait(backoff)
                backoff = min(backoff * 2, 120)


def cleanup_media(days):
    root = media_dir()
    if not root.exists():
        return 0
    cutoff = time.time() - days * 86400
    removed = 0
    for f in root.rglob("*"):
        if f.is_file() and f.stat().st_mtime < cutoff:
            try:
                f.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def run_forever(poll=10):
    workers = {}
    last_cleanup = 0.0
    log.info("support runner started; OCR: %s", ocr.languages() or "yo'q")
    while True:
        close_old_connections()
        try:
            wanted = {}
            for b in Bot.objects.filter(enabled=True).exclude(token_enc=""):
                token = decrypt(b.token_enc)
                if token and b.mode != MODE_OFF:
                    wanted[b.id] = token
            for bid, w in list(workers.items()):
                if wanted.get(bid) != w.token or not w.is_alive():
                    w.stop_event.set()
                    workers.pop(bid)
            for bid, token in wanted.items():
                if bid not in workers:
                    w = BotWorker(bid, token)
                    w.start()
                    workers[bid] = w
            if time.time() - last_cleanup > 86400:
                cleanup_media(Settings.load().media_days)
                last_cleanup = time.time()
        except Exception:  # noqa: BLE001
            log.exception("runner loop error")
        time.sleep(poll)

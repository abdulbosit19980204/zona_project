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

from . import engine, ocr, vision
from .models import (MODE_COLLECT, MODE_LIVE, MODE_OFF, MODE_SHADOW, Bot, Entry, EntryVersion, Group, HistoryJob,
                     Media, Message, Settings)
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
class NullClient:
    """Tarixni o'qishda: hech kimga hech narsa yuborilmaydi."""

    def send(self, *a, **k):
        return None

    def typing(self, *a, **k):
        pass

    def edit_buttons(self, *a, **k):
        pass

    def answer_callback(self, *a, **k):
        pass

    def download(self, *a, **k):
        raise TelegramError("tarix rejimida yuklab bo'lmaydi")


class Handler:
    def __init__(self, bot: Bot, client: Client, history=False):
        self.bot = bot
        self.tg = client
        self.history = history       # guruh tarixi: faqat yig'ish va o'rganish, hech narsa yuborilmaydi
        self.photo_bytes = {}        # tarixda oldindan yuklangan rasmlar: message_id -> bytes
        self.settings = Settings.load()

    @staticmethod
    def when(msg):
        return msg.get("_date") or timezone.now()

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
        if not self.history:
            group.last_message_at = timezone.now()
        group.save()
        mode = MODE_COLLECT if self.history else group.effective_mode()
        user = engine.identify(sender["id"], sender.get("username", ""), _full_name(sender))
        text = (msg.get("text") or msg.get("caption") or "").strip()
        media = _media_of(msg) or (("history", "photo", "", "image/jpeg") if msg["message_id"] in self.photo_bytes else None)
        photo = media[0] if media else None
        self.media_meta = media
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")
        if mode == MODE_OFF:
            return None
        if user.is_staff:
            return self.on_staff(msg, group, user, text, reply_to)

        # savol egasining qo'shimcha ma'lumoti: xodimning aniqlashtiruvchi savoliga yoki botning so'roviga javob
        if reply_to:
            parent = Message.objects.filter(bot=self.bot, chat_id=chat["id"], message_id=reply_to).first()
            q = None
            if parent and parent.kind in (Message.CLARIFY, Message.INFO) and parent.question_id:
                q = parent.question
            elif not parent:
                q = Message.objects.filter(bot=self.bot, chat_id=chat["id"], bot_reply_id=reply_to,
                                           kind=Message.QUESTION).first()
            if q:
                return self.on_info(msg, group, user, text, photo, q, mode)

        if not engine.is_question(text, bool(photo)):
            return None
        q, created = Message.objects.get_or_create(
            bot=self.bot, chat_id=chat["id"], message_id=msg["message_id"],
            defaults={"group": group, "user": user, "text": text[:4000], "photo_file_id": photo or "",
                      "reply_to_id": reply_to, "kind": Message.QUESTION,
                      "source": "history" if self.history else "live"})
        if not created:
            return q  # takroriy yangilanish
        if self.history:
            q.created_at = self.when(msg)
            Message.objects.filter(pk=q.pk).update(created_at=q.created_at)
        self.process_question(q, mode)
        return q

    def on_info(self, msg, group, user, text, photo, q, mode):  # noqa: C901
        """Savol egasi so'ralgan ma'lumotni yubordi: zanjirga qo'shiladi; bot o'zi so'ragan bo'lsa — qayta javob beradi."""
        info, created = Message.objects.get_or_create(
            bot=self.bot, chat_id=msg["chat"]["id"], message_id=msg["message_id"],
            defaults={"group": group, "user": user, "text": text[:4000], "photo_file_id": photo or "",
                      "kind": Message.INFO, "question": q, "status": Message.CLOSED,
                      "reply_to_id": (msg.get("reply_to_message") or {}).get("message_id"),
                      "source": "history" if self.history else "live"})
        if not created:
            return info
        if self.history:
            info.created_at = self.when(msg)
            Message.objects.filter(pk=info.pk).update(created_at=info.created_at)
        if photo:
            m = self._fetch_media(info)
            if m and m.kind == Media.PHOTO and self.settings.ocr_enabled:
                self._ocr(info, m)
            info.save(update_fields=["photo_path", "ocr_text", "error"])
        if q.stage == "ask" and mode == MODE_LIVE:
            extra = "\n".join(x for x in (info.text, info.ocr_text) if x)
            q.text = (q.text + "\n" + extra).strip()[:4000]
            self.process_question(q, mode, skip_ask=True)
        return info

    def process_question(self, q, mode, skip_ask=False):
        settings = self.settings
        unapproved = mode in (MODE_SHADOW, MODE_COLLECT)
        media, image, deferred_ocr = None, None, False
        if q.photo_file_id:
            media = self._fetch_media(q)
        if media and media.kind == Media.PHOTO:
            if settings.image_match:
                entry, dist, _ex = vision.match(media, settings.image_threshold, include_unapproved=unapproved)
                if entry:
                    image = (entry, vision.confidence(dist))
            # rasm turi tanilgan va yozuv rasmdan maydon olmaydi -> OCR javobdan keyin (tezlik uchun)
            deferred_ocr = bool(image) and not image[0].extract and mode == MODE_LIVE
            if settings.ocr_enabled and not q.ocr_text and not deferred_ocr:
                self._ocr(q, media)
        raw = "\n".join(x for x in (q.text, q.ocr_text) if x).strip()
        q.lang = engine.detect_lang(q.text or q.ocr_text)
        if not raw and not image:
            q.status = Message.IGNORED
            q.save()
            return q
        if mode == MODE_LIVE:
            self.tg.typing(q.chat_id)
        d = engine.decide(raw, q.lang, allow_unapproved=unapproved, image=image)
        self._autolabel(media, d)
        try:
            return self._respond(q, d, mode, skip_ask)
        finally:
            if deferred_ocr and settings.ocr_enabled:
                self._ocr(q, media)
                Message.objects.filter(pk=q.pk).update(ocr_text=q.ocr_text)

    def _respond(self, q, d, mode, skip_ask):
        settings = self.settings
        q.stage, q.entry, q.confidence = d.stage, d.entry, d.confidence
        q.answer_text = d.text
        if d.entry:
            Entry.objects.filter(pk=d.entry.pk).update(uses=d.entry.uses + 1, last_used_at=timezone.now())

        if mode == MODE_COLLECT:
            q.status = Message.NEW  # faqat yig'ildi: javob taklifi tahlil uchun saqlanadi
            q.save()
            return q
        if mode == MODE_SHADOW:
            q.status = Message.DRAFTED
            q.save()
            if settings.drafts_to_admin:
                self._send_draft(q, d)
            return q

        # jonli rejim
        ask = engine.ask_first_text(d.entry, q.lang)
        if ask and settings.ask_first_prompt and not skip_ask and not q.photo_file_id and not d.needs_human:
            # xodimlar odatda avval so'raydigan ma'lumotni bot o'zi so'raydi; javob kelgach qayta ishlanadi
            sent = self._safe_send(q.chat_id, engine.to_html(ask), reply_to=q.message_id)
            q.stage, q.status = "ask", Message.NEW
            if sent:
                q.bot_reply_id = sent.get("message_id")
            q.save()
            return q
        if not d.needs_human and d.text:
            body = d.text
            line = engine.responsible_line(d.responsible, q.lang) if d.stage == "rule" else ""
            if line and settings.mention_responsible:
                body += "\n\n" + line
            buttons = ([[{"text": "👍", "callback_data": f"fb:{q.id}:1"}, {"text": "👎", "callback_data": f"fb:{q.id}:-1"}]]
                       if settings.feedback_buttons else None)
            sent = self._send_answer(q, engine.to_html(body, settings.signature), d.entry, buttons)
            if sent:
                q.status, q.answered_by, q.answered_at = Message.ANSWERED, "bot", timezone.now()
                q.bot_reply_id = sent.get("message_id")
            q.save()
            return q

        q.status = Message.ESCALATED
        q.save()
        if settings.escalation_ack:
            ack = ("Ваш вопрос принят." if q.lang == "ru" else "Savolingiz qabul qilindi.")
            if settings.mention_responsible and d.responsible and d.responsible[0].get("telegram"):
                tags = " ".join("@" + t for t in d.responsible[0]["telegram"][:3])
                ack += (" Ответит: " if q.lang == "ru" else " Javob beradi: ") + tags
            sent = self._safe_send(q.chat_id, engine.html.escape(ack), reply_to=q.message_id)
            if sent:
                Message.objects.filter(pk=q.pk).update(bot_reply_id=sent.get("message_id"))
        if settings.drafts_to_admin:
            self._send_draft(q, d, escalated=True)
        return q

    # ---------------------------------------------------------------- xodim javobi -> o'rganish
    def on_staff(self, msg, group, user, text, reply_to):
        """Xodim savolga (yoki savol egasining qo'shimcha ma'lumotiga) reply qildi.

        Aniqlashtiruvchi savol ("STIR yuboring", "skrin tashlang?") javob deb olinmaydi — zanjirda saqlanadi va
        keyin "javobdan oldin so'raladigan ma'lumot" sifatida o'rganiladi. Yakuniy javob — bilim bazasiga nomzod.
        """
        if not text or not reply_to:
            return None
        parent = Message.objects.filter(bot=self.bot, chat_id=msg["chat"]["id"], message_id=reply_to).first()
        if not parent:
            return None
        q = parent if parent.kind == Message.QUESTION else parent.question
        if not q or q.kind != Message.QUESTION:
            return None
        settings = self.settings
        staff_name = user.staff_name()
        clarify = settings.learn_clarifications and engine.is_clarifying(text)
        a, created = Message.objects.get_or_create(
            bot=self.bot, chat_id=msg["chat"]["id"], message_id=msg["message_id"],
            defaults={"group": group, "user": user, "text": text[:4000], "question": q, "reply_to_id": reply_to,
                      "kind": Message.CLARIFY if clarify else Message.STAFF, "status": Message.CLOSED,
                      "stage": "clarify" if clarify else "staff", "source": "history" if self.history else "live"})
        if not created:
            return a
        when = self.when(msg)
        if self.history:
            a.created_at = when
            Message.objects.filter(pk=a.pk).update(created_at=when)
        if clarify:
            return a
        corrected = q.status == Message.ANSWERED and q.answered_by == "bot"
        if q.status != Message.ANSWERED or corrected:
            q.status, q.stage, q.answered_by, q.answered_at = Message.ANSWERED, "staff", staff_name, when
            q.save()
        if settings.learn_from_staff:
            asks = list(q.staff_replies.filter(kind=Message.CLARIFY).order_by("created_at").values_list("text", flat=True))
            entry, new = learn(q, text, staff_name, priority=corrected, ask_first="\n".join(asks),
                               source="history" if self.history else "staff")
            if new and settings.notify_candidates and not self.history:
                self._send_candidate(entry, q, staff_name)
            if entry and settings.image_autolabel:
                vision.label(Media.objects.filter(message=q, kind=Media.PHOTO), entry, staff_name, auto=True)
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
                sent = self._send_answer(q, engine.to_html(q.answer_text, Settings.load().signature), q.entry)
                if sent and self.settings.image_autolabel and q.entry_id:  # admin tasdiqladi -> rasm namunasi
                    vision.label(Media.objects.filter(message=q, kind=Media.PHOTO), q.entry, by, auto=True)
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
    def _fetch_media(self, q):
        """Savoldagi faylni serverga saqlaydi (Media). Rasm uchun vizual iz hisoblanadi."""
        existing = Media.objects.filter(message=q).first()
        if existing:
            return existing
        file_id, kind, name, mime = getattr(self, "media_meta", None) or (q.photo_file_id, "photo", "", "")
        data = self.photo_bytes.get(q.message_id)
        if data is None:
            try:
                data = self.tg.download(file_id, max_bytes=(8 if kind == "photo" else 20) * 1024 * 1024)
            except TelegramError as e:
                q.error = f"Fayl olinmadi: {e}"[:300]
                return None
        m = vision.store(data, kind=kind, name=name, mime=mime, source="history" if self.history else "question", message=q)
        q.photo_path = m.path
        return m

    def _ocr(self, q, media):
        if not media or media.kind != Media.PHOTO:
            return
        if media.ocr_text:
            q.ocr_text = media.ocr_text
            return
        try:
            data = open(media.path, "rb").read() if media.path else self.photo_bytes.get(q.message_id)
        except OSError:
            data = self.photo_bytes.get(q.message_id)
        q.ocr_text = ocr.read_text(data or b"")
        Media.objects.filter(pk=media.pk).update(ocr_text=q.ocr_text)

    def _autolabel(self, media, d):
        """Ishonchli moslik (tasdiqlangan shablon/javob, ≥90%) — rasmni shu yozuvning namunasi qilib o'rganadi."""
        if (media and media.kind == Media.PHOTO and not media.label_id and self.settings.image_autolabel and d.entry
                and d.entry.status == Entry.APPROVED and d.stage in ("template", "faq") and d.confidence >= 90):
            vision.label([media], d.entry, "bot", auto=True)

    def _send_answer(self, q, body_html, entry=None, buttons=None):
        """Javob matni + (bo'lsa) yozuvga biriktirilgan rasm/video/fayllar, savolga reply qilib."""
        sent = self._safe_send(q.chat_id, body_html, reply_to=q.message_id, buttons=buttons)
        ids = list(entry.attachments or []) if entry else []
        if sent and ids:
            files = {m.id: m for m in Media.objects.filter(id__in=ids)}
            items, order = [], []
            for i in ids:
                m = files.get(i)
                if not m:
                    continue
                fid = (m.tg_file_ids or {}).get(str(self.bot.id))
                data = None
                if not fid:
                    try:
                        data = open(m.path, "rb").read()
                    except OSError:
                        continue
                items.append({"kind": m.kind, "name": m.name or f"file{m.id}", "data": data, "file_id": fid})
                order.append(m)
            if items:
                try:
                    new_ids = self.tg.send_media(q.chat_id, items, reply_to=q.message_id)
                    for m, fid in zip(order, new_ids or []):
                        if fid and (m.tg_file_ids or {}).get(str(self.bot.id)) != fid:
                            Media.objects.filter(pk=m.pk).update(tg_file_ids={**(m.tg_file_ids or {}), str(self.bot.id): fid})
                except TelegramError as e:
                    log.warning("send_media failed: %s", e)
        return sent

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
        if d.entry and d.entry.attachments:
            parts.append(f"📎 {len(d.entry.attachments)} ta fayl javob bilan yuboriladi")
        if d.stage == "image":
            parts.append("🖼 Rasm turi o'rgatilgan namunadan tanildi")
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
def learn(q, answer, staff_name, priority=False, ask_first="", source="staff"):
    """Xodim javobidan bilim bazasiga nomzod (status=new). Tasdiqlanmaguncha bot uni ishlatmaydi.

    Qaytaradi: (yozuv, yangimi). Juda o'xshash nomzod bor bo'lsa — yangisi ochilmaydi, savol ko'rinishi unga qo'shiladi;
    tasdiqlangan javob allaqachon bor bo'lsa (va bot javobi tuzatilmagan bo'lsa) — nomzod kerak emas.
    """
    question = q.text.strip() or q.ocr_text.strip()[:300]
    if not question or len(answer.strip()) < 3:
        return None, False
    pool = list(Entry.objects.filter(kind=Entry.FAQ, status__in=[Entry.NEW, Entry.REVIEW, Entry.APPROVED]))
    match, score = engine.match_faq(question, pool)
    if match and score >= 88:
        if match.status == Entry.APPROVED and not priority:
            return match, False
        if match.status in (Entry.NEW, Entry.REVIEW):
            match.questions = list(dict.fromkeys([*(match.questions or []), question[:1000]]))[:50]
            if ask_first and not match.ask_first:
                match.ask_first = ask_first[:1000]
            match.priority = match.priority or priority
            match.save(update_fields=["questions", "ask_first", "priority", "updated_at"])
            return match, False
    title = question.splitlines()[0][:190]
    return Entry.objects.create(kind=Entry.FAQ, title=title, questions=[question[:1000]], answer=answer.strip(),
                                ask_first=ask_first[:1000], status=Entry.NEW, source=source, author=staff_name,
                                priority=priority), True


def snapshot(entry, editor, note=""):
    EntryVersion.objects.create(entry=entry, title=entry.title, questions=entry.questions, triggers=entry.triggers,
                                extract=entry.extract, answer=entry.answer, answer_ru=entry.answer_ru,
                                editor=editor or "", note=note[:200])


@transaction.atomic
def approve(entry, by):
    """Tasdiqlash. Kutayotgan tahrir bo'lsa — eski holat versiyaga yoziladi, tahrir qo'llanadi."""
    if entry.pending:
        snapshot(entry, by, "tahrir tasdiqlandi")
        for f in ("title", "questions", "triggers", "extract", "answer", "answer_ru", "ask_first"):
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


def _media_of(msg):
    """Xabardagi fayl: (file_id, tur, nomi, mime) yoki None. Rasm-hujjat ham rasm sifatida (iz va OCR uchun)."""
    if msg.get("photo"):
        return msg["photo"][-1]["file_id"], "photo", "", "image/jpeg"  # eng katta o'lcham
    for kind in ("video", "video_note", "animation"):
        v = msg.get(kind)
        if v:
            return v["file_id"], kind, v.get("file_name", ""), v.get("mime_type", "video/mp4")
    doc = msg.get("document") or {}
    if doc.get("file_id"):
        mime = str(doc.get("mime_type", ""))
        return doc["file_id"], "photo" if mime.startswith("image/") else "document", doc.get("file_name", ""), mime
    return None


def _photo_id(msg):
    m = _media_of(msg)
    return m[0] if m else None


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


def _history_thread(job_id):
    from .history import run_job
    close_old_connections()
    try:
        run_job(job_id)
    except Exception as e:  # noqa: BLE001
        log.exception("history job %s failed", job_id)
        HistoryJob.objects.filter(pk=job_id).update(status=HistoryJob.FAILED, error=f"{type(e).__name__}: {e}"[:500],
                                                    finished_at=timezone.now())
    finally:
        close_old_connections()


def run_forever(poll=10):
    workers = {}
    history = None
    last_cleanup = 0.0
    # jarayon qayta ishga tushsa, chala qolgan vazifa qayta navbatga qo'yiladi
    HistoryJob.objects.filter(status=HistoryJob.RUNNING).update(status=HistoryJob.QUEUED)
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
            if history is None or not history.is_alive():
                job = HistoryJob.objects.filter(status=HistoryJob.QUEUED).order_by("created_at").first()
                if job:
                    history = threading.Thread(target=_history_thread, args=(job.id,), name="support-history", daemon=True)
                    history.start()
            if time.time() - last_cleanup > 86400:
                vision.cleanup(Settings.load().media_days)
                last_cleanup = time.time()
        except Exception:  # noqa: BLE001
            log.exception("runner loop error")
        time.sleep(poll)

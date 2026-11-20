"""Bot jarayoni: har bir yoqilgan bot uchun alohida oqim, Telegram'dan long-polling.

Admin paneldagi o'zgarishlar (yoqish/o'chirish, rejim, token) qayta ishga tushirmasdan ~10 soniyada kuchga kiradi.
Xabar avval bazaga yoziladi, keyin qayta ishlanadi: jarayon qayta ishga tushsa ham savol yo'qolmaydi.
"""
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.conf import settings as dj_settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from zona import conf
from zona.crypto import decrypt

from . import contacts, engine, ocr, translit, vision
from .models import (MODE_COLLECT, MODE_LIVE, MODE_OFF, MODE_SHADOW, Bot, Entry, EntryVersion, Group, HistoryJob,
                     Media, Message, Settings, TgUser)
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
    def __init__(self, bot: Bot, client: Client, history=False, executor=None):
        self.bot = bot
        self.tg = client
        self.executor = executor     # savollarni parallel qayta ishlash (OCR/qidiruv boshqa xabarlarni to'xtatmasin)
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
            if chat.get("type") in ("group", "supergroup"):
                from . import tasks
                tasks.capture_reply(msg)
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
        if text.startswith("/kontakt") or text.startswith("/contact") or (
                text and not text.startswith("/") and self.settings.contact_lookup):
            return self.on_contact_lookup(msg, user, text.split(" ", 1)[1] if text.startswith("/") and " " in text else
                                          ("" if text.startswith("/") else text))
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

    # ---------------------------------------------------------------- kontakt qidiruvi
    LOOKUP_ROLES = {"ROP", "RSM", "ASM", "KAM", "SVR"}

    def can_lookup(self, user, chat_id):
        """Telefon raqamlari: bizning xodimlar, admin chat va rahbar darajasidagi dala xodimlari (agentlarga emas)."""
        if chat_id == self.bot.admin_chat_id or user.is_staff:
            return True
        return bool(user.staff_person_id and user.staff_person.role in self.LOOKUP_ROLES)

    def on_contact_lookup(self, msg, user, query):
        chat_id = msg["chat"]["id"]
        esc = engine.html.escape
        if not self.settings.contact_lookup:
            return None
        if not self.can_lookup(user, chat_id):
            return self._safe_send(chat_id, "🔒 Kontakt ma'lumotlari faqat xodimlar va rahbarlar uchun.")
        try:
            self.tg.typing(chat_id)
        except Exception:  # noqa: BLE001
            pass
        results, q, how = contacts.smart_search(query, deadline=15.0)
        if q.empty and how != "ai":
            return self._safe_send(chat_id, "🔎 <b>Kontakt qidiruvi</b>\nBrend, lavozim, hudud yoki ism yozing. Masalan:\n"
                                            "• <i>L'Oréal ROP</i>\n• <i>Jizzax supervayzeri</i>\n• <i>Heinz SVR Toshkent</i>\n"
                                            "• <i>Saidabror telefoni</i>")
        if not results:
            return self._safe_send(chat_id, f"Topilmadi: <i>{esc(contacts.describe(q))}</i>\n"
                                            "Brend nomi (BIC, Heinz, JJ, L'Oréal), lavozim (ROP, RSM, SVR, agent) yoki hududni tekshiring.")
        if how in ("yaqin", "ai"):
            note = "🤖 AI so'rovni shunday tushundi" if how == "ai" else "🔎 Aniq moslik yo'q — eng yaqin natijalar"
            self._safe_send(chat_id, f"{note}: <i>{esc(contacts.describe(q))}</i>")
        if len(results) > 6:
            lines = [f"🔎 <b>{len(results)} ta topildi</b> ({esc(contacts.describe(q))}). Aniqroq yozing — masalan, hudud yoki ism qo'shing:"]
            for r in results[:15]:
                lines.append(f"• {esc(r['name'])} — {esc(r['role'])} · {esc(r['brand'])}"
                             + (f" · {esc(r['place'] or r['unit'])}" if (r['place'] or r['unit']) else "")
                             + (f" · <code>{esc(r['phone'])}</code>" if r["phone"] else ""))
            return self._safe_send(chat_id, "\n".join(lines))
        for r in results:
            self._safe_send(chat_id, contacts.card_html(r))
            phone = "".join(ch for ch in (r["phone"] or "") if ch.isdigit() or ch == "+")
            if len(phone) >= 9:
                parts = r["name"].split()
                try:
                    self.tg.send_contact(chat_id, phone, parts[0] if parts else r["name"], " ".join(parts[1:3]),
                                         contacts.vcard(r))
                except TelegramError as e:
                    log.warning("send_contact failed: %s", e)
        return results

    # ---------------------------------------------------------------- guruh xabari
    def on_group(self, msg):
        chat, sender = msg["chat"], msg["from"]
        group, created = Group.objects.get_or_create(bot=self.bot, chat_id=chat["id"],
                                                     defaults={"title": chat.get("title", "")})
        if created or group.title != chat.get("title", group.title):
            group.title = chat.get("title", group.title)
        if chat.get("username") and group.username != chat["username"]:
            group.username = chat["username"]
        if not self.history:
            group.last_message_at = timezone.now()
        group.save()
        mode = MODE_COLLECT if self.history else group.effective_mode()
        user = engine.identify(sender["id"], sender.get("username", ""), _full_name(sender))
        if not self.history:  # faollik hisobi (har bir guruh xabari) — xodimlar ishini tahlil qilish uchun
            from django.db.models import F as _F
            TgUser.objects.filter(pk=user.pk).update(msg_count=_F("msg_count") + 1, last_msg_at=timezone.now())
        text = (msg.get("text") or msg.get("caption") or "").strip()
        media = _media_of(msg) or (("history", "photo", "", "image/jpeg") if msg["message_id"] in self.photo_bytes else None)
        photo = media[0] if media else None
        self.media_meta = media
        reply_to = (msg.get("reply_to_message") or {}).get("message_id")
        if mode == MODE_OFF:
            return None
        if text.startswith("/kontakt") or text.startswith("/contact"):
            # telefon raqamlari guruhga chiqarilmaydi
            uname = self.bot.username or "bot"
            return self._safe_send(chat["id"], engine.html.escape(f"Kontakt qidiruvi faqat shaxsiy chatda: @{uname} ga yozing."),
                                   reply_to=msg["message_id"])
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

        mgid = str(msg.get("media_group_id") or "")
        if mgid:
            first = Message.objects.filter(bot=self.bot, chat_id=chat["id"], media_group_id=mgid, kind=Message.QUESTION).first()
            if first:  # albomning keyingi rasmi — o'sha savolga qo'shiladi, alohida javob bo'lmaydi
                return self._album_part(first, msg, text)
        merged = self._merge_recent(chat, user, msg, text, photo)
        if merged is not None:  # skrinshot va alohida izoh (bir muallif, bir necha soniya) — bitta savol, bitta javob
            return merged
        if not engine.is_question(text, bool(photo)):
            if text and not photo and not self.history:
                Handler._recent_text[(chat["id"], user.pk)] = (time.time(), text)  # keyingi rasmga izoh bo'lishi mumkin
            return None
        if photo and not text and not self.history:
            prev_text = Handler._recent_text.pop((chat["id"], user.pk), None)
            if prev_text and time.time() - prev_text[0] <= (self.settings.merge_window or 0):
                text = prev_text[1]
        q, created = Message.objects.get_or_create(
            bot=self.bot, chat_id=chat["id"], message_id=msg["message_id"],
            defaults={"group": group, "user": user, "text": text[:4000], "photo_file_id": photo or "",
                      "reply_to_id": reply_to, "kind": Message.QUESTION, "media_group_id": mgid,
                      "source": "history" if self.history else "live"})
        if not created:
            return q  # takroriy yangilanish
        if self.history:
            q.created_at = self.when(msg)
            Message.objects.filter(pk=q.pk).update(created_at=q.created_at)
        if self.executor is not None:
            meta, data = getattr(self, "media_meta", None), self.photo_bytes.get(q.message_id)
            # albom/izoh kutish — taymer bilan: worker uxlab o'tirmaydi, boshqa savollar shu vaqtda javob oladi
            wait = 1.5 if mgid else 0.0
            if text and not photo and not engine.substantive(text) and (self.settings.merge_window or 0):
                wait = 3.5  # qisqa matn — ortidan rasm kelishi mumkin
            # yolg'iz rasm kutmaydi: tanilgan ekran darhol javob oladi (tanilmasa — _process_question o'zi kechiktiradi)
            recv = max(0, int((time.time() - (msg.get("date") or time.time())) * 1000))
            meta_t = {"recv": recv, "wait": int(wait * 1000)}
            if wait:
                timer = threading.Timer(wait, self._submit, args=(q.pk, mode, meta, data, meta_t))
                timer.daemon = True
                timer.start()
            else:
                self.executor.submit(self._process_async, q.pk, mode, meta, data, {**meta_t, "queued": time.time()})
            return q
        self.process_question(q, mode)
        return q

    _recent_text: dict = {}  # (chat, user) -> (vaqt, matn): savol deb olinmagan qisqa izoh (keyin rasm kelishi mumkin)

    def _merge_recent(self, chat, user, msg, text, photo):
        """Shu muallifning bir necha soniya oldingi savoli bilan birlashtirish: rasm + keyin izoh yoki matn + keyin rasm."""
        win = self.settings.merge_window or 0
        if not win or self.history or msg.get("media_group_id"):
            return None
        prev = (Message.objects.filter(bot=self.bot, chat_id=chat["id"], user=user, kind=Message.QUESTION,
                                       created_at__gte=timezone.now() - timezone.timedelta(seconds=win)).order_by("-id").first())
        if prev is None:
            return None
        if text and not photo and prev.photo_file_id and not engine.substantive(prev.text):
            if prev.status != Message.NEW and engine.substantive(text):
                return None  # rasmga javob berib bo'lingan, bu esa aniq yangi savol — alohida javob beriladi
            Message.objects.filter(pk=prev.pk).update(text=(prev.text + "\n" + text).strip()[:4000])
            return prev
        if photo and not prev.photo_file_id and not engine.substantive(text):
            if not Message.objects.filter(pk=prev.pk, status=Message.NEW, stage="").update(photo_file_id=photo):
                self._album_part(prev, msg, text)  # savolga javob berilgan — rasm faqat saqlanadi (ikkinchi javob yo'q)
            elif text:
                Message.objects.filter(pk=prev.pk).update(text=(prev.text + "\n" + text).strip()[:4000])
            return prev
        return None

    def _album_part(self, q, msg, text):
        """Albom (bir vaqtda yuborilgan bir nechta rasm/video): fayl o'sha savolga biriktiriladi, izoh matnga qo'shiladi.
        Yuklash fon oqimida — asosiy sikl (yangi xabarlarni qabul qilish) hech qachon kutib qolmaydi."""
        meta = _media_of(msg)
        if meta and not Media.objects.filter(message=q, kind=meta[1]).filter(name=f"album:{msg['message_id']}").exists():
            def fetch():
                close_old_connections()
                try:
                    data = self.photo_bytes.get(msg["message_id"]) or self.tg.download(meta[0], max_bytes=(8 if meta[1] == "photo" else 20) * 1024 * 1024)
                    vision.store(data, kind=meta[1], name=f"album:{msg['message_id']}", mime=meta[3], source=q.source, message=q)
                except TelegramError as e:
                    log.warning("album part failed: %s", e)
                finally:
                    if self.executor is not None:
                        close_old_connections()
            if self.executor is not None and not self.history:
                threading.Thread(target=fetch, name="support-album", daemon=True).start()
            else:
                fetch()
        if text and text not in q.text:
            Message.objects.filter(pk=q.pk).update(text=(q.text + "\n" + text).strip()[:4000])
        return q

    def _later(self, wait, qid, mode, meta, data, meta_t):
        timer = threading.Timer(wait, self._submit, args=(qid, mode, meta, data, meta_t))
        timer.daemon = True
        timer.start()

    def _submit(self, qid, mode, meta, data, meta_t):
        """Taymerdan keyin navbatga qo'yish. Pool yopilgan bo'lsa (bot oqimi qayta ishga tushdi) — savol yo'qolmasin."""
        try:
            self.executor.submit(self._process_async, qid, mode, meta, data, {**meta_t, "queued": time.time()})
        except RuntimeError:
            self._process_async(qid, mode, meta, data, {**meta_t, "queued": time.time()})

    def _process_async(self, qid, mode, meta, data, timing=None):
        """Fon oqimida: alohida Handler (holat aralashmasin), o'z DB ulanishi."""
        close_old_connections()
        try:
            h = Handler(self.bot, self.tg)
            t = dict(timing or {})
            if "queued" in t:
                t["queue"] = int((time.time() - t.pop("queued")) * 1000)  # bo'sh worker kutilgan vaqt
            h.timing = t
            if not t.get("deferred"):
                base = {k: v for k, v in t.items() if k in ("recv", "wait")}
                h.defer = lambda: self._later(3.0, qid, mode, meta, data, {**base, "deferred": 1, "wait": base.get("wait", 0) + 3000})
            h.media_meta = meta
            if data is not None:
                h.photo_bytes[0] = data
            q = Message.objects.select_related("user", "group").get(pk=qid)
            if data is not None:
                h.photo_bytes[q.message_id] = data
            h.process_question(q, mode)
        except Exception:  # noqa: BLE001
            log.exception("question %s failed", qid)
        finally:
            close_old_connections()

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
        t0 = time.monotonic()
        marks = {}
        try:
            return self._process_question(q, mode, skip_ask, marks)
        finally:
            pg = getattr(self, "progress", None)
            if pg is not None and not marks.get("deferred"):
                pg.stop()
            marks["work"] = int((time.monotonic() - t0) * 1000)
            try:
                Message.objects.filter(pk=q.pk).update(timing={**getattr(self, "timing", {}), **marks})
            except Exception:  # noqa: BLE001 — o'lchov javobni to'xtatmasin
                pass

    def _process_question(self, q, mode, skip_ask, marks):
        settings = self.settings
        unapproved = mode in (MODE_SHADOW, MODE_COLLECT)
        media, image, deferred_ocr = None, None, False
        tick = time.monotonic()
        pg = self.progress = Progress(self.tg, q, mode == MODE_LIVE and settings.progress_messages and not self.history,
                                      existing=(q.timing or {}).get("ph"))
        if pg.enabled:
            q.lang = engine.detect_lang(q.text) if (q.text or "").strip() else (q.lang or "uz")
            pg.begin()  # har bir savolga darhol reply va animatsiya

        def mark(name):
            nonlocal tick
            now = time.monotonic()
            marks[name] = marks.get(name, 0) + int((now - tick) * 1000)
            tick = now
        if q.photo_file_id:
            pg.phase("photo")
            media = self._fetch_media(q)
        images, photos = [], []
        if media and settings.image_match:
            # albomdagi HAR BIR rasm alohida tanib olinadi (turli mavzudagi ekranlar bo'lishi mumkin)
            photos = sorted(Media.objects.filter(message=q, kind=Media.PHOTO).exclude(dhash="")[:10], key=_album_order)
            best = None
            for idx, m in enumerate(photos):
                entry, dist, _ex = vision.match(m, settings.image_threshold, include_unapproved=unapproved)
                if entry:
                    images.append((entry, vision.confidence(dist), idx))
                    if best is None or dist < best[1]:
                        best, media = (entry, dist), m
            if best:
                image = (best[0], vision.confidence(best[1]))
        mark("media")
        if (not (q.text or "").strip() and media is not None and not images and (settings.merge_window or 0)
                and mode == MODE_LIVE and getattr(self, "defer", None) and not q.media_group_id):
            marks["ph"] = pg.id  # izoh kutilyapti — animatsiya davom etadi, qayta ishlashda o'sha xabar ishlatiladi
            self.defer()  # ekran tanilmadi — izoh kelishini 3 s kutamiz (worker band bo'lmaydi), keyin qayta ishlanadi
            marks["deferred"] = 1
            return q
        q.lang = engine.detect_lang(q.text or q.ocr_text)
        if mode == MODE_LIVE:
            self.tg.typing(q.chat_id)
        d = None
        if media and media.kind == Media.PHOTO and not q.ocr_text:
            strong = engine.substantive(q.text)
            if strong or (image and not image[0].extract and len({e.pk for e, _c, _i in images}) == 1):
                # tez yo'l: aniq matnli savol yoki tanilgan ekran — OCR'ni kutmasdan javob, OCR keyin (tahlil uchun)
                d = engine.decide(q.text or "", q.lang, allow_unapproved=unapproved, text=q.text, images=images, fast=True)
                deferred_ocr = d is not None and mode == MODE_LIVE
                mark("decide")
            if settings.ocr_enabled and not deferred_ocr:
                pg.phase("photo")
                self._ocr(q, media)
                mark("ocr")
        if d is None:
            raw = "\n".join(x for x in (q.text, q.ocr_text) if x).strip()
            if not raw and not images:
                pg.drop()
                q.status = Message.IGNORED
                q.save()
                return q
            q.lang = engine.detect_lang(q.text or q.ocr_text)
            pg.phase("think")
            d = engine.decide(raw, q.lang, allow_unapproved=unapproved, text=q.text, ocr=q.ocr_text, images=images,
                              asker=_asker(q), fast=True)  # avval tez (shablon/baza)
            if d is None:
                pg.phase("write")  # AI kutilayotganda matn almashib turadi
                try:
                    d = engine.decide(raw, q.lang, allow_unapproved=unapproved, text=q.text, ocr=q.ocr_text, images=images,
                                      asker=_asker(q))
                finally:
                    pg.stop()
            mark("decide")
        if len(photos) <= 1:
            self._autolabel(media, d)
        try:
            res = self._respond(q, d, mode, skip_ask)
            mark("send")
            if mode == MODE_LIVE and q.stage not in ("dup", "ask"):
                from . import tasks
                tasks.maybe_create(q, d, self.tg)  # PRBC vazifasi: mas'ulga eslatma (bot o'zi yozadi)
            return res
        finally:
            if deferred_ocr and settings.ocr_enabled:
                self._ocr(q, media)
                Message.objects.filter(pk=q.pk).update(ocr_text=q.ocr_text)

    def _duplicate_of(self, q, d):
        """Shu xodim qisqa vaqt ichida (album_window) shu savolni yuborgan va javob olgan/uzatilgan bo'lsa — takror."""
        if not q.user_id or self.history:
            return None
        since = q.created_at - timezone.timedelta(seconds=self.settings.album_window or 90)
        prev = (Message.objects.filter(bot=self.bot, chat_id=q.chat_id, user_id=q.user_id, kind=Message.QUESTION,
                                       created_at__gte=since).exclude(pk=q.pk).order_by("-created_at").first())
        if not prev:
            return None
        if d.entry and prev.entry_id == d.entry.id and prev.status == Message.ANSWERED:
            return prev
        if d.entry is None and not (q.text or "").strip() and prev.status in (Message.ESCALATED, Message.ANSWERED, Message.NEW):
            return prev  # tanilmagan matnsiz qo'shimcha rasm — oldingi savolning davomi
        return None  # boshqa turdagi ekran — alohida javob

    _answered: dict = {}  # (chat, user, yozuv) -> (vaqt, savol id): parallel kelgan bir xil rasmlar ikkalasi javob olmasin
    _answered_lock = threading.Lock()

    def _claim(self, q, entry):
        """Shu odamga shu javob (yozuv) yaqinda berilganmi; bo'lmasa — band qiladi. Qaytaradi: oldingi savol yoki None."""
        if entry is None or not q.user_id or self.history:
            return None
        key, now = (q.chat_id, q.user_id, entry.pk), time.time()
        win = self.settings.album_window or 90
        with Handler._answered_lock:
            old = Handler._answered.get(key)
            if old and now - old[0] < win and old[1] != q.pk:
                return Message.objects.filter(pk=old[1]).first()
            Handler._answered[key] = (now, q.pk)
        return None

    def _respond(self, q, d, mode, skip_ask):
        settings = self.settings
        if mode == MODE_LIVE:
            prev = self._duplicate_of(q, d) or (None if d.parts else self._claim(q, d.entry))
            if prev:
                self._dup_note(q, prev)
                q.status, q.stage, q.question = Message.CLOSED, "dup", prev
                q.save()
                return q
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
            ask_html = engine.to_html(self._script(q, ask))
            sent = self._pg().finish(ask_html) or self._safe_send(q.chat_id, ask_html, reply_to=q.message_id)
            q.stage, q.status = "ask", Message.NEW
            if sent:
                q.bot_reply_id = sent.get("message_id")
            q.save()
            return q
        if not d.needs_human and d.text and not engine.allowed(d, settings):
            # o'rganish rejimi: bot taklifi saqlanadi (panelda va admin chatida), guruhga faqat "qabul qilindi"
            q.status = Message.DRAFTED
            q.save()
            ack = ("Ваш вопрос принят — ответит специалист 🙌" if q.lang == "ru" else "Savolingiz qabul qilindi — mutaxassis javob beradi 🙌")
            if settings.mention_responsible and d.responsible and d.responsible[0].get("telegram"):
                ack += " " + " ".join("@" + t for t in d.responsible[0]["telegram"][:3])
            if settings.escalation_ack:
                sent = self._pg().finish(engine.html.escape(ack)) or self._safe_send(q.chat_id, engine.html.escape(ack), reply_to=q.message_id)
                if sent:
                    Message.objects.filter(pk=q.pk).update(bot_reply_id=sent.get("message_id"))
            else:
                self._pg().drop()
            if settings.drafts_to_admin:
                self._send_draft(q, d)
            d.needs_human = True  # PRBC vazifasi va tahlil uchun — odam javob beradi
            return q
        if not d.needs_human and d.text and len(d.parts) > 1:
            return self._respond_parts(q, d, settings)
        if not d.needs_human and d.text:
            body = self._script(q, engine.vary(d, q.lang, settings))
            line = engine.responsible_line(d.responsible, q.lang) if d.stage == "rule" else ""
            if line and settings.mention_responsible:
                body += "\n\n" + line
            buttons = ([[{"text": "👍", "callback_data": f"fb:{q.id}:1"}, {"text": "👎", "callback_data": f"fb:{q.id}:-1"}]]
                       if settings.feedback_buttons else None)
            sent = self._send_answer(q, self._decorate(q, d, engine.to_html(body, settings.signature)), d.entry, buttons)
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
            sent = self._pg().finish(engine.html.escape(ack)) or self._safe_send(q.chat_id, engine.html.escape(ack), reply_to=q.message_id)
            if sent:
                Message.objects.filter(pk=q.pk).update(bot_reply_id=sent.get("message_id"))
        else:
            self._pg().drop()
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
        if settings.learn_from_staff and corrected and q.entry_id and not self.history and len(text.strip()) >= 15:
            from . import selflearn
            if selflearn.on_correction(q, user, text):  # AI yozuvni xodim tuzatishi bilan yaxshilaydi
                return a
        if settings.learn_from_staff:
            asks = list(q.staff_replies.filter(kind=Message.CLARIFY).order_by("created_at").values_list("text", flat=True))
            entry, new = learn(q, text, staff_name, priority=corrected, ask_first="\n".join(asks),
                               source="history" if self.history else "staff")
            if new and not self.history and len(text.strip()) >= 25 and not engine.ANSWER_HINT.fullmatch(text.strip()):
                from . import selflearn
                if selflearn.trusted(user, settings):  # ishonchli xodim — darhol tasdiqlanadi (bot keyingi safar o'zi javob beradi)
                    approve(entry, f"avto: {staff_name}")
                    new = False
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
                if q.feedback > 0:
                    from . import selflearn
                    selflearn.on_feedback(q)
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
        # albom bo'laklari (album:<id>) asosiy rasmdan oldin saqlanib qolishi mumkin — ularni asosiy rasm deb olmaymiz
        existing = Media.objects.filter(message=q).exclude(name__startswith="album:").first()
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
        with _OCR_SLOTS:  # OCR protsessorni ko'p yeydi — bir vaqtda cheklangan son (qolgan ishlar to'xtamaydi)
            q.ocr_text = ocr.read_text(data or b"")
        Media.objects.filter(pk=media.pk).update(ocr_text=q.ocr_text)

    def _autolabel(self, media, d):
        """Ishonchli moslik (tasdiqlangan shablon/javob, ≥90%) — rasmni shu yozuvning namunasi qilib o'rganadi."""
        if (media and media.kind == Media.PHOTO and not media.label_id and not media.ignored and self.settings.image_autolabel and d.entry
                and d.entry.status == Entry.APPROVED and d.stage in ("template", "faq") and d.confidence >= 90):
            vision.label([media], d.entry, "bot", auto=True)

    @staticmethod
    def _script(q, text):
        """Savol o'zbek kirilida bo'lsa — javob matni ham kirillga o'giriladi."""
        return translit.lat2cyr(text) if text and translit.is_uz_cyrillic(q.text) else text

    def _decorate(self, q, d, body_html):
        """Javob boshida savol beruvchi; supervayzer harakati kerak bo'lsa — uning supervayzeri (kontaktlar bo'yicha)."""
        s = self.settings
        head = engine.mention_html(q.user) + ", " if s.mention_asker and q.user else ""
        tail = ""
        if s.mention_supervisor and q.user and engine.needs_supervisor(d):
            line = engine.supervisor_line(q.user, q.lang)
            if line:
                tail = "\n\n" + line
        return head + body_html + tail

    def _send_answer(self, q, body_html, entry=None, buttons=None):
        """Javob matni + (bo'lsa) yozuvga biriktirilgan rasm/video/fayllar, savolga reply qilib."""
        sent = self._pg().finish(body_html, buttons) or self._safe_send(q.chat_id, body_html, reply_to=q.message_id, buttons=buttons)
        ids = list(entry.attachments or []) if entry else []
        if sent and ids and self.executor is not None and not self.history:
            # fayllar fonda: javob matni darhol, video/rasm ortidan (worker keyingi savolga o'tadi)
            threading.Thread(target=self._send_files, args=(q, ids), name="support-files", daemon=True).start()
        elif sent and ids:
            self._send_files(q, ids)
        return sent

    def _send_files(self, q, ids):
        """Javob fayllari (rasm/video/hujjat). Saqlangan file_id bo'lsa — qayta yuklanmaydi (bir zumda)."""
        try:
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
                new_ids = self.tg.send_media(q.chat_id, items, reply_to=q.message_id)
                for m, fid in zip(order, new_ids or []):
                    if fid and (m.tg_file_ids or {}).get(str(self.bot.id)) != fid:
                        Media.objects.filter(pk=m.pk).update(tg_file_ids={**(m.tg_file_ids or {}), str(self.bot.id): fid})
        except TelegramError as e:
            log.warning("send_media failed: %s", e)
        finally:
            if threading.current_thread().name == "support-files":
                close_old_connections()

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

    def _dup_note(self, q, prev):
        """Bir xil ekran/savol qayta kelsa — qisqa eslatma (oldingi javobga havola bilan)."""
        link = q.group.message_link(prev.bot_reply_id or prev.message_id) if q.group_id else ""
        txt = "☝️ Bu bo'yicha javob yuqorida berilgan" if q.lang != "ru" else "☝️ Ответ на это уже дан выше"
        html_text = f'<a href="{link}">{engine.html.escape(txt)}</a>' if link else engine.html.escape(txt)
        if not (self._pg().finish(html_text)):
            self._safe_send(q.chat_id, html_text, reply_to=q.message_id)

    def _respond_parts(self, q, d, settings):
        """Albomda turli ekranlar — har biriga alohida javob (bir xilini shu odam yaqinda olgan bo'lsa — qisqa eslatma)."""
        buttons = ([[{"text": "👍", "callback_data": f"fb:{q.id}:1"}, {"text": "👎", "callback_data": f"fb:{q.id}:-1"}]]
                   if settings.feedback_buttons else None)
        first = None
        for idx, e, conf in d.parts:
            head = f"🖼 Фото {idx + 1}" if q.lang == "ru" else f"🖼 {idx + 1}-rasm"
            prev = self._claim(q, e)
            if prev is not None:
                note = "☝️ ответ выше" if q.lang == "ru" else "☝️ javobi yuqorida"
                self._safe_send(q.chat_id, engine.html.escape(f"{head}: {note}"), reply_to=q.message_id)
                continue
            part = engine.Decision("image", e, conf, engine.render_answer(e, engine.extract_fields(e, q.ocr_text or ""), q.lang),
                                   False, [], {})
            body = f"{head}\n" + self._script(q, engine.vary(part, q.lang, settings))
            html_text = self._decorate(q, part, engine.to_html(body, settings.signature))
            if first is None:
                first = self._send_answer(q, html_text, e, buttons)
            else:
                self._safe_send(q.chat_id, html_text, reply_to=q.message_id)
                if e.attachments:
                    threading.Thread(target=self._send_files, args=(q, list(e.attachments)), name="support-files", daemon=True).start()
        if first is None:
            self._pg().drop()
        q.status, q.answered_by, q.answered_at = Message.ANSWERED, "bot", timezone.now()
        if first:
            q.bot_reply_id = first.get("message_id")
        q.save()
        return q

    def _pg(self):
        """Joriy oraliq xabar (bo'lmasa — hech narsa qilmaydigan bo'sh obyekt)."""
        pg = getattr(self, "progress", None)
        return pg if pg is not None else Progress(self.tg, Message(chat_id=0, message_id=0), False)

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


PROGRESS = {
    "uz": {"start": ["Savolingizni ko'ryapman", "Ko'rib chiqyapman", "Hozir yordam beraman"],
           "photo": ["Skrinshotni o'qiyapman", "Ekrandagi xabarni aniqlayapman", "Rasmni tekshiryapman"],
           "think": ["Bilim bazasidan qidiryapman", "O'xshash holatlarni solishtiryapman"],
           "write": ["Javobni yozyapman", "Javobni tekshiryapman", "Deyarli tayyor"],
           "more": "yana biroz…", "done": "Tayyor"},
    "ru": {"start": ["Смотрю ваш вопрос", "Разбираюсь", "Сейчас помогу"],
           "photo": ["Читаю скриншот", "Разбираю сообщение на экране", "Проверяю изображение"],
           "think": ["Ищу в базе знаний", "Сравниваю похожие случаи"],
           "write": ["Пишу ответ", "Проверяю ответ", "Почти готово"],
           "more": "ещё чуть-чуть…", "done": "Готово"},
}
CLOCKS = "🕐🕑🕒🕓🕔🕕🕖🕗🕘🕙🕚🕛"
ICONS = {"start": "🔎", "photo": "🖼", "think": "📚", "write": "✍️"}
_EXPECTED = {"at": 0.0, "v": {"start": 1.0, "photo": 2.5, "think": 1.0, "write": 6.0}}


def expected_seconds():
    """Bosqichlarning kutilgan davomiyligi — oxirgi savollarning haqiqiy o'lchovlaridan (5 daqiqa kesh)."""
    import statistics
    if time.monotonic() - _EXPECTED["at"] < 300:
        return _EXPECTED["v"]
    v = dict(_EXPECTED["v"])
    try:
        rows = list(Message.objects.filter(kind=Message.QUESTION, timing__isnull=False).order_by("-id")
                    .values_list("timing", "stage")[:300])
        def med(key, stage=None):
            xs = [t[key] / 1000 for t, st in rows if isinstance(t, dict) and isinstance(t.get(key), (int, float))
                  and (stage is None or st == stage)]
            return statistics.median(xs) if len(xs) >= 5 else None
        photo = (med("media") or 0) + (med("ocr") or 0)
        v["photo"] = round(max(1.0, min(15.0, photo or v["photo"])), 1)
        v["write"] = round(max(2.0, min(30.0, med("decide", "ai") or v["write"])), 1)
    except Exception:  # noqa: BLE001
        pass
    _EXPECTED.update(at=time.monotonic(), v=v)
    return v


class Progress:
    """Oraliq xabar: har bir savolga darhol reply, keyin har soniyada jonli animatsiya — aylanayotgan soat, to'lib
    borayotgan chiziq va teskari sanoq ("~3 s"), bosqich nomi almashadi (ustida Telegram'ning "yozmoqda…" belgisi).
    Oxirida shu xabar tahrirlanib haqiqiy javobga aylanadi; keraksiz bo'lsa — "o'chirish" kadri bilan yo'qoladi."""

    _live: dict = {}  # xabar id -> faol Progress (kechiktirilgan rasm qayta ishlansa, animatsiya uzilmay davom etadi)

    def __init__(self, tg, q, enabled, existing=None, every=1.0, max_frames=25):
        self.tg, self.q, self.enabled, self.id = tg, q, enabled, existing
        self.key, self.every, self.max_frames = "start", every, max_frames
        self.phase_at = time.monotonic()
        self._stop = threading.Event()
        self._thread = None
        self._i = 0

    def _lang(self):
        return "ru" if self.q.lang == "ru" else "uz"

    def _frame(self, i):
        lang = self._lang()
        texts = PROGRESS[lang][self.key]
        label = texts[(i // 3) % len(texts)]
        exp = expected_seconds().get(self.key, 2.0)
        elapsed = time.monotonic() - self.phase_at
        frac = min(0.95, elapsed / max(exp, 0.5))
        cells = round(frac * 10)
        bar = "▰" * cells + "▱" * (10 - cells)
        remain = int(exp - elapsed + 0.999)
        tail = f"~{remain} s" if remain > 0 else PROGRESS[lang]["more"]
        return f"{CLOCKS[i % len(CLOCKS)]} {ICONS[self.key]} {label}…\n<code>{bar}</code> {tail}"

    def begin(self):
        """Darhol reply (yoki oldingi xabarni davom ettirish) va animatsiya."""
        if not self.enabled:
            return
        try:
            if self.id is None:
                sent = self.tg.send(self.q.chat_id, self._frame(0), reply_to=self.q.message_id)
                self.id = (sent or {}).get("message_id")
        except Exception as e:  # noqa: BLE001 — oraliq xabar javobni to'xtatmasin
            log.warning("progress failed: %s", e)
        if self.id is None:
            return
        old = Progress._live.get(self.id)
        if old is not None and old is not self:
            old._stop.set()  # oldingi bosqich animatsiyasi shu yerdan davom etadi
        Progress._live[self.id] = self
        if self._thread is None and hasattr(self.tg, "edit_text"):
            self._thread = threading.Thread(target=self._run, name="support-progress", daemon=True)
            self._thread.start()

    def phase(self, key):
        if key != self.key:
            self.key, self.phase_at = key, time.monotonic()

    def show(self, key):  # eski chaqiruvlar bilan moslik
        self.phase(key)
        self.begin()

    def tick(self, *a, **k):  # eski nom
        self.begin()

    def _run(self):
        last_typing = 0.0
        for i in range(1, self.max_frames + 1):
            if self._stop.wait(self.every):
                return
            try:
                if time.monotonic() - last_typing > 4:
                    self.tg.typing(self.q.chat_id)
                    last_typing = time.monotonic()
                self.tg.edit_text(self.q.chat_id, self.id, self._frame(i), quiet=True)
            except Exception as e:  # noqa: BLE001 — limitga tushsa animatsiya to'xtaydi, javob esa ketadi
                if "429" in str(e) or "Too Many" in str(e):
                    return

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(0.6)

    def finish(self, html_text, buttons=None):
        """Oraliq xabarni javobga aylantirish. Bo'lmasa — None (chaqiruvchi oddiy xabar yuboradi)."""
        self.stop()
        Progress._live.pop(self.id, None)
        if self.id is None or not hasattr(self.tg, "edit_text"):
            return None
        try:
            self.tg.edit_text(self.q.chat_id, self.id, html_text, buttons=buttons)
            return {"message_id": self.id}
        except Exception as e:  # noqa: BLE001
            log.warning("progress finish failed: %s", e)
            self.drop()
            return None

    def drop(self):
        """Keraksiz oraliq xabar: qisqa "o'chirish" kadri, keyin o'chadi (javobni kutmaydi)."""
        self.stop()
        mid, self.id = self.id, None
        Progress._live.pop(mid, None)
        if mid is None or not hasattr(self.tg, "delete"):
            return
        tg, chat = self.tg, self.q.chat_id

        def bye():
            try:
                tg.edit_text(chat, mid, "🧹 <i>…</i>", quiet=True)
                time.sleep(0.6)
            except Exception:  # noqa: BLE001
                pass
            tg.delete(chat, mid)
        if threading.current_thread() is threading.main_thread():
            bye()
        else:
            threading.Thread(target=bye, name="support-progress-drop", daemon=True).start()


_OCR_SLOTS = threading.BoundedSemaphore(max(2, (os.cpu_count() or 4) - 2))


def _asker(q):
    """Savol beruvchining roli (AI javobni roliga mos yozishi uchun): "Agent · MDLZ" yoki "Supervayzer · ..."."""
    u = q.user
    if not u:
        return ""
    if u.is_staff:
        return f"xodim (IT/support): {u.staff_name()}"
    sp = getattr(u, "staff_person", None)
    if sp is None:
        return ""
    bits = [sp.get_role_display(), sp.project.name if sp.project_id else "", getattr(sp, "territory", "") or ""]
    return " · ".join(b for b in bits if b)


def _album_order(m):
    """Albom tartibi: asosiy rasm birinchi, keyin bo'laklar Telegram xabar raqami bo'yicha (1-rasm, 2-rasm, ...)."""
    if m.name.startswith("album:"):
        try:
            return (1, int(m.name.split(":", 1)[1]))
        except ValueError:
            return (1, m.id)
    return (0, m.id)


def _media_of(msg):
    """Xabardagi fayl: (file_id, tur, nomi, mime) yoki None. Rasm-hujjat ham rasm sifatida (iz va OCR uchun)."""
    if msg.get("photo"):
        sizes = msg["photo"]
        side = lambda x: max(x.get("width", 0), x.get("height", 0))  # noqa: E731
        fit = [x for x in sizes if side(x) <= 1600]
        pick = max(fit, key=side) if fit else min(sizes, key=side)
        return pick["file_id"], "photo", "", "image/jpeg"  # ~1600px: tanish va OCR uchun yetarli, ancha tez
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
        self.last_warm = time.time() - 540  # ishga tushgandan ~1 daqiqada birinchi oldindan yuklash

    @staticmethod
    def _warm(bot, client):
        close_old_connections()
        try:
            from . import mediaprep
            n = mediaprep.warm(bot, client)
            if n:
                log.info("warmed %s attachment(s) for bot %s", n, bot.id)
        except Exception:  # noqa: BLE001
            log.exception("warm failed")
        finally:
            close_old_connections()

    def run(self):
        client = Client(self.token.split("|", 1)[0])
        backoff = 5
        workers = max(1, min(Settings.load().workers or 10, 24))
        pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix=f"support-q{self.bot_id}")
        while not self.stop_event.is_set():
            close_old_connections()
            try:
                bot = Bot.objects.get(pk=self.bot_id)
                if not bot.username:
                    me = client.get_me()
                    Bot.objects.filter(pk=bot.pk).update(username=me.get("username", ""), tg_id=me.get("id"))
                updates = client.get_updates(bot.last_update_id + 1 if bot.last_update_id else None)
                handler = Handler(bot, client, executor=pool)
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
                try:  # PRBC javob bermagan /vazifa xabarlari -> mas'ulga ko'rsatma
                    from . import tasks as _tasks
                    _tasks.check_unanswered(client)
                except Exception:  # noqa: BLE001
                    log.exception("task check failed")
                if time.time() - self.last_warm > 600:
                    self.last_warm = time.time()
                    threading.Thread(target=self._warm, args=(bot, client), name="support-warm", daemon=True).start()
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


def _ai_thread(job_id):
    from .ai_review import run_job
    from .models import AIJob
    close_old_connections()
    try:
        run_job(job_id)
    except Exception as e:  # noqa: BLE001
        log.exception("ai job %s failed", job_id)
        AIJob.objects.filter(pk=job_id).update(status=AIJob.FAILED, error=f"{type(e).__name__}: {e}"[:500], finished_at=timezone.now())
    finally:
        close_old_connections()


def _task_thread():
    from . import tasks
    close_old_connections()
    try:
        tasks.process_queue()
    except Exception:  # noqa: BLE001
        log.exception("task sender failed")
    finally:
        close_old_connections()


def run_forever(poll=10):
    from .models import AIJob, SupportTask
    workers = {}
    history = None
    ai_worker = None
    task_worker = None
    AIJob.objects.filter(status=AIJob.RUNNING).update(status=AIJob.QUEUED)
    last_cleanup = 0.0
    last_learn = time.time() - 3000  # ishga tushgandan ~10 daqiqa o'tib birinchi o'qitish
    # jarayon qayta ishga tushsa, chala qolgan vazifa qayta navbatga qo'yiladi
    HistoryJob.objects.filter(status=HistoryJob.RUNNING).update(status=HistoryJob.QUEUED)
    log.info("support runner started; OCR: %s", ocr.languages() or "yo'q")
    while True:
        close_old_connections()
        try:
            wanted = {}
            nworkers = Settings.load().workers
            for b in Bot.objects.filter(enabled=True).exclude(token_enc=""):
                token = decrypt(b.token_enc)
                if token and b.mode != MODE_OFF:
                    wanted[b.id] = f"{token}|{nworkers}"  # worker soni o'zgarsa — bot oqimi yangi pool bilan qayta ishga tushadi
            for bid, w in list(workers.items()):
                if wanted.get(bid) != w.token or not w.is_alive():
                    w.stop_event.set()
                    workers.pop(bid)
            for bid, token in wanted.items():
                if bid not in workers:
                    w = BotWorker(bid, token)  # token|workers
                    w.start()
                    workers[bid] = w
            if history is None or not history.is_alive():
                job = HistoryJob.objects.filter(status=HistoryJob.QUEUED).order_by("created_at").first()
                if job:
                    history = threading.Thread(target=_history_thread, args=(job.id,), name="support-history", daemon=True)
                    history.start()
            if ai_worker is None or not ai_worker.is_alive():
                aj = AIJob.objects.filter(status=AIJob.QUEUED).order_by("created_at").first()
                if aj:
                    ai_worker = threading.Thread(target=_ai_thread, args=(aj.id,), name="support-ai", daemon=True)
                    ai_worker.start()
            if (task_worker is None or not task_worker.is_alive()) and SupportTask.objects.filter(status=SupportTask.QUEUED).exists():
                task_worker = threading.Thread(target=_task_thread, name="support-tasks", daemon=True)
                task_worker.start()
            if time.time() - last_learn > 3600:  # o'z-o'zini o'qitish: soatlik savol ko'rinishlari, kunlik AI tahlili
                last_learn = time.time()
                try:
                    from . import selflearn
                    n = selflearn.tick()
                    selflearn.daily_review()
                    if n:
                        log.info("self-learning: %s new question variants", n)
                except Exception:  # noqa: BLE001
                    log.exception("self-learning tick failed")
            if time.time() - last_cleanup > 86400:
                vision.cleanup(Settings.load().media_days)
                last_cleanup = time.time()
        except Exception:  # noqa: BLE001
            log.exception("runner loop error")
        time.sleep(poll)

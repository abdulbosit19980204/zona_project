"""Telegram Bot API klienti (faqat standart kutubxona).

Bloklanmaslik uchun: faqat rasmiy Bot API; har bir chatga yuborish oralig'i ≥ 3 s (daqiqasiga ~20),
umumiy oqim soniyasiga ≤ 25; 429 javobida Telegram aytgan `retry_after` kutiladi.
"""
import io
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = "https://api.telegram.org"
CHAT_GAP = 3.0       # bitta guruhga ketma-ket xabarlar orasidagi minimal vaqt (s)
GLOBAL_GAP = 0.04    # umumiy: soniyasiga ~25 xabar


class TelegramError(Exception):
    def __init__(self, message, code=0, retry_after=0):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class Client:
    def __init__(self, token, base=API, timeout=35):
        self.token = token
        self.base = base.rstrip("/")
        self.timeout = timeout
        self._lock = threading.Lock()
        self._last_chat = {}
        self._last_any = 0.0

    # ------------------------------------------------------------ past daraja
    def call(self, method, params=None, timeout=None, retries=2):
        data = json.dumps({k: v for k, v in (params or {}).items() if v is not None}).encode()
        req = urllib.request.Request(f"{self.base}/bot{self.token}/{method}", data=data,
                                     headers={"Content-Type": "application/json"})
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                    body = json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                try:
                    body = json.loads(e.read().decode("utf-8"))
                except Exception:  # noqa: BLE001
                    body = {"ok": False, "error_code": e.code, "description": str(e)}
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise TelegramError(f"Tarmoq xatosi: {e}") from e
            if body.get("ok"):
                return body.get("result")
            code = body.get("error_code", 0)
            retry_after = (body.get("parameters") or {}).get("retry_after", 0)
            if code == 429 and attempt < retries:
                time.sleep(min(int(retry_after or 5), 60) + 1)
                continue
            raise TelegramError(body.get("description", "Telegram xatosi"), code, retry_after)
        raise TelegramError("Telegram javob bermadi")

    def _throttle(self, chat_id):
        with self._lock:
            now = time.monotonic()
            wait = max(self._last_chat.get(chat_id, 0) + CHAT_GAP - now, self._last_any + GLOBAL_GAP - now, 0)
            if wait:
                time.sleep(wait)
            now = time.monotonic()
            self._last_chat[chat_id] = now
            self._last_any = now

    # ------------------------------------------------------------ yuqori daraja
    def get_me(self):
        return self.call("getMe", timeout=15)

    def get_updates(self, offset, timeout=25):
        return self.call("getUpdates", {"offset": offset, "timeout": timeout,
                                        "allowed_updates": ["message", "edited_message", "callback_query",
                                                            "my_chat_member"]},
                         timeout=timeout + 10, retries=0)

    def send(self, chat_id, text, reply_to=None, buttons=None, html=True):
        self._throttle(chat_id)
        params = {"chat_id": chat_id, "text": text[:4096], "disable_web_page_preview": True,
                  "parse_mode": "HTML" if html else None}
        if reply_to:
            params["reply_parameters"] = {"message_id": int(reply_to), "allow_sending_without_reply": True}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        return self.call("sendMessage", params)

    def edit_buttons(self, chat_id, message_id, buttons=None):
        try:
            return self.call("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                                        "reply_markup": {"inline_keyboard": buttons or []}})
        except TelegramError:
            return None

    def answer_callback(self, callback_id, text="", alert=False):
        try:
            return self.call("answerCallbackQuery", {"callback_query_id": callback_id, "text": text[:200],
                                                     "show_alert": alert}, retries=0)
        except TelegramError:
            return None

    def typing(self, chat_id):
        try:
            self.call("sendChatAction", {"chat_id": chat_id, "action": "typing"}, retries=0, timeout=10)
        except TelegramError:
            pass

    # ------------------------------------------------------------ fayllar (javob biriktirmalari)
    def call_multipart(self, method, fields, files, timeout=120):
        """multipart/form-data: fields — oddiy qiymatlar (dict/list JSON qilinadi), files — {nom: (fayl_nomi, bytes)}."""
        boundary = f"----foydali{uuid.uuid4().hex}"
        body = io.BytesIO()
        for k, v in fields.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
        for k, (fname, data) in files.items():
            body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fname}\"\r\n"
                       f"Content-Type: application/octet-stream\r\n\r\n".encode())
            body.write(data)
            body.write(b"\r\n")
        body.write(f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(f"{self.base}/bot{self.token}/{method}", data=body.getvalue(),
                                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                res = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            res = json.loads(e.read().decode("utf-8") or "{}")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TelegramError(f"Tarmoq xatosi: {e}") from e
        if not res.get("ok"):
            raise TelegramError(res.get("description", "Telegram xatosi"), res.get("error_code", 0),
                                (res.get("parameters") or {}).get("retry_after", 0))
        return res["result"]

    SEND = {"photo": ("sendPhoto", "photo"), "video": ("sendVideo", "video"), "video_note": ("sendVideoNote", "video_note"),
            "animation": ("sendAnimation", "animation"), "document": ("sendDocument", "document")}

    @staticmethod
    def _file_id(result, kind):
        if kind == "photo":
            return (result.get("photo") or [{}])[-1].get("file_id")
        return (result.get(kind) or result.get("document") or {}).get("file_id")

    def send_media(self, chat_id, items, reply_to=None):
        """items: [{"kind", "name", "data" (bytes, ixtiyoriy), "file_id" (ixtiyoriy)}] -> har biri uchun file_id ro'yxati.

        Bitta fayl — o'z turida; rasm/video ko'p bo'lsa — albom (media group, 10 tadan); hujjatlar alohida."""
        reply = {"message_id": int(reply_to), "allow_sending_without_reply": True} if reply_to else None
        ids = [None] * len(items)
        album = [i for i, it in enumerate(items) if it["kind"] in ("photo", "video")]
        single = [i for i in range(len(items)) if i not in album] if len(album) > 1 else list(range(len(items)))
        if len(album) > 1:
            for start in range(0, len(album), 10):
                chunk = album[start:start + 10]
                media, files = [], {}
                for j, i in enumerate(chunk):
                    it = items[i]
                    ref = it.get("file_id") or f"attach://f{j}"
                    if not it.get("file_id"):
                        files[f"f{j}"] = (it.get("name") or f"f{j}", it["data"])
                    media.append({"type": it["kind"], "media": ref})
                self._throttle(chat_id)
                res = self.call_multipart("sendMediaGroup", {"chat_id": chat_id, "media": media, "reply_parameters": reply}, files)
                for i, r in zip(chunk, res):
                    ids[i] = self._file_id(r, items[i]["kind"])
        for i in single:
            it = items[i]
            method, field = self.SEND.get(it["kind"], self.SEND["document"])
            self._throttle(chat_id)
            if it.get("file_id"):
                r = self.call(method, {"chat_id": chat_id, field: it["file_id"], "reply_parameters": reply})
            else:
                r = self.call_multipart(method, {"chat_id": chat_id, "reply_parameters": reply},
                                        {field: (it.get("name") or field, it["data"])})
            ids[i] = self._file_id(r, it["kind"])
        return ids

    def download(self, file_id, max_bytes=8 * 1024 * 1024):
        info = self.call("getFile", {"file_id": file_id})
        if (info.get("file_size") or 0) > max_bytes:
            raise TelegramError("Fayl juda katta")
        url = f"{self.base}/file/bot{self.token}/{urllib.parse.quote(info['file_path'])}"
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read(max_bytes + 1)[:max_bytes]

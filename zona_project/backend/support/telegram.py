"""Telegram Bot API klienti (faqat standart kutubxona).

Bloklanmaslik uchun: faqat rasmiy Bot API; har bir chatga yuborish oralig'i ≥ 3 s (daqiqasiga ~20),
umumiy oqim soniyasiga ≤ 25; 429 javobida Telegram aytgan `retry_after` kutiladi.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

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

    def download(self, file_id, max_bytes=8 * 1024 * 1024):
        info = self.call("getFile", {"file_id": file_id})
        if (info.get("file_size") or 0) > max_bytes:
            raise TelegramError("Fayl juda katta")
        url = f"{self.base}/file/bot{self.token}/{urllib.parse.quote(info['file_path'])}"
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read(max_bytes + 1)[:max_bytes]

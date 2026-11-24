"""PRBC REST API klienti (https://prbc.uz/api/v1/...). Faqat standart kutubxona (urllib).

Kirish: POST /api/v1/auth/login/ {phone, password} -> JWT (access + refresh); access tugasa /auth/refresh/ (rotatsiya:
yangi refresh ham keladi). Tokenlar Connection'da shifrlangan holda saqlanadi — har safar parol yuborilmaydi."""
import base64
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone as dt_tz

from zona.crypto import decrypt, encrypt

log = logging.getLogger("prbc")
API = "/api/v1"
TIMEOUT = 30
MAX_PAGES = 200


class PrbcError(Exception):
    def __init__(self, message, status=None, payload=None):
        super().__init__(message)
        self.status, self.payload = status, payload


class AuthError(PrbcError):
    pass


class LoginError(AuthError):
    """PRBC'ga umuman kirib bo'lmadi (parol yo'q yoki noto'g'ri) — bu manba yopiqligi emas, ulanish xatosi."""


def _jwt_exp(token):
    try:
        part = token.split(".")[1]
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        return datetime.fromtimestamp(int(data["exp"]), dt_tz.utc)
    except (IndexError, KeyError, ValueError, TypeError):
        return None


def _find_tokens(data):
    """Login/refresh javobidan access va refresh: {access, refresh} yoki {tokens: {...}} yoki {data: {...}}."""
    if not isinstance(data, dict):
        return None, None
    for box in (data, data.get("tokens") or {}, data.get("data") or {}, data.get("token") or {}):
        if isinstance(box, dict) and box.get("access"):
            return box["access"], box.get("refresh")
    return None, None


def error_text(payload, status):
    if isinstance(payload, dict):
        for key in ("detail", "message", "error", "non_field_errors"):
            if payload.get(key):
                v = payload[key]
                return " ".join(map(str, v)) if isinstance(v, list) else str(v)
        return "; ".join(f"{k}: {' '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in payload.items())[:500]
    return f"HTTP {status}"


class Client:
    def __init__(self, conn, opener=None):
        self.conn = conn
        self.base = (conn.base_url or "https://prbc.uz").rstrip("/")
        self._open = opener or urllib.request.urlopen

    # ---------------------------------------------------------------- past daraja
    def _http(self, method, path, params=None, body=None, token=None):
        url = path if path.startswith("http") else f"{self.base}{path if path.startswith(API) else API + path}"
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None}, doseq=True)
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "zona-prbc/1",
            **({"Authorization": f"Bearer {token}"} if token else {})})
        try:
            with self._open(req, timeout=TIMEOUT) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                payload = json.loads(raw) if raw else None
            except ValueError:
                payload = None
            return e.code, payload
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise PrbcError(f"PRBC serveriga ulanib bo'lmadi: {getattr(e, 'reason', e)}") from e

    # ---------------------------------------------------------------- tokenlar
    def _save_tokens(self, access, refresh):
        c = self.conn
        c.access_enc = encrypt(access)
        if refresh:
            c.refresh_enc = encrypt(refresh)
        c.access_until = _jwt_exp(access)
        c.save(update_fields=["access_enc", "refresh_enc", "access_until", "updated_at"])

    def login(self):
        c = self.conn
        password = decrypt(c.password_enc) if c.password_enc else ""
        if not c.phone or not password:
            raise LoginError("PRBC telefon raqami va parol kiritilmagan (Sozlamalar → PRBC).")
        status, data = self._http("POST", "/auth/login/", body={"phone": c.phone, "password": password})
        access, refresh = _find_tokens(data)
        if status >= 400 or not access:
            raise LoginError(f"PRBC'ga kirib bo'lmadi: {error_text(data, status)}", status, data)
        self._save_tokens(access, refresh)
        return access

    def _refresh(self):
        c = self.conn
        refresh = decrypt(c.refresh_enc) if c.refresh_enc else ""
        if refresh:
            status, data = self._http("POST", "/auth/refresh/", body={"refresh": refresh})
            access, new_refresh = _find_tokens(data)
            if status < 400 and access:
                self._save_tokens(access, new_refresh)
                return access
        return self.login()

    def token(self):
        c = self.conn
        access = decrypt(c.access_enc) if c.access_enc else ""
        if access and c.access_until and (c.access_until.timestamp() - time.time()) > 60:
            return access
        return self._refresh() if c.refresh_enc else self.login()

    # ---------------------------------------------------------------- so'rovlar
    def request(self, method, path, params=None, body=None):
        status, data = self._http(method, path, params, body, self.token())
        if status == 401:  # token bekor qilingan (parol o'zgargan, seans yopilgan) — qayta kirish
            status, data = self._http(method, path, params, body, self.login())
        if status >= 400:
            cls = AuthError if status in (401, 403) else PrbcError
            raise cls(error_text(data, status), status, data)
        return data

    def get(self, path, params=None):
        return self.request("GET", path, params)

    def post(self, path, body=None):
        return self.request("POST", path, body=body or {})

    def pages(self, path, params=None, max_pages=MAX_PAGES, stop=None):
        """Sahifalangan ro'yxat ({count, next, results}) yoki oddiy ro'yxat. stop(item) True bo'lsa to'xtaydi."""
        params = dict(params or {})
        url, n = path, 0
        while url and n < max_pages:
            data = self.get(url, params if n == 0 else None)
            n += 1
            items = items_of(data)
            for it in items:
                if stop and stop(it):
                    return
                yield it
            url = data.get("next") if isinstance(data, dict) else None

    # ---------------------------------------------------------------- yuqori daraja
    def profile(self):
        return self.get("/auth/profile/")

    def create_task(self, *, title, description="", project=None, assignee_ids=(), co_assignee_ids=(), watcher_ids=(),
                    priority=None, due_at=None, start_at=None, status=None, parent=None):
        body = {"title": title[:255], "description": description[:20000]}
        for key, value in (("project", project), ("priority", priority), ("due_at", due_at), ("start_at", start_at),
                           ("status", status), ("parent", parent)):
            if value not in (None, ""):
                body[key] = value
        for key, value in (("assignee_ids", assignee_ids), ("co_assignee_ids", co_assignee_ids), ("watcher_ids", watcher_ids)):
            if value:
                body[key] = [int(v) for v in value]
        return self.post("/tasks/", body)

    def comment(self, task_id, text):
        try:
            return self.post("/task-comments/", {"task": task_id, "body": text[:4900]})
        except PrbcError as e:
            if e.status == 400 and isinstance(e.payload, dict) and "body" in e.payload:
                return self.post("/task-comments/", {"task": task_id, "text": text[:4900]})
            raise


def items_of(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("results", "items", "data", "users", "employees", "persons"):
            if isinstance(data.get(key), list):
                return data[key]
    return []

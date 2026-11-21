#!/usr/bin/env python3
"""Servislar boshqaruv markazi — barcha servislarni bitta buyruq bilan ishga tushiradi va veb-sahifada nazorat qiladi.

    python services/control/control.py              # hammasini ishga tushiradi, sahifa: http://127.0.0.1:8900
    python services/control/control.py --no-autostart

Faqat Python standart kutubxonasi — boshqa servislardan (va ularning paketlaridan) to'liq mustaqil.
Ikki rejim:
  process — servislarni o'zi jarayon sifatida ishga tushiradi (lokal kompyuter, oddiy server);
            yiqilgan servisni avtomatik qayta ishga tushiradi.
  systemd — ishlab chiqarish serveri: systemctl/journalctl orqali boshqaradi (deploy/control.services.json).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.server
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent  # zona_project/
IS_WIN = os.name == "nt"
RESTART_WINDOW, RESTART_MAX = 300, 5
LOG_LINES = 3000


def now() -> float:
    return time.time()


def iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat() if ts else None


def resolve_cmd(cmd: list[str]) -> list[str]:
    """{py:<venv>} — venv'dagi python, {npm} — npm, {python} — joriy python."""
    out = []
    for part in cmd:
        if part.startswith("{py:") and part.endswith("}"):
            venv = PROJECT / part[4:-1]
            exe = venv / ("Scripts/python.exe" if IS_WIN else "bin/python")
            out.append(str(exe))
        elif part == "{npm}":
            out.append(shutil.which("npm") or ("npm.cmd" if IS_WIN else "npm"))
        elif part == "{python}":
            out.append(sys.executable)
        else:
            out.append(part)
    return out


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def check_health(url: str) -> tuple[bool, int | None]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "zona-control"}), timeout=4) as r:
            ok = r.status < 500
    except urllib.error.HTTPError as e:  # 401/404/405 — servis javob beryapti
        ok = e.code < 500
    except (urllib.error.URLError, OSError, TimeoutError):
        return False, None
    return ok, int((time.perf_counter() - start) * 1000)


# ---------------------------------------------------------------- servis
@dataclass
class Service:
    name: str
    label: str
    group: str = ""
    cmd: list[str] = field(default_factory=list)
    cwd: str = "."
    env: dict[str, str] = field(default_factory=dict)
    port: int | None = None
    health: str = ""
    open: str = ""
    unit: str = ""
    # systemd rejimida unit o'rniga boshqaruv skripti (masalan pm2'dagi frontend): <ctl> status|start|stop|restart|logs N
    ctl: list[str] = field(default_factory=list)
    autostart: bool = True
    autorestart: bool = True
    # holat
    proc: subprocess.Popen | None = None
    desired: str = "stopped"
    state: str = "stopped"  # stopped | starting | running | crashed | external | failed
    started_at: float | None = None
    restarts: list[float] = field(default_factory=list)
    total_restarts: int = 0
    last_exit: int | None = None
    last_error: str = ""
    ext_pid: int | None = None  # systemd rejimida MainPID
    health_ok: bool | None = None
    health_ms: int | None = None
    health_at: float | None = None
    logs: deque = field(default_factory=lambda: deque(maxlen=LOG_LINES))
    lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, line: str) -> None:
        self.logs.append(f"{datetime.now():%H:%M:%S} {line.rstrip()}")


class Supervisor:
    def __init__(self, config: dict[str, Any]):
        self.mode = os.environ.get("CONTROL_MODE") or config.get("mode", "process")
        self.services: list[Service] = [
            Service(**{k: v for k, v in s.items() if k in Service.__dataclass_fields__}) for s in config["services"]]
        self.by_name = {s.name: s for s in self.services}
        self.stop_event = threading.Event()
        self.events: deque = deque(maxlen=200)

    def event(self, text: str) -> None:
        self.events.appendleft({"at": iso(now()), "text": text})

    # ---------- process rejimi ----------
    def _spawn(self, s: Service) -> None:
        env = {**os.environ, **{k: str(v) for k, v in s.env.items()}, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        cmd = resolve_cmd(s.cmd)
        kw: dict[str, Any] = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if IS_WIN else {"start_new_session": True}
        try:
            s.proc = subprocess.Popen(cmd, cwd=PROJECT / s.cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, **kw)
        except OSError as e:
            s.state, s.last_error, s.proc = "failed", f"Ishga tushmadi: {e}", None
            s.log(f"[control] {s.last_error}")
            self.event(f"{s.label}: ishga tushmadi")
            return
        s.state, s.started_at, s.last_error = "starting", now(), ""
        s.log(f"[control] ishga tushirildi (pid {s.proc.pid})")
        threading.Thread(target=self._reader, args=(s, s.proc), daemon=True).start()

    @staticmethod
    def _reader(s: Service, proc: subprocess.Popen) -> None:
        assert proc.stdout is not None
        try:
            for raw in iter(proc.stdout.readline, b""):
                s.log(raw.decode("utf-8", errors="replace"))
        finally:
            proc.stdout.close()

    @staticmethod
    def _kill(proc: subprocess.Popen) -> None:
        if proc.poll() is not None:
            return
        if IS_WIN:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        else:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                proc.wait(timeout=10)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass

    # ---------- systemd rejimi ----------
    @staticmethod
    def _sudo() -> list[str]:
        return [] if (not hasattr(os, "geteuid") or os.geteuid() == 0) else ["sudo", "-n"]

    def _systemctl(self, action: str, unit: str | Service) -> tuple[bool, str]:
        if isinstance(unit, Service) and unit.ctl:
            r = subprocess.run([*self._sudo(), *unit.ctl, action], capture_output=True, text=True, timeout=120)
        else:
            unit = unit.unit if isinstance(unit, Service) else unit
            r = subprocess.run([*self._sudo(), "systemctl", action, unit], capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stderr or r.stdout).strip()

    def _ctl_status(self, s: Service) -> None:
        """Boshqaruv skripti JSON qaytaradi: {"state": running|stopped|crashed, "pid", "restarts", "uptime"}"""
        r = subprocess.run([*self._sudo(), *s.ctl, "status"], capture_output=True, text=True, timeout=20)
        try:
            data = json.loads(r.stdout or "{}")
        except ValueError:
            data = {"state": "unknown"}
        s.state = data.get("state") or "unknown"
        s.ext_pid = data.get("pid") or None
        s.total_restarts = int(data.get("restarts") or 0)
        up = data.get("uptime")
        s.started_at = now() - float(up) if up and s.state == "running" else None
        s.desired = "running" if s.state in ("running", "starting") else "stopped"
        s.last_error = "" if r.returncode == 0 else (r.stderr or r.stdout).strip()[:300]

    def _systemd_status(self, s: Service) -> None:
        if s.ctl:
            return self._ctl_status(s)
        r = subprocess.run(["systemctl", "show", s.unit, "--property=ActiveState,SubState,MainPID,NRestarts,ActiveEnterTimestampMonotonic"],
                           capture_output=True, text=True, timeout=10)
        props = dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)
        active = props.get("ActiveState", "unknown")
        s.state = {"active": "running", "activating": "starting", "deactivating": "stopping", "failed": "crashed"}.get(active, "stopped")
        s.total_restarts = int(props.get("NRestarts") or 0)
        mono = int(props.get("ActiveEnterTimestampMonotonic") or 0)
        s.started_at = now() - (time.monotonic() - mono / 1e6) if mono and s.state == "running" else None
        s.proc = None
        s.desired = "running" if s.state in ("running", "starting") else "stopped"
        s.ext_pid = int(props.get("MainPID") or 0) or None

    # ---------- umumiy amallar ----------
    def start(self, s: Service) -> str:
        with s.lock:
            s.desired = "running"
            if self.mode == "systemd":
                ok, msg = self._systemctl("start", s)
                self.event(f"{s.label}: ishga tushirildi" if ok else f"{s.label}: xato — {msg}")
                return "ok" if ok else msg
            if s.proc and s.proc.poll() is None:
                return "allaqachon ishlayapti"
            if s.port and port_open(s.port):
                s.state = "external"
                s.last_error = f"{s.port}-port band: servis boshqa jarayon sifatida allaqachon ishlayapti"
                self.event(f"{s.label}: tashqi jarayon ishlayapti (port {s.port})")
                return s.last_error
            s.restarts.clear()
            self._spawn(s)
            self.event(f"{s.label}: ishga tushirildi")
            return "ok"

    def stop(self, s: Service) -> str:
        with s.lock:
            s.desired = "stopped"
            if self.mode == "systemd":
                ok, msg = self._systemctl("stop", s)
                self.event(f"{s.label}: to'xtatildi" if ok else f"{s.label}: xato — {msg}")
                return "ok" if ok else msg
            if s.proc:
                self._kill(s.proc)
                s.last_exit = s.proc.returncode
                s.log("[control] to'xtatildi")
            s.proc, s.state, s.started_at = None, "stopped", None
            self.event(f"{s.label}: to'xtatildi")
            return "ok"

    def restart(self, s: Service) -> str:
        if self.mode == "systemd":
            with s.lock:
                s.desired = "running"
                ok, msg = self._systemctl("restart", s)
                self.event(f"{s.label}: qayta ishga tushirildi" if ok else f"{s.label}: xato — {msg}")
                return "ok" if ok else msg
        self.stop(s)
        return self.start(s)

    def start_all(self) -> None:
        for s in self.services:
            self.start(s)

    def stop_all(self) -> None:
        for s in reversed(self.services):
            self.stop(s)

    def logs(self, s: Service, n: int = 300) -> list[str]:
        if self.mode == "systemd":
            cmd = [*s.ctl, "logs", str(n)] if s.ctl else ["journalctl", "-u", s.unit, "-n", str(n), "--no-pager", "-o", "short-iso"]
            r = subprocess.run([*self._sudo(), *cmd], capture_output=True, text=True, timeout=15)
            return (r.stdout or r.stderr).splitlines()
        return list(s.logs)[-n:]

    # ---------- kuzatuv ----------
    def watch_once(self) -> None:
        for s in self.services:
            if self.mode == "systemd":
                try:
                    self._systemd_status(s)
                except (OSError, subprocess.SubprocessError) as e:
                    s.state, s.last_error = "unknown", str(e)
                continue
            with s.lock:
                if s.state == "external":
                    if s.port and not port_open(s.port):
                        s.state = "stopped"
                    continue
                if not s.proc:
                    continue
                code = s.proc.poll()
                if code is None:
                    if s.state == "starting" and (s.health_ok or not s.health or now() - (s.started_at or 0) > 3):
                        s.state = "running"
                    continue
                # jarayon tugagan
                s.last_exit, s.proc = code, None
                s.log(f"[control] jarayon to'xtadi (kod {code})")
                if s.desired != "running" or not s.autorestart:
                    s.state = "stopped" if code == 0 else "crashed"
                    continue
                s.restarts = [t for t in s.restarts if now() - t < RESTART_WINDOW]
                if len(s.restarts) >= RESTART_MAX:
                    s.state = "crashed"
                    s.last_error = f"{RESTART_WINDOW // 60} daqiqada {RESTART_MAX} marta yiqildi — avtomatik qayta ishga tushirish to'xtatildi"
                    reason = next((ln for ln in reversed(s.logs) if "[control]" not in ln and len(ln.strip()) > 12), "")
                    if reason:
                        s.last_error += f". Oxirgi xabar: {reason[9:].strip()[:200]}"
                    self.event(f"{s.label}: {s.last_error}")
                    continue
                s.restarts.append(now())
                s.total_restarts += 1
                self.event(f"{s.label}: yiqildi (kod {code}) — avtomatik qayta ishga tushirilmoqda")
                self._spawn(s)

    def health_once(self) -> None:
        for s in self.services:
            if s.health:
                s.health_ok, s.health_ms = check_health(s.health)
                s.health_at = now()
                if s.state == "external" and not s.health_ok and s.port and not port_open(s.port):
                    s.state = "stopped"

    def loop(self) -> None:
        tick = 0
        while not self.stop_event.is_set():
            try:
                self.watch_once()
                if tick % 5 == 0:
                    self.health_once()
            except Exception as e:  # noqa: BLE001 — nazoratchi hech qachon yiqilmasin
                self.event(f"nazoratchi xatosi: {e}")
            tick += 1
            self.stop_event.wait(1)

    def status(self) -> dict[str, Any]:
        items = []
        for s in self.services:
            pid = s.proc.pid if s.proc else s.ext_pid
            items.append({
                "name": s.name, "label": s.label, "group": s.group, "state": s.state, "desired": s.desired, "pid": pid,
                "port": s.port, "open": s.open, "started_at": iso(s.started_at),
                "uptime": int(now() - s.started_at) if s.started_at and s.state in ("running", "starting") else None,
                "restarts": s.total_restarts, "last_exit": s.last_exit, "error": s.last_error,
                "health": None if not s.health else {"ok": s.health_ok, "ms": s.health_ms, "at": iso(s.health_at)},
            })
        running = sum(1 for i in items if i["state"] in ("running", "external"))
        return {"mode": self.mode, "host": socket.gethostname(), "time": iso(now()), "services": items,
                "summary": {"total": len(items), "running": running}, "events": list(self.events)[:50]}


# ---------------------------------------------------------------- autentifikatsiya
class Auth:
    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.file = data_dir / "control-auth.json"
        self.fails: dict[str, list[float]] = {}
        stored = json.loads(self.file.read_text("utf-8")) if self.file.is_file() else {}
        self.secret = stored.get("secret") or secrets.token_hex(32)
        self.generated_password: str | None = None
        env_pw = os.environ.get("CONTROL_PASSWORD", "").strip()
        if env_pw:
            self.salt, self.hash = self._hash(env_pw)
        elif stored.get("hash"):
            self.salt, self.hash = stored["salt"], stored["hash"]
        else:
            self.generated_password = secrets.token_urlsafe(12)
            self.salt, self.hash = self._hash(self.generated_password)
            (data_dir / "initial-password.txt").write_text(self.generated_password + "\n", "utf-8")
        self.file.write_text(json.dumps({"secret": self.secret, "salt": self.salt, "hash": self.hash}), "utf-8")
        try:
            os.chmod(self.file, 0o600)
        except OSError:
            pass

    @staticmethod
    def _hash(password: str, salt: str | None = None) -> tuple[str, str]:
        salt = salt or secrets.token_hex(16)
        return salt, hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()

    def check_password(self, ip: str, password: str) -> str | None:
        """None — to'g'ri; aks holda xato matni."""
        window = [t for t in self.fails.get(ip, []) if now() - t < 900]
        if len(window) >= 10:
            return "Juda ko'p urinish. 15 daqiqadan keyin qayta urinib ko'ring."
        if hmac.compare_digest(self._hash(password, self.salt)[1], self.hash):
            self.fails.pop(ip, None)
            return None
        self.fails[ip] = [*window, now()]
        return "Parol noto'g'ri."

    def make_cookie(self, hours: int = 12) -> str:
        exp = str(int(now()) + hours * 3600)
        sig = hmac.new(self.secret.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return base64.urlsafe_b64encode(f"{exp}.{sig}".encode()).decode()

    def valid(self, cookie: str) -> bool:
        try:
            exp, sig = base64.urlsafe_b64decode(cookie.encode()).decode().split(".")
        except (ValueError, UnicodeDecodeError):
            return False
        good = hmac.new(self.secret.encode(), exp.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, good) and int(exp) > now()


# ---------------------------------------------------------------- veb
LOGIN_PAGE = """<!doctype html><html lang="uz"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Servislar markazi — kirish</title><style>
:root{color-scheme:light dark;--bg:#f4f6f9;--card:#fff;--fg:#14161a;--mut:#667085;--acc:#2563eb;--bd:#e4e7ec}
@media (prefers-color-scheme:dark){:root{--bg:#0b0d10;--card:#15181d;--fg:#e8eaed;--mut:#98a2b3;--acc:#60a5fa;--bd:#262a31}}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;padding:16px}
.c{background:var(--card);border:1px solid var(--bd);border-radius:16px;padding:28px;width:100%;max-width:360px}
h1{font-size:18px;margin:0 0 4px}p{color:var(--mut);margin:0 0 18px;font-size:13px}
input{width:100%;box-sizing:border-box;padding:10px 12px;border:1px solid var(--bd);border-radius:10px;background:transparent;color:inherit;font:inherit}
button{margin-top:12px;width:100%;padding:10px;border:0;border-radius:10px;background:var(--acc);color:#fff;font:inherit;cursor:pointer}
.e{color:#dc2626;margin-top:10px;font-size:13px}</style></head><body><form class="c" method="post" action="login">
<h1>Servislar boshqaruv markazi</h1><p>Barcha servislarni ishga tushirish va nazorat qilish.</p>
<input type="password" name="password" placeholder="Parol" autofocus required>__ERR__<button type="submit">Kirish</button></form></body></html>"""


def make_handler(sup: Supervisor, auth: Auth, res: Any = None):
    page = (HERE / "page.html").read_text("utf-8")

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "zona-control"

        def log_message(self, fmt: str, *args: Any) -> None:  # jim
            return

        # --- yordamchilar ---
        def _route(self) -> list[str]:
            return [p for p in urlsplit(self.path).path.split("/") if p]

        def _ip(self) -> str:
            fwd = self.headers.get("X-Forwarded-For", "")
            return fwd.split(",")[0].strip() if fwd else self.client_address[0]

        def _authed(self) -> bool:
            for part in self.headers.get("Cookie", "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "ctl_session" and auth.valid(v):
                    return True
            return False

        def _send(self, code: int, body: bytes | str, ctype: str = "application/json; charset=utf-8",
                  headers: dict[str, str] | None = None) -> None:
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _json(self, code: int, obj: Any) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False))

        def _cookie(self, value: str, max_age: int) -> str:
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            return f"ctl_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}{secure}"

        # --- GET ---
        def do_GET(self) -> None:
            route = self._route()
            tail = route[-1] if route else ""
            if tail == "health":
                return self._json(200, {"ok": True})
            if tail == "login":
                return self._send(200, LOGIN_PAGE.replace("__ERR__", ""), "text/html; charset=utf-8")
            if not self._authed():
                if "api" in route:
                    return self._json(401, {"detail": "Tizimga kiring"})
                return self._send(303, b"", headers={"Location": "login"})
            if "api" in route:
                i = route.index("api")
                rest = route[i + 1:]
                if rest == ["status"]:
                    return self._json(200, sup.status())
                if rest == ["resources"] and res is not None:
                    rng = parse_qs(urlsplit(self.path).query).get("range", ["24h"])[0]
                    return self._json(200, res.snapshot("30d" if rng == "30d" else "24h"))
                if len(rest) == 3 and rest[0] == "services" and rest[2] == "logs" and rest[1] in sup.by_name:
                    n = int(parse_qs(urlsplit(self.path).query).get("n", ["300"])[0])
                    return self._json(200, {"lines": sup.logs(sup.by_name[rest[1]], min(n, LOG_LINES))})
                return self._json(404, {"detail": "Topilmadi"})
            return self._send(200, page, "text/html; charset=utf-8")

        # --- POST ---
        def do_POST(self) -> None:
            route = self._route()
            tail = route[-1] if route else ""
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(min(length, 10_000)).decode("utf-8", errors="replace")
            if tail == "login":
                password = parse_qs(body).get("password", [""])[0]
                err = auth.check_password(self._ip(), password)
                if err:
                    return self._send(401, LOGIN_PAGE.replace("__ERR__", f'<div class="e">{err}</div>'), "text/html; charset=utf-8")
                return self._send(303, b"", headers={"Location": "./", "Set-Cookie": self._cookie(auth.make_cookie(), 12 * 3600)})
            if tail == "logout":
                return self._send(303, b"", headers={"Location": "login", "Set-Cookie": self._cookie("", 0)})
            if not self._authed():
                return self._json(401, {"detail": "Tizimga kiring"})
            if self.headers.get("X-Control") != "1":  # CSRF himoyasi
                return self._json(403, {"detail": "Ruxsat yo'q"})
            if "api" not in route:
                return self._json(404, {"detail": "Topilmadi"})
            rest = route[route.index("api") + 1:]
            actions = {"start": sup.start, "stop": sup.stop, "restart": sup.restart}
            if len(rest) == 2 and rest[0] == "all" and rest[1] in ("start", "stop", "restart"):
                if rest[1] in ("stop", "restart"):
                    sup.stop_all()
                if rest[1] in ("start", "restart"):
                    sup.start_all()
                return self._json(200, sup.status())
            if len(rest) == 3 and rest[0] == "services" and rest[1] in sup.by_name and rest[2] in actions:
                result = actions[rest[2]](sup.by_name[rest[1]])
                return self._json(200, {"result": result, **sup.status()})
            return self._json(404, {"detail": "Topilmadi"})

    return Handler


def load_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Servislar boshqaruv markazi")
    ap.add_argument("--config", default=os.environ.get("CONTROL_CONFIG") or str(HERE / "services.json"))
    ap.add_argument("--host", default=os.environ.get("CONTROL_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("CONTROL_PORT", "8900")))
    ap.add_argument("--data", default=os.environ.get("CONTROL_DATA_DIR") or str(HERE / "data"))
    ap.add_argument("--no-autostart", action="store_true", help="servislarni avtomatik ishga tushirmaslik")
    args = ap.parse_args(argv)

    config = load_config(Path(args.config))
    sup = Supervisor(config)
    auth = Auth(Path(args.data))
    from resources import Resources  # shu papkadagi modul (standart kutubxona)
    res = Resources(config, sup.services, Path(args.data))
    server = http.server.ThreadingHTTPServer((args.host, args.port), make_handler(sup, auth, res))
    url = f"http://{args.host}:{args.port}/"
    print("=" * 64)
    print(f"  Servislar boshqaruv markazi: {url}   (rejim: {sup.mode})")
    if auth.generated_password:
        print(f"  Birinchi kirish paroli: {auth.generated_password}")
        print(f"  (saqlangan: {Path(args.data) / 'initial-password.txt'}; o'zgartirish: CONTROL_PASSWORD muhit o'zgaruvchisi)")
    print("=" * 64, flush=True)

    threading.Thread(target=sup.loop, daemon=True).start()
    threading.Thread(target=res.loop, args=(sup.stop_event,), daemon=True).start()  # server resurslari
    if not args.no_autostart and sup.mode == "process":
        threading.Thread(target=lambda: [sup.start(s) for s in sup.services if s.autostart], daemon=True).start()

    def shutdown(*_: Any) -> None:
        sup.stop_event.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        if sup.mode == "process":
            print("Servislar to'xtatilmoqda…", flush=True)
            sup.stop_all()


if __name__ == "__main__":
    main()

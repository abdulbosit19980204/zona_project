"""Server xavfsizligi: SSH hujumlari va kirishlar, sshd sozlamasi, firewall, ochiq portlar, yangilanishlar, SSL
sertifikatlar, saytlar holati, zaxiralar, yiqilgan servislar — xavf darajasi va tavsiyalar bilan. Faqat o'qiydi.

Root shart emas: loglar va ufw — sudoers'dagi aniq (jokersiz, NOEXEC) buyruqlar orqali; qolgani /proc va o'qiladigan
fayllardan. Hech narsani o'zgartirmaydi — tuzatish qarori administratorniki.
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FAIL_RX = re.compile(r"(Failed password|Invalid user|authentication failure|Connection closed by authenticating user|"
                     r"Disconnected from authenticating user|maximum authentication attempts)", re.I)
IP_RX = re.compile(r"from ((?:\d{1,3}\.){3}\d{1,3}|[0-9a-f:]{3,})", re.I)
USER_RX = re.compile(r"(?:Invalid user|Failed password for(?: invalid user)?) (\S+)", re.I)
ACC_RX = re.compile(r"^(\S+) .*Accepted (\S+) for (\S+) from (\S+)")
PORT_NAMES = {22: "SSH", 80: "HTTP (nginx)", 443: "HTTPS (nginx)", 53: "DNS (lokal)", 25: "SMTP", 3306: "MySQL",
              5432: "PostgreSQL", 6379: "Redis", 27017: "MongoDB"}


# ---------------------------------------------------------------- sof funksiyalar (testlanadi)
def parse_ssh(lines: list[str], now_ts: float) -> dict[str, Any]:
    """journalctl -o short-iso qatorlari -> urinishlar soni, soatlar bo'yicha, top IP/foydalanuvchilar."""
    fails, ips, users, hours = 0, Counter(), Counter(), [0] * 24
    for ln in lines:
        if not FAIL_RX.search(ln) or "Accepted" in ln:
            continue
        fails += 1
        m = IP_RX.search(ln)
        if m:
            ips[m.group(1)] += 1
        u = USER_RX.search(ln)
        if u:
            users[u.group(1)] += 1
        try:
            ts = datetime.fromisoformat(ln.split(" ", 1)[0]).timestamp()
            h = int((now_ts - ts) // 3600)
            if 0 <= h < 24:
                hours[23 - h] += 1
        except ValueError:
            pass
    return {"fails": fails, "hours": hours, "top_ips": ips.most_common(10), "top_users": users.most_common(8),
            "unique_ips": len(ips)}


def parse_accepted(lines: list[str]) -> list[dict[str, Any]]:
    """Muvaffaqiyatli kirishlar: IP, foydalanuvchi, usul, soni, oxirgi vaqt."""
    agg: dict[tuple, dict[str, Any]] = {}
    for ln in lines:
        m = ACC_RX.search(ln)
        if not m:
            continue
        when, method, user, ip = m.groups()
        row = agg.setdefault((ip, user, method), {"ip": ip, "user": user, "method": method, "n": 0, "first": when, "last": when})
        row["n"] += 1
        row["last"] = max(row["last"], when)
        row["first"] = min(row["first"], when)
    return sorted(agg.values(), key=lambda r: r["last"], reverse=True)


def parse_sshd(text: str) -> dict[str, str]:
    """sshd_config (va .d/*.conf): birinchi uchragan qiymat amal qiladi (OpenSSH qoidasi)."""
    out: dict[str, str] = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or ln.lower().startswith("match "):
            if ln.lower().startswith("match "):
                break
            continue
        k, _, v = ln.partition(" ")
        out.setdefault(k.lower(), v.strip().lower())
    return out


def parse_listen(text: str, v6: bool = False) -> list[tuple[str, int]]:
    """/proc/net/tcp(6) -> LISTEN (0A) holatidagi (manzil, port)."""
    out = []
    for ln in text.splitlines()[1:]:
        f = ln.split()
        if len(f) < 4 or f[3] != "0A":
            continue
        addr, port = f[1].split(":")
        port = int(port, 16)
        if v6:
            ip = "::" if set(addr) == {"0"} else ("::1" if addr.endswith("01000000") and addr.startswith("0000000000000000") else addr)
        else:
            b = bytes.fromhex(addr)[::-1]
            ip = ".".join(str(x) for x in b)
        out.append((ip, port))
    return out


def is_public(ip: str) -> bool:
    return ip in ("0.0.0.0", "::") or not (ip.startswith("127.") or ip == "::1" or ip.startswith("::ffff:127"))


def parse_updates(text: str) -> tuple[int | None, int | None]:
    """/var/lib/update-notifier/updates-available -> (jami, xavfsizlik)."""
    total = sec = None
    m = re.search(r"(\d+) updates? can be applied", text)
    if m:
        total = int(m.group(1))
    m = re.search(r"(\d+) of these updates? (?:is a|are) (?:standard )?security update", text)
    if m:
        sec = int(m.group(1))
    elif total is not None:
        sec = 0 if "security" not in text else sec
    return total, sec


# ---------------------------------------------------------------- yig'uvchi
class Security:
    def __init__(self, config: dict[str, Any], events: Any = None):
        cfg = config.get("security") or {}
        self.sites = cfg.get("sites") or []          # [{"name", "url", "host"}]
        self.backups = cfg.get("backups") or ""       # zaxiralar papkasi
        self.backup_max_hours = cfg.get("backup_max_hours") or 30
        self.events = events
        self.lock = threading.Lock()
        self.data: dict[str, Any] = {}
        self.at = 0.0
        self.slow_at = 0.0
        self.slow: dict[str, Any] = {}

    @staticmethod
    def _sudo() -> list[str]:
        return [] if (not hasattr(os, "geteuid") or os.geteuid() == 0) else ["sudo", "-n"]

    def _run(self, cmd: list[str], timeout: int = 30) -> str:
        try:
            r = subprocess.run([*self._sudo(), *cmd], capture_output=True, text=True, timeout=timeout)
            return r.stdout if r.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            return ""

    def _ssh(self) -> dict[str, Any]:
        out = self._run(["/usr/bin/journalctl", "-u", "ssh", "--since", "-24h", "--no-pager", "-q", "-o", "short-iso"], 60)
        res = parse_ssh(out.splitlines(), time.time())
        res["available"] = bool(out)
        return res

    def _accepted(self) -> list[dict[str, Any]]:
        out = self._run(["/usr/bin/journalctl", "-u", "ssh", "--since", "-7d", "--no-pager", "-q", "-o", "short-iso",
                         "--grep", "Accepted"], 60)
        return parse_accepted(out.splitlines())

    def _sshd(self) -> dict[str, str]:
        """Amaldagi sozlama: `sshd -T` (barcha Include'lar bilan). Bo'lmasa — fayllar; biror fayl o'qilmasa — "noma'lum"
        (xavfsiz deb ko'rsatilmaydi: o'qilmagan faylda "PasswordAuthentication yes" bo'lishi mumkin)."""
        out = self._run(["/usr/sbin/sshd", "-T"], 15)
        if out:
            conf = {}
            for ln in out.splitlines():
                k, _, v = ln.partition(" ")
                conf.setdefault(k.lower(), v.strip().lower())
            return conf
        text, partial = "", False
        for f in [*sorted(glob.glob("/etc/ssh/sshd_config.d/*.conf")), "/etc/ssh/sshd_config"]:
            try:
                text += Path(f).read_text() + "\n"
            except OSError:
                partial = True
        conf = parse_sshd(text)
        if partial:
            conf["_partial"] = "1"
            for k in ("passwordauthentication", "permitrootlogin"):
                conf.pop(k, None)  # noma'lum — taxmin qilinmaydi
        return conf

    def _firewall(self) -> dict[str, Any]:
        if not shutil.which("ufw") and not Path("/usr/sbin/ufw").exists():
            return {"tool": "", "active": None}
        out = self._run(["/usr/sbin/ufw", "status", "verbose"], 20)
        if not out:
            return {"tool": "ufw", "active": None}
        rules = [ln.strip() for ln in out.splitlines() if re.match(r"^\S.*\s(ALLOW|DENY|REJECT|LIMIT)\b", ln.strip())]
        return {"tool": "ufw", "active": "Status: active" in out, "rules": rules[:30]}

    @staticmethod
    def _ports() -> list[dict[str, Any]]:
        seen = set()
        rows = []
        for path, v6 in (("/proc/net/tcp", False), ("/proc/net/tcp6", True)):
            try:
                text = Path(path).read_text()
            except OSError:
                continue
            for ip, port in parse_listen(text, v6):
                pub = is_public(ip)
                key = (port, pub)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"port": port, "addr": ip, "public": pub, "name": PORT_NAMES.get(port, "")})
        return sorted(rows, key=lambda r: (not r["public"], r["port"]))

    @staticmethod
    def _cert_days(host: str) -> int | None:
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((host, 443), timeout=6) as s, ctx.wrap_socket(s, server_hostname=host) as t:
                exp = ssl.cert_time_to_seconds(t.getpeercert()["notAfter"])
            return int((exp - time.time()) // 86400)
        except (OSError, ssl.SSLError, KeyError, ValueError):
            return None

    @staticmethod
    def _http(url: str) -> dict[str, Any]:
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "foydali-monitor"}), timeout=10) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            return {"ok": False, "code": None, "ms": None, "error": str(getattr(e, "reason", e))[:120]}
        return {"ok": code < 500, "code": code, "ms": int((time.perf_counter() - t0) * 1000)}

    def _backups(self) -> dict[str, Any]:
        if not self.backups or not os.path.isdir(self.backups):
            return {}
        try:
            items = sorted(((e.stat().st_mtime, e.name) for e in os.scandir(self.backups)), reverse=True)
        except OSError:
            return {}
        if not items:
            return {"count": 0}
        last = items[0]
        return {"count": len(items), "last": last[1], "age_h": round((time.time() - last[0]) / 3600, 1)}

    @staticmethod
    def _failed_units() -> list[str]:
        try:
            r = subprocess.run(["systemctl", "--failed", "--no-legend", "--plain", "--type=service"], capture_output=True,
                               text=True, timeout=10)
            return [ln.split()[0] for ln in r.stdout.splitlines() if ln.strip()]
        except (OSError, subprocess.SubprocessError):
            return []

    @staticmethod
    def _sessions() -> list[dict[str, str]]:
        try:
            r = subprocess.run(["who", "--ips"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            return []
        rows = []
        for ln in r.stdout.splitlines():
            f = ln.split()
            if len(f) >= 4:
                rows.append({"user": f[0], "tty": f[1], "since": " ".join(f[2:4]), "from": f[-1] if len(f) > 4 else ""})
        return rows

    def collect(self) -> dict[str, Any]:
        """Tez qism — 5 daqiqada; sekin qism (sertifikatlar, 7 kunlik kirishlar, yangilanishlar) — soatda."""
        now = time.time()
        if now - self.slow_at > 3600 or not self.slow:
            upd = ""
            try:
                upd = Path("/var/lib/update-notifier/updates-available").read_text()
            except OSError:
                pass
            total, sec = parse_updates(upd)
            self.slow = {"accepted": self._accepted(),
                         "certs": {s["host"]: self._cert_days(s["host"]) for s in self.sites if s.get("host")},
                         "updates": {"total": total, "security": sec, "reboot": Path("/var/run/reboot-required").exists()},
                         "fail2ban": bool(shutil.which("fail2ban-client") or Path("/usr/bin/fail2ban-client").exists())}
            self.slow_at = now
        data = {"at": now, **self.slow, "ssh": self._ssh(), "sshd": self._sshd(), "firewall": self._firewall(),
                "ports": self._ports(), "backups": self._backups(), "failed_units": self._failed_units(),
                "sessions": self._sessions(),
                "sites": [{**s, **self._http(s["url"])} for s in self.sites if s.get("url")]}
        data["risks"], data["score"] = self.assess(data)
        with self.lock:
            self.data, self.at = data, now
        return data

    @staticmethod
    def assess(d: dict[str, Any]) -> tuple[list[dict[str, str]], int]:
        """Xavflar ro'yxati (daraja, sarlavha, nima qilish kerak) va umumiy ball (100 — yaxshi)."""
        risks: list[dict[str, str]] = []

        def add(level, title, fix):
            risks.append({"level": level, "title": title, "fix": fix})
        sshd, ssh = d.get("sshd") or {}, d.get("ssh") or {}
        root = sshd.get("permitrootlogin", "prohibit-password")
        pw = sshd.get("passwordauthentication", "yes")
        if sshd.get("_partial"):
            add("medium", "SSH sozlamasini to'liq o'qib bo'lmadi", "sudoers'da `sshd -T` ruxsatini tekshiring (deploy qayta yozadi).")
        elif root == "yes" and pw != "no":
            add("critical", "root parol bilan SSH orqali kira oladi",
                "SSH kalit bilan kirishni sozlang, so'ng PasswordAuthentication no va PermitRootLogin prohibit-password.")
        elif pw != "no":
            add("high", "SSH parol bilan kirish yoqilgan", "Kalit bilan kirishga o'ting: PasswordAuthentication no.")
        if ssh.get("fails", 0) > 500:
            add("high", f"Oxirgi 24 soatda {ssh['fails']} ta SSH parol taxmini ({ssh.get('unique_ips', 0)} IP)",
                "fail2ban o'rnating (urinayotgan IP'larni avtomatik bloklaydi) va parol bilan kirishni o'chiring.")
        fw = d.get("firewall") or {}
        if fw.get("active") is False:
            add("high", "Firewall o'chiq (ufw inactive)", "Faqat 22, 80, 443 portlarini ochib, ufw'ni yoqing.")
        if not d.get("fail2ban"):
            add("medium", "fail2ban o'rnatilmagan", "apt install fail2ban — sshd uchun himoya darhol ishlaydi.")
        for p in d.get("ports") or []:
            if p["public"] and p["port"] not in (22, 80, 443):
                add("high", f"{p['port']}-port internetga ochiq ({p['name'] or 'noma`lum'})",
                    "Kerak bo'lmasa — 127.0.0.1 ga bog'lang yoki firewall bilan yoping.")
        up = d.get("updates") or {}
        if up.get("security"):
            add("high", f"{up['security']} ta xavfsizlik yangilanishi o'rnatilmagan", "apt upgrade (ish vaqtidan tashqari).")
        elif up.get("total"):
            add("low", f"{up['total']} ta yangilanish kutmoqda", "Rejali vaqtda apt upgrade.")
        if up.get("reboot"):
            add("medium", "Server qayta yuklanishni kutyapti (yadro yangilangan)", "Tungi vaqtda qayta yuklang.")
        for host, days in (d.get("certs") or {}).items():
            if days is None:
                add("medium", f"{host}: SSL sertifikatini tekshirib bo'lmadi", "certbot certificates — holatini tekshiring.")
            elif days < 14:
                add("high" if days < 7 else "medium", f"{host}: SSL sertifikati {days} kunda tugaydi", "certbot renew")
        for s in d.get("sites") or []:
            if not s.get("ok"):
                add("critical", f"{s.get('name') or s.get('url')}: sayt javob bermayapti", "Servis va nginx loglarini tekshiring.")
        b = d.get("backups") or {}
        if b and b.get("age_h") is not None and b["age_h"] > 30:
            add("high", f"Oxirgi zaxira {b['age_h']:.0f} soat oldin", "foydali-backup.timer holatini tekshiring.")
        for u in d.get("failed_units") or []:
            add("low", f"Yiqilgan tizim servisi: {u}", "systemctl status " + u)
        weight = {"critical": 30, "high": 15, "medium": 7, "low": 2}
        score = max(0, 100 - sum(weight[r["level"]] for r in risks))
        order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        return sorted(risks, key=lambda r: order[r["level"]]), score

    def loop(self, stop: threading.Event, every: int = 300) -> None:
        while not stop.is_set():
            try:
                self.collect()
            except Exception:  # noqa: BLE001 — kuzatuvchi yiqilmasin
                pass
            stop.wait(every)

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return dict(self.data)

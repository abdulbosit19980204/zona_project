"""Server resurslari: hozirgi holat, tarix (24 soat / 31 kun) va prognoz — faqat Python standart kutubxonasi.

Linux'da /proc va systemd'dan o'qiydi (root shart emas): CPU, RAM, disk, load, tarmoq; har bir servisning RAM va CPU
iste'moli (systemd cgroup: MemoryCurrent, CPUUsageNSec; pm2'dagi panel — PID orqali); ma'lumotlar hajmi (baza, rasmlar,
zaxiralar). Tarix diskka yoziladi — nazoratchi qayta ishga tushsa ham saqlanadi. Prognoz: disk necha kunda to'ladi,
RAM/CPU cho'qqilari, xotirasi o'sib borayotgan servis (sizib chiqish) — resurslarni oldindan rejalashtirish uchun.
Windows/macOS'da (lokal) — faqat disk; qolgani "mavjud emas".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

SAMPLE_EVERY = 10          # s
MINUTE_POINTS = 1440       # 24 soat, daqiqalik
QUARTER_POINTS = 31 * 96   # 31 kun, 15 daqiqalik
SIZES_EVERY = 600          # ma'lumotlar hajmi — 10 daqiqada bir
PROC = Path("/proc")


# ---------------------------------------------------------------- /proc o'qish (sof funksiyalar — testlanadi)
def parse_meminfo(text: str) -> dict[str, int]:
    """/proc/meminfo -> baytlar: total, available, used, swap_total, swap_used."""
    kv = {}
    for line in text.splitlines():
        k, _, v = line.partition(":")
        parts = v.split()
        if parts and parts[0].isdigit():
            kv[k.strip()] = int(parts[0]) * 1024
    total, avail = kv.get("MemTotal", 0), kv.get("MemAvailable", kv.get("MemFree", 0))
    st, sf = kv.get("SwapTotal", 0), kv.get("SwapFree", 0)
    return {"total": total, "available": avail, "used": max(0, total - avail), "swap_total": st, "swap_used": max(0, st - sf)}


def parse_cpu(text: str) -> tuple[int, int]:
    """/proc/stat birinchi qatori -> (band, jami) jiffies."""
    for line in text.splitlines():
        if line.startswith("cpu "):
            vals = [int(x) for x in line.split()[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            return sum(vals) - idle, sum(vals)
    return 0, 0


def parse_cores(text: str) -> list[tuple[int, int]]:
    """/proc/stat cpuN qatorlari -> har bir yadro (band, jami)."""
    out = []
    for line in text.splitlines():
        if line.startswith("cpu") and line[3:4].isdigit():
            vals = [int(x) for x in line.split()[1:]]
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
            out.append((sum(vals) - idle, sum(vals)))
    return out


def parse_diskstats(text: str) -> tuple[int, int]:
    """/proc/diskstats -> (o'qilgan, yozilgan) baytlar — faqat butun disklar (sda, vda, nvme0n1), bo'limlarsiz."""
    rd = wr = 0
    for line in text.splitlines():
        f = line.split()
        if len(f) < 10:
            continue
        name = f[2]
        if name.startswith(("loop", "ram", "sr", "dm-")) or (name[-1].isdigit() and not name.startswith("nvme")) \
                or (name.startswith("nvme") and "p" in name[4:]):
            continue
        rd, wr = rd + int(f[5]) * 512, wr + int(f[9]) * 512
    return rd, wr


def parse_net(text: str) -> tuple[int, int]:
    """/proc/net/dev -> (qabul, yuborilgan) baytlar, lo'siz."""
    rx = tx = 0
    for line in text.splitlines()[2:]:
        name, _, rest = line.partition(":")
        if name.strip() in ("lo", "") or not rest:
            continue
        f = rest.split()
        rx, tx = rx + int(f[0]), tx + int(f[8])
    return rx, tx


def parse_systemd_show(text: str) -> dict[str, dict[str, str]]:
    """`systemctl show u1 u2 -p Id,MemoryCurrent,CPUUsageNSec` -> {unit: {prop: value}} (bloklar bo'sh qator bilan)."""
    out, cur = {}, {}
    for line in [*text.splitlines(), ""]:
        if not line.strip():
            if cur.get("Id"):
                out[cur["Id"].removesuffix(".service")] = cur
            cur = {}
            continue
        k, _, v = line.partition("=")
        cur[k] = v
    return out


def _num(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0  # "[not set]"


def dir_size(path: Path, limit: int = 200_000) -> int:
    """Papka hajmi (bayt); juda ko'p fayl bo'lsa — limitgacha sanaladi."""
    if path.is_file():
        return path.stat().st_size
    total, n, stack = 0, 0, [path]
    while stack and n < limit:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    n += 1
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def pct(values: list[float], p: float) -> float | None:
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    return vals[min(len(vals) - 1, int(round(p * (len(vals) - 1))))]


def growth_per_day(points: list[tuple[float, float]]) -> float | None:
    """Chiziqli trend (eng kichik kvadratlar): birlik/kun. Kamida 6 soatlik ma'lumot kerak."""
    pts = [(t, v) for t, v in points if v is not None]
    if len(pts) < 4 or pts[-1][0] - pts[0][0] < 6 * 3600:
        return None
    n = len(pts)
    mt, mv = sum(t for t, _ in pts) / n, sum(v for _, v in pts) / n
    den = sum((t - mt) ** 2 for t, _ in pts)
    if not den:
        return None
    return sum((t - mt) * (v - mv) for t, v in pts) / den * 86400


_SECRET_ARG = re.compile(r"(?i)((?:pass(?:word)?|token|secret|key)[=:\s]+)\S+")


def _mask_cmd(cmd: str) -> str:
    """Buyruq qatoridagi parol/token qiymatlari yashiriladi (sahifada ko'rsatiladi)."""
    return _SECRET_ARG.sub(r"\1***", cmd)


# ---------------------------------------------------------------- kuzatuvchi
class Resources:
    def __init__(self, config: dict[str, Any], services: list[Any], data_dir: Path):
        cfg = config.get("resources") or {}
        self.services = services  # control.Service ro'yxati (unit / ctl / group / label)
        self.extra = cfg.get("extra_units") or []  # boshqa loyihalar: [{"unit", "label", "group"}]
        self.paths = cfg.get("paths") or []        # [{"label", "path"}]
        self.disk_path = cfg.get("disk") or ("/" if PROC.exists() else str(Path(__file__).resolve().anchor))
        self.file = data_dir / "metrics.json"
        self.lock = threading.Lock()
        self.minutes: deque = deque(maxlen=MINUTE_POINTS)
        self.quarters: deque = deque(maxlen=QUARTER_POINTS)
        self.current: dict[str, Any] = {}
        self.sizes: list[dict[str, Any]] = []
        self.sizes_at = 0.0
        self._prev_cpu = self._prev_net = self._prev_io = None
        self._prev_cores: list[tuple[int, int]] | None = None
        self._prev_procs: dict[int, tuple[float, float]] = {}
        self._sys: dict[str, Any] = {}
        self._prev_units: dict[str, tuple[int, float]] = {}
        self._bucket: list[dict[str, Any]] = []
        self._qbucket: list[dict[str, Any]] = []
        self._load()

    # ---------- saqlash ----------
    def _load(self) -> None:
        try:
            data = json.loads(self.file.read_text("utf-8"))
            self.minutes.extend(data.get("minutes") or [])
            self.quarters.extend(data.get("quarters") or [])
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        with self.lock:
            data = {"minutes": list(self.minutes), "quarters": list(self.quarters)}
        tmp = self.file.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(data, separators=(",", ":")), "utf-8")
            os.replace(tmp, self.file)
        except OSError:
            pass

    # ---------- o'lchash ----------
    def _read(self, name: str) -> str:
        try:
            return (PROC / name).read_text()
        except OSError:
            return ""

    def _units(self, dt: float) -> list[dict[str, Any]]:
        """Har bir servis: RAM (bayt) va CPU (% bitta yadroga nisbatan emas — butun serverga nisbatan)."""
        rows, units = [], []
        for s in self.services:
            if getattr(s, "unit", ""):
                units.append((s.unit, s.label, s.group or "Servislar"))
        for x in self.extra:
            units.append((x["unit"], x.get("label") or x["unit"], x.get("group") or "Boshqa loyihalar"))
        known = {u for u, _l, _g in units}
        for u in self._discover():  # serverdagi qolgan barcha ishlayotgan servislar (BioLab, tizim...)
            if u not in known:
                units.append((u, u, "BioLab" if u.startswith("biolab") else "Tizim"))
        props = {}
        if units and shutil.which("systemctl"):
            try:
                r = subprocess.run(["systemctl", "show", *[u for u, _l, _g in units], "-p", "Id,MemoryCurrent,CPUUsageNSec,ActiveState"],
                                   capture_output=True, text=True, timeout=10)
                props = parse_systemd_show(r.stdout)
            except (OSError, subprocess.SubprocessError):
                props = {}
        ncpu = os.cpu_count() or 1
        now = time.monotonic()
        for unit, label, group in units:
            p = props.get(unit) or {}
            mem, cpu_ns = _num(p.get("MemoryCurrent")), _num(p.get("CPUUsageNSec"))
            rows.append(self._row(unit, label, group, mem, cpu_ns / 1e9, now, ncpu, p.get("ActiveState", "")))
        for s in self.services:  # systemd'dan tashqari (pm2'dagi panel) — PID orqali
            pid = getattr(s, "ext_pid", None) or (s.proc.pid if getattr(s, "proc", None) else None)
            if getattr(s, "unit", "") or not pid:
                continue
            mem, cpu_s = self._pid_usage(pid)
            rows.append(self._row(s.name, s.label, s.group or "Servislar", mem, cpu_s, now, ncpu, "active"))
        return rows

    _disc: tuple[float, list[str]] = (0.0, [])

    def _discover(self) -> list[str]:
        """Ishlayotgan va yiqilgan barcha systemd servislari (daqiqada bir yangilanadi)."""
        if time.time() - self._disc[0] < 60 or not shutil.which("systemctl"):
            return self._disc[1]
        try:
            r = subprocess.run(["systemctl", "list-units", "--type=service", "--state=running,failed", "--no-legend", "--plain"],
                               capture_output=True, text=True, timeout=10)
            names = [ln.split()[0].removesuffix(".service") for ln in r.stdout.splitlines() if ln.strip()]
        except (OSError, subprocess.SubprocessError):
            names = []
        self._disc = (time.time(), names)
        return names

    def _row(self, key, label, group, mem, cpu_s, now, ncpu, state):
        prev = self._prev_units.get(key)
        self._prev_units[key] = (cpu_s, now)
        cpu = None
        if prev and now > prev[1] and cpu_s >= prev[0]:
            cpu = round(100 * (cpu_s - prev[0]) / (now - prev[1]) / ncpu, 1)
        return {"key": key, "label": label, "group": group, "mem": mem, "cpu": cpu, "state": state}

    def _procs(self, top: int = 15) -> list[dict[str, Any]]:
        """Eng ko'p CPU / RAM ishlatayotgan jarayonlar (barcha foydalanuvchilar; /proc o'qiladi)."""
        if not PROC.exists():
            return []
        tck = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
        ncpu, now, rows, seen = os.cpu_count() or 1, time.monotonic(), [], {}
        users = self._users()
        for d in os.scandir(PROC):
            if not d.name.isdigit():
                continue
            pid = int(d.name)
            try:
                stat = (PROC / d.name / "stat").read_text()
                name = stat[stat.index("(") + 1:stat.rindex(")")]
                f = stat.rsplit(")", 1)[1].split()
                cpu_s = (int(f[11]) + int(f[12])) / tck
                rss = int(f[21]) * 4096
                uid = (PROC / d.name).stat().st_uid
            except (OSError, ValueError, IndexError):
                continue
            prev = self._prev_procs.get(pid)
            seen[pid] = (cpu_s, now)
            cpu = round(100 * (cpu_s - prev[0]) / (now - prev[1]) / ncpu, 1) if prev and now > prev[1] else None
            rows.append({"pid": pid, "name": name, "user": users.get(uid, str(uid)), "cpu": cpu, "mem": rss})
        self._prev_procs = seen
        by_cpu = sorted(rows, key=lambda r: -(r["cpu"] or 0))[:top]
        by_mem = sorted(rows, key=lambda r: -r["mem"])[:top]
        pick = {r["pid"]: r for r in [*by_cpu, *by_mem]}
        for r in pick.values():
            try:
                cmd = (PROC / str(r["pid"]) / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            except OSError:
                cmd = ""
            r["cmd"] = _mask_cmd(cmd)[:160]
        return sorted(pick.values(), key=lambda r: -((r["cpu"] or 0) * 1e12 + r["mem"]))[:top * 2]

    _users_cache: tuple[float, dict[int, str]] = (0.0, {})

    def _users(self) -> dict[int, str]:
        if time.time() - self._users_cache[0] < 600:
            return self._users_cache[1]
        out = {}
        try:
            for ln in Path("/etc/passwd").read_text().splitlines():
                f = ln.split(":")
                if len(f) > 2 and f[2].isdigit():
                    out[int(f[2])] = f[0]
        except OSError:
            pass
        self._users_cache = (time.time(), out)
        return out

    def _system(self) -> dict[str, Any]:
        if not self._sys:
            info: dict[str, Any] = {"host": os.uname().nodename if hasattr(os, "uname") else ""}
            try:
                for ln in Path("/etc/os-release").read_text().splitlines():
                    if ln.startswith("PRETTY_NAME="):
                        info["os"] = ln.split("=", 1)[1].strip('"')
            except OSError:
                pass
            info["kernel"] = os.uname().release if hasattr(os, "uname") else ""
            try:
                cpu = next((ln.split(":", 1)[1].strip() for ln in Path("/proc/cpuinfo").read_text().splitlines()
                            if ln.startswith("model name")), "")
                info["cpu_model"] = cpu
            except (OSError, StopIteration):
                pass
            self._sys = info
        up = self._read("uptime").split()
        return {**self._sys, "uptime": float(up[0]) if up else None, "procs": sum(1 for d in os.scandir(PROC) if d.name.isdigit()) if PROC.exists() else None}

    def _pid_usage(self, pid: int) -> tuple[int, float]:
        status, stat = self._read(f"{pid}/status"), self._read(f"{pid}/stat")
        rss = next((int(ln.split()[1]) * 1024 for ln in status.splitlines() if ln.startswith("VmRSS:")), 0)
        try:
            f = stat.rsplit(")", 1)[1].split()
            ticks = int(f[11]) + int(f[12]) + int(f[13]) + int(f[14])  # utime stime cutime cstime
            return rss, ticks / os.sysconf("SC_CLK_TCK")
        except (IndexError, ValueError, AttributeError, OSError):
            return rss, 0.0

    def sample(self) -> dict[str, Any]:
        t = time.time()
        cur: dict[str, Any] = {"at": t, "cores": os.cpu_count() or 1}
        busy, total = parse_cpu(self._read("stat"))
        if total:
            if self._prev_cpu and total > self._prev_cpu[1]:
                cur["cpu"] = round(100 * (busy - self._prev_cpu[0]) / (total - self._prev_cpu[1]), 1)
            self._prev_cpu = (busy, total)
        mem = parse_meminfo(self._read("meminfo"))
        if mem["total"]:
            cur["mem"] = mem
        try:
            cur["load"] = list(os.getloadavg())
        except (OSError, AttributeError):
            pass
        try:
            du = shutil.disk_usage(self.disk_path)
            cur["disk"] = {"total": du.total, "used": du.used, "free": du.free}
        except OSError:
            pass
        rx, tx = parse_net(self._read("net/dev"))
        if rx or tx:
            if self._prev_net and t > self._prev_net[2]:
                dt = t - self._prev_net[2]
                cur["net"] = {"rx": max(0, (rx - self._prev_net[0]) / dt), "tx": max(0, (tx - self._prev_net[1]) / dt)}
            self._prev_net = (rx, tx, t)
        stat = self._read("stat")
        cores = parse_cores(stat)
        if cores:
            prev = self._prev_cores or []
            pcts = []
            for i, (busy_i, total_i) in enumerate(cores):
                if i < len(prev) and total_i > prev[i][1]:
                    pcts.append(round(100 * (busy_i - prev[i][0]) / (total_i - prev[i][1]), 1))
                else:
                    pcts.append(None)
            cur["cores_pct"] = pcts
            self._prev_cores = cores
        rd, wr = parse_diskstats(self._read("diskstats"))
        if rd or wr:
            if self._prev_io and t > self._prev_io[2]:
                dt = t - self._prev_io[2]
                cur["io"] = {"rd": max(0, (rd - self._prev_io[0]) / dt), "wr": max(0, (wr - self._prev_io[1]) / dt)}
            self._prev_io = (rd, wr, t)
        cur["procs"] = self._procs()
        cur["system"] = self._system()
        cur["services"] = self._units(SAMPLE_EVERY)
        if time.time() - self.sizes_at > SIZES_EVERY:
            self.sizes_at = time.time()
            self.sizes = [{"label": p["label"], "path": p["path"], "bytes": dir_size(Path(p["path"]))}
                          for p in self.paths if Path(p["path"]).exists()]
        cur["sizes"] = self.sizes
        with self.lock:
            self.current = cur
            self._bucket.append(cur)
            if not self.minutes or t - self.minutes[-1]["t"] >= 60:
                self._flush_minute(t)
        return cur

    @staticmethod
    def _avg(rows: list[dict[str, Any]], getter) -> float | None:
        vals = [v for v in (getter(r) for r in rows) if v is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    def _point(self, rows, t):
        svc = {}
        for r in rows:
            for s in r.get("services") or []:
                svc.setdefault(s["key"], []).append(s)
        return {
            "t": int(t), "cpu": self._avg(rows, lambda r: r.get("cpu")),
            "cpu_max": max((r["cpu"] for r in rows if r.get("cpu") is not None), default=None),
            "mem": self._avg(rows, lambda r: (r.get("mem") or {}).get("used")),
            "disk": self._avg(rows, lambda r: (r.get("disk") or {}).get("used")),
            "load": self._avg(rows, lambda r: (r.get("load") or [None])[0]),
            "rx": self._avg(rows, lambda r: (r.get("net") or {}).get("rx")),
            "tx": self._avg(rows, lambda r: (r.get("net") or {}).get("tx")),
            "rd": self._avg(rows, lambda r: (r.get("io") or {}).get("rd")),
            "wr": self._avg(rows, lambda r: (r.get("io") or {}).get("wr")),
            "s": {k: [self._avg(v, lambda x: x["mem"]), self._avg(v, lambda x: x["cpu"])] for k, v in svc.items()},
        }

    def _flush_minute(self, t: float) -> None:
        if not self._bucket:
            return
        p = self._point(self._bucket, t)
        self._bucket = []
        self.minutes.append(p)
        self._qbucket.append(p)
        if not self.quarters or t - self.quarters[-1]["t"] >= 900:
            q = {"t": int(t)}
            for k in ("cpu", "mem", "disk", "load", "rx", "tx", "rd", "wr"):
                q[k] = self._avg(self._qbucket, lambda x, k=k: x.get(k))
            q["cpu_max"] = max((x["cpu_max"] for x in self._qbucket if x.get("cpu_max") is not None), default=None)
            keys = {k for x in self._qbucket for k in x.get("s", {})}
            q["s"] = {k: [self._avg(self._qbucket, lambda x, k=k: (x["s"].get(k) or [None, None])[0]),
                          self._avg(self._qbucket, lambda x, k=k: (x["s"].get(k) or [None, None])[1])] for k in keys}
            self.quarters.append(q)
            self._qbucket = []

    def loop(self, stop: threading.Event) -> None:
        last_save = time.time()
        while not stop.is_set():
            try:
                self.sample()
                if time.time() - last_save > 300:
                    self.save()
                    last_save = time.time()
            except Exception:  # noqa: BLE001 — kuzatuvchi hech qachon yiqilmasin
                pass
            stop.wait(SAMPLE_EVERY)
        self.save()

    # ---------- natija ----------
    def forecast(self) -> dict[str, Any]:
        with self.lock:
            mins, qs, cur = list(self.minutes), list(self.quarters), dict(self.current)
        out: dict[str, Any] = {"notes": []}
        day = [m for m in mins if m["t"] >= time.time() - 86400]
        out["cpu_p95_24h"] = pct([m.get("cpu") for m in day], 0.95)
        out["cpu_peak_24h"] = max((m["cpu_max"] for m in day if m.get("cpu_max") is not None), default=None)
        out["mem_peak_24h"] = max((m["mem"] for m in day if m.get("mem") is not None), default=None)
        out["load_p95_24h"] = pct([m.get("load") for m in day], 0.95)
        series = qs if len(qs) >= 8 else mins
        disk = cur.get("disk") or {}
        g = growth_per_day([(p["t"], p.get("disk")) for p in series[-7 * 96:]])
        out["disk_growth_day"] = g
        if g and g > 0 and disk.get("total"):
            left = disk["total"] * 0.9 - disk["used"]
            out["disk_days_to_90"] = max(0, int(left / g))
        mem = cur.get("mem") or {}
        cores = cur.get("cores") or 1
        if mem.get("total") and out["mem_peak_24h"]:
            share = out["mem_peak_24h"] / mem["total"]
            if share > 0.85:
                out["notes"].append(("bad", f"RAM cho'qqisi {share:.0%} — swap yo'q bo'lsa servislar o'chib qolishi mumkin: RAM qo'shing yoki swap yoqing."))
            elif share > 0.7:
                out["notes"].append(("warn", f"RAM cho'qqisi {share:.0%} — yangi og'ir servis qo'shishdan oldin RAM'ni oshirishni rejalashtiring."))
        if mem.get("total") and not mem.get("swap_total"):
            out["notes"].append(("info", "Swap yoqilmagan: RAM to'lib qolsa tizim jarayonni o'ldiradi. 2–4 GB swap — arzon sug'urta."))
        if out["load_p95_24h"] and out["load_p95_24h"] > cores:
            out["notes"].append(("warn", f"Yuklama (load) ko'pincha {out['load_p95_24h']:.1f} — yadrolar soni {cores}: CPU yetishmayapti."))
        if out["cpu_p95_24h"] is not None and out["cpu_p95_24h"] > 80:
            out["notes"].append(("warn", f"CPU 24 soatda 95% vaqt {out['cpu_p95_24h']:.0f}% gacha band."))
        d90 = out.get("disk_days_to_90")
        if d90 is not None and d90 < 60:
            out["notes"].append(("bad" if d90 < 14 else "warn", f"Disk shu sur'atda ~{d90} kunda 90% ga yetadi — eski zaxira/rasmlarni tozalang yoki diskni kengaytiring."))
        # xotirasi o'sib borayotgan servis (sizib chiqish belgisi): oxirgi 24 soat trendi
        for key in {k for m in day for k in m.get("s", {})}:
            pts = [(m["t"], (m["s"].get(key) or [None])[0]) for m in day]
            gr = growth_per_day(pts)
            last = next((v for _t, v in reversed(pts) if v), 0)
            if gr and last and gr > max(150 * 1024 * 1024, 0.3 * last):
                label = next((s["label"] for s in cur.get("services") or [] if s["key"] == key), key)
                out["notes"].append(("warn", f"{label}: xotirasi kuniga ~{gr / 1048576:.0f} MB o'smoqda — sizib chiqish bo'lishi mumkin (qayta ishga tushirish vaqtincha yordam beradi)."))
        if not out["notes"]:
            out["notes"].append(("ok", "Resurslar yetarli — hozircha kengaytirish shart emas."))
        return out

    def snapshot(self, rng: str = "24h") -> dict[str, Any]:
        with self.lock:
            cur = dict(self.current)
            series = list(self.minutes) if rng == "24h" else list(self.quarters)
        groups: dict[str, dict[str, Any]] = {}
        for s in cur.get("services") or []:
            g = groups.setdefault(s["group"], {"group": s["group"], "mem": 0, "cpu": 0.0})
            g["mem"] += s["mem"] or 0
            g["cpu"] += s["cpu"] or 0
        mem = cur.get("mem") or {}
        known = sum(g["mem"] for g in groups.values())
        if mem.get("used") and mem["used"] > known:
            groups["Tizim va boshqalar"] = {"group": "Tizim va boshqalar", "mem": mem["used"] - known, "cpu": None}
        return {"current": cur, "groups": sorted(groups.values(), key=lambda g: -g["mem"]),
                "series": [{k: p.get(k) for k in ("t", "cpu", "cpu_max", "mem", "disk", "load", "rx", "tx", "rd", "wr")} for p in series],
                "range": rng, "forecast": self.forecast(), "available": bool(PROC.exists())}

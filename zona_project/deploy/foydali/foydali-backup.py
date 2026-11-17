"""Foydali: bazalarning kunlik zaxira nusxasi (SQLite online backup — servislar ishlab turganda ham xavfsiz).
/var/lib/foydali/backups/<sana>/ ga yoziladi, 14 kundan eskilari o'chiriladi. systemd: foydali-backup.timer"""
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

DATA = Path("/var/lib/foydali")
OUT = DATA / "backups"
KEEP_DAYS = 14
DBS = {"zona.sqlite3": DATA / "db.sqlite3", "qrdrive.sqlite3": DATA / "qrdrive" / "qrdrive.sqlite3"}

day = OUT / datetime.now().strftime("%Y-%m-%d")
day.mkdir(parents=True, exist_ok=True)
for name, src in DBS.items():
    if not src.is_file():
        continue
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(day / name) as d:
        s.backup(d)
    print(f"zaxira: {day / name}")
for old in OUT.iterdir():
    if old.is_dir() and time.time() - old.stat().st_mtime > KEEP_DAYS * 86400:
        shutil.rmtree(old, ignore_errors=True)

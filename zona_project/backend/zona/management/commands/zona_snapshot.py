"""Bazaning deploy uchun nusxasi (snapshot): python manage.py zona_snapshot [yo'l]

- SQLite "backup" API bilan izchil nusxa olinadi (server ishlab turgan paytda ham xavfsiz).
- Nusxadan vaqtinchalik ma'lumotlar tozalanadi: kirish sessiyalari va JWT tokenlari (serverda hamma qaytadan kiradi).
- Standart yo'l: <repo>/deploy/data/zona.sqlite3 — git orqali serverga boradi; serverda deploy/install.sh
  uni faqat BIRINCHI marta doimiy joyga (/var/lib/zona/db.sqlite3) ko'chiradi, keyingi yangilanishlar ishchi bazaga tegmaydi.
"""
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

DEFAULT = Path(settings.BASE_DIR).parent / "deploy" / "data" / "zona.sqlite3"
CLEAN = ["django_session", "token_blacklist_blacklistedtoken", "token_blacklist_outstandingtoken"]


class Command(BaseCommand):
    help = "Bazaning deploy uchun izchil nusxasini yaratadi (deploy/data/zona.sqlite3)."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT))

    def handle(self, *args, **opts):
        if connection.vendor != "sqlite":
            raise CommandError("Faqat SQLite bazasi uchun.")
        src_path = Path(settings.DATABASES["default"]["NAME"])
        dst_path = Path(opts["path"]).resolve()
        if dst_path == src_path.resolve():
            raise CommandError("Nusxa ishchi bazaning o'zi bo'lib qolmasin.")
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst_path.with_suffix(".tmp")
        tmp.unlink(missing_ok=True)
        src = sqlite3.connect(str(src_path))
        dst = sqlite3.connect(str(tmp))
        with dst:
            src.backup(dst)
        src.close()
        tables = {r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in CLEAN:
            if t in tables:
                dst.execute(f"DELETE FROM {t}")  # noqa: S608 — jadval nomlari ro'yxatdan
        dst.commit()
        dst.execute("PRAGMA journal_mode=DELETE")  # bitta fayl (WAL'siz) — git va ko'chirish uchun
        dst.execute("VACUUM")
        ok = dst.execute("PRAGMA integrity_check").fetchone()[0]
        dst.close()
        if ok != "ok":
            tmp.unlink(missing_ok=True)
            raise CommandError(f"Nusxa tekshiruvdan o'tmadi: {ok}")
        tmp.replace(dst_path)
        self.stdout.write(self.style.SUCCESS(f"Snapshot tayyor: {dst_path} ({dst_path.stat().st_size // 1024} KB)"))

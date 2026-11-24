"""PRBC worker — alohida jarayon (systemd: foydali-prbc). Boshqa servislarga bog'liq emas.

    python manage.py prbc_worker          # doimiy: xodimlar har N daqiqada, vazifalar har 2 daqiqada
    python manage.py prbc_worker --once   # bitta to'liq sinxronlash (qo'lda yoki cron)
"""
import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from prbc import people, tasks
from prbc.client import Client, PrbcError
from prbc.models import Connection

log = logging.getLogger("prbc")
TICK, TASK_EVERY = 10, 120


class Command(BaseCommand):
    help = "PRBC: xodimlarni sinxronlash, bo'shaganlarni belgilash, vazifalarni yaratish va kuzatish"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="bitta sinxronlash va chiqish")

    def handle(self, *args, **opts):
        if opts["once"]:
            r = people.run()
            self.stdout.write(f"{'OK' if r.ok else 'XATO'}: {r.stats} {r.error}")
            return
        stop = {"flag": False}
        signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
        last_task = 0.0
        self.stdout.write("PRBC worker ishga tushdi")
        while not stop["flag"]:
            close_old_connections()
            try:
                conn = Connection.get()
                Connection.objects.filter(pk=1).update(worker_beat=timezone.now())
                if conn.enabled and conn.phone and conn.password_enc:
                    due = (conn.last_sync_at is None
                           or (timezone.now() - conn.last_sync_at).total_seconds() >= max(5, conn.sync_minutes) * 60)
                    if conn.sync_requested or due:
                        people.run(conn)
                    from support.models import SupportTask
                    if SupportTask.objects.filter(status=SupportTask.QUEUED, attempts__lt=3).exists():
                        tasks.process_support_queue(client=Client(Connection.get()))  # bot navbati — ~10 soniyada
                    if time.time() - last_task >= TASK_EVERY or conn.sync_requested:
                        last_task = time.time()
                        tasks.poll(client=Client(Connection.get()))  # holat va "bajarildi" hisoboti
                elif conn.sync_requested:  # ulanish yoqilmagan — so'rov bajarilmaydi, sababi yoziladi
                    Connection.objects.filter(pk=1).update(sync_requested=False,
                                                           last_error="PRBC ulanishi yoqilmagan yoki parol kiritilmagan.")
            except PrbcError as e:
                Connection.objects.filter(pk=1).update(last_error=str(e)[:2000])
            except Exception:  # noqa: BLE001 — worker hech qachon yiqilmasin
                log.exception("prbc worker tick failed")
            for _ in range(TICK):
                if stop["flag"] or Connection.objects.filter(pk=1, sync_requested=True).exists():
                    break
                time.sleep(1)

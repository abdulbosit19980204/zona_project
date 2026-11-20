"""Standart holatlar uchun shartlarni o'rgatilgan rasmlardan chiqarish: manage.py support_mine_triggers [--apply]."""
from django.core.management.base import BaseCommand

from support.mining import mine


class Command(BaseCommand):
    help = "Standart holatlar rasmlaridan shart iboralarini topadi (--apply bilan yozuvlarga qo'shadi)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--entries", nargs="*", type=int)

    def handle(self, *args, **opts):
        for r in mine(opts.get("entries"), apply=opts["apply"]):
            self.stdout.write(f"#{r['entry']} {r['title'][:60]} | namuna: {r.get('samples', 0)} | mavjud: {r.get('kept', 0)} | "
                              f"yangi: {r['added'] or r.get('note', '—')}")

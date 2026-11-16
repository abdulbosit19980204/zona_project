from django.core.management.base import BaseCommand

from zona import knowledge_seed


class Command(BaseCommand):
    help = "Savollar bazasini tartibga soladi: zonalar, jarayon nomlari, doimiy savollar uchun qoida va misollar."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Faqat ko'rsatish, saqlamaslik")

    def handle(self, *args, **opts):
        knowledge_seed.apply(dry_run=opts["dry_run"], log=self.stdout.write)

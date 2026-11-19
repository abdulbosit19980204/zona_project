from django.core.management.base import BaseCommand

from support.runner import run_forever


class Command(BaseCommand):
    help = "Support botlarni ishga tushirish (admin paneldagi barcha yoqilgan botlar)."

    def handle(self, *args, **opts):
        run_forever()

"""Tarjimasi yo'q yoki eskirgan barcha matnlarni AI orqali uz/ru/en tillariga o'giradi.

    python manage.py zona_translate

"Tarjima" AI vazifasi (Sozlamalar → AI) yoqilgan bo'lishi kerak.
"""
from django.core.management.base import BaseCommand, CommandError

from zona import translation


class Command(BaseCommand):
    help = "Matnlarni AI orqali uz/ru/en tillariga tarjima qilish"

    def handle(self, *args, **options):
        if not translation.enabled():
            raise CommandError("'Tarjima' AI vazifasi yoqilmagan: Sozlamalar → AI da provayder va model tanlang.")
        before = translation.status()["pending"]
        self.stdout.write(f"Tarjima kutayotgan maydonlar: {before}")
        while True:
            done = translation.translate_pending()
            self.stdout.write(f"  tarjima qilindi: {done}")
            st = translation.status()
            if st["last_error"]:
                raise CommandError(f"AI xatosi: {st['last_error']} (qolgan: {st['pending']})")
            if not done or not st["pending"]:
                break
        self.stdout.write(self.style.SUCCESS(f"Tayyor. Qolgan: {translation.status()['pending']}"))

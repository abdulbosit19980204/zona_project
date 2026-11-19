"""Rasm namunalarini bilim bazasi yozuviga o'rgatish (idempotent: bir xil rasm shu yozuvga ikki marta qo'shilmaydi).

  python manage.py support_label_images --title "PRBC → 1C: klient 1C'da allaqachon bor" rasm1.png rasm2.jpg
"""
import hashlib
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from support import ocr, vision
from support.models import Entry, Media


class Command(BaseCommand):
    help = "Rasmlarni yozuvning namunasi qilib saqlash va o'rgatish."

    def add_arguments(self, parser):
        parser.add_argument("files", nargs="+")
        parser.add_argument("--title", required=True, help="Bilim bazasi yozuvining sarlavhasi")
        parser.add_argument("--by", default="boshlang'ich namuna")

    def handle(self, *args, **opts):
        entry = Entry.objects.filter(title=opts["title"]).first()
        if not entry:
            raise CommandError(f"Yozuv topilmadi: {opts['title']}")
        for f in opts["files"]:
            data = Path(f).read_bytes()
            sha = hashlib.sha256(data).hexdigest()
            if Media.objects.filter(sha256=sha, label=entry).exists():
                self.stdout.write(f"  bor: {Path(f).name}")
                continue
            m = vision.store(data, kind=Media.PHOTO, name=Path(f).name, mime="image/png", source="seed")
            Media.objects.filter(pk=m.pk).update(ocr_text=ocr.read_text(data))
            vision.label([m], entry, opts["by"])
            self.stdout.write(f"  o'rgatildi: {Path(f).name} -> {entry.title} (iz {m.dhash})")

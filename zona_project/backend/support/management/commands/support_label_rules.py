"""Mavjud savollarga tez qoidalar bo'yicha tizim belgisi (ilova / manba / toifa). AI yoki xodim belgilaganlariga tegmaydi.
Faqat yangi ustunlar yoziladi — savol matni, holati, javoblari o'zgarmaydi."""
from django.core.management.base import BaseCommand

from support import systems
from support.models import Message


class Command(BaseCommand):
    help = "Savollarga qoidalar bo'yicha tizim belgisi qo'yish (ilova, manba, toifa)"

    def handle(self, *args, **opts):
        n = 0
        qs = (Message.objects.filter(kind=Message.QUESTION).exclude(labeled_by__in=["ai", "staff"])
              .select_related("entry").only("id", "text", "ocr_text", "entry__title", "labeled_by"))
        for q in qs.iterator(chunk_size=500):
            systems.apply(q, q.entry, save=True)
            n += bool(q.labeled_by)
        self.stdout.write(f"belgilandi: {n} / {qs.count()}")

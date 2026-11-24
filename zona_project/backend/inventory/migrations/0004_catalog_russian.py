"""Katalogning ruscha tarjimasi: faqat bo'sh maydonlar to'ldiriladi — qo'lda yozilganlarga tegilmaydi."""
from django.db import migrations


def fill(apps, schema_editor):
    from inventory.seed import fill_russian
    fill_russian(apps)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_ack_telegram_ru")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]

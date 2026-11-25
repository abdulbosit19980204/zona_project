"""Katalogga qo'shimcha IT qurilma turlari: video kuzatuv (faol) va boshqa IT vositalar (nofaol — boshqaruvchi yoqadi).
Faqat YO'Q turlar yaratiladi — mavjud turlar, ularning holati va kiritilgan qurilmalarga tegilmaydi."""
from django.db import migrations


def add(apps, schema_editor):
    from inventory.catalog_extra import add_missing
    add_missing(apps.get_model("inventory", "DeviceType"))


class Migration(migrations.Migration):
    dependencies = [("inventory", "0007_default_specs")]
    operations = [migrations.RunPython(add, migrations.RunPython.noop)]

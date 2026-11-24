"""Har bir qurilma turiga standart texnik xususiyat maydonlari (RAM, disk, protsessor, diagonal...).
Faqat maydonlari BO'SH turlarga yoziladi — qo'lda tahrirlanganlarga tegilmaydi."""
from django.db import migrations


def fill(apps, schema_editor):
    from inventory.specs import default_specs
    DeviceType = apps.get_model("inventory", "DeviceType")
    for d in DeviceType.objects.all():
        if not d.specs:
            specs = default_specs(d.name)
            if specs:
                d.specs = specs
                d.save(update_fields=["specs"])


class Migration(migrations.Migration):
    dependencies = [("inventory", "0006_specs")]
    operations = [migrations.RunPython(fill, migrations.RunPython.noop)]

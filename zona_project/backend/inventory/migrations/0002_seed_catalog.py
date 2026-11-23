"""Boshlang'ich katalog (shablondan): tashkilotlar, filiallar, joylar, 30 ta qurilma turi va brendlari.
Faqat bo'sh jadvallarni to'ldiradi — qayta ishga tushsa ham mavjud yozuvlarga tegmaydi."""
from django.db import migrations


def seed(apps, schema_editor):
    from inventory.seed import seed_catalog
    seed_catalog(apps)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]

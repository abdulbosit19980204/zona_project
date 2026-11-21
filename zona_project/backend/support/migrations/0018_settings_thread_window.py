from django.db import migrations, models


class Migration(migrations.Migration):
    """Faqat yangi ustun qo'shiladi (db_default bilan) — mavjud ma'lumot o'zgarmaydi."""

    dependencies = [
        ("support", "0017_resolution"),
    ]

    operations = [
        migrations.AddField(
            model_name="settings",
            name="thread_window",
            field=models.PositiveIntegerField(db_default=15, default=15,
                                              verbose_name="Bitta suhbat: oxirgi xabardan keyin (daqiqa); 0 — o'chiq"),
        ),
    ]

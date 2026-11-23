from django.db import migrations, models


class Migration(migrations.Migration):
    """Faqat yangi ustunlar (db_default / null) — mavjud ma'lumot o'zgarmaydi."""

    dependencies = [
        ('support', '0024_open_questions'),
    ]

    operations = [
        migrations.AddField(
            model_name='settings',
            name='collapse_after',
            field=models.PositiveSmallIntegerField(db_default=3, default=3, verbose_name="Javobni yig'ish (daqiqa, 0 — yig'ilmaydi)"),
        ),
        migrations.AddField(
            model_name='message',
            name='alert_text',
            field=models.TextField(blank=True, db_default='', default=''),
        ),
        migrations.AddField(
            model_name='message',
            name='reply_html',
            field=models.TextField(blank=True, db_default='', default=''),
        ),
        migrations.AddField(
            model_name='message',
            name='collapsed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

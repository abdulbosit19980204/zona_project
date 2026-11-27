"""Bot javoblari aniqligini baholash — javob yubormasdan (support.evaluate).

  python manage.py support_eval --days 30 --limit 200 --out /var/lib/foydali/eval
  python manage.py support_eval --limit 20 --no-judge          # tez: faqat qamrov va mas'ul, AI-hakamsiz

Natija: <out>/eval_YYYYMMDD_HHMM.json (har savol) va .md (xulosa, xato va qisman javoblar jadvali).
AI-hakam har yuborilgan javobga bitta AI so'rovi qiladi; bot javobi AI'dan bo'lsa — yana bitta.
"""
import os

from django.core.management.base import BaseCommand
from django.utils import timezone

from support import evaluate


class Command(BaseCommand):
    help = "Bot aniqligi: xodim javob bergan savollarga bot hozir nima javob berardi va u to'g'rimi."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--no-judge", action="store_true")
        parser.add_argument("--out", default="/var/lib/foydali/eval")

    def handle(self, *args, **o):
        os.makedirs(o["out"], exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
        base = os.path.join(o["out"], f"eval_{stamp}")

        def progress(i, n, row):
            if i % 10 == 0 or i == n:
                self.stdout.write(f"{i}/{n} …")

        summ, rows = evaluate.run(o["days"], o["limit"], use_judge=not o["no_judge"], out_path=base + ".json",
                                  progress=progress)
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write(evaluate.markdown(summ, rows))
        self.stdout.write(self.style.SUCCESS(f"{summ}\nfayllar: {base}.json, {base}.md"))

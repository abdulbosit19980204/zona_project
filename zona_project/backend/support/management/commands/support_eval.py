"""Bot javoblari aniqligini baholash — javob yubormasdan (support.evaluate).

  python manage.py support_eval --days 30 --limit 200              # AI'siz: baza/shablon qamrovi va mas'ul
  python manage.py support_eval --limit 50 --with-ai --judge       # AI javob + AI-hakam (limit sarflanadi!)

OGOHLANTIRISH: AI so'rovlari jonli bot bilan bir xil provayder limitidan (bepul Gemini kunlik limiti 27.11 da shu
buyruq tufayli tugagan). --with-ai / --judge ni faqat pullik provayder bilan va kichik --limit bilan ishlating.

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
        parser.add_argument("--judge", action="store_true",
                            help="AI-hakam (har yuborilgan javobga 1 AI so'rovi) — jonli bot bilan umumiy limitdan!")
        parser.add_argument("--with-ai", action="store_true",
                            help="Bot javobida AI ham (jonli botdagidek). Standart: faqat baza/shablon/qoida")
        parser.add_argument("--out", default="/var/lib/foydali/eval")

    def handle(self, *args, **o):
        os.makedirs(o["out"], exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M")
        base = os.path.join(o["out"], f"eval_{stamp}")

        def progress(i, n, row):
            if i % 10 == 0 or i == n:
                self.stdout.write(f"{i}/{n} …")

        summ, rows = evaluate.run(o["days"], o["limit"], use_judge=o["judge"], out_path=base + ".json",
                                  progress=progress, use_ai=o["with_ai"])
        with open(base + ".md", "w", encoding="utf-8") as f:
            f.write(evaluate.markdown(summ, rows))
        self.stdout.write(self.style.SUCCESS(f"{summ}\nfayllar: {base}.json, {base}.md"))

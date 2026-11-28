"""AI'siz semantik qidiruv (support.semantic) — model, indeks, chegara sozlash.

  python manage.py support_semantic --download        # model fayllari (bir marta, ~120 MB)
  python manage.py support_semantic --build           # indeks (o'zgargan matnlargina hisoblanadi)
  python manage.py support_semantic --query "lokatsiya uzoq deyapti"
  python manage.py support_semantic --tune            # belgilangan to'plamda chegara × aniqlik / qamrov
  python manage.py support_semantic --eval 88         # AI'siz baholash: semantik bosqich bilan va usiz qamrov
"""
import time

from django.core.management.base import BaseCommand, CommandError

from support import semantic


class Command(BaseCommand):
    help = "AI'siz semantik qidiruv: model yuklash, indeks, sinov va chegara tanlash."

    def add_arguments(self, parser):
        parser.add_argument("--download", action="store_true")
        parser.add_argument("--build", action="store_true")
        parser.add_argument("--query", default="")
        parser.add_argument("--tune", action="store_true")
        parser.add_argument("--eval", type=int, default=0, help="chegara (%), baholash shu bilan")
        parser.add_argument("--days", type=int, default=30)
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **o):
        if o["download"]:
            semantic.download(progress=self.stdout.write)
        if not semantic.available():
            raise CommandError("model yoki kutubxona yo'q: --download va `pip install .[semantic]`")
        if o["build"] or o["query"] or o["tune"] or o["eval"]:
            t = time.monotonic()
            rows = semantic.ensure_index()
            self.stdout.write(f"indeks: {len(rows)} qator, {time.monotonic() - t:.1f} s")
        if o["query"]:
            from support.models import Entry
            t = time.monotonic()
            top = semantic.search(o["query"], k=5)
            ms = (time.monotonic() - t) * 1000
            titles = dict(Entry.objects.filter(pk__in=[e for e, _s in top]).values_list("pk", "title"))
            for eid, s in top:
                self.stdout.write(f"  {s:.3f}  #{eid} {titles.get(eid, '')[:80]}")
            self.stdout.write(f"  ({ms:.0f} ms)")
        if o["tune"]:
            pairs = semantic.labeled()
            self.stdout.write(f"belgilangan to'plam: {len(pairs)} ibora")
            for r in semantic.tune(pairs):
                self.stdout.write(f"  chegara {r['th']:.2f}: javob {r['answered']}/{r['total']} (qamrov {r['coverage']}%), "
                                  f"to'g'ri {r['correct']} — aniqlik {r['precision']}%")
        if o["eval"]:
            from support import evaluate
            base, _rows = evaluate.run(o["days"], o["limit"], use_judge=False, use_ai=False)
            with semantic.forced(o["eval"]):
                sem, rows = evaluate.run(o["days"], o["limit"], use_judge=False, use_ai=False)
            self.stdout.write(f"AI'siz qamrov: semantiksiz {base['coverage_pct']}% → semantik ({o['eval']}%) bilan "
                              f"{sem['coverage_pct']}% ({sem['bot_answered']}/{sem['questions']}); mas'ul to'g'ri "
                              f"{sem['owner_ok_pct_on_handoff']}%")
            for r in rows:
                if r["sent"] and "semantik" in (r.get("note") or ""):
                    self.stdout.write(f"  + «{r['question'][:80]}» → {r['entry'][:60]} | xodim: {r['staff_answer'][:60]}")

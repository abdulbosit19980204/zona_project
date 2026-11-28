"""Deploydan keyingi sinov — javob yubormasdan, AI chaqirmasdan (support.smoke).

  python manage.py support_smoke                   # 3 ta asosiy savol: PASS / FAIL (xato bo'lsa chiqish kodi 1)
  python manage.py support_smoke --standards 15    # + eng ko'p ishlatiladigan 15 standart × 5 haqiqiy ibora (AI'siz)
"""
from django.core.management.base import BaseCommand, CommandError

from support import smoke


class Command(BaseCommand):
    help = "Deploydan keyingi bot sinovi (AI'siz): 3 asosiy savol va ixtiyoriy standartlar qamrovi."

    def add_arguments(self, parser):
        parser.add_argument("--standards", type=int, default=0, help="N ta eng ko'p ishlatiladigan standart")
        parser.add_argument("--phrases", type=int, default=5, help="Har standartga nechta haqiqiy ibora")

    def handle(self, *args, **o):
        res = smoke.run_smoke()
        for text, ok, note in res:
            self.stdout.write(f"{'PASS' if ok else 'FAIL'}  {text} → {note}")
        if o["standards"]:
            rows = smoke.standards(o["standards"], o["phrases"])
            hit = sum(r["hit"] for r in rows)
            total = sum(r["total"] for r in rows)
            self.stdout.write(f"\nStandartlar (AI'siz): {hit}/{total} ibora topildi"
                              f" ({round(100 * hit / total) if total else 0}%)")
            for r in rows:
                self.stdout.write(f"  #{r['id']} {r['title'][:70]} — {r['hit']}/{r['total']} (uses {r['uses']})")
                for text, ok, got in r["phrases"]:
                    if not ok:
                        self.stdout.write(f"      ✗ «{text[:90]}» → {got[:60]}")
        if not all(ok for _t, ok, _n in res):
            raise CommandError("sinov o'tmadi")

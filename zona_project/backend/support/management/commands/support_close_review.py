"""Review navbatini serverda yopish: mavzuli «Standartga mos» -> standartga qo'shiladi, qolgan new/review -> rad etiladi.

  python manage.py support_close_review --dry-run                    # faqat sonlar va namunalar
  python manage.py support_close_review                              # bajarish (avval baza zaxirasi!)
  python manage.py support_close_review --older-than 7               # haftalik: 7 kundan eski yozuvlar
  python manage.py support_close_review --only-same                  # faqat «Standartga mos», rad etish yo'q

Rad etilganlar o'chirilmaydi (status=rejected); id'lari --ids-file ga yoziladi. Qaytarish:
  Entry.objects.filter(pk__in=ids).update(status="new")
"""
from django.core.management.base import BaseCommand

from support import review_close
from support.models import Entry


class Command(BaseCommand):
    help = "Review navbatini yopish (interfeyssiz): mavzuli «Standartga mos» -> standart, qolgani -> rad etilgan."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Hech narsa o'zgartirmaydi, sonlar va namunalar")
        parser.add_argument("--older-than", type=int, default=0, help="Faqat N kundan eski yozuvlar (haftalik: 7)")
        parser.add_argument("--only-same", action="store_true", help="Faqat «Standartga mos» ni qo'shish, rad etmaslik")
        parser.add_argument("--ids-file", default="/tmp/review_rejected_ids.txt")
        parser.add_argument("--samples", type=int, default=15)
        parser.add_argument("--by", default=review_close.BY)

    def handle(self, *args, **o):
        p = review_close.plan(o["older_than"], reject_rest=not o["only_same"])
        n_abs = sum(map(len, p["absorb"].values()))
        self.stdout.write(f"navbat: {Entry.objects.filter(status__in=[Entry.NEW, Entry.REVIEW]).count()}")
        self.stdout.write(f"absorb: {n_abs} -> {len(p['absorb'])} standart")
        titles = dict(Entry.objects.filter(pk__in=p["absorb"]).values_list("pk", "title"))
        for t, ids in sorted(p["absorb"].items(), key=lambda kv: -len(kv[1])):
            self.stdout.write(f"  # {t} {titles.get(t, '')[:60]} — {len(ids)}")
        self.stdout.write(f"reject: {len(p['reject'])}")
        for e in Entry.objects.filter(pk__in=p["reject"][: o["samples"]]):
            self.stdout.write(f"  R {e.pk} {e.claude_kind or '-'} {e.title[:70]} | {(e.answer or '')[:60]}")
        if o["dry_run"]:
            self.stdout.write("DRY: hech narsa o'zgarmadi")
            return
        absorbed, rejected = review_close.apply(p, o["by"])
        if p["reject"]:
            with open(o["ids_file"], "w", encoding="utf-8") as f:
                f.write("\n".join(map(str, p["reject"])))
        self.stdout.write(self.style.SUCCESS(f"bajarildi: standartga {absorbed}, rad etildi {rejected}; "
                                             f"id'lar: {o['ids_file']}"))

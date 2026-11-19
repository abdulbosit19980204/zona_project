"""Bilim bazasini platformadagi savollar bazasidan boshlang'ich to'ldirish (idempotent).

Manba (faqat o'qiladi, o'zgartirilmaydi):
  1) Qoidasi yozilgan savol turlari (zona Task.rule)  -> savol-javob; savol misollari -> savol ko'rinishlari.
     Tashkilot yozgan qoida bo'lgani uchun holati: tasdiqlangan.
  2) Aralash holatlar (EdgeCase)                       -> "avval kimga, qachon boshqasiga" javobi; tasdiqlangan.
  3) Qoidasi yo'q, lekin mas'uli bor savol turlari     -> "kim hal qiladi" javobi; holati: ko'rib chiqilmoqda
     (aniq yechim matni yo'q — xodimlar to'ldirib tasdiqlaydi).
Bor yozuv (shu sarlavha, manba=seed) qayta yaratilmaydi va o'zgartirilmaydi.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from support.models import Entry
from zona.models import EdgeCase, Task

BY = "boshlang'ich import"


def _ru(obj, field):
    return ((obj.i18n or {}).get("ru") or {}).get(field, "")


def _clean(items, limit=30):
    out = []
    for x in items:
        x = " ".join(str(x or "").split())
        if len(x) >= 3 and x.lower() not in {o.lower() for o in out}:
            out.append(x[:300])
    return out[:limit]


def _who(m):
    return m.name if m else ""


class Command(BaseCommand):
    help = "Support bilim bazasini savollar bazasi (vazifalar, qoidalar, aralash holatlar) asosida to'ldirish."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--no-routing", action="store_true", help="Qoidasiz (faqat mas'ul) savollarni qo'shmaslik")

    def handle(self, *args, **opts):
        existing = set(Entry.objects.values_list("title", flat=True))
        rows = []

        tasks = Task.objects.select_related("owner", "process__zone").prefetch_related("fallbacks__member")
        for t in tasks:
            title = " ".join(t.title.split())[:200]
            if not title or title in existing:
                continue
            questions = _clean([*(t.examples or []), _ru(t, "title")])
            zone = t.process.zone if t.process_id and t.process.zone_id else None
            nxt = [f for f in t.fallbacks.all() if f.member_id]
            if t.rule.strip():
                ans, ans_ru = t.rule.strip(), _ru(t, "rule").strip()
                if t.owner:
                    ans += f"\n\nMas'ul: **{_who(t.owner)}**"
                    if ans_ru:
                        ans_ru += f"\n\nОтветственный: **{_who(t.owner)}**"
                status = Entry.APPROVED
            elif t.owner and not opts["no_routing"] and (questions or t.frequent):
                ans = f"Bu savolni **{_who(t.owner)}** hal qiladi — savolingizni batafsil yozing (rasm bilan bo'lsa yaxshi)."
                ans_ru = f"Этот вопрос решает **{_who(t.owner)}** — опишите вопрос подробно (лучше со скриншотом)."
                if nxt:
                    ans += f"\nJavob bo'lmasa: {_who(nxt[0].member)}" + (f" ({nxt[0].condition})" if nxt[0].condition else "")
                    ans_ru += f"\nЕсли нет ответа: {_who(nxt[0].member)}"
                status = Entry.REVIEW
            else:
                continue
            rows.append(Entry(kind=Entry.FAQ, title=title, questions=questions, answer=ans, answer_ru=ans_ru,
                              zone=zone, responsible=t.owner, status=status, source="seed", author=BY,
                              approved_by=BY if status == Entry.APPROVED else "",
                              approved_at=timezone.now() if status == Entry.APPROVED else None))
            existing.add(title)

        for e in EdgeCase.objects.select_related("first_owner"):
            title = " ".join(e.situation.split())[:200]
            if not title or title in existing:
                continue
            ans = f"Avval **{_who(e.first_owner) or 'supervayzeringiz'}**ga yozing."
            if e.then_text:
                ans += f"\n{e.then_text}"
            ru_sit, ru_then = _ru(e, "situation"), _ru(e, "then_text")
            ans_ru = f"Сначала напишите: **{_who(e.first_owner) or 'супервайзеру'}**." + (f"\n{ru_then}" if ru_then else "")
            rows.append(Entry(kind=Entry.FAQ, title=title, questions=_clean([ru_sit]), answer=ans, answer_ru=ans_ru,
                              responsible=e.first_owner, status=Entry.APPROVED, source="seed", author=BY,
                              approved_by=BY, approved_at=timezone.now()))
            existing.add(title)

        approved = sum(1 for r in rows if r.status == Entry.APPROVED)
        self.stdout.write(f"qo'shiladi: {len(rows)} (tasdiqlangan: {approved}, ko'rib chiqish uchun: {len(rows) - approved})")
        if opts["dry_run"]:
            for r in rows[:8]:
                self.stdout.write(f"  [{r.status}] {r.title}  ← {len(r.questions)} ta savol ko'rinishi")
            return
        with transaction.atomic():
            Entry.objects.bulk_create(rows)
        self.stdout.write(f"bilim bazasida jami: {Entry.objects.count()}")

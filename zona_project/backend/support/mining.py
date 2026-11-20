"""Standart holatlar uchun shartlarni (trigger) o'rgatilgan rasmlardan avtomatik chiqarish.

Har bir standart holat (template) yozuvining rasm namunalari OCR bilan o'qiladi va shu ekranga xos iboralar topiladi:
- nomzodlar: rasmlarda ko'p takrorlanadigan 2–4 so'zli iboralar va sarlavhadagi «...» ichidagi xato matni;
- qabul shartlari: o'z rasmlarining kamida yarmida bor, boshqa standart holatlar rasmlarida YO'Q, boshqa savollar va
  rasmlar matnida ko'pi bilan 2 marta uchraydi.
Natija — oddiy (regexsiz) iboralar: bot ularni tinish belgilari, kirill/lotin farqiga chidamli holda solishtiradi.
Mavjud shartlar o'zgarmaydi, faqat yangilari qo'shiladi; javob matniga tegilmaydi.
"""
import logging
import re
from collections import Counter

from zona.search.normalize import fold

from . import ocr
from .models import Entry, Media, Message

log = logging.getLogger("support")
WORD = re.compile(r"\w+", re.UNICODE)
QUOTED = re.compile(r"[«\"“]([^»\"”]{4,120})[»\"”]")
STOP = {"va", "bu", "da", "na", "i", "v", "s", "the", "a", "an", "to", "of", "ham", "uchun", "bilan", "eto", "ili"}


def norm(text):
    """Taqqoslash uchun: lotinga o'girilgan, kichik harf, faqat so'zlar bitta bo'shliq bilan."""
    return " ".join(WORD.findall(fold(text or "")))


def _ngrams(words, lo=2, hi=4):
    for n in range(lo, hi + 1):
        for i in range(len(words) - n + 1):
            g = words[i:i + n]
            if g[0] in STOP or g[-1] in STOP:
                continue
            if any(w.isdigit() or len(w) == 1 for w in g):
                continue
            if sum(len(w) >= 3 for w in g) < 2:
                continue
            yield " ".join(g)


def ensure_ocr(entry, limit=12):
    """Rasm namunalarining matni (yo'q bo'lsa — o'qib saqlaydi)."""
    out = []
    for m in Media.objects.filter(label=entry, kind=Media.PHOTO).exclude(path="").order_by("-id")[:limit]:
        if not m.ocr_text:
            try:
                m.ocr_text = ocr.read_text(open(m.path, "rb").read()) or ""
                Media.objects.filter(pk=m.pk).update(ocr_text=m.ocr_text)
            except OSError:
                continue
        if m.ocr_text.strip():
            out.append(m.ocr_text)
    return out


def mine(entry_ids=None, apply=False, per_entry=3):
    """Har bir standart holat uchun shart iboralarini topish. apply=True — yozuvlarga qo'shadi."""
    from .engine import _trigger_hit
    qs = Entry.objects.filter(status=Entry.APPROVED, kind=Entry.TEMPLATE)
    if entry_ids:
        qs = qs.filter(pk__in=entry_ids)
    targets = list(qs)
    all_templates = list(Entry.objects.filter(kind=Entry.TEMPLATE).exclude(status=Entry.ARCHIVED))
    docs = {e.id: [norm(t) for t in ensure_ocr(e)] for e in all_templates}
    labeled_ids = set(Media.objects.filter(label__isnull=False).values_list("id", flat=True))
    noise = [norm(t) for t in Media.objects.filter(kind=Media.PHOTO).exclude(ocr_text="").exclude(id__in=labeled_ids)
             .values_list("ocr_text", flat=True)[:1500]]
    noise += [norm(t) for t in Message.objects.filter(kind=Message.QUESTION).exclude(text="").values_list("text", flat=True)[:2000]]
    report = []
    for e in targets:
        own = docs.get(e.id) or []
        if not own:
            report.append({"entry": e.id, "title": e.title, "added": [], "note": "rasm matni yo'q"})
            continue
        others = [d for k, ds in docs.items() if k != e.id for d in ds]
        cands = Counter()
        statistical = len(own) >= 5 and not e.triggers  # kam namunada tasodifiy so'zlar (ism, manzil) xos bo'lib ko'rinadi
        if statistical:
            for d in own:
                for g in set(_ngrams(d.split())):
                    cands[g] += 1
        title_phrases = []
        for q in QUOTED.findall(e.title) + QUOTED.findall(e.answer or ""):
            for part in re.split(r"[—…\.]", q):
                w = norm(part).split()
                if len(w) == 1 and len(w[0]) >= 10:
                    title_phrases.append(w[0])  # uzun yagona so'z (masalan, «Синхронизировать»)
                for g in _ngrams(w, 2, min(6, len(w))):
                    title_phrases.append(g)
        other_bigrams = {" ".join(x.split()[i:i + 2]) for x in others for i in range(len(x.split()) - 1)}
        scored = []
        for g in set(cands) | set(title_phrases):
            from_title = g in title_phrases
            own_hits = sum(1 for d in own if g in d)
            need = 0.5 if from_title else 0.6
            if not own_hits or own_hits / len(own) < need or len(g) < 10:
                continue
            if any(g in d for d in others):
                continue
            words = g.split()
            if not from_title and any(" ".join(words[i:i + 2]) in other_bigrams for i in range(len(words) - 1)):
                continue  # umumiy UI matni (boshqa ekranlarda ham bor) — xos emas
            noise_hits = sum(1 for d in noise if g in d)
            if noise_hits > 2:
                continue
            score = 10 * own_hits / len(own) + (3 if from_title else 0) + 0.5 * len(words) - noise_hits
            scored.append((score, g))
        chosen = []
        for _s, g in sorted(scored, key=lambda x: -x[0]):
            if any(g in c or c in g for c in chosen):
                continue
            chosen.append(g)
            if len(chosen) >= per_entry:
                break
        existing = [t for t in (e.triggers or [])]
        new = [g for g in chosen if not any(_trigger_hit(t, g, g) for t in existing)]
        if apply and new:
            Entry.objects.filter(pk=e.pk).update(triggers=[*existing, *new])
        report.append({"entry": e.id, "title": e.title, "samples": len(own), "added": new, "kept": len(existing)})
    return report

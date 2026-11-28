"""Deploydan keyingi sinov (KOORDINATSIYA 5-band) va AI'siz standartlar sinovi (0h).

1. Uchta asosiy savol — kutilgan natija bilan (PASS / FAIL):
   «lokatsiya uzoq deyapti» -> geolokatsiya standarti; «aktiv vizit bor» -> «User already has an active visit»;
   «Assalomu alaykum» -> javob yo'q (savol emas).
2. Eng ko'p ishlatiladigan N standart × K ta haqiqiy agent iborasi — AI'siz (shablon / FAQ) topiladimi.
   Iboralar: shu standartga qo'shilgan (Claude «Standartga mos» deb absorb qilgan) yozuvlarning manba savollari —
   bot o'shanda topa olmagan haqiqiy matnlar; keyin standartning o'z manbalari va bot shu standart bilan javob bergan
   savollar. Hech narsa yuborilmaydi, AI chaqirilmaydi.
"""
from .models import Entry, Message

SMOKE = [
    ("lokatsiya uzoq deyapti", ("joylashuv", "uzoq", "geolok", "активной зоне"), True),
    ("aktiv vizit bor", ("active visit", "aktiv vizit", "ochiq vizit"), True),
    ("Assalomu alaykum", (), False),
]


def _decide(text):
    """Jonli botdagidek to'liq yo'l (shablon, FAQ, qoida), faqat AI'siz — AI limiti tugagandagi holat."""
    from . import engine
    with engine.no_ai():
        return engine.decide(text, engine.detect_lang(text), text=text, live=False)


def run_smoke():
    """-> [(savol, ok, izoh)]"""
    out = []
    for text, keys, want_answer in SMOKE:
        d = _decide(text)
        title = (d.entry.title if d is not None and d.entry else "")
        answered = bool(d is not None and not d.needs_human and d.text)
        if want_answer:
            ok = answered and any(k.lower() in title.lower() for k in keys)
        else:
            ok = not answered and (d is None or d.entry is None)
        out.append((text, ok, f"{d.stage if d else '-'} · {title or 'javob yo‘q'}"))
    return out


def _phrases(e, k):
    from . import engine
    ids = []
    for a in Entry.objects.filter(claude_target=e, status=Entry.ARCHIVED).only("sources"):
        ids += list(a.sources or [])
    ids += list(e.sources or [])
    seen, out = set(), []
    by_id = dict(Message.objects.filter(pk__in=ids, kind=Message.QUESTION).values_list("pk", "text"))
    texts = [by_id[i] for i in dict.fromkeys(ids) if i in by_id]  # manba tartibida
    texts += list(Message.objects.filter(entry=e, kind=Message.QUESTION, source="live").order_by("-id")
                  .values_list("text", flat=True)[:30])
    for t in texts:
        t = " ".join((t or "").split())
        if t and t.lower() not in seen and engine.learnable_question(t):
            seen.add(t.lower())
            out.append(t)
        if len(out) >= k:
            break
    return out


def standards(n=15, k=5):
    """-> [{"id", "title", "uses", "phrases": [(matn, ok, topilgani)], "hit", "total"}]"""
    rows = []
    for e in Entry.objects.filter(status=Entry.APPROVED).order_by("-uses")[:n]:
        res = []
        for text in _phrases(e, k):
            d = _decide(text)
            got = d.entry if d is not None and not d.needs_human else None
            ok = got is not None and (got.pk == e.pk or got.title.strip().lower() == e.title.strip().lower())
            res.append((text, ok, got.title if got is not None else "—"))
        rows.append({"id": e.pk, "title": e.title, "uses": e.uses, "phrases": res,
                     "hit": sum(1 for _t, ok, _g in res if ok), "total": len(res)})
    return rows

"""Bilim bazasidagi takror savol-javoblarni topish va tozalash.

Bir savolga turli vaqtda turli xodimlar har xil javob yozgan bo'lishi mumkin: biri qisqa, biri batafsil. Bu modul:
- o'xshash yozuvlarni guruhlaydi (savol ko'rinishlari bo'yicha, imlo va qo'shimchalarga chidamli o'xshashlik);
- har bir yozuvga sifat bahosi beradi va guruhda eng yaxshisini "qoldiriladigan" deb belgilaydi;
- birlashtiradi: savol ko'rinishlari, rasm namunalari va biriktirmalar qoldirilganiga o'tadi, qolganlari ARXIVga tushadi.

Hech narsa o'chirilmaydi — arxivdagi yozuvni qaytarish mumkin, qoldirilgan yozuvning eski holati versiyalar tarixida turadi.
"""
import math
import re
from collections import defaultdict

from django.db import transaction

from .engine import _dice, toks
from .models import Entry, Media

ACTIVE = [Entry.APPROVED, Entry.REVIEW, Entry.NEW]
STEP_RE = re.compile(r"^\s*(\d+[.)]|[-•–])\s+", re.M)


def _qtokens(e):
    words = toks(" ".join([e.title, *(e.questions or [])[:15]]))
    return list(dict.fromkeys(words))[:50]


def quality(e):
    """0..100: javob sifati taxmini — tasdiqlangani, baholar, ishlatilishi, batafsilligi (lekin haddan uzun emas)."""
    score = 0.0
    score += {Entry.APPROVED: 25, Entry.REVIEW: 10}.get(e.status, 0)
    score += min(20, 6 * math.log1p(e.uses or 0))
    score += max(-25, min(15, 5 * (e.likes or 0) - 8 * (e.dislikes or 0)))
    n = len((e.answer or "").strip())
    if n < 25:
        score -= 10
    elif n < 80:
        score += 4
    elif n <= 900:
        score += 15  # batafsil, lekin o'qib bo'ladigan
    else:
        score += 8
    score += min(8, 3 * len(STEP_RE.findall(e.answer or "")))  # qadam-baqadam yozilgan
    score += 4 if e.answer_ru else 0
    score += 3 if e.ask_first else 0
    score += 3 if e.attachments else 0
    score += 2 if e.priority else 0
    score += min(5, len(e.questions or []) / 2)
    return max(0, min(100, round(score)))


def _reasons(e):
    out = []
    if e.status == Entry.APPROVED:
        out.append("approved")
    if e.likes:
        out.append("liked")
    if e.uses:
        out.append("used")
    if len(STEP_RE.findall(e.answer or "")) >= 2:
        out.append("steps")
    if len((e.answer or "").strip()) > 300:
        out.append("detailed")
    if len((e.answer or "").strip()) < 80:
        out.append("short")
    return out


def find_groups(threshold=75, statuses=None):
    """Takrorlar guruhlari. threshold — savol o'xshashligi chegarasi (0..100)."""
    entries = list(Entry.objects.filter(status__in=statuses or ACTIVE).only(
        "id", "title", "questions", "answer", "answer_ru", "ask_first", "attachments", "status", "uses", "likes",
        "dislikes", "priority", "author", "source", "kind", "updated_at"))
    tok = {e.id: _qtokens(e) for e in entries}
    by_id = {e.id: e for e in entries}
    # nomzod juftliklar: kamida ikkita umumiy so'z o'zagi (hamma bilan hammani solishtirmaslik uchun)
    index = defaultdict(set)
    for eid, ts in tok.items():
        for w in ts:
            if len(w) >= 3:
                index[w[:5]].add(eid)
    shared = defaultdict(int)
    for ids in index.values():
        if len(ids) > 60:  # juda umumiy so'z (klient, zakaz) — farqlamaydi
            continue
        ids = sorted(ids)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                shared[(a, b)] += 1
    parent = {e.id: e.id for e in entries}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    sims = {}
    for (a, b), n in shared.items():
        if n < 2 or by_id[a].kind != by_id[b].kind:
            continue
        s = _dice(tok[a], tok[b])
        if s >= threshold:
            sims[(a, b)] = s
            parent[find(a)] = find(b)
    groups = defaultdict(list)
    for e in entries:
        groups[find(e.id)].append(e)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        ranked = sorted(members, key=lambda e: (-quality(e), -(e.uses or 0), e.id))
        best = ranked[0]
        rows = []
        for e in ranked:
            key = (min(e.id, best.id), max(e.id, best.id))
            q_sim = 100 if e.id == best.id else sims.get(key) or _dice(tok[e.id], tok[best.id])
            a_sim = 100 if e.id == best.id else _dice(list(dict.fromkeys(toks(e.answer)))[:80], list(dict.fromkeys(toks(best.answer)))[:80])
            rows.append({"id": e.id, "title": e.title, "answer": e.answer, "status": e.status, "uses": e.uses,
                         "likes": e.likes, "dislikes": e.dislikes, "author": e.author, "quality": quality(e),
                         "question_sim": q_sim, "answer_sim": a_sim, "questions": len(e.questions or []),
                         "reasons": _reasons(e), "best": e.id == best.id})
        sim = min(r["question_sim"] for r in rows)
        out.append({"keep": best.id, "similarity": sim, "entries": rows})
    out.sort(key=lambda g: (-g["similarity"], -len(g["entries"])))
    return out


@transaction.atomic
def merge_group(keep_id, merge_ids, by, answer=None, answer_ru=None, title=None, note="takrorlar birlashtirildi"):
    """Guruhni bitta yozuvga birlashtirish. Qolganlari arxivga tushadi (o'chirilmaydi). Natija: qoldirilgan yozuv."""
    from .runner import snapshot
    keep = Entry.objects.select_for_update().get(pk=keep_id)
    others = list(Entry.objects.filter(pk__in=[i for i in merge_ids if i != keep_id]).exclude(status=Entry.ARCHIVED))
    if not others and answer is None:
        return keep, 0
    snapshot(keep, by, f"{note}: {', '.join('#' + str(o.id) for o in others)}" if others else note)
    qs = [*(keep.questions or [])]
    for o in others:
        qs += [o.title, *(o.questions or [])]
    keep.questions = [q for q in dict.fromkeys(x.strip() for x in qs if x and x.strip()) if q != keep.title][:60]
    att = list(keep.attachments or [])
    for o in others:
        att += [a for a in (o.attachments or []) if a not in att]
    keep.attachments = att[:10]
    if not keep.ask_first:
        keep.ask_first = next((o.ask_first for o in others if o.ask_first), "")
    if not keep.answer_ru and answer_ru is None:
        keep.answer_ru = next((o.answer_ru for o in others if o.answer_ru), "")
    if answer and answer.strip():
        keep.answer = answer.strip()
    if answer_ru is not None and answer_ru.strip():
        keep.answer_ru = answer_ru.strip()
    if title and title.strip():
        keep.title = title.strip()[:200]
    keep.uses = (keep.uses or 0) + sum(o.uses or 0 for o in others)
    keep.likes = (keep.likes or 0) + sum(o.likes or 0 for o in others)
    keep.dislikes = (keep.dislikes or 0) + sum(o.dislikes or 0 for o in others)
    keep.priority = keep.priority or any(o.priority for o in others)
    keep.save()
    if others:
        ids = [o.id for o in others]
        Media.objects.filter(label_id__in=ids).update(label=keep)  # rasm namunalari yo'qolmasin
        Entry.objects.filter(pk__in=ids).update(status=Entry.ARCHIVED)
        from . import vision
        vision._CACHE["key"] = None
    return keep, len(others)


# mijozga xos qismlar: nom (qo'shtirnoqda / KATTA harflarda), nuqta kodi, hudud kodi (К-2, D17, Sr4), raqam, havola
_VARIABLE = [r"📍[^\n]*", r"https?://\S+", r"[«\"“][^»\"”\n]{1,80}[»\"”]", r"(?i:\buz)[-\s]?\d+", r"@\w+",
             r"\b[A-ZА-ЯЁʻ'`]{3,}(?:\s+[A-ZА-ЯЁʻ'`]{2,})+\b",
             r"(?<![\w-])[КKДDСSRРТT][А-Яа-яA-Za-z]?\s?[-№]?\s?\d{1,3}(?![\w])", r"\d[\d\s.,:]*"]


def generic_phrase(text):
    """Savol ko'rinishi mijozga xos qismlarsiz: «D17 Afsona makon lokatsiyasini to'g'rilab bering» ->
    «lokatsiyasini to'g'rilab bering». Mazmunli so'z kam qolsa — bo'sh satr."""
    from .engine import meaningful
    t = text or ""
    for p in _VARIABLE:
        t = re.sub(p, " ", t)
    t = " ".join(t.split()).strip(" -—,.;:!?")
    return t[:300] if len(meaningful(t)) >= 2 else ""


@transaction.atomic
def absorb(target_id, ids, by):
    """Claude mos deb topgan o'rganilgan yozuvlar standart javobga qo'shiladi: savol ko'rinishlari (mijoz nomi va
    kodlarsiz) standartning savollariga, rasm namunalari unga o'tadi, o'zlari ARXIVga (o'chirilmaydi). Javob matni
    o'zgarmaydi. Qaytaradi: nechta yozuv qo'shildi."""
    from .engine import learnable_question
    from .runner import snapshot
    target = Entry.objects.select_for_update().get(pk=target_id)
    others = list(Entry.objects.filter(pk__in=ids, status__in=[Entry.NEW, Entry.REVIEW]).exclude(pk=target.pk))
    if not others:
        return 0
    snapshot(target, by, "standartga qo'shildi: " + ", ".join("#" + str(o.id) for o in others)[:150])
    have = {x.strip().lower() for x in [target.title, *(target.questions or [])]}
    qs = list(target.questions or [])
    for o in others:
        for raw in [o.title, *(o.questions or [])[:3]]:
            g = generic_phrase(raw)
            if not learnable_question(g):
                continue  # salomlashuv standartning savol ko'rinishiga tushmasin
            if g and g.lower() not in have and len(qs) < 60:
                have.add(g.lower())
                qs.append(g)
    target.questions = qs
    target.uses = (target.uses or 0) + sum(o.uses or 0 for o in others)
    target.save(update_fields=["questions", "uses", "updated_at"])
    ids = [o.id for o in others]
    Media.objects.filter(label_id__in=ids).update(label=target)
    Entry.objects.filter(pk__in=ids).update(status=Entry.ARCHIVED)
    from . import vision
    vision._CACHE["key"] = None
    return len(others)


def auto_clean(by, threshold=92, dry_run=False):
    """Deyarli bir xil (≥threshold) guruhlarni avtomatik eng yaxshisiga birlashtirish."""
    groups = [g for g in find_groups(threshold) if g["similarity"] >= threshold]
    merged = 0
    if not dry_run:
        for g in groups:
            _keep, n = merge_group(g["keep"], [r["id"] for r in g["entries"]], by, note="avto-tozalash: takrorlar birlashtirildi")
            merged += n
    return {"groups": len(groups), "merged": merged if not dry_run else sum(len(g["entries"]) - 1 for g in groups)}

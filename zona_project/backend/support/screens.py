"""Umumiy rasm turlari (ekranlar): agentlar yuboradigan skrinshotlar bir necha o'nlab ekranlardan iborat —
"Вы не в активной зоне", "Новая торговая точка" (moderatsiya), vizitlar kalendari, savat, buyurtma, kirish oynasi...

Har bir rasm vizual izi (dHash) bo'yicha eng yaqin turga biriktiriladi. Tur nomi rasmdagi matndan (OCR) avtomatik
olinadi — ko'pchilik rasmda takrorlanadigan sarlavha qatori; admin o'zgartirsa — qulflanadi. Tegi (aksiya, vizit,
lokatsiya...) shu rasmlardagi matn va savollardan. Savollar tur ichida jamlanadi (bir xil ekran — turli savollar);
ekranning o'zi savolni hal qilsa (masalan, "moderatsiyaga yuborildi") — turga standart javob biriktiriladi.

Tanish uchun faqat vakillar izi (hashes) kerak — rasmlarning o'zi saqlanmaydi (slim.py).
"""
import re
import threading
from collections import Counter, defaultdict

from django.db import transaction

from .models import Media, Message, ScreenType

TH = 14            # tur ichidagi o'xshashlik (javob uchun ishlatiladigan image_threshold dan kengroq — ekran darajasi)
MIN_SIZE = 5       # avtomatik tur — kamida shuncha rasm
MAX_REPS = 24      # turning vakil izlari (tanish uchun)
WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
NOISE = re.compile(r"\blte\b|кб/с|kb/s|\b4g\b|\b5g\b|%|©|®|›|„", re.I)
NAV = ("визиты", "каталог", "задания", "корзина", "профиль", "главная", "заказы")  # pastki menyu — sarlavha emas
_lock = threading.Lock()


def _h(m):
    dh = m["dhash"] if isinstance(m, dict) else m.dhash
    dm = (m["dhash_mid"] if isinstance(m, dict) else m.dhash_mid) or dh
    return int(dh, 16), int(dm, 16)


def dist(a, b):
    f = (a[0] ^ b[0]).bit_count()
    m = (a[1] ^ b[1]).bit_count()
    return min(m, (f + m) / 2)


# ---------------------------------------------------------------- nom va teg
def _candidates(ocr):
    """OCR'ning yuqori qatorlaridan sarlavhaga nomzodlar (shovqin — status bar, raqamlar, ismlar — tashlanadi)."""
    from .dedupe import generic_phrase
    out = []
    for ln in (ocr or "").splitlines()[:14]:
        low = ln.lower()
        if sum(1 for w in WEEKDAYS if re.search(rf"(?<!\w){w}(?!\w)", low)) >= 3:
            out.append("Vizitlar (kalendar)")
            continue
        if NOISE.search(ln) or sum(1 for w in NAV if w in low) >= 3:
            continue
        ln = re.sub(r"^[\W\d_]+", "", ln).strip()
        letters = sum(c.isalpha() for c in ln)
        if len(ln) < 6 or letters < 5 or letters / max(1, len(ln)) < 0.6:
            continue
        g = generic_phrase(ln)
        words = [w for w in re.findall(r"\w+", g or "") if len(w) >= 3 and not w.isdigit()]
        if len(words) >= 2:
            g = " ".join(g.split())[:60].strip(" -—,.;:!?")
            out.append(g[:1].upper() + g[1:].lower())
    return list(dict.fromkeys(out))


def name_of(ocrs, loose=False):
    """Eng ko'p rasmda uchraydigan sarlavha qatori (kamida 15% rasmda; loose — kamida 2 ta). To'liqroq qator ustun:
    "Вы не в активной зоне" — "Торговой точки" dan yaxshiroq. Bo'lmasa bo'sh."""
    texts = [o for o in ocrs if o]
    if not texts:
        return ""
    df = Counter()
    for o in texts:
        df.update(_candidates(o)[:6])
    if not df:
        return ""
    need = 2 if loose else max(2, 0.15 * len(texts))
    best = max(((ln, n * (0.5 + 0.1 * min(5, len(ln.split())))) for ln, n in df.items() if n >= need),
               key=lambda x: x[1], default=None)
    return best[0] if best else ""


def title_key(title):
    """Nomlarni solishtirish: "Оформление заказа" = "Оформлении заказа", "Проверьте товары в корзине перед (оформлением)"."""
    words = [w[:5] for w in re.findall(r"\w+", (title or "").lower()) if len(w) >= 3][:3]
    return " ".join(words)


def tag_of(texts):
    """Turning tegi: rasmlardagi matn va savollar bo'yicha eng ko'p uchraydigan teg (kamida 30%)."""
    from . import tags as T
    c = Counter()
    for t in texts:
        c.update(set(T.detect(t)))
    if not c or not texts:
        return ""
    key, n = c.most_common(1)[0]
    return key if n >= 0.3 * len(texts) else ""


# ---------------------------------------------------------------- tanish (yangi rasmlar)
_CACHE = {"key": None, "reps": []}


def _reps():
    from django.db.models import Count, Max
    agg = ScreenType.objects.aggregate(n=Count("id"), u=Max("updated_at"))
    key = (agg["n"], str(agg["u"]))
    if _CACHE["key"] != key:
        reps = []
        for t in ScreenType.objects.filter(hidden=False).only("id", "hashes"):
            for pair in t.hashes or []:
                try:
                    reps.append((int(pair[0], 16), int(pair[1] or pair[0], 16), t.id))
                except (ValueError, IndexError, TypeError):
                    continue
        _CACHE.update(key=key, reps=reps)
    return _CACHE["reps"]


def nearest(m, th=TH):
    """(tur id, masofa) yoki (None, 64). Xotiradagi vakillar bo'yicha — mikrosoniyalar."""
    if not (m.get("dhash") if isinstance(m, dict) else m.dhash):
        return None, 64
    a = _h(m)
    best, bd = None, 65
    for f, mid, tid in _reps():
        x = dist(a, (f, mid))
        if x < bd:
            bd, best = x, tid
    return (best, bd) if best is not None and bd <= th else (None, bd)


def assign_new(limit=1000):
    """Turga biriktirilmagan yangi rasmlar — eng yaqin turga (fonda, javob tezligiga ta'sir qilmaydi)."""
    n = 0
    by = defaultdict(list)
    for m in (Media.objects.filter(kind=Media.PHOTO, screen__isnull=True, ignored=False).exclude(dhash="")
              .order_by("-id").values("id", "dhash", "dhash_mid")[:limit]):
        tid, _d = nearest(m)
        if tid:
            by[tid].append(m["id"])
    for tid, ids in by.items():
        n += Media.objects.filter(id__in=ids, screen__isnull=True).update(screen_id=tid)
        _recount([tid])
    return n


def _recount(ids):
    from django.db.models import Count
    counts = dict(Media.objects.filter(screen_id__in=ids).values("screen_id").annotate(n=Count("id")).values_list("screen_id", "n"))
    for tid in ids:
        ScreenType.objects.filter(pk=tid).update(count=counts.get(tid, 0))


def add_to(ids, screen):
    """Admin rasmlarni turga qo'shadi: rasmlar biriktiriladi, birinchilari turning vakillariga qo'shiladi
    (keyingi shunday rasmlar o'zi tanilsin)."""
    rows = list(Media.objects.filter(id__in=ids, kind=Media.PHOTO).exclude(dhash="").values("id", "dhash", "dhash_mid"))
    Media.objects.filter(id__in=[r["id"] for r in rows]).update(screen=screen, ignored=False)
    reps = list(screen.hashes or [])
    have = [(int(a, 16), int(b or a, 16)) for a, b in reps]
    for r in rows:
        h = _h(r)
        if len(reps) < MAX_REPS and all(dist(h, x) > 3 for x in have):
            reps.append([r["dhash"], r["dhash_mid"] or r["dhash"]])
            have.append(h)
    screen.hashes = reps
    screen.save(update_fields=["hashes", "updated_at"])
    _recount([screen.pk])
    _CACHE["key"] = None
    return len(rows)


# ---------------------------------------------------------------- qayta guruhlash (kechasi / tugma bilan)
def rebuild(min_size=MIN_SIZE):
    """Barcha rasmlarni ekran turlariga guruhlash. Mavjud turlar saqlanadi (vakillari bo'yicha moslanadi, admin
    nomlagani o'zgarmaydi); yangi katta guruhlar — yangi tur; bir xil nomli guruhlar — bitta tur."""
    if not _lock.acquire(blocking=False):
        return {"busy": True}
    try:
        return _rebuild(min_size)
    finally:
        _lock.release()


def _rebuild(min_size):
    rows = list(Media.objects.filter(kind=Media.PHOTO, ignored=False).exclude(dhash="")
                .order_by("id").values("id", "dhash", "dhash_mid", "ocr_text", "message__text", "screen_id"))
    clusters = []  # [seed_hash, [rows]]
    for r in rows:
        h = _h(r)
        best, bd = None, 99
        for c in clusters:
            x = dist(h, c[0])
            if x < bd:
                bd, best = x, c
        if best is not None and bd <= TH:
            best[1].append(r)
        else:
            clusters.append([h, [r]])
    existing = {t.id: t for t in ScreenType.objects.all()}
    ex_reps = [(int(a, 16), int(b or a, 16), t.id) for t in existing.values() for a, b in (t.hashes or [])]
    by_title = {}
    for t in existing.values():
        by_title.setdefault(t.title.lower(), t.id)
    assign = defaultdict(list)
    created = 0
    for seed, members in sorted(clusters, key=lambda c: -len(c[1])):
        # mavjud turga mos keladimi (vakillari bo'yicha) — yoki admin qo'lda biriktirgan rasmlar ko'pchiligi shu turda
        manual = Counter(r["screen_id"] for r in members if r["screen_id"])
        tid = None
        if manual and manual.most_common(1)[0][1] >= 0.5 * len(members):
            tid = manual.most_common(1)[0][0]
        if tid is None and ex_reps:
            bd, bt = 99, None
            for f, mid, t in ex_reps:
                x = dist(seed, (f, mid))
                if x < bd:
                    bd, bt = x, t
            if bd <= TH:
                tid = bt
        if tid is None and len(members) < min_size:
            continue
        title = name_of([r["ocr_text"] for r in members])
        if tid is None and title and title_key(title) in by_title:
            tid = by_title[title_key(title)]  # bir xil nomli ekran (boshqa rangda / o'lchamda) — bitta tur
        if tid is None:
            t = ScreenType.objects.create(title=title or "Nomsiz ekran", count=0)
            existing[t.id] = t
            created += 1
            tid = t.id
            if title:
                by_title[title_key(title)] = tid
        assign[tid].extend(members)
    from .models import Tag
    tag_titles = dict(Tag.objects.values_list("key", "title"))
    # nomlar: avtomatik turlar — rasmlardagi matndan; topilmasa — kamroq uchraydigan qator yoki teg nomi
    names = {}
    for tid, members in assign.items():
        t = existing[tid]
        if t.title_locked:
            names[tid] = t.title
            continue
        ocrs = [r["ocr_text"] for r in members]
        names[tid] = name_of(ocrs) or name_of(ocrs, loose=True) or ""
    # bir xil nomli avtomatik turlar — bittasiga (eng kattasiga) birlashtiriladi
    by_key = {}
    for tid in sorted(assign, key=lambda x: -len(assign[x])):
        k = title_key(names[tid])
        if not k:
            continue
        if k in by_key and not existing[tid].title_locked:
            assign[by_key[k]].extend(assign.pop(tid))
        else:
            by_key.setdefault(k, tid)
    with transaction.atomic():
        Media.objects.filter(kind=Media.PHOTO, screen__isnull=False).exclude(
            id__in=[r["id"] for ms in assign.values() for r in ms]).filter(screen__title_locked=False).update(screen=None)
        for tid, members in assign.items():
            ids = [r["id"] for r in members]
            for i in range(0, len(ids), 500):
                Media.objects.filter(id__in=ids[i:i + 500]).update(screen_id=tid)
            t = existing[tid]
            step = max(1, len(members) // MAX_REPS)
            reps, have = [], []
            for r in members[::step]:
                h = _h(r)
                if all(dist(h, x) > 2 for x in have):
                    reps.append([r["dhash"], r["dhash_mid"] or r["dhash"]])
                    have.append(h)
                if len(reps) >= MAX_REPS:
                    break
            t.hashes = reps
            t.count = len(members)
            if not t.title_locked:
                t.tag = tag_of(["\n".join(x for x in (r["ocr_text"], r["message__text"]) if x) for r in members[:300]]) or t.tag
                t.title = names.get(tid) or (f"{tag_titles[t.tag]} — ekran" if t.tag in tag_titles else "") or t.title
            t.save()
        # rasmsiz qolgan avtomatik turlar — yashiriladi (o'chirilmaydi)
        ScreenType.objects.exclude(pk__in=assign.keys()).filter(title_locked=False).update(count=0, hidden=True)
        ScreenType.objects.filter(pk__in=assign.keys(), hidden=True, title_locked=False).update(hidden=False)
    _CACHE["key"] = None
    return {"types": len(assign), "created": created, "photos": sum(len(v) for v in assign.values()), "total": len(rows)}


def rebuild_async():
    def run():
        from django.db import close_old_connections
        close_old_connections()
        try:
            rebuild()
        finally:
            close_old_connections()
    threading.Thread(target=run, name="support-screens", daemon=True).start()


# ---------------------------------------------------------------- panel uchun
def listing(media_dict, limit_questions=6):
    """Turlar: namunalar (fayli bor so'nggilari), rasmlar va savollar soni, eng ko'p savollar (tur ichida jamlangan)."""
    from .models import Tag
    titles = dict(Tag.objects.values_list("key", "title"))
    types = list(ScreenType.objects.filter(hidden=False, count__gt=0).select_related("entry"))
    ids = [t.id for t in types]
    samples = defaultdict(list)
    for m in (Media.objects.filter(screen_id__in=ids).exclude(path="").select_related("label", "message__group")
              .order_by("-created_at")[:4000]):
        if len(samples[m.screen_id]) < 4:
            samples[m.screen_id].append(m)
    questions = defaultdict(Counter)
    qcount = Counter()
    seen = set()
    for sid, mid, problem, text, title in (Media.objects.filter(screen_id__in=ids, message__kind=Message.QUESTION)
                                           .values_list("screen_id", "message_id", "message__problem", "message__text",
                                                        "message__entry__title")):
        if (sid, mid) in seen:
            continue
        seen.add((sid, mid))
        qcount[sid] += 1
        q = (title or problem or text or "").strip()
        if q and q != "Rasmli savol":
            questions[sid][" ".join(q.split())[:90]] += 1
    out = []
    for t in types:
        out.append({"id": t.id, "title": t.title, "locked": t.title_locked, "tag": t.tag, "tag_title": titles.get(t.tag, ""),
                    "count": t.count, "questions": qcount.get(t.id, 0),
                    "top": [{"q": q, "n": n} for q, n in questions[t.id].most_common(limit_questions)],
                    "entry": t.entry_id, "entry_title": t.entry.title if t.entry_id else "",
                    "samples": [media_dict(m) for m in samples[t.id]]})
    return out

"""Rasmlarni saqlash va tanish: "vizual iz" (difference hash) + eng yaqin o'rgatilgan namuna (kNN).

Agentlar yuboradigan skrinshotlar deyarli doim bir xil ekranlar (PRBC, ProTarget, 1C natijasi): faqat ism, kod,
summa kabi foydalanuvchi ma'lumotlari farq qiladi. Bunday matn o'zgarishlari rasmning umumiy tuzilishini
(rang bloklari, tugmalar, kartochkalar joylashuvi) deyarli o'zgartirmaydi, shuning uchun:
  - har bir rasmdan 64 bitli dHash (butun rasm) va o'rta qism dHash'i (status bar/klaviaturasiz) olinadi;
  - yangi rasm o'rgatilgan (label qilingan) rasmlar bilan Hamming masofasi bo'yicha solishtiriladi;
  - masofa chegaradan kichik bo'lsa — o'sha bilim bazasi yozuvi, OCR'siz, millisekundlarda.
Namunalar: admin panelda rasm turiga yozuv biriktiradi; xodim javobi yoki ishonchli moslikdan avtomatik ham o'rganiladi.
"""
import hashlib
import io
import mimetypes
from pathlib import Path

from django.utils import timezone

from .models import Entry, Media

EXT = {"photo": ".jpg", "video": ".mp4", "video_note": ".mp4", "animation": ".mp4", "document": ""}


def _dhash(img, size=8):
    g = img.convert("L").resize((size + 1, size), resample=1)  # 1 = LANCZOS/ANTIALIAS
    px = list(g.getdata())
    bits = 0
    for row in range(size):
        for col in range(size):
            left, right = px[row * (size + 1) + col], px[row * (size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return f"{bits:016x}"


def features(data):
    """Rasm o'lchami va ikki dHash. Rasm emas bo'lsa — bo'sh."""
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        w, h = img.size
        mid = img.crop((0, int(h * 0.12), w, int(h * 0.80))) if h > 200 else img
        return {"width": w, "height": h, "dhash": _dhash(img), "dhash_mid": _dhash(mid)}
    except Exception:  # noqa: BLE001 — buzilgan yoki rasm bo'lmagan fayl
        return {}


def hamming(a, b):
    if not a or not b:
        return 64
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _h(obj, key):
    return (obj.get(key) if isinstance(obj, dict) else getattr(obj, key, "")) or ""


def distance(m1, m2):
    """Ikki rasm orasidagi masofa (0 — bir xil, 64 — butunlay boshqa). O'rta qism ustunroq: status bar farqiga chidamli."""
    full = hamming(_h(m1, "dhash"), _h(m2, "dhash"))
    mid = hamming(_h(m1, "dhash_mid"), _h(m2, "dhash_mid"))
    return min(mid, (full + mid) / 2)


def store(data, kind="photo", name="", mime="", source="question", message=None):
    """Faylni serverga yozadi (sha256 bo'yicha bir marta) va Media yozuvini qaytaradi."""
    from .runner import media_dir
    if kind == "video" and source in ("answer", "seed"):
        from .mediaprep import compress_video
        data = compress_video(data, name)  # javob videolari siqiladi (ffmpeg bo'lsa) — tez yuklanadi va ochiladi
    sha = hashlib.sha256(data).hexdigest()
    ext = Path(name).suffix.lower() if name and Path(name).suffix else (EXT.get(kind) or mimetypes.guess_extension(mime or "") or "")
    folder = media_dir() / "files" / sha[:2]
    path = folder / f"{sha}{ext}"
    extra, prev = {}, None
    if kind == Media.PHOTO:
        # aynan shu rasm (sha256) avval kelgan — iz, OCR va ekran turi qayta hisoblanmaydi
        prev = Media.objects.filter(sha256=sha, kind=Media.PHOTO).exclude(dhash="").order_by("-id").first()
    if prev is not None:
        feats = {"width": prev.width, "height": prev.height, "dhash": prev.dhash, "dhash_mid": prev.dhash_mid}
        extra = {"ocr_text": prev.ocr_text, "screen_id": prev.screen_id}
    else:
        feats = features(data) if kind == Media.PHOTO else {}
    write = True
    if kind == Media.PHOTO and source in ("question", "live") and message is not None and feats.get("dhash"):
        # tanish ekran turi va unda yetarli namuna fayli bor — yangi fayl diskka yozilmaydi (iz + OCR + Telegram
        # file_id qoladi; asl rasm kerak bo'lsa — bot orqali Telegram'dan). Noyob / yangi ekranlar saqlanadi.
        from . import screens, slim
        tid = extra.get("screen_id") or screens.nearest(feats)[0]
        if tid and Media.objects.filter(screen_id=tid).exclude(path="").count() >= slim.KEEP_PER_TYPE \
                and not path.exists():
            write, extra["screen_id"] = False, tid
    if write:
        try:
            folder.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(data)
        except OSError:
            path = Path("")
    else:
        path = Path("")
        extra.update(slim=True, full_size=len(data))
    m = Media.objects.create(kind=kind, path=str(path) if str(path) not in ("", ".") else "", name=name[:200],
                             mime=mime[:100] or (mimetypes.guess_type(name)[0] or "") if name else mime[:100],
                             size=len(data), sha256=sha, source=source, message=message, **feats,
                             **{k: v for k, v in extra.items() if v not in (None, "")})
    m.prev_alert = (prev.message.alert_text if prev is not None and prev.message_id else None)
    return m


def match(media_or_feats, threshold, include_unapproved=False):
    """Eng yaqin o'rgatilgan namuna: (yozuv, masofa, namuna) yoki (None, 64, None)."""
    if not _h(media_or_feats, "dhash"):
        return None, 64, None
    statuses = (Entry.APPROVED, Entry.REVIEW, Entry.NEW) if include_unapproved else (Entry.APPROVED,)
    a_full, a_mid = int(_h(media_or_feats, "dhash") or "0", 16), int(_h(media_or_feats, "dhash_mid") or "0", 16)
    own = getattr(media_or_feats, "pk", None)
    best_d, best = 65, None
    for mid, full, middle, eid, status in _examples():
        if mid == own or status not in statuses:
            continue
        f = bin(a_full ^ full).count("1")
        m = bin(a_mid ^ middle).count("1")
        d = min(m, (f + m) / 2)
        if d < best_d:
            best_d, best = d, (mid, eid)
    if best and best_d <= threshold:
        return Entry.objects.filter(pk=best[1]).first(), best_d, Media.objects.filter(pk=best[0]).first()
    return None, best_d, None


_CACHE = {"key": None, "rows": []}


def _examples():
    """O'rgatilgan rasmlar izlari xotirada (butun son sifatida) — har savolda bazadan qayta o'qilmaydi."""
    from django.db.models import Count, Max
    agg = Media.objects.filter(label__isnull=False).aggregate(n=Count("id"), m=Max("id"), e=Max("label__updated_at"))
    key = (agg["n"], agg["m"], str(agg["e"]))
    if _CACHE["key"] != key:
        _CACHE["rows"] = [(m.id, int(m.dhash, 16), int(m.dhash_mid or m.dhash, 16), m.label_id, m.label.status)
                          for m in Media.objects.filter(kind=Media.PHOTO, label__isnull=False).exclude(dhash="").select_related("label")]
        _CACHE["key"] = key
    return _CACHE["rows"]


def confidence(dist):
    return max(0, min(100, round(100 - dist * 3)))


def label(media_qs, entry, by="", auto=False):
    """Rasmlarni yozuvga o'rgatish. Avtomatik o'rgatish qo'lda qo'yilgan yorliqni almashtirmaydi."""
    n = 0
    for m in media_qs:
        if auto and ((m.label_id and not m.label_auto) or m.ignored):
            continue  # qo'lda qo'yilgan yorliq va rad etilgan rasm avtomatik o'zgarmaydi
        m.label, m.label_auto, m.label_by, m.ignored = entry, auto, by[:150], False
        m.save(update_fields=["label", "label_auto", "label_by", "ignored"])
        n += 1
    _CACHE["key"] = None
    return n


def clusters(qs, threshold):
    """Yorliqsiz rasmlarni o'xshashligi bo'yicha guruhlash (admin ularni bir bosishda o'rgatadi)."""
    items = [m for m in qs if m.dhash]
    used, out = set(), []
    for i, m in enumerate(items):
        if m.pk in used:
            continue
        group = [m]
        used.add(m.pk)
        for n in items[i + 1:]:
            if n.pk not in used and distance(m, n) <= threshold:
                group.append(n)
                used.add(n.pk)
        out.append(group)
    out.sort(key=lambda g: -len(g))
    return out


def cleanup(days):
    """O'rgatilmagan, biriktirilmagan eski savol rasmlarini o'chirish (0 — hech narsa o'chirilmaydi)."""
    if not days:
        return 0
    from .models import Settings
    attached = {i for a in Entry.objects.exclude(attachments=[]).values_list("attachments", flat=True) for i in a}
    cutoff = timezone.now() - timezone.timedelta(days=days)
    # bot javoblari tahlil uchun kamida answer_keep_days saqlanadi; xato / tekshirilmagan javoblar — tuzatilguncha
    keep_bot = timezone.now() - timezone.timedelta(days=max(days, Settings.load().answer_keep_days or 0))
    n = 0
    for m in (Media.objects.filter(created_at__lt=cutoff, label__isnull=True, source__in=["question", "history"])
              .exclude(path="").select_related("message")):
        msg = m.message
        if msg is not None and (msg.review in ("wrong", "check") or (msg.answered_by == "bot" and m.created_at > keep_bot)):
            continue
        if m.pk in attached or Media.objects.filter(sha256=m.sha256).exclude(pk=m.pk).filter(label__isnull=False).exists():
            continue
        try:
            Path(m.path).unlink(missing_ok=True)
        except OSError:
            continue
        Media.objects.filter(pk=m.pk).update(path="")
        n += 1
    return n

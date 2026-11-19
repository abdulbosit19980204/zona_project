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
    sha = hashlib.sha256(data).hexdigest()
    ext = Path(name).suffix.lower() if name and Path(name).suffix else (EXT.get(kind) or mimetypes.guess_extension(mime or "") or "")
    folder = media_dir() / "files" / sha[:2]
    path = folder / f"{sha}{ext}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
    except OSError:
        path = Path("")
    feats = features(data) if kind == Media.PHOTO else {}
    return Media.objects.create(kind=kind, path=str(path) if str(path) not in ("", ".") else "", name=name[:200],
                                mime=mime[:100] or (mimetypes.guess_type(name)[0] or "") if name else mime[:100],
                                size=len(data), sha256=sha, source=source, message=message, **feats)


def match(media_or_feats, threshold, include_unapproved=False):
    """Eng yaqin o'rgatilgan namuna: (yozuv, masofa, namuna) yoki (None, 64, None)."""
    if not _h(media_or_feats, "dhash"):
        return None, 64, None
    statuses = [Entry.APPROVED, Entry.REVIEW, Entry.NEW] if include_unapproved else [Entry.APPROVED]
    best, best_d, best_m = None, 65, None
    for m in Media.objects.filter(kind=Media.PHOTO, label__status__in=statuses).exclude(dhash="").select_related("label"):
        if getattr(media_or_feats, "pk", None) == m.pk:
            continue
        d = distance(media_or_feats, m)
        if d < best_d:
            best, best_d, best_m = m.label, d, m
    if best is not None and best_d <= threshold:
        return best, best_d, best_m
    return None, best_d, None


def confidence(dist):
    return max(0, min(100, round(100 - dist * 3)))


def label(media_qs, entry, by="", auto=False):
    """Rasmlarni yozuvga o'rgatish. Avtomatik o'rgatish qo'lda qo'yilgan yorliqni almashtirmaydi."""
    n = 0
    for m in media_qs:
        if auto and m.label_id and not m.label_auto:
            continue
        m.label, m.label_auto, m.label_by = entry, auto, by[:150]
        m.save(update_fields=["label", "label_auto", "label_by"])
        n += 1
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
    attached = {i for a in Entry.objects.exclude(attachments=[]).values_list("attachments", flat=True) for i in a}
    cutoff = timezone.now() - timezone.timedelta(days=days)
    n = 0
    for m in Media.objects.filter(created_at__lt=cutoff, label__isnull=True, source__in=["question", "history"]).exclude(path=""):
        if m.pk in attached or Media.objects.filter(sha256=m.sha256).exclude(pk=m.pk).filter(label__isnull=False).exists():
            continue
        try:
            Path(m.path).unlink(missing_ok=True)
        except OSError:
            continue
        Media.objects.filter(pk=m.pk).update(path="")
        n += 1
    return n

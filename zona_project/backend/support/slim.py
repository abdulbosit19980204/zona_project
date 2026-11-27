"""Rasmlar joyi: serverda faqat kerakli rasmlar to'liq saqlanadi.

Tanish uchun rasmning o'zi emas, vizual izi (dHash) va o'qilgan matni (OCR) kerak — ular bazada qoladi. Shuning uchun:
  - tanilgan / standart savol rasmi (ekran turi, o'rgatilgan namuna, bot standart javob bergan) — 1 soatdan keyin
    fayl o'chiriladi; har bir turdan bir nechta so'nggi namuna kichik eskiz (≈15 KB) bo'lib qoladi (panelda ko'rinishi uchun);
  - tanilmagan savol rasmi — `media_full_days` kun to'liq, keyin eskiz;
  - ochiq savol (hal bo'lmagan / jarayonda / uzatilgan) rasmi — yechilguncha (ko'pi bilan 14 kun) to'liq;
  - javob biriktirmalari, admin yuklagan namunalar — hech qachon tegilmaydi.
Asl rasm Telegram'da qoladi: panel uni kerak bo'lganda bot orqali oladi (saqlamasdan) yoki xabar havolasini beradi.
Ish fonda, kichik paketlarda — javob tezligiga ta'sir qilmaydi.
"""
import io
import time
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from .models import Entry, Media, Message, ScreenType, Settings

THUMB_SIDE = 480
KEEP_PER_TYPE = 6
KNOWN_AFTER = timezone.timedelta(hours=1)
OPEN_KEEP = timezone.timedelta(days=14)
SOURCES = ("question", "history", "live")
BOT_STAGES = ("template", "faq", "rule", "ai", "image", "prbc")


def thumb_bytes(data, side=THUMB_SIDE):
    """Kichik eskiz (WebP, bo'lmasa JPEG): (bayt, mime) yoki (None, "")."""
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
        img = img.convert("RGB")
        if max(img.size) > side:
            k = side / max(img.size)
            img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS)
        out = io.BytesIO()
        try:
            img.save(out, "WEBP", quality=55, method=4)
            return out.getvalue(), "image/webp"
        except (OSError, KeyError, ValueError):
            out = io.BytesIO()
            img.save(out, "JPEG", quality=60, optimize=True)
            return out.getvalue(), "image/jpeg"
    except Exception:  # noqa: BLE001 — buzilgan fayl
        return None, ""


def cached_thumb(m):
    """Panel ro'yxati uchun eskiz (asl fayl o'zgarmaydi): media/thumbcache/<sha>.webp — bir marta yasaladi.
    Qaytaradi: (bayt, mime) yoki (None, "")."""
    from .runner import media_dir
    folder = media_dir() / "thumbcache" / (m.sha256 or "xx")[:2]
    for ext, mime in ((".webp", "image/webp"), (".jpg", "image/jpeg")):
        p = folder / f"{m.sha256 or m.pk}{ext}"
        if p.exists():
            try:
                return p.read_bytes(), mime
            except OSError:
                break
    try:
        data = Path(m.path).read_bytes()
    except OSError:
        return None, ""
    small, mime = thumb_bytes(data, side=240)
    if not small or len(small) >= len(data):
        return data, m.mime or "image/jpeg"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{m.sha256 or m.pk}{'.webp' if mime == 'image/webp' else '.jpg'}").write_bytes(small)
    except OSError:
        pass
    return small, mime


def _unlink_if_unused(path, pk):
    if path and not Media.objects.filter(path=path).exclude(pk=pk).exists():
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass
        sha = Path(path).stem
        if not Media.objects.filter(sha256=sha, slim=False).exclude(path="").exclude(pk=pk).exists():
            from .runner import media_dir
            for ext in (".webp", ".jpg"):  # panel eskizi keshi ham (asl fayl endi yo'q)
                try:
                    (media_dir() / "thumbcache" / sha[:2] / f"{sha}{ext}").unlink(missing_ok=True)
                except OSError:
                    pass


def drop(m):
    """Faylni o'chirish (iz va OCR qoladi)."""
    old = m.path
    Media.objects.filter(pk=m.pk).update(path="", slim=True, full_size=m.full_size or m.size)
    _unlink_if_unused(old, m.pk)


def to_thumb(m):
    """Asl nusxa o'rniga eskiz."""
    from .runner import media_dir
    old = m.path
    try:
        data = Path(old).read_bytes()
    except OSError:
        Media.objects.filter(pk=m.pk).update(path="", slim=True)
        return False
    small, mime = thumb_bytes(data)
    if not small or len(small) >= len(data):
        Media.objects.filter(pk=m.pk).update(slim=True, full_size=m.size)  # eskiz kichraymaydi — o'zi qoladi
        return False
    ext = ".webp" if mime == "image/webp" else ".jpg"
    folder = media_dir() / "thumbs" / (m.sha256 or "xx")[:2]
    path = folder / f"{m.sha256 or m.pk}{ext}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(small)
    except OSError:
        return False
    Media.objects.filter(pk=m.pk).update(path=str(path), slim=True, full_size=m.size, size=len(small), mime=mime)
    _unlink_if_unused(old, m.pk)
    return True


def _open(msg, now):
    if msg is None or msg.kind != Message.QUESTION or msg.created_at < now - OPEN_KEEP:
        return False
    return msg.resolution in (Message.NO, Message.WORK, Message.ASKED) or (
        msg.status == Message.ESCALATED and msg.resolution != Message.YES and msg.source == "live")


def run(limit=300, pause=0.01):
    """Bir paket: nechta eskizga almashdi / o'chirildi. Fonda chaqiriladi."""
    now = timezone.now()
    s = Settings.load()
    full_cut = now - timezone.timedelta(days=max(1, s.media_full_days or 3))
    attached = {i for a in Entry.objects.exclude(attachments=[]).values_list("attachments", flat=True) for i in a}
    keep = set()
    for tid in ScreenType.objects.filter(count__gt=0).values_list("id", flat=True):
        keep.update(Media.objects.filter(screen_id=tid).exclude(path="").order_by("-created_at").values_list("id", flat=True)[:KEEP_PER_TYPE])
    qs = (Media.objects.filter(kind=Media.PHOTO, slim=False, source__in=SOURCES).exclude(path="")
          .filter(Q(created_at__lt=now - KNOWN_AFTER)).select_related("message").order_by("id"))
    stats = {"thumb": 0, "drop": 0, "kept": 0}
    for m in qs[:limit * 4]:
        if stats["thumb"] + stats["drop"] >= limit:
            break
        if m.pk in attached or _open(m.message, now):
            stats["kept"] += 1
            continue
        msg = m.message
        standard = msg is not None and msg.answered_by == "bot" and msg.stage in BOT_STAGES and msg.review not in ("wrong", "check")
        known = bool(m.screen_id or m.label_id or m.ignored or standard)
        if known and m.screen_id and m.pk not in keep:
            drop(m)
            stats["drop"] += 1
        elif known or m.created_at < full_cut:
            stats["thumb" if to_thumb(m) else "kept"] += 1
        else:
            stats["kept"] += 1
            continue
        if pause:
            time.sleep(pause)
    return stats


def full_bytes(m):
    """Asl rasm: serverda bo'lsa — fayl; eskizga almashgan bo'lsa — bot orqali Telegram'dan (saqlanmaydi). Yo'q — None."""
    if not m.slim and m.path:
        try:
            return Path(m.path).read_bytes()
        except OSError:
            return None
    msg = m.message
    if msg is None or not msg.bot_id:
        return None
    fid = (m.tg_file_ids or {}).get(str(msg.bot_id)) or ("" if (m.name or "").startswith("album:") else msg.photo_file_id)
    if not fid:
        return None
    try:
        from zona.crypto import decrypt

        from .telegram import Client
        token = decrypt(msg.bot.token_enc)
        return Client(token).download(fid, max_bytes=10 * 1024 * 1024) if token else None
    except Exception:  # noqa: BLE001 — Telegram'da yo'q / tarmoq
        return None


def link(m):
    """Telegram'dagi asl xabar havolasi (albom bo'lagi — o'z xabari)."""
    msg = m.message
    if msg is None or not msg.group_id:
        return ""
    mid = msg.message_id
    if (m.name or "").startswith("album:"):
        try:
            mid = int(m.name.split(":", 1)[1])
        except ValueError:
            pass
    return msg.group.message_link(mid)

"""Qurilma rasmlari: serverda siqiladi (≤1600px JPEG) va kichik nusxa (ro'yxat uchun) yasaladi.

Fayllar baza yonidagi papkada (ZONA_INVENTORY_MEDIA yoki <db papkasi>/inventory-media), veb ildizda emas.
Rasm manzili imzolangan: <img src> token yubora olmaydi, shuning uchun havola imzo bilan beriladi.
"""
import io
import os
import uuid
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.signing import Signer
from django.utils import timezone

MAX_SIDE, THUMB_SIDE, QUALITY = 1600, 360, 82
MAX_BYTES = 15 * 1024 * 1024
_signer = Signer(salt="inventory-photo")


def media_dir():
    base = os.environ.get("ZONA_INVENTORY_MEDIA") or str(Path(str(settings.DATABASES["default"]["NAME"])).parent / "inventory-media")
    return Path(base)


def sign(pk):
    return _signer.signature(str(pk))[:24]


def check(pk, sig):
    return bool(sig) and sign(pk) == sig


def url(photo, thumb=False):
    return f"/api/inventory/photos/{photo.pk}/file/?k={sign(photo.pk)}{'&t=1' if thumb else ''}"


def payload(photo):
    return {"id": photo.pk, "url": url(photo), "thumb": url(photo, thumb=True), "width": photo.width,
            "height": photo.height}


def _encode(img, side):
    from PIL import Image
    im = img.copy()
    im.thumbnail((side, side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return buf.getvalue(), im.size


def store(data, user=None):
    """Rasmni tekshiradi, aylantiradi (EXIF), siqadi va Photo yozuvini qaytaradi. Rasm bo'lmasa ValueError."""
    from PIL import Image, ImageOps, UnidentifiedImageError

    from .models import Photo
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
            img = bg
        elif img.mode == "L":
            img = img.convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("Fayl rasm emas yoki buzilgan.") from e
    full, size = _encode(img, MAX_SIDE)
    small, _ = _encode(img, THUMB_SIDE)
    now = timezone.now()
    folder = media_dir() / f"{now:%Y}" / f"{now:%m}"
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex
    path, thumb = folder / f"{name}.jpg", folder / f"{name}_t.jpg"
    path.write_bytes(full)
    thumb.write_bytes(small)
    cleanup_orphans()
    return Photo.objects.create(path=str(path), thumb=str(thumb), size=len(full), width=size[0], height=size[1],
                                uploaded_by=user if user and user.is_authenticated else None)


def remove_files(photo):
    for p in (photo.path, photo.thumb):
        try:
            if p:
                Path(p).unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_orphans():
    """Yuklangan, lekin qurilmaga biriktirilmay qolgan (forma yopilgan) rasmlar 2 kundan keyin o'chiriladi."""
    from .models import Photo
    old = Photo.objects.filter(item__isnull=True, created_at__lt=timezone.now() - timedelta(days=2))[:50]
    for photo in old:
        remove_files(photo)
        photo.delete()

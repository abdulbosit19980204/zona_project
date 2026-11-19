"""Rasmdagi matnni serverning o'zida o'qish (Tesseract, bepul). O'rnatilmagan bo'lsa — bo'sh matn qaytadi."""
import functools
import os
import shutil
import subprocess
import tempfile

WANT = ("rus", "uzb", "eng")  # uzb_cyrl'siz: rus modeli o'zbek kirilini ham o'qiydi, ~25% tezroq


@functools.lru_cache(maxsize=1)
def languages():
    exe = shutil.which("tesseract")
    if not exe:
        return ""
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    have = {line.strip() for line in out.splitlines()[1:]}
    return "+".join(lang for lang in WANT if lang in have)


def available():
    return bool(languages())


def _shrink(data, max_side=1600):
    """OCR uchun: kulrang va eng katta tomoni ≤1600px (skrinshot matni uchun yetarli, bir necha baravar tez)."""
    try:
        import io

        from PIL import Image
        img = Image.open(io.BytesIO(data)).convert("L")
        if max(img.size) > max_side:
            k = max_side / max(img.size)
            img = img.resize((int(img.width * k), int(img.height * k)))
        out = io.BytesIO()
        img.save(out, "PNG", optimize=False)
        return out.getvalue()
    except Exception:  # noqa: BLE001
        return data


def read_text(image_bytes, timeout=25):
    langs = languages()
    if not langs or not image_bytes:
        return ""
    image_bytes = _shrink(image_bytes)
    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(image_bytes)
        res = subprocess.run(["tesseract", path, "stdout", "-l", langs, "--psm", "6"],
                             capture_output=True, text=True, timeout=timeout)
        text = res.stdout or ""
    except (OSError, subprocess.SubprocessError):
        text = ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if len(line) > 1)[:4000]

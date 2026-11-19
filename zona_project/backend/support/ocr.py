"""Rasmdagi matnni serverning o'zida o'qish (Tesseract, bepul). O'rnatilmagan bo'lsa — bo'sh matn qaytadi."""
import functools
import os
import shutil
import subprocess
import tempfile

WANT = ("rus", "uzb", "eng", "uzb_cyrl")


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


def read_text(image_bytes, timeout=25):
    langs = languages()
    if not langs or not image_bytes:
        return ""
    fd, path = tempfile.mkstemp(suffix=".img")
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

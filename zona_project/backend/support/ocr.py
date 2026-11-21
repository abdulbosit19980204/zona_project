"""Rasmdagi matnni serverning o'zida o'qish (Tesseract, bepul). O'rnatilmagan bo'lsa — bo'sh matn qaytadi."""
import functools
import os
import re
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


# ------------------------------------------------------------------ skrinshotdagi asosiy xabar
# Agent skrinshoti: yuqorida telefon holat qatori (soat, %, belgilar), o'rtada ilova ekrani va eng muhimi — xato
# yoki holat xabari ("Ошибка...", "Awaiting approval", "Клиент уже есть", "moderatsiyaga yuborildi").
ERROR_WORDS = re.compile(
    r"(ошибк|error|xato|xatolik|already|inactive|не обработан|amalga oshmadi|не удалось|не удаётся|не удается|failed|fail\b|невозможно|нельзя|запрещ|отказ|"
    r"denied|invalid|неверн|некоррект|не найден|not found|topilmadi|недоступ|нет доступа|доступ|уже есть|уже существ|"
    r"allaqachon|mavjud emas|mavjud|rad etil|отклон|превыш|лимит|limit|timeout|тайм-аут|awaiting|ожида|kutil|"
    r"модерац|moderats|заблок|blok|не пробива|не провод|не отправ|не сохран|не загруж|не синхрон|sinxron|"
    r"approval|pending|warning|внимание|diqqat|предупрежд|попробуйте|qayta urin|try again|обратитесь|"
    r"не активн|faol emas|истек|muddati|не хватает|недостаточно|yetarli emas|остаток|qoldiq)", re.IGNORECASE)


# ilova menyusi va tugmalari (har bir skrinshotda bor — xabar emas)
UI_NOISE = re.compile(r"(?<!\w)(визиты|каталог|задачи|корзина|профиль|назад|главная|меню|мини-приложение|"
                      r"vizitlar|katalog|vazifalar|savat|profil|orqaga|bosh sahifa)(?!\w)", re.IGNORECASE)


def _clean(line):
    letters = sum(c.isalpha() for c in line)
    words = [w for w in re.findall(r"[^\W\d_]{3,}", line)]
    return letters >= 8 and letters / max(1, len(line)) >= 0.55 and len(words) >= 2


def main_message(text, limit=220):
    """OCR matnidan asosiy xabar: xato/holat so'zlari bor qator (va uning davomi), bo'lmasa eng mazmunli qatorlar.
    Holat qatori ("15:06 7 156 22"), ilova sarlavhasi va tasodifiy belgilar tashlanadi."""
    lines = [" ".join(UI_NOISE.sub(" ", ln).split()) for ln in (text or "").splitlines()]
    good = [(i, ln) for i, ln in enumerate(lines) if _clean(ln)]
    if not good:
        return ""
    hit = next((i for i, ln in good if ERROR_WORDS.search(ln)), None)
    if hit is not None:
        # xabar odatda 2-4 qatorga bo'lingan: oldingi va keyingi toza qatorlar bilan birga
        idx = [i for i, _ln in good]
        pos = idx.index(hit)
        start = pos - 1 if pos > 0 and idx[pos - 1] == hit - 1 and not lines[hit - 1].endswith((".", "!", ":")) else pos
        out, n = [], 0
        for i, ln in good[start:]:
            if out and i != good[start + len(out) - 1][0] + 1:
                break
            out.append(ln)
            n += len(ln)
            if n >= limit or ln.endswith(("!", ".")) and len(out) >= 2:
                break
        msg = " ".join(out)
    else:
        msg = " ".join(ln for _i, ln in sorted(good, key=lambda x: -len(x[1]))[:2])
    return msg[:limit].strip()

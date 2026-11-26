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
    return fix_homoglyphs("\n".join(line for line in lines if len(line) > 1)[:4000])


# Tesseract (rus+uzb+eng) ruscha qisqa so'zni ba'zan lotin harflari bilan o'qiydi: "отправлена Ha модерацию" ("на" emas) —
# shunda "на модерацию" sharti topilmaydi. Faqat qisqa (≤3 harf), butunlay o'xshash harflardan iborat va kirillcha so'z
# yonidagi so'z kirillchaga aylantiriladi; "BABAYEVA AMINA" kabi lotincha nomlar tegmaydi.
_LAT2CYR = str.maketrans("AaBCcEeHKkMOoPpTXxy", "АаВСсЕеНКкМОоРрТХху")
_HOMO = re.compile(r"^[AaBCcEeHKkMOoPpTXxy]{1,3}$")
_CYR = re.compile(r"[а-яё]", re.IGNORECASE)


def fix_homoglyphs(text):
    parts = re.split(r"(\s+)", text or "")
    words = [i for i, p in enumerate(parts) if p and not p.isspace()]
    bare = {i: parts[i].strip(".,!?:;«»\"'()") for i in words}
    for n, i in enumerate(words):
        w = bare[i]
        if not _HOMO.match(w):
            continue
        near = [bare[words[j]] for j in (n - 1, n + 1) if 0 <= j < len(words)]
        if any(_CYR.search(x) and not re.search(r"[a-z]", x, re.IGNORECASE) for x in near):
            parts[i] = parts[i].replace(w, w.translate(_LAT2CYR))
    return "".join(parts)


# ------------------------------------------------------------------ qizil yozuv (xato izohi)
# Ilovalar xato sababini qizil rangda yozadi ("Для данной ТТ не найдены активные маршруты доставки. Обратитесь к
# своему администратору"). Butun ekran matnida bu qator boshqa so'zlar (to'lov turlari, menyu) orasida yo'qolib
# ketadi — shu sabab qizil piksellar alohida ajratiladi va faqat ular o'qiladi.
RED_MIN_DENSITY = 0.004   # qatordagi qizil piksellar ulushi: matn qatori
RED_MAX_DENSITY = 0.45    # bundan ko'pi — qizil tugma/fon (matn emas)


def _red_layers(image_bytes, max_side=1600):
    """(niqob, qizillik): niqob — aniq qizil piksellar (qator izlash uchun); qizillik — R - max(G, B) kulrang
    tasvirda (qizil matn qora, oq fon va qora/kulrang matn oq): siqilgan JPEG'dagi ingichka harflar ham saqlanadi."""
    try:
        import io

        from PIL import Image, ImageChops
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        if max(img.size) > max_side:
            k = max_side / max(img.size)
            img = img.resize((int(img.width * k), int(img.height * k)))
        r, g, b = img.split()
        redness = ImageChops.subtract(r, ImageChops.lighter(g, b))
        mask = ImageChops.multiply(redness.point(lambda v: 255 if v >= 55 else 0), r.point(lambda v: 255 if v >= 140 else 0))
        return mask, redness
    except Exception:  # noqa: BLE001
        return None, None


def red_mask(image_bytes, max_side=1600):
    """Qizil piksellar niqobi (L rejim: 255 — qizil). PIL'siz yoki rasm buzuq bo'lsa — None."""
    return _red_layers(image_bytes, max_side)[0]


def red_bands(mask):
    """Qizil matn qatorlari: [(y0, y1), ...] — yaqin qatorlar bitta xabarga birlashtiriladi."""
    from PIL import Image
    w, h = mask.size
    col = mask.resize((1, h), Image.Resampling.BOX).getdata()
    rows = [v / 255 for v in col]
    bands, start, gap = [], None, 0
    for y, dens in enumerate(rows + [0.0] * 8):
        text_row = RED_MIN_DENSITY <= dens <= RED_MAX_DENSITY
        if text_row:
            if start is None:
                start = y
            gap = 0
        elif start is not None:
            gap += 1
            if gap > 10:
                bands.append((start, y - gap + 1))
                start, gap = None, 0
    merged = []
    for a, b in bands:  # bir xabarning qatorlari (orasi bo'sh joy, qizil tugma emas) — birlashtiriladi
        if merged and a - merged[-1][1] <= 24 and max(rows[merged[-1][1]:a] or [0]) <= RED_MAX_DENSITY:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(a, b) for a, b in merged if 9 <= b - a <= 160]


def _tesseract(img, langs, timeout):
    fd, path = tempfile.mkstemp(suffix=".png")
    try:
        with os.fdopen(fd, "wb") as f:
            img.save(f, "PNG")
        res = subprocess.run(["tesseract", path, "stdout", "-l", langs, "--psm", "6"],
                             capture_output=True, text=True, timeout=timeout)
        return res.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def red_text(image_bytes, timeout=15):
    """Skrinshotdagi qizil yozuv (xato sababi). Bo'lmasa yoki o'qilmasa — bo'sh satr."""
    langs = languages()
    if not langs or not image_bytes:
        return ""
    mask, redness = _red_layers(image_bytes)
    if mask is None:
        return ""
    try:
        from concurrent.futures import ThreadPoolExecutor

        from PIL import Image, ImageOps
        crops = []
        for a, b in red_bands(mask)[:3]:
            y0, y1 = max(0, a - 6), min(mask.height, b + 6)
            box = mask.crop((0, y0, mask.width, y1)).getbbox()
            if not box:
                continue
            x0, x1 = max(0, box[0] - 8), min(mask.width, box[2] + 8)
            crop = redness.crop((x0, y0, x1, y1)).point(lambda v: 255 - min(255, v * 2))  # qizil -> qora, qolgani oq
            k = 3 if crop.height < 80 else 2 if crop.height < 160 else 1
            if k > 1:
                crop = crop.resize((crop.width * k, crop.height * k), Image.Resampling.LANCZOS)
            crops.append(ImageOps.expand(crop, border=16, fill=255))
        if not crops:
            return ""
        # bo'laklar bir vaqtda (har biri alohida tesseract jarayoni) — ketma-ket emas
        with ThreadPoolExecutor(max_workers=len(crops)) as pool:
            texts = list(pool.map(lambda c: _tesseract(c, langs, timeout), crops))
        out = []
        for txt in texts:
            lines = [" ".join(ln.split()) for ln in txt.splitlines()]
            msg = " ".join(ln for ln in lines if _clean(ln))
            # qizil yorliqlar ("Скидка на корзину", "Активный визит") — xato emas: xato so'zi yoki to'liq gap bo'lsin
            if msg and (ERROR_WORDS.search(msg) or len(re.findall(r"[^\W\d_]{3,}", msg)) >= 5):
                out.append(msg)
        return " ".join(out)[:500].strip()
    except Exception:  # noqa: BLE001
        return ""


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

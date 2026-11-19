"""O'zbek lotin -> kirill (savol kirillda bo'lsa, javob ham kirillda). Brendlar, kodlar, havolalar o'zgarmaydi."""
import re

KEEP = {"prbc", "protarget", "pro-target", "telegram", "excel", "gps", "sku", "akb", "kpi", "vpn", "id", "uz", "tt", "svr",
        "rop", "asm", "rsm", "kam", "horeca", "mny", "bic", "heinz", "jj", "l'oréal", "loreal", "1c", "edo", "stir"}
APOS = "'ʻʼ‘’`"
MULTI = [("yo" + a, "йў") for a in APOS] + [("o" + a, "ў") for a in APOS] + [("g" + a, "ғ") for a in APOS] + [
    ("sh", "ш"), ("ch", "ч"), ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ye", "е")]
SINGLE = {"a": "а", "b": "б", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "ҳ", "i": "и", "j": "ж", "k": "к", "l": "л",
          "m": "м", "n": "н", "o": "о", "p": "п", "q": "қ", "r": "р", "s": "с", "t": "т", "u": "у", "v": "в", "x": "х",
          "y": "й", "z": "з", "c": "с", "w": "в"}
WORD = re.compile(r"[A-Za-z" + APOS + r"]+|[^A-Za-z" + APOS + r"]+")
SKIP = re.compile(r"(https?://\S+|@\w+|`[^`]*`|\{[a-z_]+\}|\b[A-Z0-9]{2,}[-\d]*\b)")


FOREIGN = re.compile(r"(ee|oo|w|th|ph|ck|ou)", re.IGNORECASE)  # o'zbekchada uchramaydi -> inglizcha so'z, tegilmaydi


def _word(w):
    if w.lower() in KEEP or (w.isupper() and len(w) > 1) or FOREIGN.search(w):
        return w
    if w[:1] in APOS:  # qisqartmadan keyingi qo'shimcha: PRBC'ga -> PRBC'га
        return w[0] + _word(w[1:]) if len(w) > 1 else w
    for a in APOS:  # PRBC'ga, 1C'da: qisqartma o'zgarmaydi, qo'shimchasi kirillga
        left, sep, right = w.partition(a)
        if sep and right and left and (left.isupper() or left.lower() in KEEP) and not (left.lower() in ("o", "g", "yo")):
            return left + sep + _word(right)
    out, i, low = [], 0, w.lower()
    while i < len(w):
        for lat, cyr in MULTI:
            if low.startswith(lat, i):
                piece = "э" if (lat == "ye" and False) else cyr
                out.append(piece.upper() if w[i].isupper() else piece)
                i += len(lat)
                break
        else:
            ch = w[i]
            if ch in APOS:
                out.append("ъ")
            else:
                c = SINGLE.get(ch.lower(), ch)
                if ch.lower() == "e" and i == 0:
                    c = "э"
                out.append(c.upper() if ch.isupper() else c)
            i += 1
    return "".join(out)


def lat2cyr(text):
    """Javob matnini kirillga o'girish: kodlar (UZ-00032829), @username, havolalar, {maydon} va brendlar tegilmaydi."""
    parts, last = [], 0
    for m in SKIP.finditer(text or ""):
        parts.append(("t", text[last:m.start()]))
        parts.append(("k", m.group(0)))
        last = m.end()
    parts.append(("t", (text or "")[last:]))
    out = []
    for kind, chunk in parts:
        if kind == "k":
            out.append(chunk)
            continue
        out.append("".join(_word(tok) if tok[:1].isalpha() or tok[:1] in APOS else tok for tok in WORD.findall(chunk)))
    return "".join(out)


def is_uz_cyrillic(text):
    """O'zbek kirilida yozilganmi (ў қ ғ ҳ harflari bor va kirill harflari ko'p)."""
    letters = [c for c in text or "" if c.isalpha()]
    if not letters:
        return False
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    return cyr / len(letters) >= 0.5 and bool(re.search(r"[ўқғҳЎҚҒҲ]", text))

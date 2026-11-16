"""Matnni yagona qidiruv shakliga keltirish.

"Парол тиклаш", "parolni tiklash", "Пароль не работает", "PAROL" -> bir xil lotin o'zaklar.
1) kichik harf, 2) o'zbek/rus kirill -> lotin, 3) apostrof va belgilarni olib tashlash,
4) to'xtash so'zlari, 5) o'zbek va rus qo'shimchalarini kesish (yengil stemming).
"""
import re
import unicodedata

CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "i", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # o'zbek kirill
    "ў": "o", "қ": "q", "ғ": "g", "ҳ": "h",
    # qozoq/qirg'iz/tojik harflari ham uchrab qoladi
    "ә": "a", "ө": "o", "ү": "u", "ұ": "u", "ң": "n", "і": "i", "ӣ": "i", "ӯ": "u", "ҷ": "j", "һ": "h",
}
APOS = re.compile(r"[ʻʼ’‘`´'ʹʽ\"«»]")
WORD = re.compile(r"[a-z0-9]+")

STOP = {
    # o'zbek
    "va", "bilan", "uchun", "kerak", "bu", "shu", "u", "men", "biz", "siz", "ular", "bor", "yoq", "emas", "ham",
    "lekin", "yoki", "qanday", "nima", "nega", "qachon", "qayerda", "kim", "kimga", "iltimos", "bering", "beringlar",
    "qiling", "qilib", "edi", "ekan", "dagi", "uchta", "bitta", "har", "hamma", "juda", "endi", "hali", "agar",
    "mening", "bizning", "sizning", "menga", "bizga", "sizga", "qilish", "qildim", "qilyapman", "kerakmi",
    # rus
    "i", "v", "na", "ne", "s", "so", "po", "za", "k", "ko", "o", "ob", "ot", "do", "iz", "u", "a", "no", "ili",
    "kak", "chto", "eto", "dlya", "pri", "ya", "my", "vy", "on", "ona", "oni", "mne", "nam", "vam", "pozhaluysta",
    "nado", "nuzhno", "mozhno", "kto", "kogda", "gde", "pochemu", "uzhe", "eshe", "esho", "tolko", "vse", "vsyo",
    "u", "nas", "menya", "kakoy", "kakaya", "kakie", "ili", "zhe", "li", "by", "bud", "budet",
    # ingliz
    "the", "a", "an", "to", "of", "in", "on", "for", "is", "are", "and", "or", "my", "i", "we", "how", "what",
    "please", "can", "not", "with", "need",
}

# uzunidan qisqasiga: o'zbek (lotinlashtirilgan, apostrofsiz) va rus (translit) qo'shimchalari
SUFFIXES = sorted({
    # o'zbek
    "larimizni", "laringizni", "larimizga", "lariningiz", "larining", "larini", "larida", "laridan", "lariga",
    "larning", "larga", "lardan", "larda", "larni", "lari", "lar",
    "imizni", "ingizni", "imizga", "ingizga", "imiz", "ingiz", "ning", "dagi", "dan", "ga", "ka", "qa", "da",
    "ni", "im", "ing", "si", "mayapti", "mayapman", "yapti", "yapman", "moqda", "madi", "maydi", "magan",
    "ilmagan", "ilgan", "gan", "kan", "qan", "ib", "ish", "moq", "adi", "aydi", "di", "dim", "ilsin", "sin",
    "ladi", "lash", "lashtirish", "tirish", "dirish",
    # rus
    "iyami", "yami", "ami", "iyah", "yah", "ah", "ov", "ev", "ey", "om", "em", "oy", "uyu", "yuyu", "aya", "yaya",
    "oe", "ee", "ie", "ye", "yy", "iy", "ih", "yh", "ogo", "ego", "omu", "emu", "imi", "ymi", "at", "yat", "it",
    "et", "ut", "yut", "esh", "ish", "ete", "ite", "li", "la", "lo", "ny", "ni", "tsya", "sya", "ts", "ost",
    "ostyu", "eniya", "enie", "eniye", "aniya", "anie", "ka", "ki", "ku", "koy", "ok", "a", "u", "y", "e", "o", "i",
}, key=len, reverse=True)


def translit(text: str) -> str:
    text = unicodedata.normalize("NFC", text.lower())
    return "".join(CYR.get(ch, ch) for ch in text)


def fold(text: str) -> str:
    """Kichik harf + kirill->lotin + apostrofsiz. Pozitsiyalarni saqlamaydi."""
    text = APOS.sub("", translit(text or ""))
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def stem(word: str) -> str:
    if word.isdigit() or len(word) <= 4:
        return word
    for suf in SUFFIXES:
        if word.endswith(suf) and len(word) - len(suf) >= 4:
            return word[: -len(suf)]
    return word


def fold_word(word: str) -> str:
    w = fold(word)
    # boshidagi "ye" (ер/yer) -> "e": kirill "е" bilan bir xil bo'lsin
    return "e" + w[2:] if w.startswith("ye") else w


def tokens(text: str, keep_stop=False):
    out = []
    for w in WORD.findall(fold(text)):
        if w.startswith("ye"):
            w = "e" + w[2:]
        if not keep_stop and (w in STOP or len(w) < 2):
            continue
        out.append(stem(w))
    return out


def word_spans(text: str):
    """Asl matndagi so'zlar va ularning o'zaklari: [(start, end, stem)]. Ajratib ko'rsatish uchun."""
    spans = []
    for m in re.finditer(r"[\w'ʻʼ’‘`-]+", text or ""):
        parts = WORD.findall(fold(m.group(0)))
        if parts:
            spans.append((m.start(), m.end(), stem(fold_word(parts[0]))))
    return spans


def trigrams(word: str):
    w = f"  {word} "
    return {w[i:i + 3] for i in range(len(w) - 2)}

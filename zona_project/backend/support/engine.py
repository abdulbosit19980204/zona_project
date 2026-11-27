"""Savolga javob tanlash "zinapoyasi": eng arzon bosqichdan boshlab.

1) shablon (kalit so'z / regex, rasm matni bilan)  2) bilim bazasidan o'xshash savol
3) mavjud savollar bazasi qoidasi (zona.search)    4) AI (ixtiyoriy, kunlik limit bilan)
5) hech biri ishonchli bo'lmasa — mas'ulni topib, odamga uzatish.

Bu modul Telegram'dan mustaqil: kirish — matn, chiqish — Decision. Shu sabab testlash oson.
"""
import html
import re
from dataclasses import dataclass, field

from django.db.models import Q
from django.utils import timezone

from zona.models import AITaskConfig, AIUsage, Member, StaffPerson, Task, TeamContact
from zona.search import search as run_search
from zona.search.normalize import fold, tokens

from .models import Entry, Settings, TgUser
from .ocr import fix_homoglyphs

GREETING = {"salom", "assalomu", "alaykum", "rahmat", "raxmat", "spasibo", "privet", "zdravstvuyte", "ok", "okey",
            "xop", "xo'p", "xorosho", "yaxshi", "tushunarli", "ponyatno", "ha", "yoq", "da", "net", "+", "👍"}
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass
class Decision:
    stage: str = ""            # template / faq / rule / ai / "" (topilmadi)
    entry: Entry | None = None
    confidence: int = 0
    text: str = ""             # tayyor javob (oddiy matn)
    needs_human: bool = True
    responsible: list = field(default_factory=list)  # [{"name", "telegram", "level"}]
    fields: dict = field(default_factory=dict)
    unapproved: bool = False   # soya rejimida tasdiqlanmagan shablon ishlatildi
    note: str = ""
    parts: list = field(default_factory=list)  # albomda turli ekranlar: [(rasm_tartibi, yozuv, ishonch)] — alohida javoblar
    owner: bool = False        # mas'ul toifa sozlamasidan (category_owners) — butun tizimda ustun, supervayzer belgilanmaydi
    live: str = ""             # PRBC'dagi jonli holat kartasi (mijoz arizasi) — javob boshida turadi


# ------------------------------------------------------------------ yordamchilar
def detect_lang(text):
    letters = [c for c in text or "" if c.isalpha()]
    if not letters:
        return "uz"
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    if cyr / len(letters) < 0.5:
        return "uz"
    # o'zbek kirill harflari bo'lsa — o'zbekcha
    return "uz" if re.search(r"[ўқғҳЎҚҒҲ]", text) else "ru"


REPORT_START = re.compile(r"^\s*(✅|☑️|🌅|📊|📅|📌|📢|🔔|⚡|🟢|🔴|#)")


def is_question(text, has_photo=False, forwarded=False):
    """Salom/rahmat/stiker emas, mazmunli xabar yoki rasm. Forward qilingan xabarlar, avtomatik hisobot va
    e'lonlar (ko'p qatorli, savol belgisisiz, emoji bilan boshlanadigan) savol hisoblanmaydi."""
    if forwarded:
        return False
    t = (text or "").strip()
    if t.startswith("/"):
        return False  # bot buyruqlari (/vazifa, /start...) — savol emas
    lines = [x for x in t.splitlines() if x.strip()]
    if t and "?" not in t and (REPORT_START.match(t) and len(lines) >= 2 or len(lines) >= 8):
        return False
    if has_photo:
        return True
    if len(t) < 6:
        return False
    # "iltimos", "yordam bering", "добавьте пжл" kabi faqat umumiy so'zlar — savol emas (rasm bilan kelsa birlashtiriladi)
    m = meaningful(t)
    if not m or (len(m) == 1 and "?" not in t):
        return False
    words = re.findall(r"[\w'ʻʼ’]+", t.lower())
    if not words:
        return False
    if len(words) <= 3 and all(w.replace("ʻ", "'").replace("’", "'") in GREETING for w in words):
        return False
    if greeting_only(t):
        return False  # «Assalam aleykum», «Всем доброе утро», «Добрый день» — salom, savol emas
    return True


_GREET_PREFIX = ("assal", "asal", "aleyk", "alayk", "alek", "salom", "salam", "zdrav", "dobr", "utr", "den", "dnya",
                 "vecher", "privet", "vsem", "hammag", "xayrl", "hayrl", "kun", "tong", "yaxshimi", "qalay", "rahmat",
                 "raxmat", "spasib", "kollegi", "kolleg", "dostlar", "do'stlar")


def greeting_only(text):
    """Xabar faqat salomlashuvdan iborat (kirill/lotin, imlo xatolari bilan): «Assalam aleykum», «Ассаламу алейкум»,
    «Всем доброе утро», «Добрый день, коллеги». @murojaat va tinish belgilari hisobga olinmaydi."""
    t = re.sub(r"@\w+", " ", text or "")
    words = [w for w in toks(t) if not w.isdigit()]
    return bool(words) and len(words) <= 6 and all(w.startswith(_GREET_PREFIX) or w in GREETING for w in words)


CLARIFY_WORDS = re.compile(
    r"\b(yuboring|yuboringchi|yuborib|tashlang|tashlab|tashlavoring|skrin\w*|skrinshot\w*|screen\w*|rasm\w*|foto\w*|"
    r"stir\w*|inn|kod\w*|kodini|raqam\w*|nomer\w*|nomini|qaysi|qanaqa|qanday|qachon|qayer\w*|aniqroq|batafsil|"
    r"ko'rsating|korsating|"
    r"пришлите|отправьте|скиньте|скин\w*|скрин\w*|фото\w*|инн|код\w*|номер\w*|какой|какая|какие|когда|где|уточните|"
    r"покажите)\b", re.IGNORECASE)
ANSWER_HINT = re.compile(r"\b(qildim|qilindi|bo'ldi|boldi|tuzatildi|qo'shildi|qoshildi|ochildi|yopildi|o'tkazildi|"
                         r"tayyor|hal qilindi|сделал|сделано|исправил|исправлено|добавил|готово|открыл)\b", re.IGNORECASE)


HANDOFF_WORDS = re.compile(
    r"\b(помогите|поможите|посмотрите|гляньте|глянь|подключитесь|ответьте|к вам|вам|сюда|тут|"
    r"yordam|bering|beringlar|qarang|qarab|qaravoring|ko'ring|koring|javob|bera|olasizmi|aka|opa|brat|help|pls|plz|please)\b",
    re.IGNORECASE)
REWRITE_ASK = re.compile(
    r"(правильно|нормально|подробн\w*|четко|чётко|понятно|точнее)\s+(напиш|опиш)\w*|(напиш|опиш)\w*\s+(правильно|"
    r"нормально|подробн\w*|понятн\w*|точнее)|подробнее|aniq(roq)?\s+yoz\w*|to'g'ri\s+yoz\w*|togri\s+yoz\w*|"
    r"tushunarli\s+yoz\w*|tushuntir\w*", re.IGNORECASE)


def not_an_answer(text):
    """Xodim xabari bilim bazasi uchun javob emasmi: faqat boshqa xodimni chaqirish ("@operator", "Vali помогите"),
    "savolni to'g'ri yozing" kabi qayta so'rash yoki mazmunsiz qisqa gap ("Tekshiring")."""
    t = (text or "").strip()
    if not t:
        return True
    if REWRITE_ASK.search(t) and len(t) <= 200:
        return True
    # "Готово", "Tekshiring", "Qayta tekwiring, limit qowildi", "Eldar можете помочь" — qayta ishlatib bo'lmaydi
    return is_handoff(t) or len(_handoff_rest(t)) <= 1 or status_reply(t) or handoff_to(t) is not None


# Xodimning holat xabari: ishni O'ZI bajardi va "tekshiring" dedi yoki boshqa xodimni chaqirdi. Bu bilim emas —
# agentga "qayta tekshiring" deyish xato; to'g'ri javob — so'rovni bajaradigan odamni belgilash.
_CHECK = ("prover", "perepro", "posmotr", "glyan", "tekshir", "tekwir", "tekshr", "tekwr", "teksh", "tekw", "korib",
          "korin", "koring", "korvor", "qayta", "snova", "seychas", "sichas",
          "hozir", "xozir", "moment", "minut", "check", "poprob", "urinib", "chiqdimi", "vyshl", "polucil", "poluchil")
_DONE = ("gotov", "sdelal", "sdelan", "ispravil", "ispravlen", "dobavil", "dobavlen", "zakrepil", "otkryl", "otkril",
         "vklyuchil", "qoshild", "qowild", "qoshdim", "qowdim", "yoqild", "yoqdim", "ochild", "ochdim", "tayyor", "boldi",
         "tuzatil", "togrila", "qildim", "qilindi", "okey", "reshen", "reshil", "postavil", "pomenyal", "izmenil")
_HELP = ("mozhet", "mojet", "pomoch", "pomog", "prosh", "pozh", "pojal", "iltimos", "plz", "pls", "kollegi")
_GREET = ("dobr", "utr", "vecher", "zdravst", "assalom", "asalom", "aleykum", "alaykum", "alekum", "salom",
          "privet", "uzur", "izvin", "rahmat", "raxmat", "spasib", "segodn", "bugun")
# o'zi bajaradigan amal (qayta kirish, sinxronlash, bildirishnoma...) — bu haqiqiy ko'rsatma, holat xabari emas
_SELF = ("perezayd", "perezagruz", "vyyd", "vyxod", "zayd", "zaxod", "obnov", "sinxron", "sinhron", "sinxr", "chiqib",
         "kirib", "kiring", "kirvol", "yopib", "yoping", "uvedoml", "bildirish", "oblak", "oblok", "kesh", "udal",
         "ochirib", "ustanov", "ornat", "nastroy", "sozlam", "sbros", "zakroy", "zakrit", "zakryt", "vyklyuch",
         "bosing", "bosib", "bosvor", "nazhm", "najm", "tanlang", "vyber", "otkroy", "oching", "ochib")
_SHORT = {"yana", "eshe", "esho", "eshyo", "raz", "den", "dnya", "aka", "opa", "brat", "uka", "ok", "oke", "okey", "xop"}
_NAMES = {"at": 0.0, "set": set()}


def _staff_first_names():
    """Xodimlar ismlari (Eldar, Гузель, Saidabror...) — "Eldar можете помочь" da ism mazmun emas (10 daqiqa kesh)."""
    import time as _t
    if _t.monotonic() - _NAMES["at"] < 600 and _NAMES["set"]:
        return _NAMES["set"]
    names = set()
    for n in [*Member.objects.values_list("name", flat=True), *TeamContact.objects.values_list("name", flat=True)]:
        names.update(w for w in re.findall(r"[a-z]+", fold(n or "")) if len(w) >= 3)
    _NAMES.update(at=_t.monotonic(), set=names)
    return names


_ENDINGS = ("ning", "ga", "ka", "qa", "ni", "da", "om", "em", "u", "a", "e", "y", "i", "ya", "yu")


def _people_index():
    """[(Member, nom so'zlari, telegram username'lar)] — jamoa kontaktlari o'z jamoasiga (Eldar, Guzel -> Pro-target)."""
    import time as _t
    if _t.monotonic() - _PEOPLE_IDX["at"] < 600 and _PEOPLE_IDX["rows"]:
        return _PEOPLE_IDX["rows"]
    rows = []
    for m in Member.objects.all():
        rows.append((m, {w for w in re.findall(r"[a-z]+", fold(m.name or "")) if len(w) >= 4},
                     {_norm_username(m.telegram)} - {""}))
    for c in TeamContact.objects.select_related("member"):
        if c.member_id:
            rows.append((c.member, {w for w in re.findall(r"[a-z]+", fold(c.name or "")) if len(w) >= 4},
                         {_norm_username(c.telegram)} - {""}))
    _PEOPLE_IDX.update(at=_t.monotonic(), rows=rows)
    return rows


_PEOPLE_IDX = {"at": 0.0, "rows": []}


def _who(word):
    """So'z xodim ismimi ("Саиду" -> Saidabror, "Saidga", "Eldar", "Гузель"): (mos Member'lar, aniq ismmi yoki
    "-ga/-ka" qo'shimchali — o'zi uzatish belgisi)."""
    stems = {word}
    for end in _ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 4:
            stems.add(word[: -len(end)])
    out, exact = set(), False
    for m, names, _u in _people_index():
        for n in names:
            for st in stems:
                if n == st or (len(st) >= 4 and n.startswith(st)):
                    out.add(m)
                    exact = exact or n == word or (st != word and word.endswith(("ga", "ka", "qa")))
    return out, exact


def handoff_to(text):
    """Xodim savolni boshqa xodimga uzatdi: "К Саиду", "Saidabrorga", "Eldar можете помочь", "@StargroupSaid".
    Qaytaradi: o'sha mas'ul (Member) — aniq bitta bo'lsa; aks holda None. Bu javob emas — savol mas'ulga tegishli."""
    t = (text or "").strip()
    if not t or len(t) > 80:
        return None
    hits, rest = set(), 0
    signal = "@" in t  # "К Саиду", "Saidga", "Eldar можете помочь", @username — "Вы супер" esa maqtov, uzatish emas
    for u in re.findall(r"@(\w+)", t):
        un = _norm_username(u)
        found = {m for m, _n, users in _people_index() if un in users}
        if not found:
            return None  # tanilmagan odam chaqirildi — kimga tegishli ekanini bilmaymiz
        hits |= found
    for w in re.findall(r"[a-z]+", fold(re.sub(r"@\w+", " ", t))):
        if w in ("k", "ko"):
            signal = True
            continue
        if w.startswith(_HELP) or w.startswith(_CHECK):
            signal = True
            continue
        if len(w) < 3 or w in GREETING or w in _SHORT or w.startswith(_GREET):
            continue
        found, exact = _who(w)
        if found:
            hits |= found
            signal = signal or exact
        else:
            rest += 1
    return next(iter(hits)) if len(hits) == 1 and rest == 0 and signal else None


HANDOFF_UZ = ("Bu so'rovni **{n}** bajaradi — so'rov unga yuborildi. Kerak bo'lsa nuqta kodi va nomini yozing; "
              "bajarilgach shu yerda javob beriladi.")
HANDOFF_RU = ("Этот запрос выполняет **{n}** — запрос передан. При необходимости напишите код и название ТТ; "
              "когда будет готово, ответим здесь.")


def status_reply(text):
    """Xodim xabari faqat holatmi: "Проверьте", "Готово, прошу проверить", "Qayta tekwiring, limit qowildi",
    "Можете проверить? На сегодняшний день закрепил", "Eldar можете помочь". "Перезайдите и проверьте",
    "В уведомлениях проверьте" — haqiqiy ko'rsatma (agent o'zi qiladi), holat emas."""
    t = (text or "").strip()
    if not t or len(t) > 140:
        return False
    words = re.findall(r"[a-z]+", fold(re.sub(r"@\w+", " ", t)))
    if any(w.startswith(_SELF) for w in words):
        return False
    names = _staff_first_names()
    signal, rest = False, 0
    for w in words:
        if len(w) < 3 or w in GREETING or w in _SHORT:
            continue
        if w.startswith(_CHECK) or w.startswith(_DONE) or w.startswith(_HELP):
            signal = True
        elif w.startswith(_GREET) or w in names:
            continue
        else:
            rest += 1
    return (signal and rest <= 1) or ("@" in t and rest == 0)


def _handoff_rest(t):
    rest = HANDOFF_WORDS.sub(" ", re.sub(r"@\w+", " ", t))
    return re.findall(r"[^\W\d_][\w'ʻʼ’]*", rest)


def is_handoff(text):
    """Xodim savolni boshqa xodimga yo'naltirdi ("@operator", "Vali помогите") — bu javob emas, savol javob kutadi.
    "Готово", "qildim" kabi bajarildi xabarlari — javob (yo'naltirish emas)."""
    t = (text or "").strip()
    if not t or ANSWER_HINT.search(t):
        return False
    words = _handoff_rest(t)
    if "@" in t and len(words) <= 2:
        return True
    return bool(HANDOFF_WORDS.search(t)) and len(words) <= 1


def is_clarifying(text):
    """Xodim javobi aslida aniqlashtiruvchi savolmi ("STIR yuboring", "skrin tashlang?") — bunday matn javob emas."""
    t = (text or "").strip()
    if not t or len(t) > 260 or ANSWER_HINT.search(t):
        return False
    return t.endswith("?") or bool(CLARIFY_WORDS.search(t)) or bool(REWRITE_ASK.search(t))


def tokens_text(text):
    """Tahlil uchun: matnning tartiblangan o'zaklari (o'xshash so'rovlarni bitta deb sanash)."""
    return " ".join(sorted(set(tokens(text or ""))))[:200]


def ask_first_text(entry, lang):
    if not entry or not entry.ask_first.strip():
        return ""
    head = "Чтобы помочь быстрее, пришлите, пожалуйста:" if lang == "ru" else "Tezroq yordam berishimiz uchun, iltimos, yuboring:"
    return f"{head}\n{entry.ask_first.strip()}"


def _norm_username(u):
    return (u or "").strip().lstrip("@").lower()


def identify(tg_id, username="", name=""):
    """Telegram foydalanuvchini topish/yaratish va xodimligini aniqlash (Member yoki jamoa kontakti)."""
    user, _ = TgUser.objects.get_or_create(tg_id=tg_id, defaults={"username": username or "", "name": name or ""})
    changed = False
    if username and user.username != username:
        user.username, changed = username, True
    if name and user.name != name:
        user.name, changed = name, True
    uname = _norm_username(username)
    contact = TeamContact.objects.filter(telegram_id=tg_id).first()
    if not contact and uname:
        contact = next((c for c in TeamContact.objects.exclude(telegram="") if _norm_username(c.telegram) == uname), None)
    member = None
    if not contact and uname:
        member = next((m for m in Member.objects.exclude(telegram="") if _norm_username(m.telegram) == uname), None)
    if contact and contact.telegram_id != tg_id:
        TeamContact.objects.filter(pk=contact.pk).update(telegram_id=tg_id)  # username o'zgarsa ham taniladi
    if (contact.pk if contact else None) != user.contact_id or (member.pk if member else None) != user.member_id:
        user.contact, user.member, changed = contact, member, True
    if user.staff_link not in ("manual", "none") and not (contact or member):
        # aniq belgi — Telegram ID (PRBC / jamoa tuzilmasidan); bo'lmasa — ism va username bo'yicha ehtiyotkor moslik
        from .staffsync import staff_by_tg
        sp = staff_by_tg(tg_id, username)
        if sp and sp.pk != user.staff_person_id:
            user.staff_person, user.staff_link, changed = sp, "prbc", True
        elif not sp and not user.staff_person_id and not user.staff_link:
            sp = match_staff_person(name, username)
            if sp:
                user.staff_person, user.staff_link, changed = sp, "auto", True
    if changed:
        user.save()
    else:
        TgUser.objects.filter(pk=user.pk).update(last_seen=timezone.now())
    return user


def _name_tokens(name):
    # Haydarov = Xaydarov = Хайдаров (h/x yozilishi turlicha)
    return {t.replace("kh", "x").replace("h", "x") for t in re.findall(r"[a-z]+", fold(name or "")) if len(t) >= 3}


def match_staff_person(tg_name, username=""):
    """Telegram ismi (va username: "Haydarov010") ni kontaktlardagi dala xodimiga ehtiyotkorlik bilan bog'lash: kamida
    2 so'z (familiya va ism) mos kelishi va nomzod YAGONA bo'lishi shart. Shubha bo'lsa — bog'lanmaydi (paneldan qo'lda).
    Masalan: ism «Жасур» + username «Haydarov010» -> «Xaydarov Jasur Lazizovich» (SVR)."""
    tn = _name_tokens(tg_name) | _name_tokens(re.sub(r"[\d_]+", " ", username or ""))
    if len(tn) < 2:
        return None
    hits = []
    for sp in StaffPerson.objects.filter(is_vacancy=False).exclude(name="").only("id", "name"):
        common = tn & _name_tokens(sp.name)
        if len(common) >= 2:
            hits.append((len(common), sp))
    if not hits:
        return None
    hits.sort(key=lambda x: -x[0])
    if len(hits) > 1 and hits[0][0] == hits[1][0]:
        return None  # bir xil ismli bir nechta xodim — taxmin qilmaymiz
    return hits[0][1]


def supervisor_of(user):
    """Savol beruvchining supervayzeri: kontaktlardagi rahbarlar zanjiri bo'yicha birinchi SVR (yoki birinchi rahbar)."""
    sp = user.staff_person if user and user.staff_person_id else None
    seen = set()
    cur = sp.manager if sp else None
    first = cur
    while cur and cur.pk not in seen:
        if cur.role == "SVR":
            return cur
        seen.add(cur.pk)
        cur = cur.manager
    return first


def mention_html(tg_user=None, name="", username=""):
    """Telegram belgisi: username bo'lsa @username, bo'lmasa ID orqali (tg://user) — ikkalasi ham bildirishnoma beradi."""
    username = username or (tg_user.username if tg_user else "")
    if username:
        return "@" + html.escape(username)
    if tg_user:
        return f'<a href="tg://user?id={int(tg_user.tg_id)}">{html.escape(name or tg_user.name or "foydalanuvchi")}</a>'
    return html.escape(name)


SUPERVISOR_HINT = re.compile(r"supervayzer|supervizor|супервайзер", re.IGNORECASE)


def needs_supervisor(d):
    """Javob supervayzer harakatini talab qiladimi (mas'ul — Supervayzerlar yoki javob matnida supervayzer).
    Toifa mas'uli belgilangan savolda (masalan, aksiya — operator) supervayzer belgilanmaydi."""
    if getattr(d, "owner", False):
        return False
    if d.entry and d.entry.responsible_id and SUPERVISOR_HINT.search(d.entry.responsible.name or ""):
        return True
    return bool(SUPERVISOR_HINT.search(d.text or ""))


def tag_people(body_html):
    """Javobda ismi aytilgan mas'ullar Telegram'da belgilanadi: «Saidabror» -> «Saidabror (@StargroupSaid)» —
    bildirishnoma boradi. Supervayzerlar jamoasi bu yerda belgilanmaydi (savol beruvchining o'z supervayzeri alohida)."""
    for m in Member.objects.exclude(level="EXT").prefetch_related("contacts"):
        if m.is_team and SUPERVISOR_HINT.search(m.name or ""):
            continue
        tgs = _person(m)["telegram"][:3]
        if not tgs or len(m.name or "") < 3 or any("@" + t.lower() in body_html.lower() for t in tgs):
            continue
        pat = re.compile(r"(?<![\w@])(" + re.escape(html.escape(m.name)) + r")(?!\w)", re.IGNORECASE)
        body_html = pat.sub(lambda x: x.group(1) + " (" + " ".join("@" + html.escape(t) for t in tgs) + ")", body_html, count=1)
    return body_html


def supervisor_line(user, lang):
    """«Supervayzeringiz: @...» — supervayzer ham guruhda yozgan bo'lsa belgilanadi, aks holda faqat ismi."""
    sv = supervisor_of(user)
    if not sv:
        return ""
    tg = TgUser.objects.filter(staff_person=sv).first()
    who = mention_html(tg, sv.name) if tg else html.escape(sv.name)
    return ("👤 Ваш супервайзер: " if lang == "ru" else "👤 Supervayzeringiz: ") + who


# ------------------------------------------------------------------ 1. shablon
_WORDS = re.compile(r"\w+", re.UNICODE)


def _norm_words(text):
    return " ".join(_WORDS.findall(text or ""))


def _trigger_hit(trigger, folded, raw, folded_norm=None):
    """Shart: "re:..." — regex (asl matnda); oddiy ibora — lotinga o'girilgan matnda (tinish belgilariga chidamli);
    "a && b" — ikkalasi ham bo'lishi kerak."""
    trigger = (trigger or "").strip()
    if not trigger:
        return False
    if trigger.startswith("re:"):
        try:
            return bool(re.search(trigger[3:], raw, re.IGNORECASE | re.MULTILINE))
        except re.error:
            return False
    def hit(part):
        p = TYPO_RE.sub(lambda m: TYPOS[m.group(1).lower()], fold(part)).strip()
        return p in folded or (folded_norm is not None and _norm_words(p) in folded_norm)
    return all(hit(part) for part in trigger.split("&&") if part.strip())


def extract_fields(entry, raw):
    out = {}
    for pattern in entry.extract or []:
        try:
            m = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        except re.error:
            continue
        if m:
            out.update({k: " ".join(v.split()) for k, v in m.groupdict().items() if v and v.strip() and k not in out})
    return out


def match_template(raw, entries):
    folded = TYPO_RE.sub(lambda m: TYPOS[m.group(1).lower()], fold(raw))
    folded_norm = _norm_words(folded)
    best, best_hits = None, 0
    for e in entries:
        hits = sum(1 for t in e.triggers or [] if _trigger_hit(t, folded, raw, folded_norm))
        if hits > best_hits:
            best, best_hits = e, hits
    if not best:
        return None, {}, 0
    return best, extract_fields(best, raw), min(100, 85 + 5 * best_hits)


# ------------------------------------------------------------------ 2. o'xshash savol
# agentlar yozishida tez-tez uchraydigan imlo shakllari -> bitta o'zak (fold va stem'dan keyin)
TYPOS = {"kilent": "klient", "kliyent": "klient", "klent": "klient", "kilient": "klient", "kliet": "klient",
         "kilyent": "klient", "magazn": "magazin", "magazen": "magazin", "zakas": "zakaz", "zakazl": "zakaz",
         "prbs": "prbc", "protagret": "protarget", "protaget": "protarget", "protargit": "protarget",
         "marshurt": "marshrut", "marshirut": "marshrut", "aksya": "aksiya", "aktsiya": "aksiya", "skitka": "skidka",
         "xal": "hal", "korinma": "korin", "korinmay": "korin", "chiqma": "chiq", "chiqmay": "chiq",
         # o/u almashishi va sinonimlar: tochka = nuqta, qushish = qoshish
         "qush": "qosh", "kushish": "qoshish", "koshish": "qoshish", "tochka": "nuqta", "tochk": "nuqta",
         "ttochka": "nuqta", "torgoviy": "nuqta", "torgovaya": "nuqta"}
TYPO_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, TYPOS), key=len, reverse=True)) + r")", re.IGNORECASE)


def toks(text):
    """So'z o'zaklari + imlo shakllarini birlashtirish (kilent -> klient)."""
    return [TYPOS.get(t, t) for t in tokens(TYPO_RE.sub(lambda m: TYPOS[m.group(1).lower()], fold(text or "")))]


def _damerau1(a, b):
    """Bitta harf qo'shilgan/tushgan/almashgan yoki ikki qo'shni harf o'rni almashgan (kilent~klient)."""
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        diff = [i for i in range(la) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    if la > lb:
        a, b = b, a
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def _tok_eq(a, b):
    """Bir xil o'zak: to'liq teng, biri ikkinchisining boshlanishi (≥4 harf) yoki umumiy boshlanish ≥5 harf
    (o'zbekcha qo'shimchalar: tiklayman / tiklash, parolim / parol)."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    if min(len(a), len(b)) >= 5 and _damerau1(a, b):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 5


MAX_TOKENS = 60  # uzun rasm matni (OCR) solishtirishni sekinlashtirmasin


def _dice(a, b):
    if not a or not b:
        return 0
    bset = set(b)
    common = 0
    for x in a:
        if x in bset:
            common += 1
        elif any(y[:1] == x[:1] and _tok_eq(x, y) for y in b):  # imlo farqi — faqat bosh harfi bir xil so'zlar orasida
            common += 1
    return round(100 * 2 * common / (len(a) + len(b)))


def similarity(a_text, b_text):
    """0..100: so'z o'zaklari bo'yicha Dice o'xshashligi (prefiks, imlo xatosi va qo'shimchalarga chidamli)."""
    return _dice(list(dict.fromkeys(toks(a_text))), list(dict.fromkeys(toks(b_text))))


_INDEX = {"key": None, "tok": {}}


def _entry_tokens(entries):
    """Har bir yozuvning savol ko'rinishlari tokenlari — yozuvlar o'zgarmaguncha keshda (har savolda qayta hisoblanmaydi)."""
    key = tuple(sorted((e.pk, e.updated_at.timestamp() if e.updated_at else 0) for e in entries))
    if _INDEX["key"] != key:
        _INDEX["tok"] = {e.pk: [list(dict.fromkeys(toks(q))) for q in [e.title, *(e.questions or [])]] for e in entries}
        _INDEX["key"] = key
    return _INDEX["tok"]


def match_faq(raw, entries):
    """Eng o'xshash yozuv. Teng ballda — savolga so'zma-so'z mos ko'rinish, keyin umumiy so'zlari ko'pi ustun."""
    raw_t = list(dict.fromkeys(toks(raw)))[:MAX_TOKENS]
    target, raw_set = " ".join(raw_t), set(raw_t)
    index = _entry_tokens(entries)
    best, key = None, (0, 0, 0)
    for e in entries:
        for qt in index.get(e.pk) or []:
            s = _dice(raw_t, qt)
            if not s:
                continue
            k = (s, int(" ".join(qt) == target), len(set(qt) & raw_set))
            if k > key:
                best, key = e, k
    return best, key[0]


# ------------------------------------------------------------------ 3. mavjud qoidalar
def rule_answer(raw, lang):
    res = run_search(raw[:500], 3, lang)
    people = res.get("people") or []
    conf = people[0]["confidence"] if people else 0
    task = None
    if res.get("tasks"):
        task = Task.objects.filter(id=res["tasks"][0]["id"]).select_related("owner", "process__zone").first()
    resp = []
    ids = [p["member"] for p in people[:2]]
    for m in Member.objects.filter(id__in=ids).prefetch_related("contacts"):
        resp.append(_person(m))
    resp.sort(key=lambda r: ids.index(r["id"]) if r.get("id") in ids else 9)
    return task, conf, resp


def team_telegrams(m):
    """Jamoa a'zolarining Telegram'lari: jamoa kontaktlari (Ulug'bek...) va jamoaga qo'shilgan yakka xodimlar
    (Kamoliddin, Timur — «Jamoa a'zosi»)."""
    tgs = [c.telegram.lstrip("@") for c in m.contacts.all() if c.telegram]
    if m.pk:
        tgs += [x.telegram.lstrip("@") for x in Member.objects.filter(member_of=m).exclude(telegram="").order_by("order", "id")]
    return list(dict.fromkeys(tgs))


def _person(m):
    """Mas'ul: jamoa bo'lsa — jamoa nomi va a'zolarining Telegram'lari (ish bo'linmaydi, kim bo'sh bo'lsa oladi)."""
    tgs = team_telegrams(m) if m.is_team else []
    if m.telegram:
        tgs.insert(0, m.telegram.lstrip("@"))
    return {"id": m.id, "name": m.name, "role": m.role, "level": m.level, "telegram": tgs[:6], "is_team": m.is_team,
            "contact": getattr(m, "contact_id", None)}


# ------------------------------------------------------------------ 4. AI
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "confidence": {"type": "number"},
        "needs_human": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["answer", "confidence", "needs_human", "reason"],
    "additionalProperties": False,
}

AI_SYSTEM = """Sen {company} kompaniyasining Telegram support guruhidagi yordamchisisan. Savollar asosan agentlar,
supervayzerlar va operatorlardan: 1C, PRBC, ProTarget mobil ilovasi, klient (savdo nuqtasi) qo'shish, marshrut,
dostup. Faqat quyida berilgan TASDIQLANGAN JAVOBLAR va QOIDALARga tayan. Bilmagan narsangni o'ylab topma.

Qoidalar:
- Javob qisqa, aniq, xushmuomala; 2-6 qator; kerak bo'lsa raqamlangan qadamlar.
- Savol tilida javob ber (o'zbekcha savolga o'zbek lotin, ruscha savolga rus).
- Rasm matni (OCR) xato o'qilgan bo'lishi mumkin — faqat aniq ko'ringan kod/holatlarga tayan.
- Savol o'zbek lotin/kirill, yangi alifbo (ş, ç, ō) yoki ruscha bo'lishi mumkin; imlo xatolarini tushun.
- Eng yaqin tasdiqlangan javob savolga mos kelsa — o'shani asos qilib, savolga moslab tushunarli javob yoz. Uning muhim
  bandlarini (muddat, nima tekshiriladi, nima yuborish kerak, natija qayerda ko'rinadi) TASHLAB KETMA — qisqartirma.
- Ma'lumot yetarli bo'lmasa yoki shaxsiy/moliyaviy qaror kerak bo'lsa: needs_human=true, confidence past.
- Kim hal qilishini aytsang — faqat MAS'ULLAR ro'yxatidagi odam/jamoa nomini ayt. Ro'yxatda yo'q rol yoki bo'limni
  ("operator", "menejer", "buxgalteriya" va h.k.) O'YLAB TOPMA; bilmasang — mas'ulni aytma, needs_human=true.
- SAVOL BERUVCHI rolini hisobga ol: agentga — "supervayzeringizga murojaat qiling" kabi; supervayzer yoki rahbarning
  o'ziga "supervayzeringizga yozing" dema — u bajaradigan amalni ayt.
- Agentga HECH QACHON faqat "qayta tekshiring / проверьте / tekshirib ko'ring" deb javob berma: bu xodim ishni o'zi
  bajarib bo'lgach aytadigan gap. So'rov xodim amalini talab qilsa (aksiya/skidka yoqish, marshrut, perechisleniye,
  limit, dostup) — kim bajarishini (MAS'ULLAR ro'yxatidan) ayt va kerakli ma'lumotni (nuqta kodi, nomi) so'ra.
- EKRANDAGI QIZIL XATO XABARI berilgan bo'lsa — bu eng muhim belgi: javobni aynan shu xabar sababiga qarab ber
  (ekrandagi boshqa so'zlar — menyu, to'lov turlari, tugmalar — sabab emas).
- confidence: 0..1 — javob aynan shu savolga to'g'ri ekaniga ishonching."""


def ai_quota_left(settings):
    since = timezone.now() - timezone.timedelta(days=1)
    used = AIUsage.objects.filter(task=AITaskConfig.SUPPORT, at__gte=since).count()
    return max(0, settings.ai_daily_limit - used)


_PEOPLE = {"at": 0.0, "text": ""}


def people_text():
    """Mas'ullar ro'yxati (zona): ism, lavozim, bo'lim, qaysi savollar — AI rolni to'g'ri aytishi uchun (10 daqiqa kesh)."""
    import time as _t
    if _t.monotonic() - _PEOPLE["at"] < 600 and _PEOPLE["text"]:
        return _PEOPLE["text"]
    rows = []
    for m in Member.objects.select_related("department").exclude(level="EXT").order_by("name")[:40]:
        bits = [m.role, m.department.name if m.department_id else "", f"savollar: {m.trigger}" if m.trigger else ""]
        rows.append(f"- {m.name}{' (jamoa)' if m.is_team else ''}: " + "; ".join(b for b in bits if b))
    _PEOPLE.update(at=_t.monotonic(), text="\n".join(rows))
    return _PEOPLE["text"]


AI_LIVE_SECONDS = 25


def ai_answer(raw, lang, context_entries, rule_task, settings, ocr="", image_entries=(), asker="", history="", alert=""):
    """AI javobi o'zimizning ma'lumotlarga tayanadi: bilim bazasidagi eng yaqin javoblar, rasmdan tanilgan ekranlar,
    xodimlarning o'xshash savollarga bergan haqiqiy javoblari (misol sifatida) va qoida."""
    from zona import conf
    from zona.ai import service as ai
    from zona.ai.providers import AIError

    if not settings.ai_enabled or ai_quota_left(settings) <= 0:
        return None
    ctx, seen = [], set()
    for e in [*image_entries, *context_entries][:6]:
        if e.pk in seen:
            continue
        seen.add(e.pk)
        ans = e.answer_ru if lang == "ru" and e.answer_ru else e.answer
        tag = " (RASMDAN TANILGAN EKRAN)" if e in image_entries else ""
        ctx.append(f"- SAVOL{tag}: {e.title}\n  JAVOB: {ans[:800]}")
    if rule_task is not None and rule_task.rule:
        ctx.append(f"- QOIDA ({rule_task.title}): {rule_task.rule[:600]}")
    examples = staff_examples(raw)
    people = people_text()
    system = AI_SYSTEM.format(company=conf.get("COMPANY_NAME")) + "\n\nTASDIQLANGAN JAVOBLAR VA QOIDALAR:\n" + (
        "\n".join(ctx) or "(hozircha yo'q)")
    if people:
        system += "\n\nMAS'ULLAR (faqat shulardan ayt):\n" + people
    owner = owner_line(raw, ocr)
    if owner:
        system += "\n\n" + owner
    if asker:
        system += f"\n\nSAVOL BERUVCHI: {asker}"
    if examples:
        system += ("\n\nXODIMLARIMIZNING O'XSHASH SAVOLLARGA BERGAN HAQIQIY JAVOBLARI (uslub va mazmun uchun namuna; "
                   "kompaniya amaliyotini shulardan o'rgan):\n" + "\n".join(f"- SAVOL: {q}\n  XODIM JAVOBI: {a}" for q, a in examples))
    tongue = "faqat RUS tilida" if lang == "ru" else "faqat O'ZBEK (lotin) tilida"
    message = f"JAVOB TILI: {tongue} (savol shu tilda)."
    if history:
        # bitta mavzu bo'yicha butun suhbat: odam bir nechta xabarda yozgan (matn, rasm, lokatsiya, aniqlashtirish)
        message += ("\n\nSUHBAT (shu odam bilan shu mavzu bo'yicha, eskidan yangiga). Butun suhbatni tushunib, "
                    "OXIRGI xabarga javob ber; oldin aytilganni takrorlama:\n" + history[-3000:])
    message += f"\n\nSAVOL:\n{raw[:2000]}"
    if alert:
        message += f"\n\nEKRANDAGI QIZIL XATO XABARI (eng muhim — javob shu sababga):\n{alert[:500]}"
    if ocr:
        message += f"\n\nRASMDAGI MATN (OCR, xato o'qilgan bo'lishi mumkin):\n{ocr[:1500]}"
    from zona.ai.providers import deadline
    try:
        # guruhdagi odam kutyapti: AI (zaxira modellar bilan birga) ko'pi bilan AI_LIVE_SECONDS — keyin odamga uzatiladi
        with deadline(AI_LIVE_SECONDS):
            data, meta = ai.run(AITaskConfig.SUPPORT, None, raw[:200], system, message, AI_SCHEMA)
    except AIError:
        return None
    conf_pct = round(100 * max(0.0, min(1.0, float(data.get("confidence") or 0))))
    return {"text": str(data.get("answer") or "").strip(), "confidence": conf_pct,
            "needs_human": bool(data.get("needs_human")), "reason": str(data.get("reason") or "")[:300], "meta": meta}


# ------------------------------------------------------------------ yig'ish
def decide(raw, lang="uz", allow_unapproved=False, image=None, text=None, ocr="", images=None, fast=False,
           asker="", history="", alert="", leader=False, live=False):
    """Savol -> Decision (_decide) + toifa mas'uli: masalan, barcha aksiya savollari — operatorga (category_owners).

    alert — skrinshotdagi QIZIL xato yozuvi (ocr.red_text): ekrandagi boshqa so'zlardan ustun.
    leader — savol beruvchi o'zi supervayzer/rahbar: unga "supervayzeringizga yozing" degan javob berilmaydi
    (AI uning o'zi bajaradigan amalni aytadi; bo'lmasa — xodimga uzatiladi)."""
    d = _decide(raw, lang, allow_unapproved, image, text, ocr, images, fast, asker, history, alert)
    if d is None:
        return live_prbc(None, raw, text, ocr, lang) if live else None
    if leader and not d.needs_human and needs_supervisor(d):
        if fast:
            return None  # AI kerak — sekin yo'lda
        d = _for_leader(d, raw, lang, text, ocr, asker, history, alert)
    if not d.needs_human and status_reply(d.text):
        # "Проверьте", "qayta tekshiring" — agentga javob emas: so'rovni bajaradigan mas'ulga uzatiladi (belgilanadi)
        d.needs_human, d.note = True, ("javob faqat holat xabari — mas'ulga uzatildi. " + d.note)[:300]
    apply_owner(d, text if text is not None else raw, ocr)
    return live_prbc(d, raw, text, ocr, lang) if live else d


def live_prbc(d, raw, text, ocr, lang):
    """Savolda/skrinshotda mijozning STIR, JShShIR yoki 1C kodi bo'lsa — arizaning PRBC'dagi haqiqiy holati (prbc.outlets).

    Bazadagi standart javob (shablon, ekran, o'xshash savol) bo'lsa — holat kartasi uning ustiga qo'shiladi; javob
    topilmagan yoki faqat AI/qoida bo'lsa — javob shu karta (aniq ma'lumot taxmindan ustun). PRBC o'chiq, javob bermadi
    yoki ariza topilmadi — avvalgi qaror o'zgarmaydi."""
    import logging
    try:
        from prbc import outlets
        card, ids = outlets.status_for("\n".join(x for x in (text, ocr) if x) or raw, lang)
    except Exception:  # noqa: BLE001 — jonli holat qo'shimcha: xatosi javobni to'xtatmasin
        logging.getLogger("support").exception("PRBC jonli holat")
        return d
    if not card:
        return d
    note = "PRBC jonli holat: " + ", ".join(ids)
    if d is not None and not d.needs_human and d.text and d.stage in ("template", "image", "faq") and not d.parts:
        d.text, d.live = f"{card}\n\n{d.text}", card
        d.note = (note + ". " + d.note)[:300]
        return d
    resp = list(d.responsible) if d is not None else []
    return Decision("prbc", None, 100, card, False, resp, live=card, note=note)


LEADER_ROLES = ("SVR", "RSM", "ASM", "ROP")


def is_leader(user):
    """Savol beruvchi supervayzer yoki undan yuqori rahbarmi (kontaktlardagi dala xodimi roli bo'yicha)."""
    sp = user.staff_person if user is not None and user.staff_person_id else None
    return bool(sp and sp.role in LEADER_ROLES)


def _for_leader(d, raw, lang, text, ocr, asker, history, alert=""):
    """Supervayzerga supervayzerni ko'rsatuvchi javob o'rniga: AI shu yozuv asosida uning o'zi nima qilishini aytadi.
    AI ham supervayzerga yo'naltirsa yoki ishonmasa — odam javob beradi (savol ochiq qolmaydi, eslatmalar bor)."""
    settings = Settings.load()
    ctx = [d.entry] if d.entry is not None else []
    who = (asker or "supervayzer") + " — U O'ZI SUPERVAYZER/RAHBAR: uni supervayzerga yo'naltirma"
    ai = ai_answer(text if text is not None and substantive(text) else raw, lang, ctx, None, settings, ocr=ocr,
                   asker=who, history=history, alert=alert)
    if (ai and ai["text"] and not ai["needs_human"] and ai["confidence"] >= settings.ai_min_confidence
            and not SUPERVISOR_HINT.search(ai["text"])):
        return Decision("ai", d.entry, ai["confidence"], ai["text"], False, d.responsible,
                        note=("savol beruvchi supervayzer. " + ai["reason"])[:300])
    resp = [r for r in d.responsible if not SUPERVISOR_HINT.search(r.get("name") or "")]
    return Decision("", d.entry, d.confidence, d.text, True, resp,
                    note="savol beruvchi supervayzer — supervayzerga yo'naltiruvchi javob berilmadi, xodimga uzatildi")


class _NoContacts:
    @staticmethod
    def all():
        return []


class ContactOwner:
    """Jamoa a'zosi (TeamContact: Guzel, Eldar...) mas'ul sifatida — Member o'rnida ishlatiladi (ism, Telegram, lavozim)."""

    is_team = False
    contacts = _NoContacts()

    def __init__(self, c):
        self.contact, self.contact_id, self.id, self.pk = c, c.pk, None, None
        self.name = c.name
        self.role = c.role or (c.member.role if c.member_id else "")
        self.level = c.member.level if c.member_id else ""
        self.telegram = c.telegram or ""
        self.team = c.member if c.member_id else None

    def __eq__(self, other):
        return isinstance(other, ContactOwner) and other.contact_id == self.contact_id

    def __hash__(self):
        return hash(("contact", self.contact_id))


def owner_of(value):
    """Settings.category_owners qiymati: 12 (xodim) yoki "c:34" (jamoa a'zosi) -> Member / ContactOwner / None."""
    from zona.models import TeamContact
    if isinstance(value, str) and value.startswith("c:") and value[2:].isdigit():
        c = TeamContact.objects.select_related("member").filter(pk=int(value[2:])).first()
        return ContactOwner(c) if c else None
    if value and str(value).isdigit():
        return Member.objects.filter(pk=int(value)).prefetch_related("contacts").first()
    return None


def category_owner(category, settings=None):
    """Toifa uchun belgilangan mas'ul (Settings.category_owners: {"promo": 12 yoki "c:34"}) yoki None."""
    s = settings or Settings.load()
    return owner_of((s.category_owners or {}).get(category or ""))


def category_backup(category, settings=None):
    """Toifaning zaxira mas'uli (Settings.category_backups) — asosiy bilan bir xil bo'lsa None."""
    s = settings or Settings.load()
    raw = (s.category_backups or {}).get(category or "")
    if not raw or raw == (s.category_owners or {}).get(category or ""):
        return None
    return owner_of(raw)


def owner_tags(resp, lang="uz", limit=3):
    """Javobda belgilanadigan mas'ul(lar): «@asosiy» yoki «@asosiy · zaxira: @zaxira»."""
    if not resp or not resp[0].get("telegram"):
        return ""
    out = " ".join("@" + t for t in resp[0]["telegram"][:limit])
    b = resp[0].get("backup") or {}
    extra = [t for t in (b.get("telegram") or [])[:limit] if t not in resp[0]["telegram"]]
    if extra:
        out += (" · запасной: " if lang == "ru" else " · zaxira: ") + " ".join("@" + t for t in extra)
    return out


def owner_line(text, ocr=""):
    """AI uchun: savol toifasining mas'uli bo'lsa — faqat u; agent zaxiradagi odamlarga yo'naltirilmaydi
    (mas'ul hal qila olmasa, o'zi keyingi navbatdagiga uzatadi)."""
    from .systems import detect
    cat = detect(text or "", ocr or "")["category"]
    m = category_owner(cat)
    if m is None:
        return ""
    tg = f" (@{m.telegram.lstrip('@')})" if m.telegram else ""
    b = category_backup(cat)
    if b is not None:
        tg += f" yoki zaxira — {b.name}" + (f" (@{b.telegram.lstrip('@')})" if b.telegram else "")
    return (f"BU SAVOLNING MAS'ULI — FAQAT {m.name}{tg}. Savol beruvchini boshqa odam yoki jamoaga (dasturchi, "
            f"supervayzer, Pro-target, zaxiradagi mas'ullar) YO'NALTIRMA va \"ular tekshiradi\" kabi bosqichlarni yozma: "
            f"{m.name} o'zi hal qiladi, hal qila olmasa — kerakli odamga o'zi uzatadi.")


def apply_owner(d, text, ocr=""):
    """Toifa mas'uli belgilangan bo'lsa — javobdagi mas'ul, @belgilash va vazifa ijrochisi faqat u (supervayzer/dasturchi emas)."""
    s = Settings.load()
    if not s.category_owners:
        return d
    from .systems import detect
    cat = detect(text or "", ocr or "", d.entry.title if d.entry is not None else "")["category"]
    m = category_owner(cat, s)
    if m is not None:
        main = _person(m)
        b = category_backup(cat, s)
        if b is not None:
            main["backup"] = _person(b)  # aralash ishlar (aksiya): zaxira mas'ul ham belgilanadi
        d.responsible, d.owner = [main], True
    return d


def _decide(raw, lang="uz", allow_unapproved=False, image=None, text=None, ocr="", images=None, fast=False,  # noqa: C901
            asker="", history="", alert=""):
    """Savol -> Decision. allow_unapproved: soya rejimida ko'rib chiqilayotgan shablonlar ham.

    image: (yozuv, ishonch) yoki images: [(yozuv, ishonch, rasm_tartibi), ...] — rasm turi o'rgatilgan namunadan tanilgan.
    text/ocr: savol matni va rasm matni alohida. Xodim aniq savol yozgan bo'lsa (substantive) — javob MATN bo'yicha tanlanadi
    (rasm bilan ham, rasmsiz ham bir xil javob), rasm va OCR qo'shimcha kontekst bo'ladi. Matn bo'sh/umumiy bo'lsa
    ("ko'rib bering") — rasm hal qiladi; albomda turli ekranlar bo'lsa — har biriga javob.
    fast=True — AI'gacha bo'lgan bosqichlarda topilmasa None qaytaradi (OCR'siz tez urinish uchun)."""
    settings = Settings.load()
    if text is None:
        text = raw
    if not (ocr or "").strip() and not images and not image and greeting_only(text):
        # faqat salom — bilim bazasidan javob tanlanmaydi (salom savol ko'rinishiga o'xshab qolmasin)
        return Decision("", None, 0, "", True, [], note="faqat salomlashuv — savol emas")
    ocr = fix_homoglyphs(ocr)  # saqlangan eski OCR'da ham: "отправлена Ha модерацию"
    strong_text = substantive(text)
    imgs = list(images or ([(image[0], image[1], 0)] if image and image[0] is not None else []))
    statuses = [Entry.APPROVED, Entry.REVIEW, Entry.NEW] if allow_unapproved else [Entry.APPROVED]
    entries = list(Entry.objects.filter(status__in=statuses))
    templates = [e for e in entries if e.kind == Entry.TEMPLATE]
    # standart holatlar savol ko'rinishlari bo'yicha ham topiladi (shartlari bo'lmasa ham)
    faqs = [e for e in entries if e.kind == Entry.FAQ or (e.kind == Entry.TEMPLATE and e.questions)]

    def own(e):
        return [_person(e.responsible)] if e.responsible_id else []

    def image_decision(e, conf_):
        fields = extract_fields(e, raw)
        return Decision("image", e, conf_, render_answer(e, fields, lang), False, own(e), fields, e.status != Entry.APPROVED)

    distinct = []
    for e, c, idx in sorted(imgs, key=lambda x: -x[1]):
        if e is not None and all(e.pk != d[0].pk for d in distinct):
            distinct.append((e, c, idx))
    if distinct and not strong_text and ocr:
        # ekranlar bir-biriga o'xshash bo'lishi mumkin (ProTarget xato oynalari: bir xil belgi va tugma), lekin ekrandagi
        # matn aniq boshqa holatni aytsa ("Token has been expired" ≠ "Inactive user account") — matn hal qiladi
        te, tfields, tconf = match_template(ocr, templates)
        if te and all(te.pk != x[0].pk for x in distinct):
            return Decision("template", te, tconf, render_answer(te, tfields, lang), False, own(te), tfields,
                            te.status != Entry.APPROVED, note="ekrandagi matn (OCR) rasm o'xshashligidan ustun")
    if distinct and ocr:
        # siyrak ekran (o'rtada bitta belgi va 1-2 qator matn) rasm xeshi bo'yicha boshqa siyrak ekranga o'xshab ketadi:
        # "Tasdiq kutilmoqda" ≠ "Request was throttled". Ekrandagi matn shablonga umuman aloqasi yo'q bo'lsa — rasmga ishonilmaydi
        distinct = [x for x in distinct if not ocr_contradicts(x[0], ocr)]
    if alert and len(meaningful(alert)) >= 2 and not (strong_text and match_template(text, templates)[0]):
        # skrinshotdagi QIZIL xato yozuvi — eng aniq belgi ("Для данной ТТ не найдены активные маршруты доставки"):
        # ekrandagi boshqa so'zlar (to'lov turlari, menyu) emas, shu xabar bo'yicha javob
        te, tfields, tconf = match_template(alert, templates)
        if te:
            tfields = extract_fields(te, raw)
            return Decision("template", te, tconf, render_answer(te, tfields, lang), False, own(te), tfields,
                            te.status != Entry.APPROVED, note="qizil xato yozuvi: " + alert[:120])
        fe, fscore = match_faq(alert, faqs)
        if fe and fscore >= settings.faq_threshold:
            return Decision("faq", fe, fscore, render_answer(fe, {}, lang), False, own(fe), {}, fe.status != Entry.APPROVED,
                            note="qizil xato yozuvi: " + alert[:120])
    if strong_text and (ocr or distinct) and match_template(text, templates)[0] is None:
        info = info_screen(ocr, distinct, templates)
        if info:
            # ma'lumot ekrani ("Торговая точка ... отправлена на модерацию!"): ekranning o'zi javob — imzodagi
            # "Qo'shib bering, Navoiy SRZ" kabi iltimos boshqa savol emas (nuqtani Pro-target tasdiqlaydi, o'zi qo'shiladi).
            # Matn boshqa savolga aniq mos kelsa (bilim bazasidagi savol-javob) — matn ustun.
            ie, iconf, how = info
            fe, fscore = match_faq(text, faqs)
            if not fe or fe.pk == ie.pk or fscore < settings.faq_threshold:
                fields = extract_fields(ie, raw)
                return Decision(how, ie, iconf, render_answer(ie, fields, lang), False, own(ie), fields,
                                ie.status != Entry.APPROVED, note="ma'lumot ekrani: imzodagi iltimos ekran holatini so'raydi")
    if strong_text and ocr and match_template(text, templates)[0] is None:
        # matn — umumiy alomat ("zakaz o'tmayapti"), ekrandagi xabar esa aniq sababni aytadi ("Заказ не оформлен:
        # на складе недостаточно остатка") — aniq holat shabloni ustun (matn shu mavzuda bo'lsa: umumiy so'z bor)
        te, tfields, tconf = match_template(ocr, templates)
        if te and tconf >= 95:
            topic = set(toks(" ".join([te.title, *(te.triggers or []), *(te.questions or [])])))
            if set(toks(text)) & topic:
                tfields = extract_fields(te, raw)
                return Decision("template", te, tconf, render_answer(te, tfields, lang), False, own(te), tfields,
                                te.status != Entry.APPROVED, note="ekrandagi aniq xabar (OCR) umumiy matndan ustun")
    if distinct:
        if strong_text:
            # matn hal qiladi: shu matnga eng mos tanilgan ekran yoki (agar matn boshqa narsani so'rasa) matn bo'yicha javob
            rel = sorted(((max(similarity(text, q) for q in [e.title, *(e.questions or [])]), e, c) for e, c, _i in distinct),
                         key=lambda x: -x[0])
            t_e, t_score = match_faq(text, faqs)
            t_score = t_score if t_e else 0
            if rel[0][0] >= 40 and rel[0][0] + 5 >= t_score:
                return image_decision(rel[0][1], rel[0][2])
        elif len(distinct) == 1:
            return image_decision(distinct[0][0], distinct[0][1])
        else:
            parts = []
            for e, c, idx in sorted(distinct, key=lambda x: x[2]):
                head = f"🖼 Фото {idx + 1} — {e.title}" if lang == "ru" else f"🖼 {idx + 1}-rasm — {e.title}"
                parts.append(f"{head}\n{render_answer(e, extract_fields(e, raw), lang)}")
            best = distinct[0]
            return Decision("image", best[0], min(c for _e, c, _i in distinct), "\n\n".join(parts), False, own(best[0]), {},
                            any(e.status != Entry.APPROVED for e, _c, _i in distinct),
                            note="albom: " + ", ".join(f"{i + 1}-rasm→#{e.pk}" for e, _c, i in distinct),
                            parts=[(i, e, c) for e, c, i in sorted(distinct, key=lambda x: x[2])])

    # aniq matnli savolda shablon va bazadan qidiruv faqat matn bo'yicha (uzun rasm matni javobni chalg'itmasin)
    qtext = text if strong_text else raw
    e, fields, conf = match_template(qtext, templates)
    if e:
        return Decision("template", e, conf, render_answer(e, fields, lang), False, own(e), fields,
                        e.status != Entry.APPROVED)

    e, score = match_faq(qtext, faqs)
    faq_ok = bool(e) and score >= settings.faq_threshold
    ai_first = settings.ai_enabled and settings.ai_primary and not (faq_ok and score >= settings.ai_primary_below)
    if faq_ok and not ai_first:
        return Decision("faq", e, score, render_answer(e, {}, lang), False, own(e), {}, e.status != Entry.APPROVED)
    if fast:
        return None

    # qidiruvga faqat savolning boshi (uzun rasm matni qidiruvni sekinlashtiradi, mas'ulni aniqlashga qo'shmaydi)
    query = qtext.strip()[:200]
    task, rule_conf, resp = rule_answer(query, lang) if query else (None, 0, [])
    if rule_conf < settings.route_threshold:
        # qoida ishonchsiz mos keldi — uning mas'uli (boshqa bo'lim xodimi) savolga biriktirilmaydi va belgilanmaydi
        resp = []
    raw_t = list(dict.fromkeys(toks(alert + " " + qtext if alert else qtext)))[:MAX_TOKENS]
    index = _entry_tokens(faqs)
    ranked = sorted(faqs, key=lambda x: -max((_dice(raw_t, qt) for qt in index.get(x.pk) or []), default=0))
    approved_ctx = [x for x in ranked if x.status == Entry.APPROVED]

    ai = None
    if ai_first:
        # AI asosiy: javobni bilim bazasidagi eng yaqin javoblar va qoidaga tayanib tuzadi (Claude; zaxira — Gemini)
        ai = ai_answer(qtext, lang, approved_ctx, task, settings, ocr=ocr if strong_text else "",
                       image_entries=[d[0] for d in distinct], asker=asker, history=history, alert=alert)
        if ai and ai["text"] and not ai["needs_human"] and ai["confidence"] >= settings.ai_min_confidence:
            top = e if faq_ok else None
            return Decision("ai", top, ai["confidence"], ai["text"], False, own(top) if top else resp, note=ai["reason"])
    if faq_ok:
        return Decision("faq", e, score, render_answer(e, {}, lang), False, own(e), {}, e.status != Entry.APPROVED)
    if task is not None and task.rule and rule_conf >= settings.route_threshold:
        return Decision("rule", None, rule_conf, rule_text(task, lang), False, resp, note=f"task:{task.id}")
    if ai is None:
        ai = ai_answer(qtext, lang, approved_ctx, task, settings, ocr=ocr if strong_text else "",
                       image_entries=[d[0] for d in distinct], asker=asker, history=history, alert=alert)
        if ai and ai["text"] and not ai["needs_human"] and ai["confidence"] >= settings.ai_min_confidence:
            return Decision("ai", None, ai["confidence"], ai["text"], False, resp, note=ai["reason"])
    d = Decision("", None, max(score, rule_conf), "", True, resp)
    if ai:
        d.note = f"AI ishonchi past ({ai['confidence']}%): {ai['reason']}"
        d.text = ai["text"]  # admin uchun qoralama sifatida ko'rsatiladi
    return d


def followup(raw, lang, history, asker="", previous=""):
    """Bitta mavzu bo'yicha davom xabari (bot javob bergan, odam yana yozdi): shablon/baza o'sha javobni takrorlaydi —
    shuning uchun to'g'ridan-to'g'ri AI, butun suhbat bilan. AI ishonmasa — odamga (needs_human)."""
    settings = Settings.load()
    faqs = [e for e in Entry.objects.filter(status=Entry.APPROVED)
            if e.kind == Entry.FAQ or (e.kind == Entry.TEMPLATE and e.questions)]
    raw_t = list(dict.fromkeys(toks(raw)))[:MAX_TOKENS]
    index = _entry_tokens(faqs)
    ranked = sorted(faqs, key=lambda x: -max((_dice(raw_t, qt) for qt in index.get(x.pk) or []), default=0))
    task, _rc, resp = rule_answer(raw.strip()[:200], lang) if raw.strip() else (None, 0, [])
    if _rc < settings.route_threshold:
        resp = []
    ai = ai_answer(raw, lang, ranked, task, settings, asker=asker, history=history)
    resp = apply_owner(Decision("", None, 0, "", True, resp), raw).responsible
    if (ai and ai["text"] and not ai["needs_human"] and ai["confidence"] >= settings.ai_min_confidence
            and " ".join(ai["text"].split()) != " ".join((previous or "").split())):
        return Decision("ai", None, ai["confidence"], ai["text"], False, resp, note=ai["reason"])
    d = Decision("", None, 0, "", True, resp)
    if ai:
        d.note = f"AI ishonchi past ({ai['confidence']}%): {ai['reason']}"
        d.text = ai["text"]
    return d


FILLER_TEXT = ("korib bering ko'rib ber iltimos yordam bering qiling qilib shu bu mana nima qilay qilish kerak qanday "
               "savol rasm skrin screenshot qarab qara bering beringlar aka opa uka brat pomogite posmotrite pojaluysta "
               "eto vot chto delat kak help please tekshirib tekshiring muammo problema oshibka xato xatolik "
               "dobavte dobavit pjl pls plz pozhaluysta pojalusta srochno tezroq tez iltimos qarang qarab bering "
               "sdelayte sdelat proverte reshite hal qiling qilvoring qilib bering qivoring")
_FILLER: set = set()


def meaningful(text):
    """Mazmunli so'zlar (umumiy/iltimos so'zlari, salomlashuv va raqamlarsiz)."""
    if not _FILLER:
        _FILLER.update(toks(FILLER_TEXT))
        _FILLER.update(toks(" ".join(GREETING)))
    text = re.sub(r"@\w+", " ", text or "")  # "@StargroupSaid нима бовоти" — murojaat (kimga), savol mazmuni emas
    return [w for w in dict.fromkeys(toks(text)) if w not in _FILLER and len(w) >= 2 and not w.isdigit()]


OCR_GENERIC = {"prbc", "protarget", "x", "orqaga", "назад"}  # ilova sarlavhasi — holat haqida hech narsa demaydi


def ocr_contradicts(e, ocr):
    """Rasm o'xshashligi bo'yicha tanilgan SHABLON ekrandagi matnga zid: ekran siyrak (2-15 mazmunli so'z — o'qish oson,
    xesh esa ishonchsiz), shablon shartlaridan birortasi ham yo'q va matnda shablon mavzusidan bitta so'z ham yo'q.
    Tarixdagi ~750 ta rasm javobida faqat xato deb belgilanganlarini rad etadi."""
    if e.kind != Entry.TEMPLATE or not e.triggers:
        return False
    words = [w for w in meaningful(ocr) if w not in OCR_GENERIC]
    if not (2 <= len(words) <= 15):
        return False
    if match_template(ocr, [e])[0] is not None:
        return False
    topic = set(toks(" ".join([e.title, *(e.triggers or []), *(e.questions or []), e.answer or "", e.answer_ru or ""])))
    return not (set(toks(" ".join(words))) & topic)


def info_screen(ocr, distinct, templates):
    """Rasm — ma'lumot ekrani (yozuvda auto_close > 0: "nuqta moderatsiyaga yuborildi"): (yozuv, ishonch, bosqich) yoki None.
    Avval ekrandagi matn (OCR) bo'yicha, bo'lmasa rasm o'xshashligi bo'yicha."""
    if ocr:
        te, _f, tconf = match_template(ocr, templates)  # ekrandagi eng mos holat ma'lumot xabari bo'lsagina
        if te and te.auto_close:
            return te, tconf, "template"
    for e, c, _i in distinct or []:
        if e.auto_close:
            return e, c, "image"
    return None


def substantive(text):
    """Xodim aniq savol yozganmi (kamida 2 ta mazmunli so'z), yoki faqat "ko'rib bering" kabi umumiy so'zlarmi."""
    return len(meaningful(text)) >= 2


# ------------------------------------------------------------------ o'rganish filtri (bilim bazasiga nomzod)
# Salomlashuv, "тоже самое", "почему так", "vot shu" — savol mazmuni emas: bular nomzod bo'lsa, bot salomga ham
# birovning holatiga yozilgan javobni qaytaradi. Faqat o'rganishda ishlatiladi (javob berish oqimiga ta'sir qilmaydi).
LEARN_STOP_TEXT = ("assalom assalomu asalom aleykum alaykum alekum aleykim yaxshimisiz yaxshimisizlar qalaysiz "
                   "salomatmisiz xayrli hayrli kun tong kech dobriy dobroe dobrogo den dnya utro vecher zdravstvuyte "
                   "privet tut toje samoe samoye tak pochemu vot shu mana bu ham xuddi bunda bunaqa takoy takaya "
                   "здравствуйте добрый доброе день утро вечер привет тут тоже самое так почему вот это такой такая "
                   "ассалом ассалому алейкум алайкум яхшимисиз шу мана бу хам худди")
_LEARN_STOP: set = set()
_DONE_RX = re.compile(r"готов|сделал|исправил|подключ|отвязал|привязал|переподключ|добавил|включил|"
                      r"tuzatil|to.g.rila|qo.sh(dim|ildi)|ulan(di|dim)|uladim|yoq(dim|ildi)|bo.ldi|tayyor|✅", re.I)
_BOT_HANDOFF_RX = re.compile(r"bu so.rovni .{1,80} bajaradi|этот запрос выполняет|so.rovingiz .{1,80} yetkazildi|"
                             r"запрос передан|so.rov unga yuborildi", re.I)


def learnable_question(text):
    """Savoldan o'rganish mumkinmi: mijoz nomi, kod, hudud ("Нукус к3"), @murojaat va havola olib tashlangach
    salomlashuv/«тоже самое»/«почему так» dan tashqari kamida 2 ta mazmunli so'z qolishi kerak."""
    from .dedupe import generic_phrase
    g = generic_phrase(text or "")
    if not g or greeting_only(g):
        return False
    if not _LEARN_STOP:
        _LEARN_STOP.update(toks(LEARN_STOP_TEXT))
    return len([w for w in meaningful(g) if w not in _LEARN_STOP]) >= 2


def learnable_answer(text):
    """Javob bilim bo'ladimi: aniq holatga yozilgan qisqa «bajarildi» ("Готово", "отвязала, переподключите",
    "Tuzatildi ✅") va botning o'z uzatish matni ("Bu so'rovni … bajaradi") — nomzod emas."""
    t = (text or "").strip()
    if not t or _BOT_HANDOFF_RX.search(t):
        return False
    return not (len(t) <= 60 and _DONE_RX.search(t))


_STAFF = {"key": None, "rows": []}


def staff_examples(query, k=3, min_score=35):
    """Xodimlarning o'xshash savollarga bergan haqiqiy javoblari (oxirgi 1500 ta) — AI'ga namuna sifatida.
    Kesh: yangi xodim javobi kelmaguncha qayta o'qilmaydi."""
    from django.db.models import Count, Max

    from .models import Message
    agg = Message.objects.filter(kind=Message.STAFF, question__isnull=False).aggregate(n=Count("id"), m=Max("id"))
    key = (agg["n"], agg["m"])
    if _STAFF["key"] != key:
        rows = []
        for m in (Message.objects.filter(kind=Message.STAFF, question__isnull=False, question__kind=Message.QUESTION)
                  .select_related("question").order_by("-id")[:1500]):
            qt = (m.question.text or m.question.ocr_text[:300]).strip()
            if len(m.text.strip()) < 12 or not qt or not_an_answer(m.text):
                continue  # "Проверьте", "Готово", "Eldar можете помочь" — namuna emas (AI agentga shuni takrorlamasin)
            rows.append((list(dict.fromkeys(toks(qt)))[:MAX_TOKENS], qt[:300], m.text.strip()[:500]))
        _STAFF["rows"], _STAFF["key"] = rows, key
    qt = list(dict.fromkeys(toks(query or "")))[:MAX_TOKENS]
    if not qt:
        return []
    scored = sorted(((_dice(qt, t), q, a) for t, q, a in _STAFF["rows"]), key=lambda x: -x[0])
    out, seen = [], set()
    for s, q, a in scored:
        if s < min_score or len(out) >= k:
            break
        if a not in seen:
            seen.add(a)
            out.append((q, a))
    return out


def allowed(d, settings):
    """Bot bu javobni chatga yozadimi (aks holda — o'rganish rejimi: "qabul qilindi", xodim javob beradi).
    Yozuvdagi answer_mode umumiy sozlamadan ustun: on — har doim, off — hech qachon."""
    e = d.entry
    if e is not None and e.answer_mode == "on":
        return True
    if e is not None and e.answer_mode == "off":
        return False
    policy = getattr(settings, "answer_policy", "all")
    if policy == "all":
        return True
    if d.stage == "prbc":
        return True  # PRBC'dan o'qilgan aniq holat — taxmin emas
    known = e is not None and d.stage in ("image", "template", "faq")
    if policy == "kb":
        return known
    return known and e.kind == Entry.TEMPLATE  # standard


def render_answer(entry, fields, lang):
    return render_text(entry.answer_ru if lang == "ru" and entry.answer_ru else entry.answer, fields)


OPENERS = {
    "uz": {"image": ["", "", "Ko'rdim 👀", "Tushunarli 👍", "Mana yechimi 👇", "Skrinshot bo'yicha:"],
           "other": ["", "", "Tushunarli 👍", "Mana javob 👇", "Bu tez hal bo'ladi."]},
    "ru": {"image": ["", "", "Вижу скриншот 👀", "Понятно 👍", "Вот решение 👇"],
           "other": ["", "", "Понятно 👍", "Вот ответ 👇", "Это быстро решается."]},
}


def vary(d, lang, settings, rnd=None):
    """Standart javobni har safar biroz boshqacha: AI oldindan yozgan variantlardan biri (mazmuni bir xil) va qisqa
    insoniy kirish so'zi. Bir zumda — javob paytida AI chaqirilmaydi. PRBC holat kartasi (d.live) doim saqlanadi."""
    text = _vary(d, lang, settings, rnd)
    if d.live and d.live not in text:
        text = f"{d.live}\n\n{text}"
    return text


def _vary(d, lang, settings, rnd=None):
    import random
    rnd = rnd or random
    if not getattr(settings, "answer_variety", False) or d.stage not in ("image", "template", "faq") or d.entry is None:
        return d.text
    if d.entry.kind == Entry.TEMPLATE:
        return d.text  # standart holat — bazadagi javob aynan o'zi: AI qayta yozmaydi, kirish so'zi qo'shilmaydi
    text = d.text
    key = "ru" if lang == "ru" else "uz"
    pool = [v.get(key) for v in (d.entry.variants or []) if isinstance(v, dict) and v.get(key)]
    if pool and not (d.note or "").startswith("albom"):  # albomdagi bir nechta ekran bo'yicha qo'shma javob almashtirilmaydi
        pick = rnd.choice([None, *pool])
        if pick:
            text = render_text(pick, d.fields or {})
    opener = rnd.choice(OPENERS[key]["image" if d.stage == "image" else "other"])
    if opener and not text.startswith(opener):
        text = f"{opener}\n{text}"
    return text


def render_text(text, fields):
    lines = []
    for line in text.splitlines():
        keys = PLACEHOLDER.findall(line)
        if keys and not all(fields.get(k) for k in keys):
            continue  # qiymati topilmagan qatorni tashlab ketamiz
        lines.append(PLACEHOLDER.sub(lambda m: fields.get(m.group(1), m.group(0)), line))
    return "\n".join(lines).strip()


def rule_text(task, lang):
    from zona import translation
    title = translation.current(task, "title", lang)
    rule = translation.current(task, "rule", lang)
    return f"{title}\n\n{rule}".strip()


def responsible_line(resp, lang):
    if not resp:
        return ""
    r = resp[0]
    who = r["name"] + (" (" + ", ".join("@" + t for t in r["telegram"]) + ")" if r.get("telegram") else "")
    b = r.get("backup")
    if b:
        who += ("; запасной: " if lang == "ru" else "; zaxira: ") + b["name"] + (
            " (" + ", ".join("@" + t for t in b["telegram"]) + ")" if b.get("telegram") else "")
    return ("Ответственный: " if lang == "ru" else "Mas'ul: ") + who


def to_html(text, signature=""):
    """Oddiy matn -> Telegram HTML: maxsus belgilar ekranlanadi, **qalin** va `kod` qo'llab-quvvatlanadi."""
    out = html.escape(text or "")
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", out)
    if signature:
        out += f"\n\n<i>{html.escape(signature)}</i>"
    return out


def staff_q():
    """Xodimlar ro'yxati (Telegram'i bor) — panel va testlar uchun."""
    return Q(member__isnull=False) | Q(contact__isnull=False)

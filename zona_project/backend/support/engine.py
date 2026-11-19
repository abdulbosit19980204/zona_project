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

from zona.models import AITaskConfig, AIUsage, Member, Task, TeamContact
from zona.search import search as run_search
from zona.search.normalize import fold, tokens

from .models import Entry, Settings, TgUser

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


def is_question(text, has_photo=False):
    """Salom/rahmat/stiker emas, mazmunli xabar yoki rasm."""
    if has_photo:
        return True
    t = (text or "").strip()
    if len(t) < 6:
        return False
    words = re.findall(r"[\w'ʻʼ’]+", t.lower())
    if not words:
        return False
    if len(words) <= 3 and all(w.replace("ʻ", "'").replace("’", "'") in GREETING for w in words):
        return False
    return True


CLARIFY_WORDS = re.compile(
    r"\b(yuboring|yuboringchi|yuborib|tashlang|tashlab|tashlavoring|skrin\w*|skrinshot\w*|screen\w*|rasm\w*|foto\w*|"
    r"stir\w*|inn|kod\w*|kodini|raqam\w*|nomer\w*|nomini|qaysi|qanaqa|qanday|qachon|qayer\w*|aniqroq|batafsil|"
    r"ko'rsating|korsating|"
    r"пришлите|отправьте|скиньте|скин\w*|скрин\w*|фото\w*|инн|код\w*|номер\w*|какой|какая|какие|когда|где|уточните|"
    r"покажите)\b", re.IGNORECASE)
ANSWER_HINT = re.compile(r"\b(qildim|qilindi|bo'ldi|boldi|tuzatildi|qo'shildi|qoshildi|ochildi|yopildi|o'tkazildi|"
                         r"tayyor|hal qilindi|сделал|сделано|исправил|исправлено|добавил|готово|открыл)\b", re.IGNORECASE)


def is_clarifying(text):
    """Xodim javobi aslida aniqlashtiruvchi savolmi ("STIR yuboring", "skrin tashlang?") — bunday matn javob emas."""
    t = (text or "").strip()
    if not t or len(t) > 260 or ANSWER_HINT.search(t):
        return False
    return t.endswith("?") or bool(CLARIFY_WORDS.search(t))


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
    if changed:
        user.save()
    else:
        TgUser.objects.filter(pk=user.pk).update(last_seen=timezone.now())
    return user


# ------------------------------------------------------------------ 1. shablon
def _trigger_hit(trigger, folded, raw):
    trigger = (trigger or "").strip()
    if not trigger:
        return False
    if trigger.startswith("re:"):
        try:
            return bool(re.search(trigger[3:], raw, re.IGNORECASE | re.MULTILINE))
        except re.error:
            return False
    return all(fold(part).strip() in folded for part in trigger.split("&&") if part.strip())


def extract_fields(entry, raw):
    out = {}
    for pattern in entry.extract or []:
        try:
            m = re.search(pattern, raw, re.IGNORECASE | re.MULTILINE)
        except re.error:
            continue
        if m:
            out.update({k: v.strip() for k, v in m.groupdict().items() if v and k not in out})
    return out


def match_template(raw, entries):
    folded = fold(raw)
    best, best_hits = None, 0
    for e in entries:
        hits = sum(1 for t in e.triggers or [] if _trigger_hit(t, folded, raw))
        if hits > best_hits:
            best, best_hits = e, hits
    if not best:
        return None, {}, 0
    return best, extract_fields(best, raw), min(100, 85 + 5 * best_hits)


# ------------------------------------------------------------------ 2. o'xshash savol
def _tok_eq(a, b):
    """Bir xil o'zak: to'liq teng, biri ikkinchisining boshlanishi (≥4 harf) yoki umumiy boshlanish ≥5 harf
    (o'zbekcha qo'shimchalar: tiklayman / tiklash, parolim / parol)."""
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n >= 5


def similarity(a_text, b_text):
    """0..100: so'z o'zaklari bo'yicha Dice o'xshashligi (prefiks mosligi bilan — imlo/qo'shimchaga chidamli)."""
    a, b = list(dict.fromkeys(tokens(a_text))), list(dict.fromkeys(tokens(b_text)))
    if not a or not b:
        return 0
    common = sum(1 for x in a if any(_tok_eq(x, y) for y in b))
    return round(100 * 2 * common / (len(a) + len(b)))


def match_faq(raw, entries):
    """Eng o'xshash yozuv. Teng ballda — savolga so'zma-so'z mos ko'rinish, keyin umumiy so'zlari ko'pi ustun."""
    target = " ".join(tokens(raw))
    best, key = None, (0, 0, 0)
    for e in entries:
        for q in [e.title, *(e.questions or [])]:
            s = similarity(raw, q)
            if not s:
                continue
            k = (s, int(" ".join(tokens(q)) == target), len(set(tokens(q)) & set(tokens(raw))))
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


def _person(m):
    """Mas'ul: jamoa bo'lsa — jamoa nomi va a'zolarining Telegram'lari (ish bo'linmaydi, kim bo'sh bo'lsa oladi)."""
    tgs = [c.telegram.lstrip("@") for c in m.contacts.all() if c.telegram] if m.is_team else []
    if m.telegram:
        tgs.insert(0, m.telegram.lstrip("@"))
    return {"id": m.id, "name": m.name, "role": m.role, "level": m.level, "telegram": tgs[:4], "is_team": m.is_team}


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
- Ma'lumot yetarli bo'lmasa yoki shaxsiy/moliyaviy qaror kerak bo'lsa: needs_human=true, confidence past.
- confidence: 0..1 — javob aynan shu savolga to'g'ri ekaniga ishonching."""


def ai_quota_left(settings):
    since = timezone.now() - timezone.timedelta(days=1)
    used = AIUsage.objects.filter(task=AITaskConfig.SUPPORT, at__gte=since).count()
    return max(0, settings.ai_daily_limit - used)


def ai_answer(raw, lang, context_entries, rule_task, settings):
    from zona import conf
    from zona.ai import service as ai
    from zona.ai.providers import AIError

    if not settings.ai_enabled or ai_quota_left(settings) <= 0:
        return None
    ctx = []
    for e in context_entries[:5]:
        ans = e.answer_ru if lang == "ru" and e.answer_ru else e.answer
        ctx.append(f"- SAVOL: {e.title}\n  JAVOB: {ans[:800]}")
    if rule_task is not None and rule_task.rule:
        ctx.append(f"- QOIDA ({rule_task.title}): {rule_task.rule[:600]}")
    system = AI_SYSTEM.format(company=conf.get("COMPANY_NAME")) + "\n\nTASDIQLANGAN JAVOBLAR VA QOIDALAR:\n" + (
        "\n".join(ctx) or "(hozircha yo'q)")
    try:
        data, meta = ai.run(AITaskConfig.SUPPORT, None, raw[:200], system, f"SAVOL:\n{raw[:3000]}", AI_SCHEMA)
    except AIError:
        return None
    conf_pct = round(100 * max(0.0, min(1.0, float(data.get("confidence") or 0))))
    return {"text": str(data.get("answer") or "").strip(), "confidence": conf_pct,
            "needs_human": bool(data.get("needs_human")), "reason": str(data.get("reason") or "")[:300], "meta": meta}


# ------------------------------------------------------------------ yig'ish
def decide(raw, lang="uz", allow_unapproved=False):
    """Savol matni (+ rasm matni) -> Decision. allow_unapproved: soya rejimida ko'rib chiqilayotgan shablonlar ham."""
    settings = Settings.load()
    statuses = [Entry.APPROVED, Entry.REVIEW, Entry.NEW] if allow_unapproved else [Entry.APPROVED]
    entries = list(Entry.objects.filter(status__in=statuses))
    templates = [e for e in entries if e.kind == Entry.TEMPLATE]
    faqs = [e for e in entries if e.kind == Entry.FAQ]

    task, rule_conf, resp = rule_answer(raw, lang)

    e, fields, conf = match_template(raw, templates)
    if e:
        return Decision("template", e, conf, render_answer(e, fields, lang), False, resp, fields,
                        e.status != Entry.APPROVED)

    e, score = match_faq(raw, faqs)
    if e and score >= settings.faq_threshold:
        return Decision("faq", e, score, render_answer(e, {}, lang), False, resp, {}, e.status != Entry.APPROVED)

    if task is not None and task.rule and rule_conf >= settings.route_threshold:
        return Decision("rule", None, rule_conf, rule_text(task, lang), False, resp, note=f"task:{task.id}")

    ranked = sorted(faqs, key=lambda x: -max(similarity(raw, q) for q in [x.title, *(x.questions or [])]))
    ai = ai_answer(raw, lang, [x for x in ranked if x.status == Entry.APPROVED], task, settings)
    if ai and ai["text"] and not ai["needs_human"] and ai["confidence"] >= settings.ai_min_confidence:
        return Decision("ai", None, ai["confidence"], ai["text"], False, resp, note=ai["reason"])
    d = Decision("", None, max(score, rule_conf), "", True, resp)
    if ai:
        d.note = f"AI ishonchi past ({ai['confidence']}%): {ai['reason']}"
        d.text = ai["text"]  # admin uchun qoralama sifatida ko'rsatiladi
    return d


def render_answer(entry, fields, lang):
    text = entry.answer_ru if lang == "ru" and entry.answer_ru else entry.answer
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

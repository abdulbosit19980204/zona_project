"""Bot bo'yicha AI tahlili: bilim bazasini ko'rib chiqish va javobsiz savollardan yangi javoblar taklif qilish.

AI hech narsani o'zi o'zgartirmaydi — faqat Suggestion (taklif) yaratadi. Xodim tasdiqlasa qo'llanadi (eski holat
versiyada qoladi). Har bir AI chaqiruvi natijasi zona.AIAnalysis'da saqlanadi (AI tahlillar tarixi).
"""
import logging
import re

from django.db.models import Q
from django.utils import timezone

from zona.models import AITaskConfig

from .models import AIJob, Entry, Message, Suggestion

log = logging.getLogger("support")
CHUNK = 8

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"suggestions": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "entry_id": {"type": "integer"},
            "kind": {"type": "string", "enum": ["improve", "questions", "merge", "archive", "ok"]},
            "answer": {"type": "string"}, "answer_ru": {"type": "string"}, "ask_first": {"type": "string"},
            "add_questions": {"type": "array", "items": {"type": "string"}},
            "merge_into": {"type": "integer"}, "reason": {"type": "string"},
        },
        "required": ["entry_id", "kind", "answer", "answer_ru", "ask_first", "add_questions", "merge_into", "reason"],
        "additionalProperties": False}}},
    "required": ["suggestions"], "additionalProperties": False,
}
NEW_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "question_ids": {"type": "array", "items": {"type": "integer"}},
            "existing_entry_id": {"type": "integer"},
            "title": {"type": "string"}, "questions": {"type": "array", "items": {"type": "string"}},
            "answer": {"type": "string"}, "ask_first": {"type": "string"}, "reason": {"type": "string"},
        },
        "required": ["question_ids", "existing_entry_id", "title", "questions", "answer", "ask_first", "reason"],
        "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}

RULES = """Sen StarGroup distributsiya kompaniyasining support bilim bazasi muharririsan. Savollar agent va supervayzerlardan:
1C, PRBC, ProTarget ilovasi, klient (savdo nuqtasi), marshrut, zakaz, aksiya, to'lov. Javoblarni Telegram guruhida bot beradi.
Qoidalar:
- Faqat berilgan ma'lumotga tayan. Kompaniyaga xos raqam, muddat yoki qoidani O'YLAB TOPMA — bilmasang, javobni o'zgartirma.
- Javob aniq, qisqa (2-8 qator), qadamlar raqamlangan, xushmuomala; o'zbek lotin yozuvida; answer_ru — rus tilida.
- Agentlar imlo xatosi bilan, o'zbek kirill/lotin, yangi alifbo (ş, ç, ō, ḡ) va ruscha yozadi — add_questions shunday haqiqiy
  ko'rinishlarni o'z ichiga olsin (3-8 ta, takrorsiz).
- ask_first — javob berishdan oldin agentdan so'rash kerak bo'lgan ma'lumot (STIR, skrinshot, TT kodi...), kerak bo'lmasa bo'sh."""


def _run(label, system, message, schema):
    """AI chaqiruvi. Barcha modellar band bo'lsa (503) — 20/60 soniya kutib yana urinadi (tahlil to'xtab qolmasin)."""
    import time

    from zona.ai import service as ai
    system += "\n\nreason va boshqa izohlarni O'ZBEK tilida (lotin) yoz."
    for wait in (20, 60, None):
        try:
            data, _meta = ai.run(AITaskConfig.SUPPORT, None, label, system, message, schema)
            return data
        except Exception as e:  # noqa: BLE001
            busy = any(x in str(e) for x in ("503", "429", "high demand", "band", "overloaded", "Rate limit"))
            if not busy or wait is None:
                raise
            time.sleep(wait)


def _entry_text(e):
    return (f"[id={e.id}] SARLAVHA: {e.title}\nSAVOL KO'RINISHLARI: {'; '.join((e.questions or [])[:12])}\n"
            f"JAVOB (uz): {e.answer[:1200]}\nJAVOB (ru): {e.answer_ru[:800]}\nAVVAL SO'RASH: {e.ask_first}\n"
            f"ISHLATILGAN: {e.uses}, 👍 {e.likes}, 👎 {e.dislikes}")


def review_entries(job):
    """Bilim bazasini bo'laklab ko'rib chiqish: yomon baholangan, ko'p ishlatilgan, savol ko'rinishi kam yozuvlar birinchi."""
    scope = (job.params or {}).get("scope", "priority")
    limit = int((job.params or {}).get("limit") or 40)
    qs = Entry.objects.filter(status__in=[Entry.APPROVED, Entry.REVIEW]).exclude(suggestions__status=Suggestion.PENDING)
    if scope == "disliked":
        qs = qs.filter(dislikes__gt=0)
    correction = (job.params or {}).get("correction")
    auto = bool((job.params or {}).get("auto"))
    auto_safe = bool((job.params or {}).get("auto_safe"))
    ids_param = [int(x) for x in (job.params or {}).get("ids") or []][:200]
    if ids_param:  # tanlangan yozuvlar (masalan, ko'rmasdan tasdiqlanganlarni qayta tekshirish)
        qs = Entry.objects.filter(pk__in=ids_param)
        limit = len(ids_param)
    entries = sorted(qs, key=lambda e: (-(e.dislikes * 5), -e.uses, len(e.questions or []), -e.id))[:limit]
    ids = {e.id for e in Entry.objects.filter(status__in=[Entry.APPROVED, Entry.REVIEW])}
    titles = "\n".join(f"{e.id}: {e.title}" for e in Entry.objects.filter(status=Entry.APPROVED).only("id", "title")[:400])
    created = 0
    for i in range(0, len(entries), CHUNK):
        chunk = entries[i:i + CHUNK]
        system = (RULES + "\n\nVAZIFA: har bir yozuvni ko'rib chiq. kind: improve — javob noaniq/xato/to'liqsiz bo'lsa yaxshilangan "
                  "answer/answer_ru ber; questions — faqat yangi savol ko'rinishlari kerak bo'lsa; merge — boshqa yozuv bilan "
                  "deyarli bir xil bo'lsa merge_into=o'sha id; archive — eskirgan/foydasiz bo'lsa; ok — o'zgartirish shart emas. "
                  "Ishlatilmaydigan maydonlarni bo'sh qoldir (merge_into=0).\n\nBAZADAGI BOSHQA YOZUVLAR (id: sarlavha):\n" + titles)
        message = "\n\n".join(_entry_text(e) for e in chunk)
        if correction:
            system += ("\n\nXODIM TUZATISHI: bot shu yozuv bilan javob berdi, xodim esa boshqacha javob yozdi. Xodim javobidagi "
                       "to'g'ri va foydali ma'lumotni javobga qo'shib kind=improve qaytar (xodim javobi aniq bir holatga xos "
                       "bo'lsa — umumiy qoidani yoz; foydali narsa bo'lmasa — ok). Savolni add_questions'ga ham qo'sh.")
            message += (f"\n\nSAVOL: {correction.get('question', '')}\nBOT JAVOBI: {correction.get('bot', '')}\n"
                        f"XODIM ({correction.get('by', '')}) JAVOBI: {correction.get('staff', '')}")
        try:
            data = _run(f"Support: bilim bazasi tahlili ({len(chunk)} ta yozuv)", system, message, REVIEW_SCHEMA)
        except Exception as e:  # noqa: BLE001 — bitta bo'lak yiqilsa keyingisiga o'tamiz, topilgan takliflar saqlanadi
            job.error = f"{type(e).__name__}: {e}"[:500]
            job.progress = {**(job.progress or {}), "failed_chunks": (job.progress or {}).get("failed_chunks", 0) + 1}
            continue
        for s in data.get("suggestions") or []:
            eid, kind = s.get("entry_id"), s.get("kind")
            entry = next((x for x in chunk if x.id == eid), None)
            if not entry or kind == "ok":
                continue
            payload = {}
            if kind == "improve" and s.get("answer", "").strip() and s["answer"].strip() != entry.answer.strip():
                payload = {"answer": s["answer"].strip(), "answer_ru": s.get("answer_ru", "").strip() or entry.answer_ru,
                           "ask_first": s.get("ask_first", "").strip() or entry.ask_first}
            elif kind == "questions":
                new_q = [q.strip() for q in s.get("add_questions") or [] if q.strip() and q.strip() not in (entry.questions or [])]
                if not new_q:
                    continue
                payload = {"questions": new_q[:10]}
            elif kind == "merge" and s.get("merge_into") in ids and s["merge_into"] != eid:
                payload = {"merge_into": s["merge_into"]}
            elif kind == "archive":
                payload = {}
            else:
                continue
            sg = Suggestion.objects.create(job=job, kind=kind, entry=entry, payload=payload, reason=s.get("reason", "")[:2000],
                                           target_id=payload.get("merge_into"))
            created += 1
            if (auto and kind in ("improve", "questions")) or (auto_safe and kind == "questions"):
                try:
                    apply(sg, job.created_by or "avto")  # o'z-o'zini o'qitish: eski holat versiyada qoladi
                except Exception:  # noqa: BLE001
                    log.exception("auto apply failed")
        job.progress = {"done": min(i + CHUNK, len(entries)), "total": len(entries), "suggestions": created}
        job.save(update_fields=["progress", "error"])
    return created


def review_unanswered(job):
    """Odamga ketgan / javobsiz savollar (va xodimlar javoblari) -> yangi yozuv yoki mavjudiga savol ko'rinishi."""
    days = int((job.params or {}).get("days") or 30)
    since = timezone.now() - timezone.timedelta(days=days)
    qs = (Message.objects.filter(kind=Message.QUESTION, created_at__gte=since)
          .filter(Q(status__in=[Message.ESCALATED, Message.NEW, Message.DRAFTED]) | Q(stage__in=["staff", "panel"]))
          .prefetch_related("staff_replies").order_by("-created_at")[:120])
    items = []
    for q in qs:
        text = (q.text or q.ocr_text or "").strip()
        if len(text) < 6:
            continue
        staff = [r.text for r in sorted(q.staff_replies.all(), key=lambda r: r.created_at) if r.kind in (Message.STAFF, Message.CLARIFY)]
        items.append(f"[q={q.id}] {text[:400]}" + (f"\n   XODIM: {' | '.join(s[:300] for s in staff)}" if staff else ""))
    if not items:
        job.progress = {"done": 0, "total": 0, "suggestions": 0}
        return 0
    titles = "\n".join(f"{e.id}: {e.title}" for e in Entry.objects.filter(status=Entry.APPROVED).only("id", "title")[:400])
    created = 0
    for i in range(0, len(items), 25):
        chunk = items[i:i + 25]
        system = (RULES + "\n\nVAZIFA: quyidagi savollar bot javob bera olmagan savollar. O'xshashlarini guruhla. Har guruh uchun: "
                  "mavjud yozuvga mos kelsa existing_entry_id=o'sha id va questions=savolning qisqa ko'rinishlari; mos yozuv yo'q "
                  "bo'lsa existing_entry_id=0, title, questions va answer (faqat XODIM javobi bo'lsa unga tayan; bo'lmasa answer='' "
                  "qoldir — o'ylab topma). Salom, rahmat, hisobot kabi savol bo'lmaganlarni tashlab ket.\n\nMAVJUD YOZUVLAR:\n" + titles)
        try:
            data = _run(f"Support: javobsiz savollar tahlili ({len(chunk)} ta)", system, "\n".join(chunk), NEW_SCHEMA)
        except Exception as e:  # noqa: BLE001 — bitta bo'lak yiqilsa keyingisiga o'tamiz, topilgan takliflar saqlanadi
            job.error = f"{type(e).__name__}: {e}"[:500]
            job.progress = {**(job.progress or {}), "failed_chunks": (job.progress or {}).get("failed_chunks", 0) + 1}
            continue
        for it in data.get("items") or []:
            qids = [x for x in it.get("question_ids") or [] if isinstance(x, int)]
            ex = Entry.objects.filter(pk=it.get("existing_entry_id") or 0).first()
            questions = [q.strip() for q in it.get("questions") or [] if q.strip()][:10]
            if ex:
                new_q = [q for q in questions if q not in (ex.questions or [])]
                if not new_q:
                    continue
                Suggestion.objects.create(job=job, kind=Suggestion.QUESTIONS, entry=ex, payload={"questions": new_q},
                                          reason=it.get("reason", "")[:2000], question_ids=qids)
            elif it.get("title", "").strip():
                Suggestion.objects.create(job=job, kind=Suggestion.NEW, payload={
                    "title": it["title"].strip()[:200], "questions": questions, "answer": it.get("answer", "").strip(),
                    "ask_first": it.get("ask_first", "").strip()}, reason=it.get("reason", "")[:2000], question_ids=qids)
            else:
                continue
            created += 1
        job.progress = {"done": min(i + 25, len(items)), "total": len(items), "suggestions": created}
        job.save(update_fields=["progress", "error"])
    return created


# ====================================================================== takrorlarni tozalash
DEDUPE_SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "group": {"type": "integer"}, "same": {"type": "boolean"}, "keep_id": {"type": "integer"},
            "merge_ids": {"type": "array", "items": {"type": "integer"}},
            "title": {"type": "string"}, "answer": {"type": "string"}, "answer_ru": {"type": "string"}, "reason": {"type": "string"},
        },
        "required": ["group", "same", "keep_id", "merge_ids", "title", "answer", "answer_ru", "reason"],
        "additionalProperties": False}}},
    "required": ["groups"], "additionalProperties": False,
}
DEDUPE_TASK = """VAZIFA: har bir guruhda bir-biriga o'xshash bilim bazasi yozuvlari bor (bir savolga turli xodimlar turli javob yozgan).
- same — guruhdagi yozuvlar HAQIQATAN bitta savolga javobmi? Faqat umumiy so'zlari bor, lekin boshqa-boshqa muammo bo'lsa — same=false.
- keep_id — qoldiriladigan eng yaxshi yozuv (aniq, to'g'ri, ko'p ishlatilgan/yaxshi baholangan).
- merge_ids — keep_id ga qo'shiladigan (arxivga tushadigan) takrorlar; boshqa mavzudagi yozuvni qo'shma.
- answer — eng optimal javob: qisqa javob ham, batafsil javob ham bor bo'lsa, ulardagi FOYDALI ma'lumotlarni birlashtirib,
  aniq va qisqa (2-8 qator, kerak bo'lsa raqamlangan qadamlar) yoz. Faqat berilgan javoblardagi ma'lumotdan foydalan.
  answer_ru — rus tilida. title — qisqa aniq sarlavha. reason — nima uchun shunday qaror qilding (1-2 gap)."""


def _group_text(n, rows):
    return f"=== GURUH {n} ===\n" + "\n\n".join(_entry_text(e) for e in rows)


def ai_merge_groups(groups):
    """groups: [[Entry, ...], ...] -> AI qarorlari ro'yxati (guruh tartibida, same=false bo'lsa ham)."""
    data = _run(f"Support: takrorlarni tozalash ({len(groups)} guruh)", RULES + "\n\n" + DEDUPE_TASK,
                "\n\n".join(_group_text(i + 1, g) for i, g in enumerate(groups)), DEDUPE_SCHEMA)
    out = []
    for d in data.get("groups") or []:
        i = (d.get("group") or 0) - 1
        if not 0 <= i < len(groups):
            continue
        ids = {e.id for e in groups[i]}
        keep = d.get("keep_id") if d.get("keep_id") in ids else None
        merge = [x for x in d.get("merge_ids") or [] if x in ids and x != keep]
        out.append({"index": i, "same": bool(d.get("same")) and bool(keep) and bool(merge), "keep": keep, "merge": merge,
                    "title": (d.get("title") or "").strip(), "answer": (d.get("answer") or "").strip(),
                    "answer_ru": (d.get("answer_ru") or "").strip(), "reason": (d.get("reason") or "").strip()})
    return out


def review_dedupe(job):
    """Takrorlar guruhlarini AI bilan ko'rib chiqish. params.auto=true — qarorlar darhol qo'llanadi (arxivga, o'chirmasdan)."""
    from .dedupe import find_groups
    params = job.params or {}
    threshold = int(params.get("threshold") or 75)
    auto = bool(params.get("auto"))
    busy = set(Suggestion.objects.filter(status=Suggestion.PENDING, kind=Suggestion.DEDUPE).values_list("entry_id", flat=True))
    groups = [g for g in find_groups(threshold) if not any(r["id"] in busy for r in g["entries"])][: int(params.get("limit") or 40)]
    by_id = {e.id: e for e in Entry.objects.filter(pk__in=[r["id"] for g in groups for r in g["entries"]])}
    created = applied = 0
    step = 4
    for i in range(0, len(groups), step):
        chunk = [[by_id[r["id"]] for r in g["entries"][:6] if r["id"] in by_id] for g in groups[i:i + step]]
        try:
            decisions = ai_merge_groups(chunk)
        except Exception as e:  # noqa: BLE001
            job.error = f"{type(e).__name__}: {e}"[:500]
            continue
        for d in decisions:
            if not d["same"]:
                continue
            payload = {"keep": d["keep"], "merge": d["merge"], "title": d["title"], "answer": d["answer"], "answer_ru": d["answer_ru"]}
            sg = Suggestion.objects.create(job=job, kind=Suggestion.DEDUPE, entry_id=d["keep"], payload=payload, reason=d["reason"][:2000])
            created += 1
            if auto:
                try:
                    apply(sg, f"AI avto-tozalash ({job.created_by})")
                    applied += 1
                except Exception as e:  # noqa: BLE001
                    log.warning("dedupe auto-apply failed: %s", e)
        job.progress = {"done": min(i + step, len(groups)), "total": len(groups), "suggestions": created, "applied": applied}
        job.save(update_fields=["progress", "error"])
    return created


# ====================================================================== javob variantlari
VARIANTS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {"entry_id": {"type": "integer"},
                       "variants": {"type": "array", "items": {
                           "type": "object", "properties": {"uz": {"type": "string"}, "ru": {"type": "string"}},
                           "required": ["uz", "ru"], "additionalProperties": False}}},
        "required": ["entry_id", "variants"], "additionalProperties": False}}},
    "required": ["items"], "additionalProperties": False,
}
VARIANTS_TASK = """VAZIFA: har bir javobni 3 xil uslubda QAYTA YOZ — chatdagilar har safar bir xil shablonni ko'rib zerikmasin, lekin
MAZMUN AYNAN SAQLANSIN:
- hamma qadamlar, raqamlar, muddatlar, tugma va bo'lim nomlari («...»), kodlar, odam nomlari (**qalin**) o'zgarmaydi;
- {kod}, {nom} kabi jingalak qavsdagi maydonlar aynan qoladi;
- yangi ma'lumot qo'shma, hech narsani olib tashlama; uzunligi asl javobga yaqin; emoji va **qalin** belgilar mumkin;
- uz — o'zbek lotin (o', g' bilan), ru — rus tilida (asl ru javob bo'lmasa, uz'dan tarjima qil);
- uslublar: 1) qisqa va do'stona, 2) qadam-baqadam, 3) xotirjam tushuntiruvchi."""

_NUM = re.compile(r"\d+")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_FIELD = re.compile(r"\{[a-z_]+\}")
_URL = re.compile(r"https?://\S+")


def valid_variant(orig, text):
    """Variant mazmunni buzmaganmi: maydonlar, raqamlar, qalin nomlar va havolalar saqlangan, uzunligi yaqin."""
    if not text or not orig:
        return False
    if set(_FIELD.findall(orig)) != set(_FIELD.findall(text)):
        return False
    if not set(_NUM.findall(orig)) <= set(_NUM.findall(text)):
        return False
    if not {b.strip().lower() for b in _BOLD.findall(orig)} <= {b.strip().lower() for b in _BOLD.findall(text)} | {
            w.lower() for w in text.split()}:
        return False
    if not set(_URL.findall(orig)) <= set(_URL.findall(text)):
        return False
    return 0.55 * len(orig) <= len(text) <= 1.6 * len(orig) + 40


def write_variants(job):
    """Ko'p ishlatiladigan tasdiqlangan javoblar uchun 3 tadan variant (mazmuni bir xil) — bot ulardan birini tanlaydi."""
    params = job.params or {}
    ids = [int(x) for x in params.get("ids") or []][:100]
    qs = Entry.objects.filter(pk__in=ids) if ids else Entry.objects.filter(status=Entry.APPROVED, variants__isnull=True)
    entries = sorted(qs, key=lambda e: (-(e.uses or 0), -e.image_examples.count(), e.id))[: len(ids) or int(params.get("limit") or 25)]
    done = 0
    for i in range(0, len(entries), 5):
        chunk = entries[i:i + 5]
        text = "\n\n".join(f"[id={e.id}] SARLAVHA: {e.title}\nJAVOB (uz):\n{e.answer[:1500]}\nJAVOB (ru):\n{(e.answer_ru or '')[:1200]}"
                           for e in chunk)
        try:
            data = _run(f"Support: javob variantlari ({len(chunk)} ta)", RULES + "\n\n" + VARIANTS_TASK, text, VARIANTS_SCHEMA)
        except Exception as e:  # noqa: BLE001
            job.error = f"{type(e).__name__}: {e}"[:500]
            continue
        for item in data.get("items") or []:
            e = next((x for x in chunk if x.id == item.get("entry_id")), None)
            if not e:
                continue
            ok = []
            for v in item.get("variants") or []:
                uz = (v.get("uz") or "").strip()
                ru = (v.get("ru") or "").strip()
                if valid_variant(e.answer, uz):
                    ok.append({"uz": uz, "ru": ru if (not e.answer_ru or valid_variant(e.answer_ru, ru)) else ""})
            if ok:
                Entry.objects.filter(pk=e.pk).update(variants=ok[:4])  # javob matni o'zgarmaydi
                done += 1
        job.progress = {"done": min(i + 5, len(entries)), "total": len(entries), "suggestions": done}
        job.save(update_fields=["progress", "error"])
    return done


def run_job(job_id):
    job = AIJob.objects.get(pk=job_id)
    job.status, job.error = AIJob.RUNNING, ""
    job.save(update_fields=["status", "error"])
    n = {AIJob.REVIEW_ENTRIES: review_entries, AIJob.DEDUPE: review_dedupe,
         AIJob.VARIANTS: write_variants}.get(job.kind, review_unanswered)(job)
    job.status = AIJob.FAILED if job.error and not n else AIJob.DONE
    job.progress = {**(job.progress or {}), "suggestions": n}
    job.finished_at = timezone.now()
    job.save()
    return n


# ====================================================================== taklifni qo'llash
def apply(s, by, edits=None):
    """Taklifni qo'llash (editor). edits — xodim tasdiqlashdan oldin tahrirlagan payload."""
    from .runner import approve, snapshot
    payload = {**(s.payload or {}), **(edits or {})}
    e = s.entry
    if s.kind == Suggestion.IMPROVE and e:
        snapshot(e, by, "AI taklifi qo'llandi")
        for f in ("answer", "answer_ru", "ask_first"):
            if payload.get(f) is not None:
                setattr(e, f, payload[f])
        e.save()
    elif s.kind == Suggestion.QUESTIONS and e:
        snapshot(e, by, "AI: savol ko'rinishlari qo'shildi")
        e.questions = list(dict.fromkeys([*(e.questions or []), *payload.get("questions", [])]))[:60]
        e.save(update_fields=["questions", "updated_at"])
    elif s.kind == Suggestion.MERGE and e and s.target_id:
        t = s.target
        snapshot(t, by, f"AI: #{e.id} birlashtirildi")
        t.questions = list(dict.fromkeys([*(t.questions or []), e.title, *(e.questions or [])]))[:60]
        t.save(update_fields=["questions", "updated_at"])
        e.status = Entry.ARCHIVED
        e.save(update_fields=["status", "updated_at"])
    elif s.kind == Suggestion.DEDUPE:
        from .dedupe import merge_group
        keep_id = payload.get("keep") or (e.id if e else None)
        if not keep_id or not Entry.objects.filter(pk=keep_id).exists():
            raise ValueError("Qoldiriladigan yozuv topilmadi.")
        e, _n = merge_group(keep_id, payload.get("merge") or [], by, answer=payload.get("answer") or None,
                            answer_ru=payload.get("answer_ru") or None, title=payload.get("title") or None,
                            note="AI: takrorlar birlashtirildi")
    elif s.kind == Suggestion.ARCHIVE and e:
        e.status = Entry.ARCHIVED
        e.save(update_fields=["status", "updated_at"])
    elif s.kind == Suggestion.NEW:
        if not payload.get("answer", "").strip():
            raise ValueError("Yangi yozuv uchun javob matnini yozing.")
        e = Entry.objects.create(kind=Entry.FAQ, title=payload.get("title", "")[:200] or "AI taklifi",
                                 questions=payload.get("questions", []), answer=payload["answer"].strip(),
                                 ask_first=payload.get("ask_first", ""), status=Entry.REVIEW, source="bot", author=f"AI ({by})")
        approve(e, by)
        s.entry = e
    s.status, s.decided_by, s.decided_at = Suggestion.APPROVED, by, timezone.now()
    s.payload = payload
    s.save()
    return s


def reject(s, by):
    s.status, s.decided_by, s.decided_at = Suggestion.REJECTED, by, timezone.now()
    s.save(update_fields=["status", "decided_by", "decided_at"])
    return s


"""Bot bo'yicha AI tahlili: bilim bazasini ko'rib chiqish va javobsiz savollardan yangi javoblar taklif qilish.

AI hech narsani o'zi o'zgartirmaydi — faqat Suggestion (taklif) yaratadi. Xodim tasdiqlasa qo'llanadi (eski holat
versiyada qoladi). Har bir AI chaqiruvi natijasi zona.AIAnalysis'da saqlanadi (AI tahlillar tarixi).
"""
import logging

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
    from zona.ai import service as ai
    data, _meta = ai.run(AITaskConfig.SUPPORT, None, label, system, message, schema)
    return data


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
        try:
            data = _run(f"Support: bilim bazasi tahlili ({len(chunk)} ta yozuv)", system,
                        "\n\n".join(_entry_text(e) for e in chunk), REVIEW_SCHEMA)
        except Exception as e:  # noqa: BLE001
            job.error = f"{type(e).__name__}: {e}"[:500]
            break
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
            Suggestion.objects.create(job=job, kind=kind, entry=entry, payload=payload, reason=s.get("reason", "")[:2000],
                                      target_id=payload.get("merge_into"))
            created += 1
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
        except Exception as e:  # noqa: BLE001
            job.error = f"{type(e).__name__}: {e}"[:500]
            break
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


def run_job(job_id):
    job = AIJob.objects.get(pk=job_id)
    job.status, job.error = AIJob.RUNNING, ""
    job.save(update_fields=["status", "error"])
    n = review_entries(job) if job.kind == AIJob.REVIEW_ENTRIES else review_unanswered(job)
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


"""O'z (lokal) AI modelimizni o'qitish uchun ma'lumot to'plami (JSONL, chat formati).

Har bir qator — bitta o'rganish misoli:
  {"messages": [{"role": "system", ...}, {"role": "user", "content": suhbat + kontekst}, {"role": "assistant", "content": javob}],
   "meta": {...}}
Manbalar: (1) AI tekshirgan haqiqiy suhbatlar — muammo va uni HAL QILGAN javob (train=True);
(2) tasdiqlangan bilim bazasi — har bir savol ko'rinishi -> tasdiqlangan javob.
Telefon raqamlari yashiriladi. Fayl serverdan tashqariga avtomatik yuborilmaydi — faqat admin yuklab oladi.
"""
import json
import re

from . import conversation
from .models import Entry, Message
from .ocr import main_message
from .systems import APP_LABEL, ORIGIN_LABEL

SYSTEM = ("Sen savdo kompaniyasining IT qo'llab-quvvatlash (L1) yordamchisisan. Agentlar PRBC (Telegram mini-ilova), "
          "ProTarget (mobil ilova) va 1C bilan ishlaydi. Muammoni qaysi tizimda ko'ringani va qaysi tizimdan chiqqanini "
          "aniqla, qisqa va aniq yechim ber; kerak bo'lsa avval yetishmayotgan ma'lumotni so'ra.")
PHONE = re.compile(r"(?<!\d)(\+?998[\s-]?)?\(?\d{2}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}(?!\d)")


def mask(text):
    return PHONE.sub("<telefon>", text or "")


def _final_answer(q):
    """Savolni hal qilgan javob: oxirgi xodim javobi; bo'lmasa — savol egasi tasdiqlagan bot javobi."""
    staff = [m.text for m in q.staff_replies.filter(kind=Message.STAFF).order_by("created_at") if (m.text or "").strip()]
    if staff:
        return staff[-1]
    if q.answered_by == "bot" and q.resolution == Message.YES and q.answer_text:
        return q.answer_text
    return ""


def _user_turn(q):
    lines = [f"Guruh: {q.group.title}" if q.group_id else ""]
    if q.app:
        lines.append(f"Ilova: {APP_LABEL.get(q.app, q.app)}")
    shot = main_message(q.ocr_text or "")
    convo = [ln for ln in conversation.context(q).splitlines() if not ln.startswith(("Xodim:", "Bot:"))]
    lines.append("Suhbat:\n" + "\n".join(convo))
    if shot:
        lines.append(f"Skrinshotdagi xabar: {shot}")
    return mask("\n".join(x for x in lines if x))


def conversation_rows(only_train=True):
    qs = (Message.objects.filter(kind=Message.QUESTION).exclude(stage="dup").select_related("group", "entry")
          .prefetch_related("staff_replies").order_by("created_at"))
    if only_train:
        qs = qs.filter(train=True)
    for q in qs.iterator(chunk_size=200):
        answer = _final_answer(q)
        if not answer.strip():
            continue
        yield {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": _user_turn(q)},
                            {"role": "assistant", "content": mask(answer)}],
               "meta": {"source": "chat", "id": q.id, "group": q.group.title if q.group_id else "", "app": q.app,
                        "origin": q.origin, "origin_label": ORIGIN_LABEL.get(q.origin, ""), "category": q.category,
                        "problem": mask(q.problem), "solution": mask(q.solution), "resolution": q.resolution,
                        "date": q.created_at.date().isoformat()}}


def kb_rows():
    for e in Entry.objects.filter(status=Entry.APPROVED).order_by("id"):
        for lang, answer in (("uz", e.answer), ("ru", e.answer_ru)):
            if not (answer or "").strip():
                continue
            for qtext in [e.title, *(e.questions or [])][:20]:
                if not (qtext or "").strip():
                    continue
                yield {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": mask(qtext)},
                                    {"role": "assistant", "content": mask(answer)}],
                       "meta": {"source": "kb", "entry": e.id, "title": e.title, "lang": lang}}


def export_lines(include_kb=True, only_train=True):
    for row in conversation_rows(only_train):
        yield json.dumps(row, ensure_ascii=False) + "\n"
    if include_kb:
        for row in kb_rows():
            yield json.dumps(row, ensure_ascii=False) + "\n"


def stats():
    base = Message.objects.filter(kind=Message.QUESTION).exclude(stage="dup")
    return {"questions": base.count(), "labeled_ai": base.filter(labeled_by="ai").count(),
            "labeled_rule": base.filter(labeled_by="rule").count(), "train": base.filter(train=True).count(),
            "kb_entries": Entry.objects.filter(status=Entry.APPROVED).count()}

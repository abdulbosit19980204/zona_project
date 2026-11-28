"""Bot javoblari aniqligini o'lchash (egasining talabi: yuborilgan javoblarning >=90% to'g'ri).

To'plam: oxirgi N kunda xodim javob bergan jonli savollar (savol -> xodimning haqiqiy javobi, kim javob bergani).
Har savolga bot HOZIR nima qilardi (javob yubormasdan): ``engine.decide`` — bilim bazasi, qoida, AI. Baholanayotgan
savolning o'z xodim javobi AI'ga namuna qilib berilmaydi (``engine.EVAL_HOLDOUT``).

Hukm (AI-hakam, xodim javobi bilan solishtirib):
  correct — mazmuni xodim javobi bilan bir xil yoki to'g'ri;  partial — qisman to'g'ri / kam;  wrong — noto'g'ri;
  bot uzatgan bo'lsa (needs_human) — handoff (mas'ul to'g'riligi alohida).
Mas'ul: botning mas'uli (toifa egasi yoki yozuv mas'uli) savolga haqiqatda javob bergan xodim / uning jamoasi bilan mosmi.
"""
import json
import logging
import time
from collections import Counter

from django.utils import timezone

from . import engine
from .models import Message

log = logging.getLogger(__name__)

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["correct", "partial", "wrong"]},
                   "reason": {"type": "string"}},
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}
JUDGE_SYSTEM = """Sen support bot javoblarining sifat nazoratchisisan. Agentning savoli, mutaxassisning haqiqiy javobi
(to'g'ri deb olinadi) va botning javobi beriladi. Botning javobini baholang:
- correct: bot javobi mutaxassis javobi bilan mazmunan bir xil yoki agentning muammosini to'g'ri hal qiladi;
- partial: yo'nalish to'g'ri, lekin muhim qadam yetishmaydi yoki ortiqcha/umumiy;
- wrong: boshqa muammoga javob, noto'g'ri ko'rsatma, yoki mutaxassis bajargan ishni bot "o'zingiz qiling" deydi.
Mutaxassis javobi aniq holatga yozilgan bo'lsa ("ulab qo'ydim", "tekshirdim, to'g'rilandi"), bot to'g'ri mas'ulga
yo'naltirishi yoki shu ishni tushuntirishi correct/partial hisoblanadi. Qisqa sabab yozing (o'zbekcha)."""


def staff_key(u):
    """Javob bergan xodim -> {ism, jamoa}: umumiy akkaunt — operatori; kontakt — jamoasi; jamoa a'zosi — jamoasi."""
    if u is None:
        return set()
    names = set()
    c = u.contact if u.contact_id else None
    if c is not None:
        if c.operator_id:
            names.add(c.operator.name)
        names.add(c.name)
        if c.member_id:
            names.add(c.member.name)
    if u.member_id:
        names.add(u.member.name)
        if u.member.member_of_id:
            names.add(u.member.member_of.name)
    return {n.strip().lower() for n in names if n}


def sample(days=30, limit=200):
    """Xodim (bot emas) mazmunli javob bergan jonli savollar, yangisidan."""
    since = timezone.now() - timezone.timedelta(days=days)
    out = []
    qs = (Message.objects.filter(kind=Message.QUESTION, source="live", created_at__gte=since)
          .select_related("user").order_by("-created_at"))
    for q in qs.iterator():
        text = (q.text or "").strip()
        if not q.ocr_text and not engine.learnable_question(text):
            continue
        r = (Message.objects.filter(question=q, kind=Message.STAFF, user__isnull=False)
             .select_related("user__member__member_of", "user__contact__member", "user__contact__operator")
             .order_by("created_at").first())
        if r is None or not engine.learnable_answer(r.text) or engine.not_an_answer(r.text) or engine.is_clarifying(r.text):
            continue
        out.append((q, r))
        if len(out) >= limit:
            break
    return out


def judge(question, staff_answer, bot_answer):
    from zona.ai import service as ai
    from zona.models import AITaskConfig
    msg = (f"AGENT SAVOLI:\n{question[:1500]}\n\nMUTAXASSIS JAVOBI (to'g'ri):\n{staff_answer[:1500]}\n\n"
           f"BOT JAVOBI:\n{bot_answer[:2000]}")
    data, _meta = ai.run(AITaskConfig.SUPPORT, None, "support eval", JUDGE_SYSTEM, msg, JUDGE_SCHEMA)
    return str(data.get("verdict") or "wrong"), str(data.get("reason") or "")[:300]


def run(days=30, limit=200, use_judge=True, out_path=None, progress=None, use_ai=False):
    """use_ai=False — bot javobi faqat bilim bazasi/shablon/qoida bilan (fast, AI so'rovisiz); True — AI ham
    (jonli botdagidek). Hakam (use_judge) har yuborilgan javobga bitta AI so'rovi. AI limiti jonli bot bilan umumiy!"""
    pairs = sample(days, limit)
    engine.EVAL_HOLDOUT.clear()
    engine.EVAL_HOLDOUT.update(q.pk for q, _r in pairs)
    rows = []
    try:
        for i, (q, r) in enumerate(pairs, 1):
            t0 = time.monotonic()
            text = (q.text or "").strip()
            lang = engine.detect_lang(text or q.ocr_text)
            try:
                if use_ai:
                    d = engine.decide(text or q.ocr_text, lang, text=text, ocr=q.ocr_text or "",
                                      alert=q.alert_text or "", live=False)
                else:  # jonli botdagidek to'liq yo'l, faqat AI'siz (fast=True qamrovni kamaytirib ko'rsatardi)
                    with engine.no_ai():
                        d = engine.decide(text or q.ocr_text, lang, text=text, ocr=q.ocr_text or "",
                                          alert=q.alert_text or "", live=False)
            except Exception as e:  # noqa: BLE001 — bitta savol xatosi butun baholashni to'xtatmasin
                log.exception("eval decide %s", q.pk)
                d, err = None, str(e)[:200]
            else:
                err = ""
            if d is None:  # javob topilmadi — jonli oqimdagidek odamga uzatiladi (toifa egasi bilan)
                d = engine.apply_owner(engine.Decision("", None, 0, "", True, []), text, q.ocr_text or "")
            sent = bool(d is not None and not d.needs_human and d.text)
            owner = d.responsible[0]["name"] if d is not None and d.responsible else ""
            who = staff_key(r.user)
            owner_ok = bool(owner) and owner.strip().lower() in who
            verdict, reason = ("handoff", "") if not sent else ("", "")
            if sent and use_judge:
                try:
                    verdict, reason = judge(text or q.ocr_text[:500], r.text, d.text)
                except Exception as e:  # noqa: BLE001
                    verdict, reason = "error", str(e)[:200]
            rows.append({"id": q.pk, "at": q.created_at.isoformat(), "group": q.group.title if q.group_id else "",
                         "question": (text or q.ocr_text)[:400], "photo": bool(q.photo_file_id),
                         "staff": r.user.staff_name(), "staff_answer": r.text[:600],
                         "stage": d.stage if d is not None else "", "confidence": d.confidence if d is not None else 0,
                         "entry": d.entry.title[:120] if d is not None and d.entry else "",
                         "bot_answer": (d.text if d is not None else "")[:800], "sent": sent,
                         "owner": owner, "owner_ok": owner_ok, "verdict": verdict, "reason": reason, "error": err,
                         "note": (d.note if d is not None else "")[:200],
                         "secs": round(time.monotonic() - t0, 1)})
            if progress:
                progress(i, len(pairs), rows[-1])
    finally:
        engine.EVAL_HOLDOUT.clear()
    summ = summary(rows)
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"at": timezone.now().isoformat(), "days": days, "summary": summ, "rows": rows}, f,
                      ensure_ascii=False, indent=1)
    return summ, rows


def summary(rows):
    n = len(rows)
    sent = [r for r in rows if r["sent"]]
    v = Counter(r["verdict"] for r in sent)
    judged = v["correct"] + v["partial"] + v["wrong"]
    hand = [r for r in rows if not r["sent"]]
    return {"questions": n, "bot_answered": len(sent), "coverage_pct": round(100 * len(sent) / n) if n else 0,
            "verdicts": dict(v), "accuracy_pct": round(100 * v["correct"] / judged) if judged else None,
            "accuracy_with_partial_pct": round(100 * (v["correct"] + v["partial"]) / judged) if judged else None,
            "handoff": len(hand),
            "owner_ok_pct_on_handoff": round(100 * sum(r["owner_ok"] for r in hand) / len(hand)) if hand else None,
            "by_stage": dict(Counter(r["stage"] or "-" for r in rows))}


def markdown(summ, rows, limit=40):
    lines = [f"# Bot aniqligi — baholash ({timezone.localdate():%d.%m.%Y})", "",
             f"- Savollar: **{summ['questions']}**; bot o'zi javob berardi: **{summ['bot_answered']}** "
             f"({summ['coverage_pct']}%), uzatardi: {summ['handoff']}",
             f"- Yuborilgan javoblar aniqligi: **{summ['accuracy_pct']}%** to'g'ri; qisman bilan {summ['accuracy_with_partial_pct']}%"
             f" — hukmlar: {summ['verdicts']}",
             f"- Uzatilganlarda mas'ul to'g'ri: {summ['owner_ok_pct_on_handoff']}%", f"- Bosqichlar: {summ['by_stage']}", "",
             "## Xato javoblar", "", "| # | Savol | Xodim javobi | Bot javobi | Sabab |", "|---|---|---|---|---|"]
    def cell(s):
        return " ".join(str(s).split()).replace("|", "/")[:160]
    for r in [r for r in rows if r["verdict"] == "wrong"][:limit]:
        lines.append(f"| {r['id']} | {cell(r['question'])} | {cell(r['staff_answer'])} | {cell(r['bot_answer'])} | "
                     f"{cell(r['reason'])} |")
    lines += ["", "## Qisman", "", "| # | Savol | Xodim javobi | Bot javobi | Sabab |", "|---|---|---|---|---|"]
    for r in [r for r in rows if r["verdict"] == "partial"][:limit]:
        lines.append(f"| {r['id']} | {cell(r['question'])} | {cell(r['staff_answer'])} | {cell(r['bot_answer'])} | "
                     f"{cell(r['reason'])} |")
    return "\n".join(lines) + "\n"

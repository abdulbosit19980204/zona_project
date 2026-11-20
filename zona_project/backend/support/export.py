"""AI o'qitish uchun eksport: support bot bilim bazasi va guruhdagi haqiqiy savol-javob zanjirlari.

Mas'uliyat platformasining savollar bazasi eksportiga (/api/knowledge/export.<fmt>) qo'shiladi:
  - tasdiqlangan yozuvlar: savol ko'rinishlari, javob (uz/ru), "javobdan oldin so'raladigan ma'lumot", mas'ul, zona;
  - xodim javob bergan savollar: savol (+ rasm matni), aniqlashtirishlar, savol egasining qo'shimcha ma'lumoti, yakuniy javob;
  - rasm turlari: o'rgatilgan skrinshotlarning OCR matni -> qaysi javob.
Shaxsiy ma'lumot: Telegram ID va username chiqarilmaydi; ism o'rniga rol (agent/xodim) yoziladi.
"""
from .models import Entry, Media, Message


def entries(lang="uz"):
    out = []
    for e in Entry.objects.filter(status=Entry.APPROVED).select_related("zone", "responsible").order_by("id"):
        out.append({
            "type": "support_answer", "id": e.id, "kind": e.kind, "zone": e.zone.name if e.zone_id else "",
            "question": e.title, "examples": list(e.questions or []),
            "answer": (e.answer_ru if lang == "ru" and e.answer_ru else e.answer), "answer_uz": e.answer,
            "answer_ru": e.answer_ru, "ask_first": e.ask_first,
            "responsible": e.responsible.name if e.responsible_id else "",
            "uses": e.uses, "likes": e.likes, "dislikes": e.dislikes,
        })
    return out


def threads(limit=5000):
    """Xodim yakuniy javob bergan savollar (jonli va guruh tarixidan)."""
    out = []
    qs = (Message.objects.filter(kind=Message.QUESTION, stage__in=["staff", "panel"])
          .prefetch_related("staff_replies").select_related("group").order_by("-created_at")[:limit])
    for q in qs:
        replies = sorted(q.staff_replies.all(), key=lambda r: r.created_at)
        final = [r.text for r in replies if r.kind == Message.STAFF] or ([q.answer_text] if q.answer_text else [])
        if not final:
            continue
        out.append({
            "type": "support_thread", "id": q.id, "group": q.group.title if q.group_id else "", "lang": q.lang,
            "question": q.text, "image_text": q.ocr_text[:2000],
            "clarifications": [r.text for r in replies if r.kind == Message.CLARIFY],
            "extra_info": [r.text for r in replies if r.kind == Message.INFO],
            "answer": final[-1], "source": q.source, "date": q.created_at.date().isoformat(),
            "problem": q.problem, "resolution": q.resolution,
            "feedback": [r.text for r in replies if r.kind == Message.FEEDBACK],
        })
    return out


def image_types():
    out = []
    for m in Media.objects.filter(kind=Media.PHOTO, label__isnull=False).exclude(ocr_text="").select_related("label")[:3000]:
        out.append({"type": "support_image", "entry": m.label_id, "question": m.label.title, "image_text": m.ocr_text[:2000],
                    "answer": m.label.answer})
    return out


def chat_lines(system, lang="uz"):
    """Fine-tuning (messages) formatidagi misollar."""
    rows = []
    for e in entries(lang):
        answer = e["answer"] if not e["ask_first"] else f"{e['answer']}\n\n(Avval so'raladi: {e['ask_first']})"
        for q in [e["question"], *e["examples"]]:
            rows.append([{"role": "system", "content": system}, {"role": "user", "content": q},
                         {"role": "assistant", "content": answer}])
    for t in threads():
        user = t["question"] + (f"\n[Rasmdagi matn]\n{t['image_text']}" if t["image_text"] else "")
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user.strip()}]
        for c, info in zip(t["clarifications"], t["extra_info"] + [""] * len(t["clarifications"])):
            msgs.append({"role": "assistant", "content": c})
            if info:
                msgs.append({"role": "user", "content": info})
        msgs.append({"role": "assistant", "content": t["answer"]})
        rows.append(msgs)
    for i in image_types():
        rows.append([{"role": "system", "content": system},
                     {"role": "user", "content": f"[Skrinshot matni]\n{i['image_text']}"},
                     {"role": "assistant", "content": i["answer"]}])
    return rows


def markdown(lang="uz"):
    out = ["", "## Support bot: tasdiqlangan javoblar", ""]
    for e in entries(lang):
        out.append(f"**{e['question']}**" + (f" · _{e['zone']}_" if e["zone"] else ""))
        if e["examples"]:
            out.append("Qanday so'raladi: " + "; ".join(f"“{x}”" for x in e["examples"][:12]))
        if e["ask_first"]:
            out.append(f"Avval so'raladi: {e['ask_first']}")
        out += [e["answer"], ""]
    th = threads(500)
    if th:
        out += ["## Guruhdagi haqiqiy savol-javoblar (xodim javoblari)", ""]
        for t in th:
            out.append(f"- **Savol:** {t['question'][:500]}")
            for c in t["clarifications"]:
                out.append(f"  - _Aniqlashtirish:_ {c[:300]}")
            out.append(f"  - **Javob:** {t['answer'][:800]}")
        out.append("")
    return "\n".join(out)

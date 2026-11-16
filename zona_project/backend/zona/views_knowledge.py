"""Savollar bazasi: AI'ni o'qitish uchun eksport va Telegram bot uchun "kim javob beradi" API.

Bot (yoki boshqa tashqi tizim) savolni POST /api/bot/ask/ ga yuboradi va tayyor javob oladi:
qaysi zona, aniq qoida, mas'ul va uning kontaktlari, mas'ul javob bermasa — keyingisi (qaysi holatda).
Bot uchun kalit: settings.ZONA["BOT_API_KEY"] yoki ZONA_BOT_API_KEY muhit o'zgaruvchisi, X-Bot-Key sarlavhasida.
"""
import hmac
import json

from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import BasePermission

from . import conf, translation
from .api import zona_api
from .models import Member, Task, Zone
from .permissions import CanView
from .search import search as run_search


class BotOrViewer(BasePermission):
    """Bot kaliti to'g'ri bo'lsa — tizimga kirmasdan; aks holda oddiy o'qish huquqi."""

    def has_permission(self, request, view):
        key = conf.get("BOT_API_KEY")
        sent = request.headers.get("X-Bot-Key", "")
        if key and sent and hmac.compare_digest(str(key), sent):
            return True
        return CanView().has_permission(request, view)


def _contact(m, lang=None):
    if not m:
        return None
    return {"id": m.id, "name": translation.current(m, "name", lang) if m.is_team else m.name,
            "role": translation.current(m, "role", lang), "phone": m.phone, "telegram": m.telegram.lstrip("@"),
            "email": m.email, "is_team": m.is_team}


def item(task, lang=None):
    """Bitta savol turi — bot va AI uchun to'liq ma'lumot."""
    p = task.process
    cur = lambda obj, f: translation.current(obj, f, lang) if obj else ""  # noqa: E731
    return {
        "id": task.id,
        "zone": cur(p.zone, "name") if p and p.zone else "",
        "process": cur(p, "name"),
        "system": cur(p.system, "name") if p and p.system else "",
        "question": cur(task, "title"),
        "examples": list(task.examples or []),
        "rule": cur(task, "rule"),
        "note": cur(task, "note"),
        "asker": task.asker,
        "frequent": task.frequent,
        "responsible": _contact(task.owner, lang),
        "escalation": [{**(_contact(f.member, lang) or {}), "condition": cur(f, "condition")}
                       for f in task.fallbacks.select_related("member").order_by("order")],
    }


def answer_text(it):
    """Telegram'ga tayyor javob matni (oddiy matn, Markdown'siz — har qanday botda xavfsiz)."""
    def who(c):
        if not c:
            return "mas'ul belgilanmagan"
        bits = [f"{c['name']} ({c['role']})"]
        if c.get("phone"):
            bits.append(c["phone"])
        if c.get("telegram"):
            bits.append("@" + c["telegram"])
        return " · ".join(bits)

    lines = [f"Savol: {it['question']}"]
    if it["zone"] or it["process"]:
        lines.append("Zona: " + " → ".join(x for x in (it["zone"], it["process"]) if x))
    lines.append(f"Kim javob beradi: {who(it['responsible'])}")
    if it["rule"]:
        lines.append(f"Qoida: {it['rule']}")
    for n, e in enumerate(it["escalation"], start=2):
        cond = f" — {e['condition']}" if e.get("condition") else ""
        lines.append(f"{n}-navbat: {who(e)}{cond}")
    return "\n".join(lines)


@zona_api(["POST"], [BotOrViewer])
def bot_ask(request):
    """{"question": "...", "lang": "uz"} -> eng mos savol turi, qoida, mas'ul va kontaktlari."""
    question = str(request.data.get("question") or "").strip()[:500]
    lang = str(request.data.get("lang") or "") or translation.request_lang(request)
    if len(question) < 3:
        return _bad("Savol matnini yuboring (kamida 3 belgi).")
    res = run_search(question, 5, lang)
    tasks = {t.id: t for t in Task.objects.filter(id__in=[x["id"] for x in res["tasks"]])
             .select_related("process__zone", "process__system", "owner").prefetch_related("fallbacks__member")}
    ranked = [item(tasks[x["id"]], lang) for x in res["tasks"] if x["id"] in tasks]
    people = res["people"]
    confidence = people[0]["confidence"] if people else 0
    best = ranked[0] if ranked else None
    found = bool(best) and confidence >= 35
    members = {m.id: m for m in Member.objects.filter(id__in=[p["member"] for p in people])}
    return _json({
        "question": question,
        "found": found,
        "confidence": confidence,
        "answer_text": answer_text(best) if found else
        "Bu savol bo'yicha aniq qoida topilmadi. Savolni batafsilroq yozing yoki supervayzeringizga murojaat qiling.",
        "best": best,
        "alternatives": ranked[1:4],
        "people": [{**(_contact(members.get(p["member"]), lang) or {}), "confidence": p["confidence"]}
                   for p in people[:3] if p["member"] in members],
    })


@zona_api(["GET"], [CanView])
def knowledge_export(request, fmt):
    """Savollar bazasini AI uchun yuklab olish.

    json  — to'liq ro'yxat (zona, jarayon, savol, misollar, qoida, mas'ul, navbat);
    jsonl — har qatorda bitta savol (RAG / vektor bazasi uchun);
    chat  — fine-tuning uchun: har bir misol savol -> tayyor javob (messages formatida);
    md    — odam o'qishi uchun hujjat."""
    lang = request.query_params.get("lang") or translation.request_lang(request)
    only = request.query_params.get("frequent") in ("1", "true")
    qs = (Task.objects.select_related("process__zone", "process__system", "owner")
          .prefetch_related("fallbacks__member").order_by("process__zone__order", "process__order", "order", "id"))
    if only:
        qs = qs.filter(frequent=True)
    items = [item(t, lang) for t in qs]
    stamp = timezone.localdate().isoformat()
    if fmt == "json":
        body = json.dumps({"generated": stamp, "zones": [{"name": translation.current(z, "name", lang),
                                                         "description": translation.current(z, "description", lang)}
                                                        for z in Zone.objects.all()],
                           "items": items}, ensure_ascii=False, indent=2)
        return _file(body, f"savollar-{stamp}.json", "application/json")
    if fmt == "jsonl":
        body = "\n".join(json.dumps({**it, "answer": answer_text(it)}, ensure_ascii=False) for it in items) + "\n"
        return _file(body, f"savollar-{stamp}.jsonl", "application/x-ndjson")
    if fmt == "chat":
        system = (f"Siz {conf.get('COMPANY_NAME')} kompaniyasining yordamchi botisiz. Xodim savoliga qaysi zona ekanini, "
                  "aniq qoidani va kim javob berishini (kontaktlari bilan) qisqa ayting.")
        lines = []
        for it in items:
            for q in [it["question"], *it["examples"]]:
                lines.append(json.dumps({"messages": [{"role": "system", "content": system},
                                                      {"role": "user", "content": q},
                                                      {"role": "assistant", "content": answer_text(it)}]},
                                        ensure_ascii=False))
        return _file("\n".join(lines) + "\n", f"savollar-chat-{stamp}.jsonl", "application/x-ndjson")
    if fmt == "md":
        out, zone, proc = [f"# Savollar bazasi — {conf.get('COMPANY_NAME')} ({stamp})", ""], None, None
        for it in items:
            if it["zone"] != zone:
                zone, proc = it["zone"], None
                out += [f"## {zone or 'Zonasiz'}", ""]
            if it["process"] != proc:
                proc = it["process"]
                out += [f"### {proc}", ""]
            out.append(f"**{it['question']}**" + (" · _doimiy_" if it["frequent"] else ""))
            if it["examples"]:
                out.append("Qanday so'raladi: " + "; ".join(f"“{e}”" for e in it["examples"]))
            out += [answer_text(it).split("\n", 1)[1] if "\n" in answer_text(it) else "", ""]
        return _file("\n".join(out), f"savollar-{stamp}.md", "text/markdown")
    return _bad("Format: json, jsonl, chat yoki md.")


def _json(data):
    return HttpResponse(json.dumps(data, ensure_ascii=False), content_type="application/json; charset=utf-8")


def _bad(text):
    return HttpResponse(json.dumps({"detail": text}, ensure_ascii=False), status=400, content_type="application/json; charset=utf-8")


def _file(body, name, ctype):
    resp = HttpResponse(body.encode("utf-8"), content_type=f"{ctype}; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    return resp

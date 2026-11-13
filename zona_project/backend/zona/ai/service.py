"""AI vazifalari: savolni yo'naltirish, xodim tahlili, tashkilot auditi.

Har bir vazifa AITaskConfig orqali o'z provayderi/modeli/effort/limitiga ega; asosiy model xato
bersa zaxira (fallback) model ishlatiladi. Har bir chaqiriq AIUsage jurnaliga yoziladi.
"""
import json
import time
from collections import defaultdict

from .. import conf
from ..models import (AITaskConfig, AIUsage, Authority, Department, EdgeCase, Member, Process, ProcessRole,
                      Task)
from . import providers
from .providers import AIError

DEFAULTS = {
    AITaskConfig.ROUTE: {"effort": "low", "max_tokens": 2500},
    AITaskConfig.PERSON: {"effort": "medium", "max_tokens": 4000},
    AITaskConfig.AUDIT: {"effort": "high", "max_tokens": 8000},
    AITaskConfig.TRANSLATE: {"effort": "low", "max_tokens": 8000},
}
LANGS = {"uz": "o'zbek (lotin)", "uz-cyrl": "o'zbek (kirill)", "ru": "rus", "en": "ingliz"}


class AIUnavailable(AIError):
    pass


def ensure_tasks():
    for key, _ in AITaskConfig.TASKS:
        AITaskConfig.objects.get_or_create(task=key, defaults=DEFAULTS[key])
    return list(AITaskConfig.objects.select_related("provider", "fallback_provider"))


def status():
    """Frontend uchun: qaysi AI vazifalari ishlaydi."""
    out = {}
    for cfg in ensure_tasks():
        out[cfg.task] = bool(cfg.enabled and cfg.provider and cfg.provider.is_active and cfg.model)
    return out


def _chain(cfg):
    chain = []
    if cfg.provider and cfg.provider.is_active and cfg.model:
        chain.append((cfg.provider, cfg.model))
    if cfg.fallback_provider and cfg.fallback_provider.is_active and (cfg.fallback_model or cfg.model):
        chain.append((cfg.fallback_provider, cfg.fallback_model or cfg.model))
    return chain


def run(task, user, label, system, message, schema):
    cfg = AITaskConfig.objects.select_related("provider", "fallback_provider").filter(task=task).first()
    if not cfg or not cfg.enabled:
        raise AIUnavailable("Bu AI vazifasi o'chirilgan. Administrator 'AI sozlamalari'da yoqishi mumkin.")
    chain = _chain(cfg)
    if not chain:
        raise AIUnavailable("AI vazifasi uchun provayder va model tanlanmagan.")
    if cfg.instructions:
        system += "\n\nQO'SHIMCHA KO'RSATMA (administrator):\n" + cfg.instructions
    last = None
    for provider, model in chain:
        t0 = time.monotonic()
        try:
            res = providers.call(provider, model, system, message, schema=schema, max_tokens=cfg.max_tokens,
                                 effort=cfg.effort if provider.kind in ("anthropic", "openai", "azure_openai", "xai", "openrouter") else "",
                                 temperature=cfg.temperature)
            data = providers.parse_json(res.text) if schema else {"text": res.text}
        except AIError as e:
            last = e
            _log(task, provider, model, user, label, t0, error=str(e))
            continue
        ms = _log(task, provider, model, user, label, t0, res=res)
        return data, {"provider": provider.name, "kind": provider.kind, "model": model,
                      "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "latency_ms": ms,
                      "fallback": provider != chain[0][0] or model != chain[0][1]}
    raise last


def _log(task, provider, model, user, label, t0, res=None, error=""):
    ms = int((time.monotonic() - t0) * 1000)
    AIUsage.objects.create(task=task, provider=provider.name, model=model, ok=not error, error=error[:500],
                           input_tokens=res.input_tokens if res else 0, output_tokens=res.output_tokens if res else 0,
                           latency_ms=ms, user=getattr(user, "username", "") or "", prompt=(label or "")[:300])
    return ms


# ------------------------------------------------------------------ kontekst
def org_context():
    """Butun tuzilma: AI faqat shu ma'lumotga tayanadi. Tartib barqaror (prompt keshlash uchun)."""
    deps = {d.id: d.name for d in Department.objects.all()}
    members = list(Member.objects.all())
    names = {m.id: m.name for m in members}
    auth = defaultdict(list)
    for a in Authority.objects.all():
        auth[a.member_id].append(a.title + (f" ({a.scope})" if a.scope else ""))
    roles = defaultdict(lambda: defaultdict(list))
    for r in ProcessRole.objects.order_by("process_id", "role", "member_id"):
        roles[r.process_id][r.role].append(r.member_id)
    tasks = defaultdict(list)
    loose = []
    for t in Task.objects.order_by("order", "id").prefetch_related("fallbacks"):
        row = [t.id, t.title, t.owner_id]
        chain = [{"id": f.member_id, **({"when": f.condition} if f.condition else {})} for f in t.fallbacks.all()]
        if chain:
            row.append(chain)
        (tasks[t.process_id] if t.process_id else loose).append(row)
    people = [{
        "id": m.id, "name": m.name, "role": m.role, "department": deps.get(m.department_id),
        "manager_id": m.manager_id, "team": m.is_team, "receives_questions_about": m.trigger,
        "does": m.does, "does_not": m.excludes, "authorities": auth.get(m.id, []),
    } for m in members]
    procs = [{
        "id": p.id, "name": p.name, "system": p.system.name if p.system else None,
        **({"description": p.description} if p.description else {}),
        "roles": {k: v for k, v in sorted(roles[p.id].items())},
        "tasks": tasks.get(p.id, []),
    } for p in Process.objects.select_related("system").order_by("order", "id")]
    edges = [{"situation": e.situation, "first_contact_id": e.first_owner_id, "then": e.then_text}
             for e in EdgeCase.objects.order_by("order", "id")]
    ctx = {"company": conf.get("COMPANY_NAME"), "people": people, "processes": procs,
           "tasks_without_process": loose, "edge_cases": edges,
           "legend": {"tasks": "[task_id, savol turi, mas'ul xodim id (null = biriktirilmagan), "
                               "ixtiyoriy: navbatdagi mas'ullar [{id, when}] — asosiy mas'ul qila olmasa, tartib bilan]",
                      "roles": "owner=egasi, approver=tasdiqlovchi, supervisor=nazoratchi, contributor=yordamchi, backup=zaxira"}}
    return json.dumps(ctx, ensure_ascii=False, separators=(",", ":")), names


BASE_RULES = """Sen {company} kompaniyasining "mas'uliyat arxitekturasi" bo'yicha yordamchisisan.
Faqat quyidagi TUZILMA ma'lumotiga tayan. Tuzilmada yo'q odam, jarayon yoki vazifani o'ylab topma.
Har bir xodimning "does_not" maydoni: u bu ishlar bilan shug'ullanmaydi va kimga borishini aytadi; shunga amal qil.
"edge_cases" — chegaradagi holatlar uchun aniq qoidalar: savol shunga o'xshasa, avval "first_contact_id" ga yo'naltir.
Javobingni JSON formatida qaytar."""


# ------------------------------------------------------------------ 1. Savol kimga
ROUTE_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "summary": {"type": "string"},
        "candidates": {"type": "array", "items": {
            "type": "object",
            "properties": {"member_id": {"type": "integer"}, "confidence": {"type": "number"},
                           "role": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["member_id", "confidence", "role", "reason"], "additionalProperties": False}},
        "process_ids": {"type": "array", "items": {"type": "integer"}},
        "task_ids": {"type": "array", "items": {"type": "integer"}},
        "answer": {"type": "string"},
        "needs_clarification": {"type": "boolean"},
        "clarifying_question": {"type": "string"},
    },
    "required": ["language", "summary", "candidates", "process_ids", "task_ids", "answer",
                 "needs_clarification", "clarifying_question"],
    "additionalProperties": False,
}

ROUTE_TASK = """VAZIFA: foydalanuvchi (agent, supervayzer yoki xodim) savol yoki muammoni o'z so'zlari bilan yozadi:
o'zbek (lotin yoki kirill), rus, ingliz yoki aralash tilda, imlo xatolari va qisqartmalar bilan.
Uning MA'NOSINI tushun va savolni kimga yo'naltirish kerakligini aniqla.
- candidates: 1-3 ta xodim, eng mosi birinchi. confidence 0..1. role: owner/executor/approver/... yoki "first_contact".
  Vazifada navbatdagi mas'ullar bo'lsa, ularni ham shu tartibda role="fallback" bilan qo'sh va answer da ayt:
  avval kimga, u qila olmasa kimga (va "when" shartini).
  reason: nega aynan u (qaysi vazifa yoki qoida asosida), qisqa.
- task_ids / process_ids: savolga eng mos 1-5 ta vazifa va jarayon id lari.
- summary: savol mazmuni bir jumlada.
- answer: foydalanuvchiga amaliy javob — kimga, nima deb murojaat qilish kerak. 2-4 jumla.
- language: savol tili (uz, uz-cyrl, ru, en). summary, reason va answer ni SHU tilda yoz.
- Savol juda noaniq bo'lsa needs_clarification=true va clarifying_question da bitta aniqlashtiruvchi savol ber;
  baribir eng ehtimoliy nomzodlarni ko'rsat. Aks holda clarifying_question bo'sh satr."""


def route(question, user, hints=None):
    ctx, names = org_context()
    system = BASE_RULES.format(company=conf.get("COMPANY_NAME")) + "\n\n" + ROUTE_TASK + "\n\nTUZILMA:\n" + ctx
    msg = f"SAVOL:\n{question.strip()}"
    if hints:
        msg += "\n\nMahalliy qidiruv taxminlari (xato bo'lishi mumkin, faqat yordam uchun):\n" + hints
    data, meta = run(AITaskConfig.ROUTE, user, question, system, msg, ROUTE_SCHEMA)
    tasks = set(Task.objects.values_list("id", flat=True))
    procs = set(Process.objects.values_list("id", flat=True))
    cands, seen = [], set()
    for c in data.get("candidates") or []:
        try:
            mid = int(c.get("member_id"))
        except (TypeError, ValueError):
            continue
        if mid in names and mid not in seen:
            seen.add(mid)
            conf_ = max(0.0, min(1.0, float(c.get("confidence") or 0)))
            cands.append({"member": mid, "confidence": round(conf_ * 100), "role": str(c.get("role") or "")[:40],
                          "reason": str(c.get("reason") or "")[:600]})
    return {
        "language": str(data.get("language") or ""),
        "summary": str(data.get("summary") or ""),
        "answer": str(data.get("answer") or ""),
        "needs_clarification": bool(data.get("needs_clarification")),
        "clarifying_question": str(data.get("clarifying_question") or ""),
        "candidates": cands[:3],
        "task_ids": [i for i in data.get("task_ids") or [] if isinstance(i, int) and i in tasks][:5],
        "process_ids": [i for i in data.get("process_ids") or [] if isinstance(i, int) and i in procs][:5],
    }, meta


# ------------------------------------------------------------------ 2-3. Tahlil
TEXT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
               "additionalProperties": False}

PERSON_TASK = """VAZIFA: rahbar uchun bitta xodimning mas'uliyat xaritasini tahlil qil (id={mid}, {name}).
Markdown formatida (## sarlavhalar, - ro'yxatlar, **qalin**), qisqa va aniq yoz. Bo'limlar:
## Asosiy mas'uliyat — qaysi jarayonlarning egasi, nechta vazifa.
## Vakolatlar — nimani tasdiqlaydi yoki hal qiladi.
## Chegaralar — nima bilan shug'ullanmaydi va bunday savollar kimga boradi.
## Aloqalar — kim bilan bir jarayonda ishlaydi, rahbari va qo'l ostidagilar.
## Xavflar — zaxirasiz jarayonlar, yuklama, kesishgan mas'uliyat, noaniqliklar.
## Tavsiyalar — 3-5 ta aniq taklif.
Til: {lang}."""

AUDIT_TASK = """VAZIFA: butun tashkilotning mas'uliyat arxitekturasini audit qil. Markdown (## sarlavhalar, ro'yxatlar).
## Umumiy xulosa — 3-4 jumla.
## Bo'shliqlar — egasiz jarayonlar, mas'ulsiz vazifalar, zaxirasi yo'q muhim jarayonlar.
## Kesishmalar — bir ish bir necha kishida, chegarasi noaniq zonalar.
## Yuklama — kimda ortiqcha, kimda kam.
## Tavsiyalar — ustuvorlik bo'yicha 5-8 ta aniq qadam (kim, nima).
Raqamlarni tuzilmadan hisobla, taxmin qilma. Til: {lang}."""


def person(member_id, user, lang="uz"):
    m = Member.objects.filter(pk=member_id).first()
    if not m:
        raise AIError("Xodim topilmadi")
    ctx, _ = org_context()
    system = (BASE_RULES.format(company=conf.get("COMPANY_NAME")) + "\n\n"
              + PERSON_TASK.format(mid=m.id, name=m.name, lang=LANGS.get(lang, LANGS["uz"])) + "\n\nTUZILMA:\n" + ctx)
    data, meta = run(AITaskConfig.PERSON, user, f"Xodim tahlili: {m.name}", system,
                     f"{m.name} (id={m.id}) bo'yicha tahlil tayyorla.", TEXT_SCHEMA)
    return {"text": str(data.get("text") or "")}, meta


def audit(user, lang="uz"):
    ctx, _ = org_context()
    system = (BASE_RULES.format(company=conf.get("COMPANY_NAME")) + "\n\n"
              + AUDIT_TASK.format(lang=LANGS.get(lang, LANGS["uz"])) + "\n\nTUZILMA:\n" + ctx)
    data, meta = run(AITaskConfig.AUDIT, user, "Tashkilot auditi", system, "Audit hisobotini tayyorla.", TEXT_SCHEMA)
    return {"text": str(data.get("text") or "")}, meta

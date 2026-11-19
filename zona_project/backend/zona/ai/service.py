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
    AITaskConfig.WORKLOAD: {"effort": "medium", "max_tokens": 8000},
    AITaskConfig.SUPPORT: {"effort": "low", "max_tokens": 1500},
}

# Sinov uchun bepul standart: Google Gemini (AI Studio kaliti bepul, kredit karta shart emas).
# "-latest" taxalluslari Google eng yangi Flash modeliga avtomatik ulaydi — model nomi eskirib qolmaydi.
FREE_PROVIDER = {"name": "Google Gemini (bepul)", "kind": "gemini"}
FREE_MODEL, FREE_FALLBACK = "gemini-flash-latest", "gemini-flash-lite-latest"


def ensure_free_default():
    """Hech qanday provayder sozlanmagan bo'lsa — bepul Gemini'ni standart qilib qo'yadi.
    Kalit ZONA_GEMINI_API_KEY muhit o'zgaruvchisidan olinadi yoki keyin "AI sozlamalari"da kiritiladi."""
    import os

    from ..crypto import encrypt
    from ..models import AIProvider
    if AIProvider.objects.exists():
        return None
    key = os.environ.get("ZONA_GEMINI_API_KEY", "").strip()
    provider = AIProvider.objects.create(name=FREE_PROVIDER["name"], kind=FREE_PROVIDER["kind"], is_active=True,
                                         api_key_enc=encrypt(key) if key else "")
    for cfg in AITaskConfig.objects.all():
        if not cfg.provider_id:
            cfg.provider, cfg.model = provider, FREE_MODEL
            cfg.fallback_provider, cfg.fallback_model = provider, FREE_FALLBACK
            cfg.enabled = True
            cfg.save()
    return provider
LANGS = {"uz": "o'zbek (lotin)", "uz-cyrl": "o'zbek (kirill)", "ru": "rus", "en": "ingliz"}


class AIUnavailable(AIError):
    pass


def ensure_tasks():
    for key, _ in AITaskConfig.TASKS:
        AITaskConfig.objects.get_or_create(task=key, defaults=DEFAULTS[key])
    ensure_free_default()
    # yangi vazifa qo'shilganda (masalan, yuklama tahlili) — boshqa vazifalar ishlatgan provayder bilan to'ldiriladi
    donor = AITaskConfig.objects.filter(enabled=True, provider__isnull=False).exclude(model="").first()
    if donor:
        for cfg in AITaskConfig.objects.filter(provider__isnull=True):
            cfg.provider, cfg.model, cfg.enabled = donor.provider, donor.model, True
            cfg.fallback_provider, cfg.fallback_model = donor.fallback_provider, donor.fallback_model
            cfg.save()
    return list(AITaskConfig.objects.select_related("provider", "fallback_provider"))


def _ready(provider):
    """Provayder ishlashga tayyormi: faol va (kerak bo'lsa) API kaliti kiritilgan."""
    if not provider or not provider.is_active:
        return False
    return not providers.PRESETS.get(provider.kind, {}).get("key") or bool(providers.api_key(provider))


def status():
    """Frontend uchun: qaysi AI vazifalari ishlaydi."""
    out = {}
    for cfg in ensure_tasks():
        out[cfg.task] = bool(cfg.enabled and cfg.model and _ready(cfg.provider))
    return out


# Asosiy/zaxira band bo'lsa avtomatik sinab ko'riladigan modellar (provayder turi bo'yicha, tejamkoridan)
AUTO_BACKUP = {
    "gemini": ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"],
    "anthropic": ["claude-haiku-5-5", "claude-sonnet-5-5"],
    "openai": ["gpt-5-mini"], "groq": ["llama-3.3-70b-versatile"], "deepseek": ["deepseek-chat"],
    "mistral": ["mistral-small-latest"], "openrouter": ["openrouter/auto"],
}
COOLDOWN = 120  # "band" degan model shuncha soniya zanjir oxiriga suriladi
_cool = {}


def _chain(cfg):
    """Asosiy -> zaxira -> admin qo'shgan zaxiralar -> o'sha va boshqa faol provayderlarning tejamkor modellari.
    Yaqinda band bo'lgan modellar oxiriga suriladi (lekin hammasi band bo'lsa ular ham sinab ko'riladi)."""
    from ..models import AIProvider
    chain, seen = [], set()

    def add(provider, model):
        if provider is not None and model and _ready(provider) and (provider.id, model) not in seen:
            seen.add((provider.id, model))
            chain.append((provider, model))

    add(cfg.provider, cfg.model)
    add(cfg.fallback_provider, cfg.fallback_model or cfg.model)
    providers_by_id = {p.id: p for p in AIProvider.objects.filter(is_active=True)}
    for row in cfg.extra_fallbacks or []:
        add(providers_by_id.get(row.get("provider")), row.get("model"))
    ordered = [p for p in (cfg.provider, cfg.fallback_provider) if p] + [p for p in providers_by_id.values()
                                                                        if p not in (cfg.provider, cfg.fallback_provider)]
    for p in ordered:
        for model in AUTO_BACKUP.get(p.kind, []):
            add(p, model)
    now = time.monotonic()
    return [x for x in chain if _cool.get((x[0].id, x[1]), 0) <= now] + [x for x in chain if _cool.get((x[0].id, x[1]), 0) > now]


def run(task, user, label, system, message, schema):
    cfg = AITaskConfig.objects.select_related("provider", "fallback_provider").filter(task=task).first()
    if not cfg or not cfg.enabled:
        raise AIUnavailable("Bu AI vazifasi o'chirilgan. Administrator 'AI sozlamalari'da yoqishi mumkin.")
    chain = _chain(cfg)
    if not chain:
        if cfg.provider and cfg.provider.is_active and not _ready(cfg.provider):
            hint = providers.PRESETS.get(cfg.provider.kind, {}).get("docs", "")
            raise AIUnavailable(f"\"{cfg.provider.name}\" uchun API kalit kiritilmagan. Sozlamalar → AI bo'limida kiriting"
                                + (f" (bepul kalit: {hint})." if hint else "."))
        raise AIUnavailable("AI vazifasi uchun provayder va model tanlanmagan.")
    if cfg.instructions:
        system += "\n\nQO'SHIMCHA KO'RSATMA (administrator):\n" + cfg.instructions
    last, tried = None, []
    for provider, model in chain:
        t0 = time.monotonic()
        try:
            res = providers.call(provider, model, system, message, schema=schema, max_tokens=cfg.max_tokens,
                                 effort=cfg.effort if provider.kind in ("anthropic", "openai", "azure_openai", "xai", "openrouter") else "",
                                 temperature=cfg.temperature)
            data = providers.parse_json(res.text) if schema else {"text": res.text}
        except AIError as e:
            last = e
            tried.append(f"{provider.name}/{model}")
            if getattr(e, "status", None) in providers.RETRY_STATUS or "vaqt tugadi" in str(e) or "ulanib" in str(e):
                _cool[(provider.id, model)] = time.monotonic() + COOLDOWN  # band — keyingi so'rovlarda oxirga
            _log(task, provider, model, user, label, t0, error=str(e))
            continue
        ms = _log(task, provider, model, user, label, t0, res=res)
        _save(task, provider, model, user, label, message, data, res)
        return data, {"provider": provider.name, "kind": provider.kind, "model": model,
                      "input_tokens": res.input_tokens, "output_tokens": res.output_tokens, "latency_ms": ms,
                      "fallback": provider != chain[0][0] or model != chain[0][1]}
    if last is not None and getattr(last, "status", None) in providers.RETRY_STATUS:
        raise AIUnavailable(f"Barcha AI modellar hozir band ({len(tried)} ta sinab ko'rildi). Bir ozdan keyin qayta urining "
                            "yoki Sozlamalar → AI bo'limida boshqa provayder qo'shing.") from last
    raise last


def _save(task, provider, model, user, label, message, data, res):
    """AI natijasini saqlash (xato bo'lsa ham asosiy ish to'xtamasin)."""
    from ..models import AIAnalysis
    try:
        AIAnalysis.objects.create(task=task, label=(label or "")[:300], user=getattr(user, "username", "") or "",
                                  provider=provider.name, model=model, prompt=(message or "")[:20000],
                                  result=data if isinstance(data, dict) else {"value": data},
                                  input_tokens=res.input_tokens or 0, output_tokens=res.output_tokens or 0)
    except Exception:  # noqa: BLE001
        pass


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
    from .. import timeload
    ctx, _ = org_context()
    load = timeload.context_for_ai()
    time_ctx = json.dumps({"total_week_h": load["total_week_h"], "people": [
        {k: p[k] for k in ("id", "name", "capacity_h", "owner_h", "backup_h", "utilization_pct", "status")} for p in load["people"]],
        "heaviest_questions": load["heaviest_questions"][:15]}, ensure_ascii=False)
    system = (BASE_RULES.format(company=conf.get("COMPANY_NAME")) + "\n\n"
              + AUDIT_TASK.format(lang=LANGS.get(lang, LANGS["uz"])) + "\n\nTUZILMA:\n" + ctx
              + "\n\nVAQT YUKLAMASI (savol vaqti × haftasiga soni; bandlik = soat / sig'im). Auditda ortiqcha yuklama va "
                "vaqt jamlanishini ham baholang:\n" + time_ctx)
    data, meta = run(AITaskConfig.AUDIT, user, "Tashkilot auditi", system, "Audit hisobotini tayyorla.", TEXT_SCHEMA)
    return {"text": str(data.get("text") or "")}, meta


# ------------------------------------------------------------------ 5. Yuklama tahlili (vaqt asosida)
WORKLOAD_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "overloaded": {"type": "array", "items": {"type": "object", "properties": {
            "member_id": {"type": "integer"}, "reason": {"type": "string"}}, "required": ["member_id", "reason"]}},
        "recommendations": {"type": "array", "items": {"type": "object", "properties": {
            "kind": {"type": "string", "enum": ["reassign", "share", "automate", "capacity", "hire", "rule", "estimate"]},
            "title": {"type": "string"}, "detail": {"type": "string"},
            "task_ids": {"type": "array", "items": {"type": "integer"}},
            "from_id": {"type": ["integer", "null"]}, "to_id": {"type": ["integer", "null"]},
            "hours_per_week": {"type": "number"}, "priority": {"type": "string", "enum": ["high", "medium", "low"]}},
            "required": ["kind", "title", "detail", "priority"]}},
        "best_fit": {"type": "array", "items": {"type": "object", "properties": {
            "zone": {"type": "string"}, "member_id": {"type": "integer"}, "why": {"type": "string"}},
            "required": ["zone", "member_id", "why"]}},
        "risks": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "overloaded", "recommendations", "best_fit", "risks"],
}

WORKLOAD_TASK = """VAZIFA: ish yuklamasini VAQT bo'yicha tahlil qil va aniq tavsiyalar ber.
Ma'lumot real bazadan: har bir savol turi uchun bir martalik vaqt (min) va haftasiga soni (per_week), xodimning haftalik
sig'imi (capacity_h), mas'ul (owner_h) va zaxira (backup_h) soatlari, bandlik (utilization_pct), zonalar bo'yicha soatlar.
"source": auto — taxmin, manual — xodim kiritgan, ai — AI taxmini.
1) summary: 3-5 gapda umumiy holat (jami soat, kim ortiqcha yuklangan, qaysi zona eng og'ir).
2) overloaded: bandligi 85% dan oshganlar va sababi (qaysi savollar ko'p vaqt oladi).
3) recommendations: aniq va bajariladigan: qaysi savolni (task_ids) kimdan (from_id) kimga (to_id) o'tkazish va necha soat
   bo'shashi; yoki avtomatlashtirish (bot javob berishi mumkin bo'lgan oddiy savollar), sig'imni oshirish, yangi qoida.
   O'tkazishda xodimning duties va not_for maydonlariga amal qil: not_for dagi ishni unga berma.
4) best_fit: har bir zona uchun mas'uliyat yuzasidan eng mos xodim va nima uchun.
5) risks: bitta odamga bog'liq jarayonlar, zaxirasiz og'ir savollar, taxminiy (auto) vaqtlar ko'pligi.
Raqamlarni faqat berilgan ma'lumotdan ol. member_id va task_ids — faqat ma'lumotdagi id lar. Til: {lang}."""


def workload(user, lang="uz"):
    from .. import timeload
    ctx = timeload.context_for_ai()
    system = (BASE_RULES.format(company=conf.get("COMPANY_NAME")) + "\n\n" + WORKLOAD_TASK.format(lang=LANGS.get(lang, LANGS["uz"])))
    data, meta = run(AITaskConfig.WORKLOAD, user, "Yuklama tahlili", system,
                     "MA'LUMOT:\n" + json.dumps(ctx, ensure_ascii=False), WORKLOAD_SCHEMA)
    ids = {p["id"] for p in ctx["people"]}
    task_ids = {t.id for t in Task.objects.only("id")}
    # model o'ylab topgan id larni tozalash
    data["overloaded"] = [o for o in data.get("overloaded") or [] if o.get("member_id") in ids]
    for r in data.get("recommendations") or []:
        r["task_ids"] = [i for i in r.get("task_ids") or [] if i in task_ids]
        for k in ("from_id", "to_id"):
            if r.get(k) not in ids:
                r[k] = None
    data["best_fit"] = [b for b in data.get("best_fit") or [] if b.get("member_id") in ids]
    return data, meta


# ------------------------------------------------------------------ 6. Vaqtni AI bilan taxminlash
ESTIMATE_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "id": {"type": "integer"}, "minutes": {"type": "integer"}, "per_week": {"type": "number"}},
        "required": ["id", "minutes", "per_week"]}}},
    "required": ["items"],
}

ESTIMATE_TASK = """VAZIFA: har bir savol turi uchun real taxmin ber:
- minutes: bitta murojaatni bajarishga ketadigan vaqt, daqiqa ("ha/yo'q" javobi 2-5, oddiy o'zgartirish 5-15,
  dostup ochish 10-20, texnik nosozlik 20-60, integratsiya/dastur xatosi 60-240, yangi funksiya 240-960);
- per_week: har doim 1 deb qaytaring (takrorlanish haftasiga 1 marta deb hisoblanadi).
"frequent": true — doimiy tushadigan savol. Zona, jarayon, mas'ul va qoidaga qarab baholang. Faqat berilgan id lar."""


def estimate_times(user, limit=120):
    """Vaqti qo'lda kiritilmagan savollar uchun AI taxmini (manba: ai)."""
    tasks = list(Task.objects.exclude(time_source="manual").select_related("process__zone", "owner")[:limit])
    done = 0
    for i in range(0, len(tasks), 40):
        chunk = tasks[i:i + 40]
        payload = [{"id": t.id, "q": t.title, "zone": t.process.zone.name if t.process_id and t.process.zone_id else "",
                    "process": t.process.name if t.process_id else "", "owner": t.owner.name if t.owner else "",
                    "rule": t.rule[:200], "frequent": t.frequent} for t in chunk]
        data, meta = run(AITaskConfig.WORKLOAD, user, f"Vaqt taxmini: {len(chunk)} ta savol",
                         BASE_RULES.format(company=conf.get("COMPANY_NAME")) + "\n\n" + ESTIMATE_TASK,
                         json.dumps(payload, ensure_ascii=False), ESTIMATE_SCHEMA)
        valid = {t.id for t in chunk}
        for it in data.get("items") or []:
            try:
                tid, minutes, per_week = int(it["id"]), int(it["minutes"]), float(it["per_week"])
            except (KeyError, TypeError, ValueError):
                continue
            if tid in valid and 1 <= minutes <= 7200 and 0 <= per_week <= 2000:
                # takrorlanish haftasiga 1 marta deb olinadi — AI faqat bajarish vaqtini aniqlaydi
                Task.objects.filter(pk=tid).exclude(time_source="manual").update(minutes=minutes, per_week=1, time_source="ai")
                done += 1
    return {"updated": done, "total": len(tasks)}, meta if tasks else {}

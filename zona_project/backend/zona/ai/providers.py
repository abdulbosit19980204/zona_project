"""AI provayderlarga yagona interfeys.

- Anthropic Claude: rasmiy `anthropic` SDK (structured output, prompt keshlash, refusal fallback).
- Google Gemini: generateContent REST API.
- OpenAI va OpenAI-mos API'lar (xAI Grok, DeepSeek, Mistral, Groq, OpenRouter, Azure, Ollama, ...):
  /chat/completions. Modelga mos kelmagan parametrlar (temperature, max_tokens nomi, JSON rejimi)
  400 xatosida avtomatik olib tashlanadi.
"""
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .. import conf
from ..crypto import decrypt

PRESETS = {
    "anthropic": {"base_url": "https://api.anthropic.com", "key": True, "effort": True,
                  "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"],
                  "docs": "https://platform.claude.com/settings/keys"},
    "openai": {"base_url": "https://api.openai.com/v1", "key": True, "docs": "https://platform.openai.com/api-keys"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "key": True,
               "docs": "https://aistudio.google.com/apikey"},
    "xai": {"base_url": "https://api.x.ai/v1", "key": True, "docs": "https://console.x.ai"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "key": True, "docs": "https://platform.deepseek.com/api_keys"},
    "mistral": {"base_url": "https://api.mistral.ai/v1", "key": True, "docs": "https://console.mistral.ai/api-keys"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "key": True, "docs": "https://console.groq.com/keys"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "key": True, "docs": "https://openrouter.ai/keys"},
    "azure_openai": {"base_url": "https://<resurs>.openai.azure.com/openai/deployments", "key": True,
                     "hint": "Model maydoniga deployment nomini yozing; API versiyani kiriting."},
    "ollama": {"base_url": "http://localhost:11434/v1", "key": False, "hint": "Lokal server, kalit shart emas."},
    "openai_compatible": {"base_url": "", "key": False, "hint": "LM Studio, vLLM va boshqa /chat/completions API."},
}

# Bu modellarda Anthropic server tomonidagi refusal fallback yoqiladi.
CLAUDE_FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}


class AIError(Exception):
    pass


@dataclass
class Result:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


def base_url(provider):
    return (provider.base_url or PRESETS.get(provider.kind, {}).get("base_url", "")).rstrip("/")


def api_key(provider):
    return decrypt(provider.api_key_enc)


def _timeout():
    return conf.get("AI_TIMEOUT")


# ------------------------------------------------------------------ HTTP
def _http(method, url, headers=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "User-Agent": "zona-ai/2", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=_timeout()) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read()[:800].decode("utf-8", "replace")
        try:
            j = json.loads(detail)
            err = j.get("error", j)
            detail = err.get("message", detail) if isinstance(err, dict) else str(err)
        except ValueError:
            pass
        raise HTTPFail(e.code, detail) from None
    except urllib.error.URLError as e:
        raise AIError(f"Provayderga ulanib bo'lmadi: {e.reason}") from None
    except TimeoutError:
        raise AIError("Provayder javob bermadi (vaqt tugadi)") from None


class HTTPFail(AIError):
    def __init__(self, status, detail):
        self.status = status
        hint = {401: "API kalit noto'g'ri", 403: "Ruxsat yo'q", 404: "Model yoki manzil topilmadi",
                429: "So'rovlar limiti yoki balans tugagan"}.get(status, f"HTTP {status}")
        super().__init__(f"{hint}: {detail}"[:480])


# ------------------------------------------------------------------ Anthropic
def _anthropic_client(provider):
    try:
        import anthropic
    except ImportError as e:
        raise AIError("anthropic paketi o'rnatilmagan: pip install stargroup-zona[ai]") from e
    return anthropic, anthropic.Anthropic(api_key=api_key(provider) or None, base_url=provider.base_url or None,
                                          timeout=_timeout(), max_retries=1)


def _call_anthropic(provider, model, system, user, schema, max_tokens, effort, temperature):
    anthropic, client = _anthropic_client(provider)
    output_config = {}
    if effort:
        output_config["effort"] = effort
    if schema:
        output_config["format"] = {"type": "json_schema", "schema": schema}
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        # tuzilma kamdan-kam o'zgaradi: tizim ko'rsatmasi keshlanadi
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
    }
    if output_config:
        kwargs["output_config"] = output_config
    try:
        if model in CLAUDE_FALLBACK_MODELS:
            resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            resp = client.messages.create(**kwargs)
    except anthropic.AuthenticationError:
        raise AIError("Claude: API kalit noto'g'ri") from None
    except anthropic.PermissionDeniedError as e:
        raise AIError(f"Claude: ruxsat yo'q ({e.message})") from None
    except anthropic.NotFoundError:
        raise AIError(f"Claude: '{model}' modeli topilmadi") from None
    except anthropic.RateLimitError:
        raise AIError("Claude: so'rovlar limiti oshdi, birozdan keyin urinib ko'ring") from None
    except anthropic.BadRequestError as e:
        raise AIError(f"Claude: so'rov rad etildi ({e.message})") from None
    except anthropic.APIStatusError as e:
        raise AIError(f"Claude: server xatosi ({e.status_code})") from None
    except anthropic.APIConnectionError:
        raise AIError("Claude: ulanib bo'lmadi") from None
    if resp.stop_reason == "refusal":
        raise AIError("Claude so'rovni bajarishdan bosh tortdi")
    if resp.stop_reason == "max_tokens":
        raise AIError("Javob max_tokens chegarasida uzilib qoldi: limitni oshiring")
    text = "".join(b.text for b in resp.content if b.type == "text")
    u = resp.usage
    inp = (u.input_tokens or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0) + (getattr(u, "cache_creation_input_tokens", 0) or 0)
    return Result(text, inp, u.output_tokens or 0)


def _models_anthropic(provider):
    anthropic, client = _anthropic_client(provider)
    try:
        return [m.id for m in client.models.list()]
    except anthropic.AuthenticationError:
        raise AIError("Claude: API kalit noto'g'ri") from None
    except anthropic.APIError as e:
        raise AIError(f"Claude: {getattr(e, 'message', e)}") from None


# ------------------------------------------------------------------ Gemini
def _call_gemini(provider, model, system, user, schema, max_tokens, effort, temperature):
    url = f"{base_url(provider)}/models/{model}:generateContent"
    gen = {"maxOutputTokens": max_tokens}
    if temperature is not None:
        gen["temperature"] = temperature
    if schema:
        gen["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": gen}
    headers = {"x-goog-api-key": api_key(provider)}
    try:
        data = _http("POST", url, headers, body)
    except HTTPFail as e:
        if e.status != 400:
            raise
        gen.pop("responseMimeType", None)
        gen.pop("temperature", None)
        data = _http("POST", url, headers, body)
    cands = data.get("candidates") or []
    if not cands:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "bo'sh javob")
        raise AIError(f"Gemini javob bermadi: {reason}")
    if cands[0].get("finishReason") in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST"):
        raise AIError("Gemini xavfsizlik filtri javobni to'xtatdi")
    text = "".join(p.get("text", "") for p in cands[0].get("content", {}).get("parts", []) if not p.get("thought"))
    u = data.get("usageMetadata", {})
    return Result(text, u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0))


def _models_gemini(provider):
    data = _http("GET", f"{base_url(provider)}/models?pageSize=200", {"x-goog-api-key": api_key(provider)})
    return [m["name"].split("/", 1)[-1] for m in data.get("models", [])
            if "generateContent" in m.get("supportedGenerationMethods", [])]


# ------------------------------------------------------------------ OpenAI-mos
def _oa_headers(provider):
    key = api_key(provider)
    if provider.kind == "azure_openai":
        return {"api-key": key}
    return {"Authorization": f"Bearer {key}"} if key else {}


def _oa_url(provider, model, path="chat/completions"):
    base = base_url(provider)
    if not base:
        raise AIError("Provayder manzili (base URL) kiritilmagan")
    if provider.kind == "azure_openai":
        return f"{base}/{model}/{path}?api-version={provider.api_version or '2024-10-21'}"
    return f"{base}/{path}"


def _call_openai(provider, model, system, user, schema, max_tokens, effort, temperature):
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    limit_key = "max_completion_tokens" if provider.kind in ("openai", "azure_openai") else "max_tokens"
    body[limit_key] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    if schema:
        body["response_format"] = {"type": "json_object"}
    if effort and provider.kind in ("openai", "azure_openai", "xai", "openrouter"):
        body["reasoning_effort"] = {"xhigh": "high", "max": "high"}.get(effort, effort)
    url, headers = _oa_url(provider, model), _oa_headers(provider)
    # modelga mos kelmagan parametrlarni bosqichma-bosqich olib tashlash
    steps = [
        lambda b: (b.pop("reasoning_effort", None), b.pop("temperature", None)),
        lambda b: b.update({("max_tokens" if limit_key == "max_completion_tokens" else "max_completion_tokens"): b.pop(limit_key)}),
        lambda b: b.pop("response_format", None),
    ]
    for i in range(len(steps) + 1):
        try:
            data = _http("POST", url, headers, body)
            break
        except HTTPFail as e:
            if e.status not in (400, 422) or i == len(steps):
                raise
            steps[i](body)
    choice = (data.get("choices") or [{}])[0]
    if choice.get("finish_reason") == "length":
        raise AIError("Javob max_tokens chegarasida uzilib qoldi: limitni oshiring")
    msg = choice.get("message") or {}
    text = msg.get("content") or ""
    if isinstance(text, list):
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
    u = data.get("usage") or {}
    return Result(text, u.get("prompt_tokens", 0), u.get("completion_tokens", 0))


def _models_openai(provider):
    if provider.kind == "azure_openai":
        return []
    data = _http("GET", _oa_url(provider, "", "models"), _oa_headers(provider))
    return sorted(m.get("id") for m in data.get("data", []) if m.get("id"))


# ------------------------------------------------------------------ umumiy
def call(provider, model, system, user, schema=None, max_tokens=4000, effort="", temperature=None):
    if not model:
        raise AIError("Model tanlanmagan")
    if PRESETS.get(provider.kind, {}).get("key") and not api_key(provider):
        raise AIError("API kalit kiritilmagan (yoki SECRET_KEY o'zgargani uchun o'qib bo'lmadi)")
    if schema and provider.kind != "anthropic":
        system += "\n\nJavobni FAQAT shu JSON sxemaga mos yagona JSON obyekt sifatida qaytar:\n" + json.dumps(schema, ensure_ascii=False)
    fn = {"anthropic": _call_anthropic, "gemini": _call_gemini}.get(provider.kind, _call_openai)
    return fn(provider, model, system, user, schema, max_tokens, effort or None, temperature)


def list_models(provider):
    fn = {"anthropic": _models_anthropic, "gemini": _models_gemini}.get(provider.kind, _models_openai)
    return fn(provider)


def check(provider):
    t0 = time.monotonic()
    models = list_models(provider)
    return {"ok": True, "models": models, "latency_ms": int((time.monotonic() - t0) * 1000)}


def parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    raise AIError("Model to'g'ri JSON qaytarmadi")

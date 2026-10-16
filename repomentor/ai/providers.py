"""Zero-cost LLM providers behind one tiny HTTP client.

* Ollama   – runs locally, unlimited and free (default).
* Groq     – free tier, needs a free API key.
* Gemini   – Google AI Studio free tier (OpenAI-compatible endpoint).
* OpenRouter – only models with the `:free` suffix are offered.

No vendor SDK is needed; everything is plain `requests`, which keeps the
dependency list short and the behaviour identical across providers.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Callable

import requests


class LLMError(Exception):
    """User-facing (Turkish) error from an LLM provider."""


class SchemaUnsupported(LLMError):
    """Ollama rejected a JSON-schema `format`; retry with plain JSON mode."""


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    base_url: str
    default_model: str
    needs_key: bool
    key_env: str | None
    signup_url: str
    context_chars: int          # prompt budget; keeps free-tier token limits safe
    note: str = ""


PROVIDERS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec(
        "ollama", "Ollama (yerel)", "http://localhost:11434", "qwen2.5-coder:7b",
        False, None, "https://ollama.com/download", 12_000,
        "Bilgisayarınızda çalışır; kodunuz dışarı çıkmaz. Sınırsız ve ücretsiz.",
    ),
    "groq": ProviderSpec(
        "groq", "Groq", "https://api.groq.com/openai/v1", "llama-3.3-70b-versatile",
        True, "GROQ_API_KEY", "https://console.groq.com/keys", 12_000,
        "Ücretsiz katman, çok hızlı. Kredi kartı gerekmez; dakikalık ve günlük token sınırı vardır.",
    ),
    "gemini": ProviderSpec(
        "gemini", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash",
        True, "GEMINI_API_KEY", "https://aistudio.google.com/apikey", 30_000,
        "Ücretsiz katman; anahtar Google AI Studio'dan alınır. Ücretsiz katmanda gönderilen veriler Google tarafından ürün geliştirmede kullanılabilir.",
    ),
    "openrouter": ProviderSpec(
        "openrouter", "OpenRouter", "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free",
        True, "OPENROUTER_API_KEY", "https://openrouter.ai/keys", 16_000,
        "Yalnızca adı ':free' ile biten ücretsiz modeller listelenir; ücretli modele istek gönderilmez.",
    ),
}

# Preferred local models, best first, matched by prefix against `ollama list`.
OLLAMA_PREFERENCE = ("qwen2.5-coder:14b", "qwen2.5-coder:7b", "qwen3", "qwen2.5:7b", "llama3.1:8b", "gemma3", "qwen2.5-coder", "qwen2.5", "llama3.2", "mistral", "phi")
NON_CHAT_MARKERS = ("whisper", "tts", "embed", "guard", "vision-preview", "playai", "distil", "orpheus", "imagen", "veo", "aqa", "learnlm", "image")


@dataclass
class LLMConfig:
    provider: str
    model: str
    api_key: str | None = None
    base_url: str | None = None
    temperature: float = 0.2
    max_output_tokens: int | None = None   # None -> provider default (local models get a tighter cap)
    timeout: float = 180                   # per request; for Ollama streaming: max silence between tokens
    extra: dict = field(default_factory=dict)

    @property
    def spec(self) -> ProviderSpec:
        return PROVIDERS[self.provider]

    @property
    def url(self) -> str:
        return base_url_for(self.provider, self.base_url)

    @property
    def context_chars(self) -> int:
        return self.spec.context_chars

    @property
    def output_tokens(self) -> int:
        """Small local models are slow (~15-40 tokens/s); keep their answers short."""
        return self.max_output_tokens or (1400 if self.provider == "ollama" else 2000)


def base_url_for(provider: str, override: str | None = None) -> str:
    if override:
        return override.rstrip("/")
    if provider == "ollama" and os.getenv("OLLAMA_BASE_URL"):
        return os.environ["OLLAMA_BASE_URL"].rstrip("/")
    return PROVIDERS[provider].base_url


def resolve_api_key(provider: str, given: str | None = None) -> str | None:
    """UI input first, then environment / Streamlit secrets."""
    if given:
        return given.strip()
    spec = PROVIDERS[provider]
    if not spec.key_env:
        return None
    if value := os.getenv(spec.key_env):
        return value
    try:  # Streamlit Community Cloud stores keys in st.secrets
        import streamlit as st

        return st.secrets.get(spec.key_env)  # type: ignore[no-any-return]
    except Exception:
        return None


def _headers(config: LLMConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    if config.provider == "openrouter":
        headers["X-Title"] = "RepoMentor AI"
    return headers


def _friendly_error(status: int, body: str, config: LLMConfig) -> LLMError:
    if status in (401, 403):
        return LLMError(f"{config.spec.label}: API anahtarı geçersiz veya yetkisiz. Anahtarı {config.spec.signup_url} adresinden kontrol edin.")
    if status == 429:
        return LLMError(f"{config.spec.label}: ücretsiz katman istek/token sınırına ulaşıldı. Biraz bekleyin veya başka bir ücretsiz sağlayıcı seçin.")
    if status == 404:
        return LLMError(f"Model bulunamadı: `{config.model}`. Listeden başka bir model seçin.")
    if status == 413 or "context" in body.lower() and "length" in body.lower():
        return LLMError("İstek modelin bağlam sınırını aştı. Daha büyük bağlamlı bir model seçin.")
    return LLMError(f"{config.spec.label} hata döndürdü (HTTP {status}): {body[:200]}")


def _post_with_retry(url: str, payload: dict, config: LLMConfig, attempts: int = 3) -> requests.Response:
    last: requests.Response | None = None
    for attempt in range(attempts):
        try:
            resp = requests.post(url, json=payload, headers=_headers(config), timeout=config.timeout)
        except requests.ConnectionError as exc:
            if config.provider == "ollama":
                raise LLMError("Ollama'ya bağlanılamadı. Ollama uygulamasının açık olduğundan emin olun (`ollama serve`).") from exc
            raise LLMError(f"{config.spec.label} sunucusuna bağlanılamadı.") from exc
        except requests.Timeout as exc:
            raise LLMError(f"Model {config.timeout:.0f} saniye içinde yanıt vermedi. Daha küçük/hızlı bir model deneyin.") from exc
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
            return resp
        last = resp
        wait = min(float(resp.headers.get("retry-after", 2 ** (attempt + 1))), 20)
        time.sleep(wait)
    assert last is not None
    return last


TokenProgress = Callable[[int], None]
MAX_STREAM_SECONDS = 600


def _ollama_stream(config: LLMConfig, payload: dict, on_tokens: TokenProgress | None) -> str:
    """Stream the answer so a slow local model never hits a fixed total timeout,
    and the UI can show how far it has got."""
    started, parts = time.monotonic(), []
    try:
        with requests.post(f"{config.url}/api/chat", json=payload, stream=True, timeout=(10, config.timeout)) as resp:
            if resp.status_code == 400 and isinstance(payload["format"], dict):
                raise SchemaUnsupported(resp.text[:200])
            if resp.status_code != 200:
                raise _friendly_error(resp.status_code, resp.text, config)
            for count, line in enumerate(resp.iter_lines(), 1):
                chunk = json.loads(line) if line else {}
                parts.append(chunk.get("message", {}).get("content", ""))
                if on_tokens and count % 20 == 0:
                    on_tokens(count)
                if chunk.get("done") or time.monotonic() - started > MAX_STREAM_SECONDS:
                    break
    except requests.ConnectionError as exc:
        raise LLMError("Ollama'ya bağlanılamadı. Ollama uygulamasının açık olduğundan emin olun (`ollama serve`).") from exc
    except requests.Timeout as exc:
        raise LLMError(f"Model {config.timeout:.0f} saniye boyunca yanıt üretmedi. Daha küçük bir model deneyin.") from exc
    return "".join(parts)


def _ollama_chat(config: LLMConfig, system: str, user: str, schema: dict | None, on_tokens: TokenProgress | None) -> str:
    payload = {
        "model": config.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": True,
        "format": schema or "json",
        "options": {"temperature": config.temperature, "num_ctx": 8192, "num_predict": config.output_tokens},
    }
    try:
        return _ollama_stream(config, payload, on_tokens)
    except SchemaUnsupported:
        payload["format"] = "json"   # very old Ollama without JSON-schema support
        return _ollama_stream(config, payload, on_tokens)


def _openai_compatible_chat(config: LLMConfig, system: str, user: str) -> str:
    payload = {
        "model": config.model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": config.temperature,
        "max_tokens": config.output_tokens,
        "response_format": {"type": "json_object"},
    }
    url = f"{config.url}/chat/completions"
    resp = _post_with_retry(url, payload, config)
    if resp.status_code == 400 and "response_format" in resp.text:
        payload.pop("response_format")
        resp = _post_with_retry(url, payload, config)
    if resp.status_code != 200:
        raise _friendly_error(resp.status_code, resp.text, config)
    try:
        return resp.json()["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError("Modelden beklenmeyen formatta yanıt geldi.") from exc


def chat_json(config: LLMConfig, system: str, user: str, schema: dict | None = None, on_tokens: TokenProgress | None = None) -> str:
    """Send one chat turn and return the raw text, asking for JSON output."""
    if config.provider == "ollama":
        return _ollama_chat(config, system, user, schema, on_tokens)
    return _openai_compatible_chat(config, system, user)


def model_size_billions(name: str) -> float | None:
    """Parameter count from an Ollama tag: `qwen2.5-coder:7b` → 7.0, `llama3.2:3b` → 3.0."""
    match = re.search(r":(\d+(?:\.\d+)?)b\b", name, re.I)
    return float(match.group(1)) if match else None


def ollama_available(base_url: str | None = None, timeout: float = 1.5) -> bool:
    try:
        return requests.get(f"{base_url_for('ollama', base_url)}/api/tags", timeout=timeout).ok
    except requests.RequestException:
        return False


def _ollama_models(base_url: str | None, timeout: float) -> list[str]:
    tags = requests.get(f"{base_url_for('ollama', base_url)}/api/tags", timeout=timeout).json()
    models = [m["name"] for m in tags.get("models", []) if not any(x in m["name"] for x in ("embed", "vision"))]

    def preference(name: str) -> int:
        return next((i for i, prefix in enumerate(OLLAMA_PREFERENCE) if name.startswith(prefix)), 99)

    return sorted(models, key=preference)


def _remote_models(provider: str, api_key: str, base_url: str | None, timeout: float) -> list[str]:
    resp = requests.get(f"{base_url_for(provider, base_url)}/models", headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout)
    if not resp.ok:
        return []
    return [m.get("id", "").removeprefix("models/") for m in resp.json().get("data", [])]


def _is_free_chat_model(provider: str, model_id: str) -> bool:
    if not model_id or any(marker in model_id.lower() for marker in NON_CHAT_MARKERS):
        return False
    if provider == "openrouter":
        return model_id.endswith(":free")
    if provider == "gemini":
        return model_id.startswith("gemini") and "pro" not in model_id
    return True


def list_models(provider: str, api_key: str | None = None, base_url: str | None = None, timeout: float = 8) -> list[str]:
    """Live model list so we never hard-code model names that may be retired."""
    spec = PROVIDERS[provider]
    try:
        if provider == "ollama":
            return _ollama_models(base_url, timeout)
        if not api_key:
            return []
        ids = _remote_models(provider, api_key, base_url, timeout)
    except (requests.RequestException, ValueError):
        return []
    return sorted((i for i in ids if _is_free_chat_model(provider, i)), key=lambda i: (i != spec.default_model, i))

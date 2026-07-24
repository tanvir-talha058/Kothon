"""Optional cloud API providers for rewrite and speech-to-text.

Kothon is offline by default; this module is only reached when the user has
explicitly enabled online features and supplied an API key. It is pure and
side-effect free — no app state, no key storage (see ``secrets_store``), no
logging of secrets — so it can be unit-tested by monkeypatching ``urllib``.

HTTP uses the standard library (``urllib.request``) so the offline build gains
no new networking dependency. Every call has a hard timeout and turns failures
into friendly ``ProviderError`` messages; callers decide how to degrade.

Providers:
  - openai      rewrite + speech-to-text
  - gemini      rewrite + speech-to-text
  - openrouter  rewrite only (LLM router, no transcription endpoint)
  - anthropic   rewrite only (Claude has no speech-to-text endpoint)
"""
from __future__ import annotations

import base64
import json
import uuid
from urllib import error, request

# Default instruction for the rewrite pass. Crucially it must NOT translate —
# Bangla stays Bangla, English stays English — only clean up the transcript.
DEFAULT_REWRITE_PROMPT = (
    "You are a transcription cleanup assistant for a voice-typing app. "
    "Rewrite the user's dictated text so it reads as clean, correctly punctuated "
    "prose: fix grammar, spelling, capitalization, and spacing. "
    "Preserve the original language and script exactly — if the text is in Bangla, "
    "keep it in Bangla; never translate. Do not add, remove, or answer content; "
    "do not add commentary or quotation marks. Return only the corrected text."
)

_REWRITE_TIMEOUT = 20.0
_STT_TIMEOUT = 60.0
_TEST_TIMEOUT = 15.0

# Per-provider metadata. Kept as plain data so the UI and validation can read it.
PROVIDERS: dict[str, dict] = {
    "openai": {
        "id": "openai",
        "label": "OpenAI",
        "supports_rewrite": True,
        "supports_stt": True,
        "default_rewrite_model": "gpt-4o-mini",
        "default_stt_model": "gpt-4o-transcribe",
    },
    "gemini": {
        "id": "gemini",
        "label": "Google Gemini",
        "supports_rewrite": True,
        "supports_stt": True,
        "default_rewrite_model": "gemini-2.0-flash",
        "default_stt_model": "gemini-2.0-flash",
    },
    "openrouter": {
        "id": "openrouter",
        "label": "OpenRouter",
        "supports_rewrite": True,
        "supports_stt": False,
        "default_rewrite_model": "openai/gpt-4o-mini",
        "default_stt_model": "",
    },
    "anthropic": {
        "id": "anthropic",
        "label": "Anthropic Claude",
        "supports_rewrite": True,
        "supports_stt": False,
        "default_rewrite_model": "claude-haiku-4-5",
        "default_stt_model": "",
    },
}


class ProviderError(Exception):
    """A cloud call failed. The message is safe to show the user (no secrets)."""


def rewrite_providers() -> list[str]:
    return [pid for pid, meta in PROVIDERS.items() if meta["supports_rewrite"]]


def stt_providers() -> list[str]:
    return [pid for pid, meta in PROVIDERS.items() if meta["supports_stt"]]


def _meta(provider: str) -> dict:
    meta = PROVIDERS.get((provider or "").strip())
    if meta is None:
        raise ProviderError(f"Unknown provider '{provider}'.")
    return meta


def rewrite_model_for(provider: str, model: str) -> str:
    return (model or "").strip() or _meta(provider)["default_rewrite_model"]


def stt_model_for(provider: str, model: str) -> str:
    return (model or "").strip() or _meta(provider)["default_stt_model"]


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(url: str, *, data: bytes | None, headers: dict[str, str],
             timeout: float, method: str = "POST") -> dict:
    """Send an HTTP request and return the parsed JSON body.

    Raises ProviderError with a user-facing message on any HTTP or network
    failure. API keys are never included in the raised text.
    """
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except error.HTTPError as exc:
        detail = ""
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            detail = (
                payload.get("error", {}).get("message")
                if isinstance(payload.get("error"), dict)
                else payload.get("error") or payload.get("message") or ""
            )
        except Exception:
            detail = ""
        hint = {401: "check your API key", 403: "access denied",
                404: "check the model name", 429: "rate limited — try again"}.get(exc.code, "")
        parts = [f"HTTP {exc.code}"]
        if detail:
            parts.append(str(detail).strip())
        elif hint:
            parts.append(hint)
        raise ProviderError(" — ".join(parts)) from None
    except error.URLError as exc:
        raise ProviderError(f"Network error: {exc.reason}") from None
    except TimeoutError:
        raise ProviderError("The request timed out.") from None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise ProviderError("The provider returned an unreadable response.") from None


def _json_bytes(obj: dict) -> bytes:
    return json.dumps(obj).encode("utf-8")


def _multipart(fields: dict[str, str], file_field: str,
               filename: str, file_bytes: bytes, content_type: str) -> tuple[bytes, str]:
    """Build a minimal multipart/form-data body (for OpenAI audio upload)."""
    boundary = f"----kothon{uuid.uuid4().hex}"
    crlf = b"\r\n"
    out = bytearray()
    for name, value in fields.items():
        out += b"--" + boundary.encode() + crlf
        out += f'Content-Disposition: form-data; name="{name}"'.encode() + crlf + crlf
        out += str(value).encode("utf-8") + crlf
    out += b"--" + boundary.encode() + crlf
    out += (
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'
        .encode() + crlf
    )
    out += f"Content-Type: {content_type}".encode() + crlf + crlf
    out += file_bytes + crlf
    out += b"--" + boundary.encode() + b"--" + crlf
    return bytes(out), f"multipart/form-data; boundary={boundary}"


# ── Rewrite ───────────────────────────────────────────────────────────────────

def rewrite(provider: str, api_key: str, model: str, prompt: str,
            text: str, language: str = "") -> str:
    """Send ``text`` to the LLM for cleanup and return the rewritten text.

    Raises ProviderError on failure. Callers must fall back to the original
    text on error so the user never loses their words.
    """
    meta = _meta(provider)
    if not meta["supports_rewrite"]:
        raise ProviderError(f"{meta['label']} does not support rewriting.")
    if not (api_key or "").strip():
        raise ProviderError("No API key set for this provider.")
    text = text or ""
    if not text.strip():
        return text
    prompt = (prompt or "").strip() or DEFAULT_REWRITE_PROMPT
    model = rewrite_model_for(provider, model)

    if provider in ("openai", "openrouter"):
        result = _rewrite_openai_compatible(provider, api_key, model, prompt, text)
    elif provider == "gemini":
        result = _rewrite_gemini(api_key, model, prompt, text)
    elif provider == "anthropic":
        result = _rewrite_anthropic(api_key, model, prompt, text)
    else:  # pragma: no cover - guarded by _meta
        raise ProviderError(f"Rewrite not implemented for '{provider}'.")

    result = (result or "").strip()
    return result or text


def _rewrite_openai_compatible(provider: str, api_key: str, model: str,
                               prompt: str, text: str) -> str:
    base = "https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.openai.com/v1"
    body = _request(
        f"{base}/chat/completions",
        data=_json_bytes({
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
        }),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=_REWRITE_TIMEOUT,
    )
    try:
        return body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ProviderError("The model returned no text.") from None


def _rewrite_gemini(api_key: str, model: str, prompt: str, text: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    )
    body = _request(
        url,
        data=_json_bytes({
            "system_instruction": {"parts": [{"text": prompt}]},
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": 0},
        }),
        headers={"Content-Type": "application/json"},
        timeout=_REWRITE_TIMEOUT,
    )
    try:
        parts = body["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        raise ProviderError("The model returned no text.") from None


def _rewrite_anthropic(api_key: str, model: str, prompt: str, text: str) -> str:
    body = _request(
        "https://api.anthropic.com/v1/messages",
        data=_json_bytes({
            "model": model,
            "max_tokens": 2048,
            "system": prompt,
            "messages": [{"role": "user", "content": text}],
        }),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout=_REWRITE_TIMEOUT,
    )
    if body.get("stop_reason") == "refusal":
        raise ProviderError("The model declined to rewrite this text.")
    try:
        return "".join(
            block.get("text", "") for block in body["content"] if block.get("type") == "text"
        )
    except (KeyError, TypeError):
        raise ProviderError("The model returned no text.") from None


# ── Speech-to-text ────────────────────────────────────────────────────────────

def transcribe(provider: str, api_key: str, model: str,
               wav_bytes: bytes, language: str = "") -> str:
    """Transcribe a WAV blob and return the recognized text.

    Raises ProviderError on failure. Only OpenAI and Gemini support this.
    """
    meta = _meta(provider)
    if not meta["supports_stt"]:
        raise ProviderError(f"{meta['label']} does not support speech-to-text.")
    if not (api_key or "").strip():
        raise ProviderError("No API key set for this provider.")
    if not wav_bytes:
        return ""
    model = stt_model_for(provider, model)

    if provider == "openai":
        return _transcribe_openai(api_key, model, wav_bytes, language).strip()
    if provider == "gemini":
        return _transcribe_gemini(api_key, model, wav_bytes).strip()
    raise ProviderError(f"Speech-to-text not implemented for '{provider}'.")  # pragma: no cover


def _transcribe_openai(api_key: str, model: str, wav_bytes: bytes, language: str) -> str:
    fields = {"model": model, "response_format": "json"}
    if language:
        fields["language"] = language
    payload, content_type = _multipart(
        fields, "file", "audio.wav", wav_bytes, "audio/wav"
    )
    body = _request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
        timeout=_STT_TIMEOUT,
    )
    return str(body.get("text", ""))


def _transcribe_gemini(api_key: str, model: str, wav_bytes: bytes) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    )
    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
    body = _request(
        url,
        data=_json_bytes({
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": "Transcribe this audio verbatim. Output only the transcript text."},
                    {"inline_data": {"mime_type": "audio/wav", "data": audio_b64}},
                ],
            }],
            "generationConfig": {"temperature": 0},
        }),
        headers={"Content-Type": "application/json"},
        timeout=_STT_TIMEOUT,
    )
    try:
        parts = body["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        raise ProviderError("The model returned no transcript.") from None


# ── Connection test ───────────────────────────────────────────────────────────

def test_connection(provider: str, api_key: str, model: str = "") -> tuple[bool, str]:
    """Validate an API key with a cheap request. Never raises."""
    try:
        _meta(provider)
        if not (api_key or "").strip():
            return False, "Enter an API key first."
        if provider in ("openai", "openrouter"):
            base = "https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.openai.com/v1"
            _request(f"{base}/models", data=None,
                     headers={"Authorization": f"Bearer {api_key}"},
                     timeout=_TEST_TIMEOUT, method="GET")
        elif provider == "gemini":
            _request(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}",
                data=None, headers={}, timeout=_TEST_TIMEOUT, method="GET",
            )
        elif provider == "anthropic":
            _request("https://api.anthropic.com/v1/models", data=None,
                     headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                     timeout=_TEST_TIMEOUT, method="GET")
        return True, "Connection OK."
    except ProviderError as exc:
        return False, str(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return False, str(exc)

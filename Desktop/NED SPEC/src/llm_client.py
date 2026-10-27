"""LLM client with swappable backends: Groq, OpenAI, Google Gemini, local Ollama.

Chosen via .env (LLM_PROVIDER=groq|openai|gemini|ollama|none). Everything goes through plain HTTP
with `requests`, so no vendor SDK is required and the file works on a machine with only three
packages installed.

If no key is configured the client is still constructed: `available` is False, and callers show the
fact sheet and cross-check table without an LLM answer. The app must never need an API key to be
useful.
"""

from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

try:                                     # .env support is optional, not required
    from dotenv import load_dotenv
    load_dotenv()
    # the plain call searches from the working directory, so launching the app from
    # elsewhere would silently drop the key; this file's own project root always works
    load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))
except Exception:                        # pragma: no cover
    pass

DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "ollama": "llama3.1",
}
# Groq meters usage per model per day, so an exhausted large model can sit next to a smaller
# one that still answers on the same key. Override with LLM_FALLBACK_MODELS=a,b, or "none".
DEFAULT_FALLBACKS = {"groq": ("openai/gpt-oss-20b",)}
KEY_VARS = {"groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
VISION_PROVIDERS = {"gemini", "openai"}

# Failures worth another model; a bad key or a malformed request would fail everywhere.
RETRYABLE = ("429", "rate limit", "quota", "tokens per", "404", "does not exist", "model_not_found",
             "500", "502", "503", "overloaded", "timeout", "timed out")


class LLMError(RuntimeError):
    """Any failure that should degrade the answer, not crash the app."""


def _worth_another_model(exc: Exception) -> bool:
    """True when a different model on the same key could plausibly succeed."""
    text = str(exc).lower()
    return any(key in text for key in RETRYABLE)


@dataclass
class LLMClient:
    provider: str = "none"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    timeout: int = 60
    fallbacks: tuple[str, ...] = ()
    model_used: str = ""              # which model actually produced the last reply

    @classmethod
    def from_env(cls) -> "LLMClient":
        provider = (os.getenv("LLM_PROVIDER") or "").strip().lower()
        if not provider:
            # pick whichever key happens to exist, so a user with one key needs no config
            for candidate, var in KEY_VARS.items():
                if os.getenv(var):
                    provider = candidate
                    break
            else:
                if os.getenv("OLLAMA_BASE_URL"):
                    provider = "ollama"
        if provider in ("", "none", "off", "disabled"):
            return cls(provider="none")
        model = os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(provider, "")
        key = os.getenv(KEY_VARS.get(provider, ""), "") if provider in KEY_VARS else ""
        base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") if provider == "ollama" \
            else os.getenv(f"{provider.upper()}_BASE_URL", "")
        raw = os.getenv("LLM_FALLBACK_MODELS") or os.getenv("LLM_FALLBACK_MODEL") or ""
        if raw.strip().lower() in ("none", "off", "0"):
            fallbacks: tuple[str, ...] = ()
        elif raw.strip():
            fallbacks = tuple(m.strip() for m in raw.split(",") if m.strip())
        else:
            fallbacks = DEFAULT_FALLBACKS.get(provider, ())
        return cls(provider=provider, model=model, api_key=key, base_url=base,
                   fallbacks=fallbacks)

    @property
    def models(self) -> tuple[str, ...]:
        """The configured model first, then each distinct fallback."""
        out: list[str] = []
        for name in (self.model, *self.fallbacks):
            if name and name not in out:
                out.append(name)
        return tuple(out)

    @property
    def available(self) -> bool:
        if self.provider == "none":
            return False
        if self.provider in KEY_VARS:
            return bool(self.api_key)
        return self.provider == "ollama"

    def describe(self) -> str:
        if not self.available:
            return "no LLM configured (extraction and cross-check still work)"
        return f"{self.provider}:{self.model}"

    # ------------------------------------------------------------------ chat
    def chat(self, system: str, user: str, temperature: float = 0.1) -> str:
        if not self.available:
            raise LLMError("no LLM configured")
        self.model_used = ""
        failure: LLMError | None = None
        for model in self.models:
            try:
                text = self._ask(system, user, temperature, model)
            except LLMError as exc:
                failure = exc
                if not _worth_another_model(exc):
                    raise
                continue
            self.model_used = model
            return text
        raise failure or LLMError("no model configured")

    def _ask(self, system: str, user: str, temperature: float, model: str) -> str:
        try:
            if self.provider == "gemini":
                return self._gemini(system, user, temperature, model)
            if self.provider == "ollama":
                return self._ollama(system, user, temperature, model)
            return self._openai_compat(system, user, temperature, model)
        except LLMError:
            raise
        except Exception as exc:                      # network, JSON, quota ...
            raise LLMError(f"{self.provider} request failed: {exc}") from exc

    def _post(self, url: str, payload: dict, headers: dict) -> dict:
        import requests
        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise LLMError(f"{resp.status_code}: {resp.text[:200]}")
        return resp.json()

    DEFAULT_BASE = {"groq": "https://api.groq.com/openai/v1",
                    "openai": "https://api.openai.com/v1"}

    def _base(self) -> str:
        base = self.base_url or self.DEFAULT_BASE.get(self.provider, "")
        if not base:
            raise LLMError(f"no endpoint configured for provider '{self.provider}'; "
                           "set OPENAI_BASE_URL-style base url or LLM_MODEL")
        return base

    def _openai_compat(self, system: str, user: str, temperature: float, model: str) -> str:
        data = self._post(f"{self._base()}/chat/completions",
                          {"model": model, "temperature": temperature,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}]},
                          {"Authorization": f"Bearer {self.api_key}"})
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise LLMError(f"unexpected response shape: {json.dumps(data)[:200]}")

    def _gemini(self, system: str, user: str, temperature: float, model: str) -> str:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        data = self._post(url, {"systemInstruction": {"parts": [{"text": system}]},
                                 "contents": [{"role": "user", "parts": [{"text": user}]}],
                                 "generationConfig": {"temperature": temperature}},
                          {"x-goog-api-key": self.api_key})
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        except (KeyError, IndexError):
            raise LLMError(f"no candidates: {json.dumps(data)[:200]}")

    def _ollama(self, system: str, user: str, temperature: float, model: str) -> str:
        data = self._post(f"{self.base_url or 'http://localhost:11434'}/api/chat",
                          {"model": model, "stream": False,
                           "messages": [{"role": "system", "content": system},
                                        {"role": "user", "content": user}],
                           "options": {"temperature": temperature}}, {})
        return (data.get("response") or "").strip()

    # ------------------------------------------------------------------ vision
    def supports_vision(self) -> bool:
        return self.available and self.provider in VISION_PROVIDERS

    def read_images(self, images: list[bytes], instruction: str) -> str:
        """Transcribe what is written on drawing page images. Only used for scanned PDFs."""
        if not self.supports_vision():
            raise LLMError(f"{self.provider} has no vision support configured")
        if self.provider == "gemini":
            parts = [{"text": instruction}]
            for img in images:
                parts.append({"inline_data": {"mime_type": "image/png",
                                              "data": base64.b64encode(img).decode()}})
            data = self._post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}"
                f":generateContent",
                {"contents": [{"role": "user", "parts": parts}],
                 "generationConfig": {"temperature": 0.0}}, {"x-goog-api-key": self.api_key})
            try:
                return "".join(p.get("text", "")
                               for p in data["candidates"][0]["content"]["parts"]).strip()
            except (KeyError, IndexError):
                raise LLMError("vision response had no text")
        urls = [{"url": "data:image/png;base64," + base64.b64encode(i).decode()} for i in images]
        return self._openai_compat_blocks(
            [{"type": "text", "text": instruction}] +
            [{"type": "image_url", "image_url": u} for u in urls])

    def _openai_compat_blocks(self, blocks: list[dict]) -> str:
        data = self._post(f"{self._base()}/chat/completions",
                          {"model": self.model, "temperature": 0.0,
                           "messages": [{"role": "user", "content": blocks}]},
                          {"Authorization": f"Bearer {self.api_key}"})
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            raise LLMError("vision response had no text")


def parse_json_object(text: str) -> Optional[dict]:
    """Best-effort JSON extraction from an LLM reply (fences, prose, trailing dots)."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None

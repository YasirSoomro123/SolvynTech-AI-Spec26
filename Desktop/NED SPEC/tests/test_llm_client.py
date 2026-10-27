"""The model chain: an exhausted model must hand over to the next one, not fail the question.

Groq meters usage per model, so the configured large model can be out of quota while a smaller
one on the same key still answers. None of these tests touch the network: the transport method
is replaced.
"""

from __future__ import annotations

import pytest

from src.llm_client import LLMClient, LLMError


def _groq(**kw) -> LLMClient:
    return LLMClient(provider="groq", model="big-model", api_key="test-key", **kw)


def test_a_groq_client_gets_a_fallback_by_default(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("LLM_FALLBACK_MODELS", raising=False)
    monkeypatch.delenv("LLM_FALLBACK_MODEL", raising=False)
    llm = LLMClient.from_env()
    assert llm.models[0] == llm.model
    assert llm.models[1:] == ("openai/gpt-oss-20b",)


def test_the_fallback_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("LLM_FALLBACK_MODELS", "none")
    assert LLMClient.from_env().fallbacks == ()


def test_an_exhausted_model_hands_over_to_the_next(monkeypatch):
    llm = _groq(fallbacks=("small-model",))
    seen: list[str] = []

    def fake(system, user, temperature, model):
        seen.append(model)
        if model == "big-model":
            raise LLMError("429: tokens per day limit reached")
        return "small answered"

    monkeypatch.setattr(llm, "_openai_compat", fake)
    assert llm.chat("system", "question") == "small answered"
    assert seen == ["big-model", "small-model"]
    assert llm.model_used == "small-model"


def test_a_rejected_key_does_not_waste_a_second_call(monkeypatch):
    llm = _groq(fallbacks=("small-model",))
    seen: list[str] = []

    def fake(system, user, temperature, model):
        seen.append(model)
        raise LLMError("401: invalid api key")

    monkeypatch.setattr(llm, "_openai_compat", fake)
    with pytest.raises(LLMError):
        llm.chat("system", "question")
    assert seen == ["big-model"]

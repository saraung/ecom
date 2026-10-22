# tests/test_mcp_llm_provider.py
"""MCP LLM provider selection (mocked; no API quota consumed).

Covers: default groq config, gemini selection + model default, explicit
model override, unknown provider, missing keys (without leaking them),
model/provider mismatch guard, and both client wirings.
"""
import pytest

import app.mcp.agent as agent_mod
from app.core.config import settings
from app.mcp.agent import (
    GEMINI_BASE_URL,
    GEMINI_DEFAULT_MODEL,
    GROQ_DEFAULT_MODEL,
    _active_client,
    _llm_config,
)


@pytest.fixture(autouse=True)
def clean_settings(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", None)
    yield


def test_default_is_groq():
    assert _llm_config() == ("groq", GROQ_DEFAULT_MODEL)
    assert GROQ_DEFAULT_MODEL == "openai/gpt-oss-120b"


def test_gemini_selection_and_default_model(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    assert _llm_config() == ("gemini", GEMINI_DEFAULT_MODEL)
    assert GEMINI_DEFAULT_MODEL == "gemini-3.1-flash-lite"


def test_explicit_model_override(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", "custom-model")
    assert _llm_config() == ("groq", "custom-model")
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "GEMINI")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "k")
    assert _llm_config() == ("gemini", "custom-model")


def test_unknown_provider_rejected(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "anthropic")
    with pytest.raises(ValueError, match="MCP_LLM_PROVIDER"):
        _llm_config()


def test_missing_keys_rejected_without_leak(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", None)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY") as exc:
        _llm_config()
    assert "gsk_" not in str(exc.value)
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY") as exc:
        _llm_config()
    assert "AIza" not in str(exc.value)


def test_groq_client_wiring_keeps_global():
    client, model = _active_client()
    assert client is agent_mod.groq
    assert model == GROQ_DEFAULT_MODEL


def test_gemini_client_wiring(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    client, model = _active_client()
    assert type(client).__name__ == "OpenAI"
    assert str(client.base_url).rstrip("/") == GEMINI_BASE_URL.rstrip("/")
    assert model == GEMINI_DEFAULT_MODEL
    # Same chat-completions interface the tool loop drives.
    assert callable(client.chat.completions.create)


def test_groq_complete_uses_selected_model(monkeypatch):
    import asyncio

    seen = {}

    class FakeCompletions:
        def create(self, **kwargs):
            seen.update(kwargs)
            raise ValueError("stop after first call")

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(agent_mod, "groq", FakeClient())
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", "pinned-model")
    with pytest.raises(RuntimeError, match="LLM request failed"):
        asyncio.run(agent_mod._groq_complete([{"role": "user", "content": "hi"}], []))
    assert seen["model"] == "pinned-model"
    assert seen["tools"] == [] and seen["tool_choice"] == "auto"


def test_groq_rejects_gemini_model(monkeypatch):
    # Stale MODEL after switching PROVIDER to groq must fail fast here,
    # not as a cryptic mid-chat provider error.
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "groq")
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", "gemini-3.1-flash-lite")
    with pytest.raises(RuntimeError, match="MCP_LLM_MODEL"):
        _llm_config()


def test_gemini_rejects_groq_model(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", "openai/gpt-oss-120b")
    with pytest.raises(RuntimeError, match="MCP_LLM_MODEL"):
        _llm_config()


def test_custom_model_names_pass_guard(monkeypatch):
    # Fine-tuned / custom names must not trip the family-prefix guard.
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", "my-acme-reranker-v2")
    assert _llm_config() == ("groq", "my-acme-reranker-v2")
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    assert _llm_config() == ("gemini", "my-acme-reranker-v2")


def test_unset_model_uses_provider_default(monkeypatch):
    monkeypatch.setattr(settings, "MCP_LLM_MODEL", None)
    assert _llm_config() == ("groq", GROQ_DEFAULT_MODEL)
    monkeypatch.setattr(settings, "MCP_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "test-gemini-key")
    assert _llm_config() == ("gemini", GEMINI_DEFAULT_MODEL)


def test_llm_call_budget_and_temperature():
    # Reasoning models count chain-of-thought against max_tokens: 500
    # produced blank finishes on tool-heavy turns.
    assert agent_mod.LLM_MAX_TOKENS >= 1500
    # Low temperature for consistent tool selection on repeated questions.
    assert 0 < agent_mod.LLM_TEMPERATURE <= 0.3


def test_date_grounding_present():
    assert "from_date" in agent_mod.DATE_GUIDANCE
    assert "to_date" in agent_mod.DATE_GUIDANCE
    today = agent_mod._today_context()
    assert today.startswith("Current UTC date: ")
    assert "without calling any further tools" in agent_mod.EMPTY_REPLY_NUDGE


def test_currency_envelope_tracks_settings(monkeypatch):
    from app.core.region import currency_code
    from app.mcp.tools import money_envelope

    env = money_envelope()
    assert env["currency"] == currency_code()
    assert isinstance(env["currency_symbol"], str) and env["currency_symbol"].strip()
    # Env-driven, not hardcoded: flipping the deployment switch flips the
    # envelope and the injected prompt line with no tool/prompt edits.
    monkeypatch.setattr(settings, "PAYMENT_CURRENCY", "USD")
    assert money_envelope() == {"currency": "USD", "currency_symbol": "$"}
    assert "USD" in agent_mod._currency_context()
    assert "currency" in agent_mod.CURRENCY_GUIDANCE
    assert "USD" in agent_mod.CURRENCY_GUIDANCE  # forbids the old bare-USD default

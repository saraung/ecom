"""MCP loopback URL resolution (tunnel-proof self-call)."""
from app.api.v1.mcp import resolve_mcp_url
from app.core import config as config_mod


def test_defaults_to_request_origin(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "MCP_LOOPBACK_URL", None)
    assert resolve_mcp_url("http://localhost:8001/") == "http://localhost:8001/mcp/"
    assert resolve_mcp_url("http://localhost:8001") == "http://localhost:8001/mcp/"


def test_env_override_wins_and_normalizes(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "MCP_LOOPBACK_URL", "http://127.0.0.1:8001/mcp")
    assert (
        resolve_mcp_url("https://abc123.ngrok-free.dev/")
        == "http://127.0.0.1:8001/mcp/"
    )
    monkeypatch.setattr(config_mod.settings, "MCP_LOOPBACK_URL", "http://127.0.0.1:8001/mcp/")
    assert (
        resolve_mcp_url("https://abc123.ngrok-free.dev/")
        == "http://127.0.0.1:8001/mcp/"
    )


def test_https_localhost_override_rejected(monkeypatch):
    import pytest

    monkeypatch.setattr(
        config_mod.settings, "MCP_LOOPBACK_URL", "https://localhost:8001/mcp/"
    )
    with pytest.raises(ValueError, match="plain HTTP"):
        resolve_mcp_url("https://abc123.ngrok-free.dev/")

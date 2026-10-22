import asyncio
import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1 import webhooks


def _request(token=None, payload=None):
    body = json.dumps(payload or {"data": {"awb": "test", "current_status": "DELIVERED"}}).encode()
    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}
    headers = [] if token is None else [(b"x-shiprocket-token", token.encode())]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers}, receive)


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_unconfigured_webhook_never_processes_events(monkeypatch, configured):
    monkeypatch.setattr(webhooks.settings, "SHIPROCKET_WEBHOOK_TOKEN", configured)
    process = Mock()
    monkeypatch.setattr(webhooks, "process_tracking_event", process)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(webhooks.shiprocket_tracking_webhook(_request("anything"), None))
    assert exc.value.status_code == 503
    process.assert_not_called()


@pytest.mark.parametrize("provided", [None, "", "wrong", "tökén"])
def test_invalid_auth_never_processes_events(monkeypatch, provided):
    monkeypatch.setattr(webhooks.settings, "SHIPROCKET_WEBHOOK_TOKEN", "correct")
    process = Mock()
    monkeypatch.setattr(webhooks, "process_tracking_event", process)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(webhooks.shiprocket_tracking_webhook(_request(provided), None))
    assert exc.value.status_code == 401
    process.assert_not_called()


@pytest.mark.parametrize("payload", [{"awb": "test"}, {"data": {"awb": "test"}}])
def test_valid_auth_preserves_event_contract(monkeypatch, payload):
    monkeypatch.setattr(webhooks.settings, "SHIPROCKET_WEBHOOK_TOKEN", "correct")
    process = Mock(return_value={"status": "success"})
    monkeypatch.setattr(webhooks, "process_tracking_event", process)
    assert asyncio.run(webhooks.shiprocket_tracking_webhook(_request("correct", payload), None)) == {"status": "success"}
    process.assert_called_once_with(None, payload)

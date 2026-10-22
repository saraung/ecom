from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import importlib.util
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.api.v1 import chat as api
from app.core.config import settings
from app.core.security import create_access_token
from app.db.database import get_session
from app.models.chat import ChatSession, ChatRateLimit
from app.models.user import User
from app.services.chat_session import allow_request


@pytest.fixture
def web(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    llm = Mock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Private answer"))]))
    monkeypatch.setattr(api, "client", SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=llm))))
    monkeypatch.setattr(api, "is_product_query", lambda message, session: False)
    monkeypatch.setattr(api, "build_system_prompt", lambda: "Support")
    monkeypatch.setattr(settings, "CHAT_MESSAGES_PER_MINUTE", 100)
    with Session(engine) as s:
        users = [User(email=f"chat{i}@example.com", username=f"chat{i}") for i in (1, 2)]
        s.add_all(users)
        s.commit()
        headers = [{"Authorization": f"Bearer {create_access_token(u.email, 'customer', audience='storefront')}"} for u in users]
    app = FastAPI()
    app.include_router(api.router)
    def session_dep():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = session_dep
    with TestClient(app) as client:
        yield engine, client, llm, headers
    engine.dispose()


def start(client, headers=None):
    response = client.post("/chat/session", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_authenticated_history_send_and_clear_require_same_account(web):
    _, client, llm, (owner, other) = web
    token = start(client, owner)
    assert client.post("/chat", json={"message": "Hello", "session_id": token}, headers=owner).status_code == 200
    for headers in ({}, other):
        assert client.get("/chat/history", params={"session_id": token}, headers=headers).status_code == 404
        assert client.delete("/chat/history", params={"session_id": token}, headers=headers).status_code == 404
        assert client.post("/chat", json={"message": "Hello", "session_id": token}, headers=headers).status_code == 404
    assert llm.call_count == 1
    assert len(client.get("/chat/history", headers={**owner, "X-Chat-Session": token}).json()) == 2
    assert client.delete("/chat/history", headers={**owner, "X-Chat-Session": token}).status_code == 200
    assert client.get("/chat/history", params={"session_id": token}, headers=owner).json() == []


def test_guest_unguessable_capability_cannot_be_forged_or_used_as_access_token(web):
    _, client, _, _ = web
    token = start(client)
    assert client.get("/chat/history", headers={"X-Chat-Session": token}).status_code == 200
    for guessed in ("arbitrary-browser-id", token[:-1] + ("a" if token[-1] != "a" else "b")):
        assert client.get("/chat/history", params={"session_id": guessed}).status_code == 404
    assert client.post("/chat/session", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_invalid_authenticated_token_never_downgrades_to_guest(web):
    _, client, llm, _ = web
    assert client.post("/chat/session", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert llm.call_count == 0


def test_history_persists_across_requests_and_is_bounded(web):
    engine, client, llm, _ = web
    token = start(client)
    for number in range(13):
        assert client.post("/chat", json={"message": f"Hello {number}", "session_id": token}).status_code == 200
    history = client.get("/chat/history", params={"session_id": token}).json()
    assert len(history) == 20 and history[0]["content"] == "Hello 3"
    with Session(engine) as s:
        assert s.exec(select(ChatSession)).one().history == history
    assert len(llm.call_args.kwargs["messages"]) <= 7


def test_input_reply_and_schema_bounds_apply_before_provider(web):
    _, client, llm, _ = web
    token = start(client)
    for message in ("a" * 2001, ["wrong type"]):
        assert client.post("/chat", json={"message": message, "session_id": token}).status_code == 422
    assert llm.call_count == 0
    llm.return_value.choices[0].message.content = "a" * 5000
    assert len(client.post("/chat", json={"message": "Hello", "session_id": token}).json()["reply"]) == 4000


def test_guest_session_rotation_does_not_reset_message_rate_limit(web, monkeypatch):
    engine, client, llm, _ = web
    monkeypatch.setattr(settings, "CHAT_MESSAGES_PER_MINUTE", 1)
    first, second = start(client), start(client)
    assert client.post("/chat", json={"message": "Hello", "session_id": first}).status_code == 200
    response = client.post("/chat", json={"message": "Hello", "session_id": second})
    assert response.status_code == 429 and response.headers["retry-after"] == "60"
    assert llm.call_count == 1
    with Session(engine) as s:
        assert s.exec(select(ChatRateLimit)).all()


def test_expired_session_cleanup_and_creation_budget(web, monkeypatch):
    engine, client, _, _ = web
    monkeypatch.setattr(settings, "CHAT_SESSIONS_PER_MINUTE", 2)
    token = start(client)
    with Session(engine) as s:
        row = s.exec(select(ChatSession)).one()
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        s.add(row)
        s.commit()
    assert client.get("/chat/history", params={"session_id": token}).status_code == 404
    start(client)
    with Session(engine) as s:
        assert len(s.exec(select(ChatSession)).all()) == 1
    assert client.post("/chat/session").status_code == 429


def test_provider_failure_rolls_back_history_but_consumes_budget(web):
    engine, client, llm, _ = web
    token = start(client)
    llm.side_effect = TimeoutError("provider down")
    assert client.post("/chat", json={"message": "Hello", "session_id": token}).status_code == 503
    assert client.get("/chat/history", params={"session_id": token}).json() == []
    import hashlib
    with Session(engine) as s:
        assert s.get(ChatRateLimit, hashlib.sha256(b"message:global").hexdigest()).count == 1


def test_global_budget_caps_provider_calls_across_accounts(web, monkeypatch):
    _, client, llm, (first, second) = web
    monkeypatch.setattr(settings, "CHAT_GLOBAL_MESSAGES_PER_MINUTE", 1)
    tokens = [start(client, headers) for headers in (first, second)]
    assert client.post("/chat", headers=first, json={"message": "Hello", "session_id": tokens[0]}).status_code == 200
    assert client.post("/chat", headers=second, json={"message": "Hello", "session_id": tokens[1]}).status_code == 429
    assert llm.call_count == 1


def test_chat_migration_upgrade(web):
    engine, _, _, _ = web
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect
    path = Path(__file__).resolve().parents[1] / "alembic/versions/u6c7d8e9f0a1_owned_chat_limits.py"
    spec = importlib.util.spec_from_file_location("chat_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE chat_rate_limits")
        connection.exec_driver_sql("DROP TABLE chat_sessions")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert {"chat_sessions", "chat_rate_limits"} <= set(inspect(connection).get_table_names())


def test_postgres_budget_concurrent_consumption_is_bounded(postgres_engine, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    monkeypatch.setattr(settings, "CHAT_MESSAGES_PER_MINUTE", 1)
    barrier = Barrier(2)
    def consume():
        with Session(postgres_engine) as s:
            barrier.wait(timeout=10)
            try:
                allow_request(s, Request({"type": "http", "client": ("127.0.0.1", 1)}), None, "message")
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(consume) for _ in range(2)]
        assert sorted(f.result(timeout=15) for f in futures) == [200, 429]

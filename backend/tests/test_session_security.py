from datetime import datetime, timedelta, timezone
import asyncio
from pathlib import Path
import importlib.util
from unittest.mock import Mock

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import BackgroundTasks, HTTPException
import pytest
from sqlalchemy import event, text
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.api.deps import get_current_user
from app.api.v1 import auth
from app.core.security import decode_access_token, hash_password, create_access_token
from app.models.password_reset import PasswordResetToken
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.services.email_service import email_service
from app.repositories import token as repo
from app.schemas.token import RefreshRequest


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="session@example.com", username="session", password_hash=hash_password("Original123"))
        s.add(user)
        s.commit()
        yield s, user
    engine.dispose()


def test_rotation_preserves_scope_and_session_and_rejects_replay(db):
    s, user = db
    first = auth._issue_tokens(s, user, "storefront")
    second = auth.refresh(RefreshRequest(refresh_token=first.refresh_token), s)
    assert second.refresh_token != first.refresh_token
    assert decode_access_token(second.access_token)["aud"] == "storefront"
    assert decode_access_token(second.access_token)["sid"] == decode_access_token(first.access_token)["sid"]
    with pytest.raises(HTTPException) as exc:
        auth.refresh(RefreshRequest(refresh_token=first.refresh_token), s)
    assert exc.value.status_code == 401
    assert get_current_user(s, first.access_token).id == user.id
    assert get_current_user(s, second.access_token).id == user.id


def test_stale_loaded_record_cannot_rotate_twice(db):
    s, user = db
    raw = repo.issue_refresh_token(s, user.id)
    record = repo.get_valid_token(s, raw)
    repo.rotate_token(s, record)
    with pytest.raises(HTTPException):
        repo.rotate_token(s, record)
    assert len(s.exec(select(RefreshToken)).all()) == 2


def test_rotation_failure_keeps_old_refresh_usable(db, monkeypatch):
    s, user = db
    first = auth._issue_tokens(s, user)
    def fail(*args, **kwargs):
        raise RuntimeError("signing unavailable")
    monkeypatch.setattr(auth, "_issue_access_token", fail)
    with pytest.raises(RuntimeError):
        auth.refresh(RefreshRequest(refresh_token=first.refresh_token), s)
    assert repo.get_valid_token(s, first.refresh_token) is not None
    assert len(s.exec(select(RefreshToken)).all()) == 1


def test_rotation_commit_failure_rolls_back_revocation_and_replacement(db):
    s, user = db
    pair = auth._issue_tokens(s, user)
    def fail(session):
        raise RuntimeError("commit unavailable")
    event.listen(s, "before_commit", fail)
    with pytest.raises(RuntimeError):
        auth.refresh(RefreshRequest(refresh_token=pair.refresh_token), s)
    event.remove(s, "before_commit", fail)
    assert repo.get_valid_token(s, pair.refresh_token) is not None
    assert len(s.exec(select(RefreshToken)).all()) == 1


def test_logout_revokes_rotated_family_but_keeps_other_login(db):
    s, user = db
    first = auth._issue_tokens(s, user)
    other = auth._issue_tokens(s, user)
    second = auth.refresh(RefreshRequest(refresh_token=first.refresh_token), s)
    auth.logout(RefreshRequest(refresh_token=second.refresh_token), s)
    auth.logout(RefreshRequest(refresh_token=second.refresh_token), s)  # idempotent
    assert repo.get_valid_token(s, second.refresh_token) is None
    for token in (first.access_token, second.access_token):
        with pytest.raises(HTTPException):
            get_current_user(s, token)
    assert get_current_user(s, other.access_token).id == user.id


def test_inactive_user_cannot_refresh(db):
    s, user = db
    pair = auth._issue_tokens(s, user)
    user.is_active = False
    s.add(user)
    s.commit()
    with pytest.raises(HTTPException) as exc:
        auth.refresh(RefreshRequest(refresh_token=pair.refresh_token), s)
    assert exc.value.status_code == 401


def test_password_change_invalidates_access_and_all_refresh_sessions(db):
    s, user = db
    pair = auth._issue_tokens(s, user)
    auth.change_password(auth.ChangePasswordRequest(current_password="Original123", new_password="Changed123"), s, user)
    assert repo.get_valid_token(s, pair.refresh_token) is None
    with pytest.raises(HTTPException):
        get_current_user(s, pair.access_token)
    new_pair = auth._issue_tokens(s, user)
    assert get_current_user(s, new_pair.access_token).id == user.id


def test_reset_token_is_hashed_single_use_and_invalidates_sessions(db):
    s, user = db
    pair = auth._issue_tokens(s, user)
    tasks = BackgroundTasks()
    auth.forgot_password(auth.ForgotPasswordRequest(email=user.email), s, tasks)
    from app.models.email_outbox import EmailOutbox
    from urllib.parse import urlparse, parse_qs
    mail = s.exec(select(EmailOutbox)).one()
    link = next(line.strip() for line in mail.plain_text.splitlines() if '/reset-password?token=' in line)
    raw = parse_qs(urlparse(link).query)["token"][0]
    assert tasks.tasks == []
    record = s.exec(select(PasswordResetToken)).one()
    assert record.token == repo._hash(raw) and record.token != raw
    auth.reset_password(auth.ResetPasswordRequest(token=raw, new_password="ResetPass123"), s)
    with pytest.raises(HTTPException):
        auth.reset_password(auth.ResetPasswordRequest(token=raw, new_password="Another123"), s)
    assert repo.get_valid_token(s, pair.refresh_token) is None
    with pytest.raises(HTTPException):
        get_current_user(s, pair.access_token)


def test_password_reset_supersedes_queued_reset_mail(db):
    s, user = db
    tasks = BackgroundTasks()

    auth.forgot_password(auth.ForgotPasswordRequest(email=user.email), s, tasks)
    auth.forgot_password(auth.ForgotPasswordRequest(email=user.email), s, tasks)

    from app.models.email_outbox import EmailOutbox

    rows = s.exec(select(EmailOutbox).where(
        EmailOutbox.event_key.like("password-reset:%")
    )).all()
    assert len(rows) == 1
    assert rows[0].sent_at is None


def test_password_reset_sends_inline_on_serverless(db, monkeypatch):
    s, user = db
    monkeypatch.setenv("VERCEL", "1")
    send = Mock(return_value=True)
    monkeypatch.setattr(email_service, "_send_email", send)

    auth.forgot_password(auth.ForgotPasswordRequest(email=user.email), s, BackgroundTasks())

    from app.models.email_outbox import EmailOutbox

    assert send.call_count == 1
    row = s.exec(select(EmailOutbox)).one()
    assert row.sent_at is not None
    assert row.attempts == 1


def test_expired_refresh_rejected_with_sqlite_naive_timestamp(db):
    s, user = db
    raw = repo.issue_refresh_token(s, user.id)
    record = repo.get_valid_token(s, raw)
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    s.add(record)
    s.commit()
    assert repo.get_valid_token(s, raw) is None


def test_websocket_rejects_logged_out_access_token(db, monkeypatch):
    from unittest.mock import AsyncMock
    from app.api.v1.notifications import websocket_endpoint
    s, user = db
    pair = auth._issue_tokens(s, user)
    auth.logout(RefreshRequest(refresh_token=pair.refresh_token), s)
    def sessions():
        yield s
    monkeypatch.setattr("app.db.database.get_session", sessions)
    socket = AsyncMock()
    asyncio.run(websocket_endpoint(socket, pair.access_token))
    assert socket.close.call_args.kwargs["code"] == 4401
    socket.send_json.assert_not_called()


def test_session_migration_backfills_families_and_hashes_old_reset_links(db):
    s, user = db
    repo.issue_refresh_token(s, user.id)
    s.add(PasswordResetToken(user_id=user.id, token="old-link", used=False,
                            expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    s.commit()
    engine = s.get_bind()
    s.close()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/o0c1d2e3f4a5_session_invalidation.py"
    spec = importlib.util.spec_from_file_location("session_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP INDEX ix_refresh_tokens_session_id")
        conn.exec_driver_sql("ALTER TABLE refresh_tokens DROP COLUMN session_id")
        conn.exec_driver_sql("ALTER TABLE users DROP COLUMN token_version")
        migration.op = Operations(MigrationContext.configure(conn))
        migration.upgrade()
        assert conn.execute(text("SELECT token_version FROM users")).scalar_one() == 0
        row = conn.execute(text("SELECT id, session_id FROM refresh_tokens")).one()
        assert row.id == row.session_id
        assert conn.execute(text("SELECT token FROM password_reset_tokens")).scalar_one() == repo._hash("old-link")

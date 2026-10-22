import hashlib
from datetime import datetime, timedelta, timezone
import uuid

from sqlmodel import Session, select
from sqlalchemy import update
from fastapi import HTTPException
from app.models.refresh_token import RefreshToken
from app.core.config import settings
from app.core.security import create_refresh_token_value


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_refresh_token(
    session: Session, user_id: uuid.UUID, scope: str = "admin", *,
    session_id: uuid.UUID | None = None, commit: bool = True,
) -> str:
    raw = create_refresh_token_value()
    record = RefreshToken(
        user_id=user_id,
        token_hash=_hash(raw),
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        scope=scope,
        session_id=session_id or uuid.uuid4(),
    )
    session.add(record)
    session.commit() if commit else session.flush()
    return raw  # only the raw value is ever sent to the client


def get_token(session: Session, raw_token: str) -> RefreshToken | None:
    record = session.exec(
        select(RefreshToken).where(RefreshToken.token_hash == _hash(raw_token))
    ).first()
    return record


def get_valid_token(session: Session, raw_token: str) -> RefreshToken | None:
    record = get_token(session, raw_token)
    if not record or record.revoked:
        return None
    expiry = record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        return None
    return record


def revoke_token(session: Session, record: RefreshToken) -> None:
    record.revoked = True
    session.add(record)
    session.commit()


def rotate_token(session: Session, old_record: RefreshToken, *, commit: bool = True) -> str:
    """Revoke old refresh token, issue a new one. Prevents replay of stolen tokens.

    The audience is copied from the record being rotated, so a refresh can never
    widen a session's reach.
    """
    try:
        claimed = session.execute(update(RefreshToken).where(
            RefreshToken.id == old_record.id,
            RefreshToken.revoked.is_(False),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        ).values(revoked=True).execution_options(synchronize_session=False))
        if claimed.rowcount != 1:
            raise HTTPException(401, "Invalid or expired refresh token")
        raw = issue_refresh_token(session, old_record.user_id, scope=old_record.scope or "admin",
                                  session_id=old_record.session_id, commit=False)
        if commit:
            session.commit()
        return raw
    except Exception:
        session.rollback()
        raise


def revoke_session(session: Session, record: RefreshToken):
    from app.models.user import User
    session.exec(select(User.id).where(User.id == record.user_id).with_for_update()).one()
    session.execute(update(RefreshToken).where(
        RefreshToken.user_id == record.user_id, RefreshToken.session_id == record.session_id,
    ).values(revoked=True).execution_options(synchronize_session=False))


def invalidate_user_sessions(session: Session, user):
    from app.models.user import User
    session.exec(select(User.id).where(User.id == user.id).with_for_update()).one()
    session.execute(update(RefreshToken).where(RefreshToken.user_id == user.id)
                    .values(revoked=True).execution_options(synchronize_session=False))
    session.execute(update(User).where(User.id == user.id)
                    .values(token_version=User.token_version + 1))


def session_is_valid(session: Session, user, payload):
    if payload.get("ver", 0) != user.token_version:
        return False
    if "sid" not in payload:
        return True  # Compatibility for already-issued short-lived JWTs.
    try:
        session_id = uuid.UUID(payload["sid"])
    except (ValueError, TypeError, AttributeError):
        return False
    return session.exec(select(RefreshToken.id).where(
        RefreshToken.session_id == session_id, RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False), RefreshToken.expires_at > datetime.now(timezone.utc),
    )).first() is not None

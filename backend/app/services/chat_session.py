"""Owned, bounded chat state and shared DB rate limits; no process-local store."""
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy import delete, select

from app.core.config import settings
from app.models.chat import ChatSession, ChatRateLimit

MAX_HISTORY = 20
MAX_REPLY = 4000


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def issue_session(session, owner):
    now = datetime.now(timezone.utc)
    row = ChatSession(owner_id=owner.id if owner else None,
                      expires_at=now + timedelta(hours=settings.CHAT_SESSION_TTL_HOURS))
    session.execute(delete(ChatSession).where(ChatSession.expires_at <= now))
    session.execute(delete(ChatRateLimit).where(ChatRateLimit.window_start < now - timedelta(days=1)))
    session.add(row)
    token = jwt.encode({"type": "chat", "aud": "chat", "jti": str(row.id),
                        "sub": str(row.owner_id) if row.owner_id else "guest", "exp": row.expires_at},
                       settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    session.commit()
    return token


def owned_session(session, token, owner, *, lock=False):
    denied = HTTPException(404, "Chat session not found or expired")
    if not token:
        raise denied
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM], audience="chat")
        if payload.get("type") != "chat" or payload.get("sub") != (str(owner.id) if owner else "guest"):
            raise denied
        identity = UUID(payload["jti"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise denied
    query = select(ChatSession).where(ChatSession.id == identity).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    row = session.execute(query).scalars().first()
    if not row or row.owner_id != (owner.id if owner else None) or utc(row.expires_at) <= datetime.now(timezone.utc):
        raise denied
    return row


def allow_request(session, request, owner, operation):
    """Durably consume fixed-minute budgets before any LLM work.

    Anonymous budgets use the ASGI peer, never user-supplied forwarded headers.
    Rotating session capabilities cannot evade them; LLM budget is also global.
    """
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    principal = str(owner.id) if owner else f"guest:{request.client.host if request.client else 'unknown'}"
    limit = settings.CHAT_SESSIONS_PER_MINUTE if operation == "session" else settings.CHAT_MESSAGES_PER_MINUTE if operation == "message" else 60
    budgets = [(f"{operation}:{principal}", limit)]
    if operation == "message":
        budgets.append(("message:global", settings.CHAT_GLOBAL_MESSAGES_PER_MINUTE))
    elif operation == "session":
        budgets.append(("session:global", 50))
    dialect = session.bind.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise HTTPException(503, "Chat rate limiter unavailable")
    try:
        # One lock order for every budget, avoiding cross-request deadlocks.
        for label, ceiling in sorted(budgets):
            key = hashlib.sha256(label.encode()).hexdigest()
            session.execute(insert(ChatRateLimit).values(key=key, window_start=now, count=0)
                            .on_conflict_do_nothing(index_elements=[ChatRateLimit.key]))
            row = session.execute(select(ChatRateLimit).where(ChatRateLimit.key == key)
                                  .with_for_update().execution_options(populate_existing=True)).scalars().one()
            if utc(row.window_start) != now:
                row.window_start, row.count = now, 0
            if row.count >= ceiling:
                raise HTTPException(429, "Chat request limit reached; please try again shortly", headers={"Retry-After": "60"})
            row.count += 1
            session.add(row)
            session.flush()
        session.commit()
    except Exception:
        session.rollback()
        raise

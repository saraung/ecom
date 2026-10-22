# app/repositories/audit.py
"""Append-only admin audit log.

``log()`` only stages the row — the caller owns the commit so audit entries
land in the SAME transaction as the action they describe (no orphan entries
on rollback, no missing entries on success). Read paths never mutate.
"""
from uuid import UUID

from sqlalchemy import func, select
from sqlmodel import Session

from app.models.admin_audit import AdminAuditLog


def log(
    session: Session,
    action: str,
    entity: str,
    entity_id: str | UUID | None,
    actor_id: UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> AdminAuditLog:
    entry = AdminAuditLog(
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None,
        before=before,
        after=after,
        ip_address=ip_address,
    )
    try:
        session.add(entry)
        session.flush()
    except Exception:
        session.rollback()
        raise
    return entry


def log_and_commit(
    session: Session,
    action: str,
    entity: str,
    entity_id: str | UUID | None,
    actor_id: UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    ip_address: str | None = None,
) -> AdminAuditLog:
    """log() + commit. Use at the END of admin write endpoints (after the
    mutation succeeded) — never before validation, so failed requests
    leave no trail claiming they happened."""
    entry = log(
        session,
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor_id=actor_id,
        before=before,
        after=after,
        ip_address=ip_address,
    )
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    session.refresh(entry)
    return entry


def client_ip(request) -> str | None:
    """Best-effort client IP.

    Honors ``X-Forwarded-For`` (leftmost = original client) when running
    behind a trusted proxy / ingress, falling back to the direct peer.
    """
    try:
        if request is not None:
            forwarded = request.headers.get("x-forwarded-for") if hasattr(
                request, "headers"
            ) else None
            if forwarded:
                first = forwarded.split(",")[0].strip()
                if first:
                    return first[:50]
            if request.client is not None:
                return request.client.host
    except Exception:
        pass
    return None


def list_entries(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    action: str | None = None,
    entity: str | None = None,
    entity_id: UUID | str | None = None,
    actor_id: UUID | None = None,
    exclude_entities: list[str] | None = None,
) -> tuple[list[AdminAuditLog], int]:
    statement = select(AdminAuditLog).order_by(
        AdminAuditLog.created_at.desc()
    )
    if action:
        statement = statement.where(AdminAuditLog.action == action)
    if entity:
        statement = statement.where(AdminAuditLog.entity == entity)
    if entity_id is not None:
        statement = statement.where(AdminAuditLog.entity_id == str(entity_id))
    if actor_id:
        statement = statement.where(AdminAuditLog.actor_id == actor_id)
    if exclude_entities:
        statement = statement.where(
            AdminAuditLog.entity.not_in(exclude_entities)
        )

    total = session.execute(
        select(func.count()).select_from(statement.subquery())
    ).scalar() or 0
    rows = session.execute(statement.offset(skip).limit(limit)).scalars().all()
    return list(rows), total

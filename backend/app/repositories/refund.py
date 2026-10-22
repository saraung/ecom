# app/repositories/refund.py
"""Persistence for the refund ledger (one row per money movement)."""
from uuid import UUID

from sqlalchemy import select
from sqlmodel import Session

from app.models.refund import Refund, RefundStatus


def get_by_id(session: Session, refund_id: UUID) -> Refund | None:
    return session.get(Refund, refund_id)


def get_by_idempotency_key(
    session: Session, key: str
) -> Refund | None:
    result = session.execute(
        select(Refund).where(Refund.idempotency_key == key)
    )
    return result.scalar_one_or_none()


def list_refunds(
    session: Session,
    skip: int = 0,
    limit: int = 20,
    status: RefundStatus | None = None,
    order_id: UUID | None = None,
) -> tuple[list[Refund], int]:
    from sqlalchemy import func

    statement = select(Refund).order_by(Refund.created_at.desc())
    if status is not None:
        statement = statement.where(Refund.status == status)
    if order_id is not None:
        statement = statement.where(Refund.order_id == order_id)

    total = session.execute(
        select(func.count()).select_from(statement.subquery())
    ).scalar() or 0
    rows = session.execute(statement.offset(skip).limit(limit)).scalars().all()
    return list(rows), total

# app/repositories/content.py
"""Storefront content blocks: public live read + admin CRUD helpers."""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlmodel import Session, select

from app.models.content_block import ContentBlock


def _live_filters(now: datetime):
    """Active + inside the publish window (null bounds = unbounded)."""
    return [
        ContentBlock.is_active == True,  # noqa: E712
        (ContentBlock.starts_at.is_(None)) | (ContentBlock.starts_at <= now),
        (ContentBlock.ends_at.is_(None)) | (ContentBlock.ends_at > now),
    ]


def get_live_blocks(
    session: Session, keys: list[str] | None = None
) -> dict[str, list[ContentBlock]]:
    """Public read: live blocks grouped by slot, sort_order first.

    Only active, in-window blocks are returned — drafts, disabled and
    expired content never reaches the storefront. Empty slots are absent
    (callers fall back to hardcoded content).
    """
    now = datetime.now(timezone.utc)
    statement = select(ContentBlock).where(*_live_filters(now))
    if keys:
        statement = statement.where(ContentBlock.key.in_(keys))
    statement = statement.order_by(
        ContentBlock.sort_order.asc(), ContentBlock.created_at.asc()
    )
    grouped: dict[str, list[ContentBlock]] = {}
    for block in session.exec(statement).all():
        grouped.setdefault(block.key, []).append(block)
    return grouped


def list_blocks_admin(session: Session, skip: int = 0, limit: int = 50) -> tuple[list[ContentBlock], int]:
    """All blocks incl. drafts/disabled/expired, newest first."""
    total = session.execute(
        select(func.count()).select_from(ContentBlock)
    ).scalar_one()
    rows = session.exec(
        select(ContentBlock)
        .order_by(ContentBlock.updated_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()
    return list(rows), int(total or 0)


def get_block_by_id(session: Session, block_id: UUID) -> ContentBlock | None:
    return session.get(ContentBlock, block_id)


def get_block_by_key(session: Session, key: str) -> ContentBlock | None:
    return session.exec(
        select(ContentBlock).where(ContentBlock.key == key)
    ).first()

# app/models/admin_audit.py
"""Append-only admin action log.

Written on every privileged mutation (refunds, role changes, coupon edits,
price/stock edits, user activation, settings saves). There are deliberately
NO update/delete paths — not even for admins. This table is the evidence
base for fraud review, partner disputes, and ex-employee investigations.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class AdminAuditLog(SQLModel, table=True):
    __tablename__ = "admin_audit_log"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    actor_id: UUID | None = Field(
        default=None, foreign_key="users.id", index=True
    )
    # e.g. "refund.approved", "role.assigned", "coupon.created"
    action: str = Field(max_length=100, index=True)
    # e.g. "order", "refund", "role", "user", "coupon", "product"
    entity: str = Field(max_length=50, index=True)
    entity_id: str | None = Field(default=None, index=True)
    before: dict | None = Field(default=None, sa_column=Column(JSON))
    after: dict | None = Field(default=None, sa_column=Column(JSON))
    ip_address: str | None = Field(default=None, max_length=50)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )

# app/schemas/audit.py
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: UUID | None = None
    actor_email: str | None = None
    action: str
    entity: str
    entity_id: str | None = None
    before: dict | None = None
    after: dict | None = None
    ip_address: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogRead]
    total: int
    page: int
    limit: int
    total_pages: int

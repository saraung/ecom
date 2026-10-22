from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, JSON
from sqlmodel import Field, SQLModel


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    owner_id: UUID | None = Field(default=None, foreign_key="users.id")
    history: list[dict] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))


class ChatRateLimit(SQLModel, table=True):
    __tablename__ = "chat_rate_limits"
    key: str = Field(max_length=64, primary_key=True)
    window_start: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    count: int = Field(default=0)

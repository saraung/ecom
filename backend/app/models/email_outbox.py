from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Text
from sqlmodel import Field, SQLModel


class EmailOutbox(SQLModel, table=True):
    __tablename__ = "email_outbox"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    event_key: str = Field(unique=True, index=True, max_length=255)
    to_email: str
    subject: str
    html_content: str = Field(sa_column=Column(Text, nullable=False))
    plain_text: str | None = Field(default=None, sa_column=Column(Text))
    attempts: int = Field(default=0)
    next_attempt_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),
                                    sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    sent_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    expires_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),
                               sa_column=Column(DateTime(timezone=True), nullable=False))

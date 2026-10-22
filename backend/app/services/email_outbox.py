"""Durable, at-least-once transactional mail on the existing DB/scheduler."""
from copy import copy
from datetime import datetime, timedelta, timezone

from sqlmodel import Session, select

from app.models.email_outbox import EmailOutbox
from app.services.email_service import EmailService, email_service


def enqueue_email(session: Session, event_key: str, template: str, *args, expires_at=None, **kwargs):
    """Render now, persist with the caller's transaction; never contact a provider."""
    existing = session.exec(select(EmailOutbox).where(EmailOutbox.event_key == event_key)).first()
    if existing:
        return existing
    payload = {}
    def capture(to_email, subject, html_content, plain_text=None):
        payload.update(to_email=to_email, subject=subject, html_content=html_content, plain_text=plain_text)
        return True
    renderer = copy(email_service)
    renderer._send_email = capture
    getattr(EmailService, template)(renderer, *args, **kwargs)
    if not payload.get("to_email"):
        raise ValueError(f"Email template {template} produced no recipient")
    row = EmailOutbox(event_key=event_key, expires_at=expires_at, **payload)
    session.add(row)
    session.flush()
    return row


def enqueue_order_email(session, order, event, *, event_id=None):
    return enqueue_email(session, f"order:{order.id}:{event}:{event_id or ''}",
                         f"send_{event}", order, order.user)


def deliver_pending_emails(session: Session, *, limit=25, now=None, sender=None):
    """Lock one row through send+ack, so multiple app workers cannot race it.

    A crash after provider acceptance can repeat a message; SMTP/SendGrid do
    not supply an exactly-once send API. Unsent rows remain durable indefinitely.
    """
    now = now or datetime.now(timezone.utc)
    sender = sender or email_service._send_email
    sent = failed = 0
    for _ in range(limit):
        row = session.exec(select(EmailOutbox).where(
            EmailOutbox.sent_at.is_(None), EmailOutbox.next_attempt_at <= now,
            (EmailOutbox.expires_at.is_(None) | (EmailOutbox.expires_at > now)),
        ).order_by(EmailOutbox.created_at, EmailOutbox.id)
            .with_for_update(skip_locked=True).execution_options(populate_existing=True)).first()
        if row is None:
            session.rollback()
            break
        row.attempts += 1
        try:
            accepted = sender(row.to_email, row.subject, row.html_content, row.plain_text)
            if not accepted:
                raise RuntimeError("Email provider did not accept the message")
            row.sent_at = now
            row.last_error = None
            sent += 1
        except Exception as exc:
            row.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            row.next_attempt_at = now + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 7)))
            failed += 1
        session.add(row)
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
    return {"sent": sent, "failed": failed}

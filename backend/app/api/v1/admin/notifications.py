# app/api/v1/admin/notifications.py
"""
Admin endpoints for promotional broadcasts.

POST /admin/notifications/promotional  -> send a message to ALL active customers
GET  /admin/notifications/promotional  -> history of sent broadcasts
"""
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from uuid import UUID

from app.api.deps import SessionDep
from app.api.deps import require_perm
from app.models.user import User
from app.repositories import notification as notification_repo
from app.schemas.notification import (
    PromotionAudienceEstimate,
    PromotionBroadcastRequest,
    PromotionBroadcastResponse,
    PromotionHistoryItem,
    PromotionRetractResponse,
)
from app.services.email_service import email_service

router = APIRouter(prefix="/admin/notifications", tags=["Admin Notifications"])

#: Hard stop per blast — protects the mail provider quota (notably the
#: 500/day Gmail SMTP path) from an accidental send-to-everyone.
MAX_PROMO_EMAILS_PER_BLAST = 5000


def _deliver_broadcast_emails(
    broadcast_id: str,
    title: str,
    message: str,
    link: str | None,
    recipients: list[tuple[str, str | None]],
) -> None:
    """Blocking fan-out worker (runs in a thread via BackgroundTasks).

    Opens its own DB session — the request session is closed by the time
    background tasks run. Records sent/failed counts on the header row so
    the Promotions history shows the email outcome.
    """
    from sqlmodel import Session as _Session

    from app.db.database import engine

    sent = 0
    failed = 0
    for email, name in recipients:
        try:
            if email_service.send_promotion_email(email, name, title, message, link):
                sent += 1
            else:
                failed += 1
        except Exception as exc:  # one bad address must not kill the blast
            print(f"Promo email to {email} failed: {exc}")
            failed += 1
    with _Session(engine) as session:
        notification_repo.record_broadcast_email_result(
            session, UUID(broadcast_id), sent, failed
        )
        session.commit()
    print(f"Promo broadcast {broadcast_id}: {sent} emailed, {failed} failed")


async def _run_email_fanout(
    broadcast_id: str,
    title: str,
    message: str,
    link: str | None,
    recipients: list[tuple[str, str | None]],
) -> None:
    """Async wrapper keeping the event loop free during SMTP sends."""
    import anyio

    await anyio.to_thread.run_sync(
        lambda: _deliver_broadcast_emails(
            broadcast_id, title, message, link, recipients
        )
    )


@router.post("/promotional", response_model=PromotionBroadcastResponse)
def send_promotional_broadcast(
    payload: PromotionBroadcastRequest,
    background_tasks: BackgroundTasks,
    session: SessionDep,
    current_user: User = Depends(require_perm("promotions.send")),
):
    """Send a promotional message to every active customer's notification feed.

    Pass ``send_email: true`` to also email the blast to shoppers whose
    Email Notifications toggle is on. Email delivery runs in the
    background; its outcome lands on the broadcast history row.
    """
    broadcast_id, recipients = notification_repo.broadcast_promotion(
        session,
        title=payload.title.strip(),
        message=payload.message.strip(),
        link=payload.link,
        created_by=current_user.id,
    )

    emails_queued = 0
    if payload.send_email:
        email_users = notification_repo.promotion_email_audience(session)
        if len(email_users) > MAX_PROMO_EMAILS_PER_BLAST:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Email audience ({len(email_users)}) exceeds the per-blast "
                    f"limit of {MAX_PROMO_EMAILS_PER_BLAST}. Narrow the audience "
                    "or raise the limit before retrying."
                ),
            )
        snapshot = [
            (u.email, u.full_name or u.username) for u in email_users if u.email
        ]
        emails_queued = len(snapshot)
        if snapshot:
            background_tasks.add_task(
                _run_email_fanout,
                str(broadcast_id),
                payload.title.strip(),
                payload.message.strip(),
                payload.link,
                snapshot,
            )

    session.commit()

    return PromotionBroadcastResponse(
        broadcast_id=broadcast_id,
        title=payload.title.strip(),
        message=payload.message.strip(),
        link=payload.link,
        recipients_count=recipients,
        emails_queued=emails_queued,
        created_at=datetime.now(timezone.utc),
    )


@router.get("/promotional/audience-estimate", response_model=PromotionAudienceEstimate)
def promotion_audience_estimate(
    session: SessionDep,
    current_user: User = Depends(require_perm("promotions.send")),
):
    """Live recipient counts for the compose form (no PII, counts only)."""
    feed = notification_repo.promotion_feed_audience(session)
    email = notification_repo.promotion_email_audience(session)
    return PromotionAudienceEstimate(
        feed_recipients=len(feed), email_recipients=len(email)
    )


@router.get("/promotional", response_model=list[PromotionHistoryItem])
def promotional_history(
    session: SessionDep,
    current_user: User = Depends(require_perm("promotions.send")),
    skip: int = 0,
    limit: int = 20,
):
    """History of promotional broadcasts (newest first)."""
    return notification_repo.promotion_history(session, skip=skip, limit=limit)


@router.delete("/promotional/{broadcast_id}", response_model=PromotionRetractResponse)
def retract_promotional_broadcast(
    broadcast_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("promotions.send")),
):
    """Retract a broadcast — delete it from every recipient's feed."""
    deleted = notification_repo.retract_broadcast(session, broadcast_id)
    if deleted == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotional broadcast not found",
        )
    session.commit()
    return PromotionRetractResponse(deleted_count=deleted)
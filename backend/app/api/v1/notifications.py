# app/api/v1/notifications.py
"""
Notifications feed (works for any authenticated user).

- Admins/managers: order_placed / order_cancelled events.
- Customers: order_status updates and promotions (from admin broadcasts).

The WebSocket endpoint is kept for real-time clients; the REST feed below is
the source of truth (persisted in the `notifications` table).
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from uuid import UUID

from app.api.deps import SessionDep, CurrentUser
from app.repositories import notification as notification_repo
from app.schemas.notification import (
    DeleteResponse,
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationRead,
    UnreadCountResponse,
)
from app.services.notification_service import notification_service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


# ============ WebSocket (real-time, optional) ============

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = None):
    """Authenticated WebSocket endpoint for real-time notifications.

    The client must pass a valid JWT access token as ``?token=<jwt>``.
    The user_id is derived server-side from the token — clients can never
    impersonate another user.
    """
    from app.core.security import decode_access_token
    from app.db.database import get_session
    from app.repositories.user import get_user_by_email
    from app.repositories.token import session_is_valid

    await websocket.accept()

    if not token:
        await websocket.close(code=4401, reason="Missing token")
        return

    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=4401, reason="Invalid token")
        return

    email = payload.get("sub")
    # Resolve the user from a short-lived session (WS has no SessionDep).
    # NOTE: get_session() is a context-manager generator (yields inside
    # `with Session(...)`), so `next()` + `close()` won't work — iterate once.
    user_id: str | None = None
    try:
        session_gen = get_session()
        session = next(session_gen)
        try:
            user = get_user_by_email(session, email) if email else None
            if user is not None and user.is_active and session_is_valid(session, user, payload):
                user_id = str(user.id)
        finally:
            try:
                next(session_gen)
            except StopIteration:
                pass
    except Exception:
        user_id = None

    if user_id is None:
        await websocket.close(code=4401, reason="Unknown or inactive user")
        return

    await notification_service.connect(user_id, websocket)
    await websocket.send_json(
        {"type": "connected", "user_id": user_id, "message": "Successfully registered"}
    )

    try:
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_text("pong")
            # Any other frame is ignored (client stays connected).

    except WebSocketDisconnect:
        notification_service.disconnect(user_id, websocket)
    except Exception:
        notification_service.disconnect(user_id, websocket)


# ============ REST feed (source of truth) ============

@router.get("", response_model=NotificationListResponse)
def list_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
    audience: str | None = None,
):
    """Get the notification feed for the current user (newest first).

    Pass ``audience=shopper`` on the storefront (own order updates +
    promotions) or ``audience=staff`` in the admin panel (operational
    alerts). Omitting it keeps the legacy unfiltered feed.
    """
    if audience is not None and audience not in ("shopper", "staff"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audience must be 'shopper' or 'staff'",
        )
    items, total, unread = notification_repo.list_for_user(
        session, current_user.id, skip=skip, limit=limit,
        unread_only=unread_only, audience=audience,
    )
    return NotificationListResponse(items=items, total=total, unread_count=unread)


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(
    session: SessionDep,
    current_user: CurrentUser,
    audience: str | None = None,
):
    """Get the unread notification count for the current user."""
    if audience is not None and audience not in ("shopper", "staff"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audience must be 'shopper' or 'staff'",
        )
    _, _, unread = notification_repo.list_for_user(
        session, current_user.id, skip=0, limit=1, audience=audience
    )
    return UnreadCountResponse(count=unread)


@router.put("/mark-all-read", response_model=MarkAllReadResponse)
def mark_all_read(
    session: SessionDep,
    current_user: CurrentUser,
    audience: str | None = None,
):
    """Mark notifications as read (optionally scoped to an audience)."""
    if audience is not None and audience not in ("shopper", "staff"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="audience must be 'shopper' or 'staff'",
        )
    updated = notification_repo.mark_all_read(session, current_user.id, audience=audience)
    return MarkAllReadResponse(updated=updated)


@router.put("/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Mark a single notification as read."""
    notification = notification_repo.mark_read(session, current_user.id, notification_id)
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notification


@router.delete("/{notification_id}", response_model=DeleteResponse)
def remove_notification(
    notification_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    """Delete a single notification."""
    deleted = notification_repo.delete_notification(session, current_user.id, notification_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return DeleteResponse(ok=True)

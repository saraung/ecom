# app/repositories/notification.py
"""
Persistence layer for the notifications feed.

Admins/managers receive order_placed / order_cancelled events; customers
receive order_status updates and promotional broadcasts. All helpers only
stage rows (session.add) — the caller decides when to commit so notification
failures can never break the main order flow.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlmodel import Session, select, col

from app.models.notification import Notification, NotificationType, PromotionBroadcast
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.core.region import format_money

ADMIN_ROLES = (UserRole.manager, UserRole.admin)

#: Audience split for the notification feed. The storefront bell shows
#: shopper types only; the admin panel bell shows staff types only.
#: Without this, staff shopping on the storefront receive operational
#: alerts ("New Order #X from [customer]") with admin-panel links.
STAFF_NOTIFICATION_TYPES = (
    NotificationType.ORDER_PLACED,
    NotificationType.ORDER_CANCELLED,
    NotificationType.REFUND_APPROVAL,
)
SHOPPER_NOTIFICATION_TYPES = (
    NotificationType.ORDER_STATUS,
    NotificationType.PROMOTION,
)


def order_status_label(status: str | OrderStatus) -> str:
    """Human-readable order status for customer-facing copy.

    "out_for_delivery" -> "Out for Delivery" (never the raw snake_case value, and
    never "Rto" from str.capitalize()). Unknown values degrade gracefully.

    ⚠️ Accepts a raw value ("out_for_delivery") or an OrderStatus member — note
    str(OrderStatus.RTO) is "OrderStatus.RTO", so members are unwrapped first.
    """
    value = status.value if isinstance(status, OrderStatus) else str(status)
    try:
        return OrderStatus(value).label
    except ValueError:
        return value.replace("_", " ").title()


def _insert(
    session: Session,
    user_id: UUID,
    ntype: NotificationType,
    title: str,
    message: str | None = None,
    link: str | None = None,
    order_id: UUID | None = None,
    broadcast_id: UUID | None = None,
) -> Notification:
    notification = Notification(
        user_id=user_id,
        type=ntype,
        title=title,
        message=message,
        link=link,
        order_id=order_id,
        broadcast_id=broadcast_id,
    )
    session.add(notification)
    return notification


def _active_users_with_roles(session: Session, roles: tuple) -> list[User]:
    return session.exec(
        select(User).where(
            col(User.role).in_(roles),
            User.is_active == True,  # noqa: E712
        )
    ).all()


def _users_with_permission(session: Session, permission: str) -> list[User]:
    """Active users holding a dynamic permission (system + custom roles).

    Falls back to the legacy role column ONLY when the RBAC grant tables
    are absent/empty (pre-backfill databases) — never on a legitimately
    empty result, which must stay empty.
    """
    try:
        from app.models.rbac import Role, RolePermissionLink, UserRoleLink
        from app.models.rbac import Permission as RBACPermission

        grant_count = session.execute(
            select(func.count()).select_from(RolePermissionLink)
        ).scalar() or 0
        if grant_count == 0:
            raise LookupError("no RBAC grants seeded")
        rows = session.execute(
            select(User)
            .join(UserRoleLink, UserRoleLink.user_id == User.id)
            .join(Role, Role.id == UserRoleLink.role_id)
            .join(
                RolePermissionLink,
                RolePermissionLink.role_id == Role.id,
            )
            .join(
                RBACPermission,
                RBACPermission.id == RolePermissionLink.permission_id,
            )
            .where(
                User.is_active == True,  # noqa: E712
                RBACPermission.key == permission,
            )
        ).scalars().all()
        # De-duplicate (one row per role grant).
        seen, unique = set(), []
        for user in rows:
            if user.id not in seen:
                seen.add(user.id)
                unique.append(user)
        return unique
    except Exception:
        pass
    # Legacy fallback (pre-RBAC databases).
    legacy = {
        "orders.view": ADMIN_ROLES,
        "orders.update": ADMIN_ROLES,
    }.get(permission, ADMIN_ROLES)
    return _active_users_with_roles(session, legacy)


def _customer_label(session: Session, order: Order) -> str:
    customer = session.get(User, order.user_id)
    if customer is None:
        return "a customer"
    return customer.full_name or customer.username or customer.email


def notify_admins_order_placed(session: Session, order: Order) -> int:
    """Create an order_placed notification for every active orders viewer."""
    label = _customer_label(session, order)
    count = 0
    for admin in _users_with_permission(session, "orders.view"):
        _insert(
            session,
            admin.id,
            NotificationType.ORDER_PLACED,
            title=f"New Order #{order.order_number}",
            message=f"New order of {format_money(order.grand_total)} from {label}",
            link=f"/orders/{order.id}",
            order_id=order.id,
        )
        count += 1
    return count


def notify_approvers_refund_pending(
    session: Session, order: Order, ledger, requester: User
) -> list[User]:
    """Alert every ELIGIBLE approver that a refund awaits their decision.

    Eligible = active, holds orders.refund, authorized for the amount
    (unlimited or limit >= amount), and is not the requester. Without this,
    staged refunds sit invisible — nobody watches the ledger unprompted.
    Returns the notified users (for email fan-out by the caller).
    """
    from app.repositories import rbac as rbac_repo

    notified = []
    for candidate in _users_with_permission(session, "orders.refund"):
        if candidate.id == requester.id:
            continue
        roles = rbac_repo.get_user_roles(session, candidate.id)
        limits = [
            r.max_refund_amount for r in roles
            if r.max_refund_amount is not None
        ]
        unlimited = len(limits) < len(roles)
        if not unlimited and not limits:
            continue
        if not unlimited and max(limits) < ledger.amount:
            continue
        _insert(
            session,
            candidate.id,
            NotificationType.REFUND_APPROVAL,
            title=f"Refund approval needed — Order #{order.order_number}",
            message=(
                f"{format_money(ledger.amount)} refund requested by "
                f"{requester.full_name or requester.email}. "
                f"Reason: {ledger.reason or '—'}"
            ),
            link=f"/refunds?status=pending_approval",
            order_id=order.id,
        )
        notified.append(candidate)
    return notified


def notify_admins_order_cancelled(session: Session, order: Order) -> int:
    """Create an order_cancelled notification for every active orders viewer."""
    label = _customer_label(session, order)
    reason = f" Reason: {order.cancellation_reason}" if order.cancellation_reason else ""
    count = 0
    for admin in _users_with_permission(session, "orders.view"):
        _insert(
            session,
            admin.id,
            NotificationType.ORDER_CANCELLED,
            title=f"Order #{order.order_number} Cancelled",
            message=f"Order #{order.order_number} from {label} was cancelled.{reason}",
            link=f"/orders/{order.id}",
            order_id=order.id,
        )
        count += 1
    return count


def notify_customer_status_changed(session: Session, order: Order, new_status: str) -> int:
    """Notify the customer that their order status changed (user app feed)."""
    label = order_status_label(new_status)
    _insert(
        session,
        order.user_id,
        NotificationType.ORDER_STATUS,
        title=f"Order #{order.order_number} {label}",
        message=f"Your order #{order.order_number} is now {label}.",
        link=f"/orders/{order.id}",
        order_id=order.id,
    )
    return 1


def _promotion_audience(session: Session) -> list[User]:
    """Every true shopper (feed audience for promotions).

    Shoppers = active + push-enabled users holding ZERO dynamic
    permissions. The legacy ``role == customer`` check is kept only as a
    fallback for databases whose RBAC rows predate the backfill — under
    dynamic RBAC a custom role (e.g. "packer") otherwise keeps receiving
    shopper promos through its untouched legacy value.
    """
    from app.models.rbac import Role, RolePermissionLink, UserRoleLink

    grant_count = session.execute(
        select(func.count()).select_from(RolePermissionLink)
    ).scalar() or 0
    use_dynamic = grant_count > 0
    privileged_ids: set = set()
    if use_dynamic:
        privileged_ids = set(
            session.execute(
                select(UserRoleLink.user_id)
                .join(Role, Role.id == UserRoleLink.role_id)
                .join(
                    RolePermissionLink,
                    RolePermissionLink.role_id == Role.id,
                )
            ).scalars().all()
        )
    customers = session.execute(
        select(User).where(
            User.is_active == True,  # noqa: E712
            User.push_notifications_enabled == True,  # noqa: E712
            User.id.not_in(privileged_ids) if privileged_ids else True,
        )
    ).scalars().all()
    # Legacy fallback: no RBAC rows at all (pre-backfill DB) → legacy check.
    if not use_dynamic:
        customers = [u for u in customers if _legacy_is_customer(u)]
    return list(customers)


def promotion_email_audience(session: Session) -> list[User]:
    """Shopper audience further gated on the Email Notifications toggle.

    Same audience as the feed, minus anyone who turned
    ``email_notifications_enabled`` off (storefront/admin Settings).
    Staff are never recipients of promotions in any channel.
    """
    return [
        u for u in _promotion_audience(session)
        if bool(getattr(u, "email_notifications_enabled", True))
    ]


#: Public alias — the feed audience for the estimate endpoint.
promotion_feed_audience = _promotion_audience


def broadcast_promotion(
    session: Session,
    title: str,
    message: str,
    link: str | None = None,
    created_by: UUID | None = None,
) -> tuple[UUID, int]:
    """Create a promotion notification for every true shopper + header row.

    Only stages rows (feed + ``PromotionBroadcast`` header) — the caller
    commits, so notification failures can never break the main flow.
    """
    broadcast_id = uuid4()
    customers = _promotion_audience(session)
    for user in customers:
        _insert(
            session,
            user.id,
            NotificationType.PROMOTION,
            title=title,
            message=message,
            link=link,
            broadcast_id=broadcast_id,
        )
    session.add(
        PromotionBroadcast(
            id=broadcast_id,
            title=title,
            message=message,
            link=link,
            recipients_count=len(customers),
            created_by=created_by,
        )
    )
    return broadcast_id, len(customers)


def record_broadcast_email_result(
    session: Session, broadcast_id: UUID, sent: int, failed: int
) -> None:
    """Stage the email fan-out outcome on the broadcast header row."""
    header = session.get(PromotionBroadcast, broadcast_id)
    if header is None:
        return
    header.email_requested = True
    header.emails_sent = int(sent)
    header.emails_failed = int(failed)
    session.add(header)


def _legacy_is_customer(user: User) -> bool:
    return str(getattr(user.role, "value", user.role)) == "customer"


def list_for_user(
    session: Session,
    user_id: UUID,
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
    audience: str | None = None,
) -> tuple[list[Notification], int, int]:
    """Return (items, total, unread_count) for a user's feed, newest first.

    ``audience`` scopes notification types: "shopper" (own order updates +
    promotions, for the storefront bell) or "staff" (operational alerts,
    for the admin panel bell). None keeps the legacy unfiltered feed.
    """
    type_filter = None
    if audience == "shopper":
        type_filter = col(Notification.type).in_(SHOPPER_NOTIFICATION_TYPES)
    elif audience == "staff":
        type_filter = col(Notification.type).in_(STAFF_NOTIFICATION_TYPES)

    def _scoped(base):
        if type_filter is not None:
            return base.where(type_filter)
        return base

    query = _scoped(select(Notification).where(Notification.user_id == user_id))
    total_query = _scoped(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user_id)
    )
    unread_query = _scoped(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
    )

    if unread_only:
        query = query.where(Notification.is_read == False)  # noqa: E712

    items = session.exec(
        query.order_by(col(Notification.created_at).desc()).offset(skip).limit(limit)
    ).all()
    total = int(session.exec(total_query).one())
    unread = int(session.exec(unread_query).one())
    return list(items), total, unread


def mark_read(session: Session, user_id: UUID, notification_id: UUID) -> Notification | None:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        return None
    if not notification.is_read:
        notification.is_read = True
        session.add(notification)
        session.commit()
        session.refresh(notification)
    return notification


def mark_all_read(
    session: Session, user_id: UUID, audience: str | None = None
) -> int:
    statement = select(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False,  # noqa: E712
    )
    if audience == "shopper":
        statement = statement.where(
            col(Notification.type).in_(SHOPPER_NOTIFICATION_TYPES)
        )
    elif audience == "staff":
        statement = statement.where(
            col(Notification.type).in_(STAFF_NOTIFICATION_TYPES)
        )
    unread = session.exec(statement).all()
    for notification in unread:
        notification.is_read = True
        session.add(notification)
    session.commit()
    return len(unread)


def delete_notification(session: Session, user_id: UUID, notification_id: UUID) -> bool:
    notification = session.get(Notification, notification_id)
    if notification is None or notification.user_id != user_id:
        return False
    session.delete(notification)
    session.commit()
    return True


def retract_broadcast(session: Session, broadcast_id: UUID) -> int:
    """Delete every notification row belonging to a promotional broadcast.

    Also deletes the broadcast header, so a retracted promo vanishes from
    history too (emails already sent can't be recalled — only the record
    of the blast goes with it).
    """
    rows = session.exec(
        select(Notification).where(col(Notification.broadcast_id) == broadcast_id)
    ).all()
    for row in rows:
        session.delete(row)
    header = session.get(PromotionBroadcast, broadcast_id)
    if header is not None:
        session.delete(header)
    return len(rows)


def _aware_moment(value: datetime | None) -> datetime:
    """Normalize a stored timestamp to offset-aware (UTC) for sorting.

    Legacy ``notifications.created_at`` values come back offset-naive
    (plain TIMESTAMP column) while new header rows are offset-aware —
    comparing them raises ``TypeError`` and 500s the history endpoint.
    """
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def promotion_history(
    session: Session, skip: int = 0, limit: int = 20
) -> list[dict]:
    """Broadcast history, newest first — header rows plus legacy fallback.

    Header rows (all new broadcasts) carry email counts. Broadcasts that
    predate the header table are reconstructed by grouping their feed rows,
    exactly as before, with zeroed email fields.
    """
    headers = session.exec(
        select(PromotionBroadcast)
        .order_by(col(PromotionBroadcast.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    header_ids = {h.id for h in headers}
    items = [
        {
            "id": h.id,
            "title": h.title,
            "message": h.message,
            "link": h.link,
            "recipients_count": int(h.recipients_count or 0),
            "email_requested": bool(h.email_requested),
            "emails_sent": int(h.emails_sent or 0),
            "emails_failed": int(h.emails_failed or 0),
            "created_at": _aware_moment(h.created_at),
        }
        for h in headers
    ]
    # Legacy broadcasts without a header row (pre-migration sends).
    filters = [col(Notification.broadcast_id).is_not(None)]
    if header_ids:
        filters.append(col(Notification.broadcast_id).not_in(header_ids))
    rows = session.exec(
        select(
            Notification.broadcast_id,
            func.min(Notification.title),
            func.min(Notification.message),
            func.min(Notification.link),
            func.count(),
            func.min(Notification.created_at),
        )
        .where(*filters)
        .group_by(col(Notification.broadcast_id))
        .order_by(func.min(Notification.created_at).desc())
        .offset(skip)
        .limit(limit)
    ).all()
    items.extend(
        {
            "id": row[0],
            "title": row[1],
            "message": row[2],
            "link": row[3],
            "recipients_count": int(row[4]),
            "email_requested": False,
            "emails_sent": 0,
            "emails_failed": 0,
            "created_at": _aware_moment(row[5]),
        }
        for row in rows
    )
    items.sort(key=lambda e: e["created_at"], reverse=True)
    return items[:limit]

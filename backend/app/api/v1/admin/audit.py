# app/api/v1/admin/audit.py
"""Read-only admin audit log viewer.

Append-only by design: this router exposes no write/update/delete paths —
entries are created exclusively by server-side actions.

Guardrail (least-privilege):
- ``reports.view`` alone (manager/auditor) sees OPERATIONAL entries only
  (orders, refunds, coupons, products, categories, notifications, settings).
- Full log (user/role/invite identity actions) requires ``users.view`` as
  well — i.e. admins. Managers requesting a sensitive ``entity`` filter get
  403 instead of a silently empty list.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import SessionDep, require_perm
from app.models.user import User
from app.repositories import audit as audit_repo
from app.repositories import user as user_repo
from app.schemas.audit import AuditLogListResponse, AuditLogRead
from app.repositories import rbac as rbac_repo


router = APIRouter(prefix="/admin/audit-log", tags=["Admin Audit"])

#: Identity-sensitive entities — hidden from reports.view-only viewers.
SENSITIVE_ENTITIES = frozenset({"user", "role", "invite"})


def _is_full_auditor(session: SessionDep, user: User) -> bool:
    """True for admins (users.view) — sees identity actions too."""
    try:
        granted = set(rbac_repo.get_user_permissions(session, user.id))
    except Exception:
        legacy = str(getattr(user.role, "value", user.role) or "")
        return legacy == "admin"
    return "users.view" in granted


@router.get("", response_model=AuditLogListResponse)
def list_audit_entries(
    session: SessionDep,
    current_user: User = Depends(require_perm("reports.view")),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    action: str | None = Query(default=None),
    entity: str | None = Query(default=None),
    entity_id: UUID | str | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
):
    """List audit entries, newest first (requires reports.view).

    Managers/auditors see operational entries; identity entries
    (user/role/invite) require users.view.
    """
    full_access = _is_full_auditor(session, current_user)
    if entity is not None and entity in SENSITIVE_ENTITIES and not full_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewing user/role/invite audit entries requires users.view",
        )
    skip = (page - 1) * limit
    entries, total = audit_repo.list_entries(
        session,
        skip=skip,
        limit=limit,
        action=action,
        entity=entity,
        entity_id=entity_id,
        actor_id=actor_id,
        exclude_entities=None if full_access else sorted(SENSITIVE_ENTITIES),
    )
    # Batch-resolve actor emails (one query, no N+1).
    actor_ids = {e.actor_id for e in entries if e.actor_id}
    emails: dict = {}
    for actor_id_ in actor_ids:
        user = user_repo.get_user_by_id(session, actor_id_)
        if user is not None:
            emails[actor_id_] = user.email
    return AuditLogListResponse(
        entries=[
            AuditLogRead(
                id=e.id,
                actor_id=e.actor_id,
                actor_email=emails.get(e.actor_id),
                action=e.action,
                entity=e.entity,
                entity_id=e.entity_id,
                before=e.before,
                after=e.after,
                ip_address=e.ip_address,
                created_at=e.created_at,
            )
            for e in entries
        ],
        total=total,
        page=page,
        limit=limit,
        total_pages=(total + limit - 1) // limit if limit else 1,
    )

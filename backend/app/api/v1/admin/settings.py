# app/api/v1/admin/settings.py
"""Admin store-policy settings (requires settings.manage — admins only).

Reads/writes the singleton ``store_settings`` row that replaced the
env-only knobs (tax, shipping, COD, restocking fees, expiry). Every save
refreshes the in-process cache immediately and writes an audit entry with
the before/after diff — money-rule changes must always have a trail.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.deps import SessionDep, require_perm
from app.core.config import STORE_DEFAULTS
from app.core.store_settings import (
    RESTOREABLE_ACTIONS,
    get_store_settings,
    read_store_settings,
    restore_values,
    update_store_settings,
    refresh_store_settings,
)
from app.models.user import User
from app.repositories import audit as audit_repo
from app.repositories import user as user_repo
from app.schemas.store_settings import (
    StoreSettingsHistoryResponse,
    StoreSettingsRead,
    StoreSettingsRestoreRequest,
    StoreSettingsUpdate,
)

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])

#: Setting keys, in display order. Derived from the canonical defaults so a
#: newly added key can never be silently invisible in the admin API.
_READABLE = tuple(STORE_DEFAULTS)

#: Audit actions that count as settings history (saves + restores — a
#: restore is itself undoable, so restoring a restore works).
_HISTORY_ACTIONS = RESTOREABLE_ACTIONS


def _read_model(session: SessionDep) -> StoreSettingsRead:
    """Side-effect-free read: never seeds. Missing row ⇒ env snapshot."""
    from app.core.region import currency_code, tax_label

    row = read_store_settings(session)
    if row is None:
        snap = get_store_settings(session, seed=False)
        return StoreSettingsRead(
            **{key: getattr(snap, key) for key in _READABLE},
            source="environment",
            updated_at=None,
            updated_by=None,
            currency=currency_code(),
            tax_label=tax_label(),
        )
    snap = get_store_settings(session)
    data = {key: getattr(snap, key) for key in _READABLE}
    return StoreSettingsRead(
        **data,
        source=snap.source,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
        currency=currency_code(),
        tax_label=tax_label(),
    )


@router.get("/store", response_model=StoreSettingsRead)
def get_store_policy(
    session: SessionDep,
    current_user: User = Depends(require_perm("settings.manage")),
):
    """Current store policy + where it came from (database vs env)."""
    return _read_model(session)


@router.put("/store", response_model=StoreSettingsRead)
def update_store_policy(
    payload: StoreSettingsUpdate,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("settings.manage")),
):
    """Save store policy. Partial update — omitted fields keep their value."""
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nothing to update",
        )
    if (
        "cod_min_order_value" in data
        or "cod_max_order_value" in data
    ):
        before = get_store_settings(session, seed=False)
        lo = data.get("cod_min_order_value", before.cod_min_order_value)
        hi = data.get("cod_max_order_value", before.cod_max_order_value)
        if hi < lo:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="cod_max_order_value must be >= cod_min_order_value",
            )

    before = {key: getattr(get_store_settings(session, seed=False), key) for key in data}
    row = update_store_settings(session, data, actor_id=current_user.id, commit=False)
    after = {key: getattr(row, key) for key in data}
    audit_repo.log_and_commit(
        session,
        action="settings.store_updated",
        entity="settings",
        entity_id=None,
        actor_id=current_user.id,
        before=before,
        after=after,
        ip_address=audit_repo.client_ip(request),
    )
    refresh_store_settings(session)
    return _read_model(session)


@router.get("/store/history", response_model=StoreSettingsHistoryResponse)
def get_store_history(
    session: SessionDep,
    current_user: User = Depends(require_perm("settings.manage")),
    limit: int = Query(default=5, ge=1, le=20),
):
    """Recent settings saves/restores, newest first (requires settings.manage).

    Deliberately scoped here (not via /admin/audit-log) so settings managers
    never depend on reports.view to see their own change history.
    """
    from app.schemas.store_settings import StoreSettingsHistoryEntry

    # Pull a few extra: entries whose before/after carry no known keys
    # (e.g. hand-written rows) are skipped below.
    entries, _ = audit_repo.list_entries(
        session, skip=0, limit=limit * 2, entity="settings"
    )
    items = []
    actor_ids = {e.actor_id for e in entries if e.actor_id}
    emails: dict = {}
    for actor_id in actor_ids:
        user = user_repo.get_user_by_id(session, actor_id)
        if user is not None:
            emails[actor_id] = user.email
    for e in entries:
        if e.action not in _HISTORY_ACTIONS:
            continue
        before = e.before or {}
        after = e.after or {}
        keys = sorted(set(before) | set(after))
        keys = [k for k in keys if k in _READABLE]
        if not keys:
            continue
        items.append(
            StoreSettingsHistoryEntry(
                audit_id=e.id,
                action=e.action,
                actor_email=emails.get(e.actor_id),
                created_at=e.created_at,
                changes=[
                    {"key": k, "before": before.get(k), "after": after.get(k)}
                    for k in keys
                ],
            )
        )
        if len(items) >= limit:
            break
    return StoreSettingsHistoryResponse(entries=items)


@router.post("/store/restore", response_model=StoreSettingsRead)
def restore_store_policy(
    payload: StoreSettingsRestoreRequest,
    request: Request,
    session: SessionDep,
    current_user: User = Depends(require_perm("settings.manage")),
):
    """Undo one past save: re-apply its `before` values (requires settings.manage).

    Only keys changed by that save are touched; everything else keeps its
    current value. The restore is itself audited (action
    "settings.store_restored", linked via entity_id), so a restore can be
    restored — there is always a way back.
    """
    try:
        before, entry = restore_values(session, payload.audit_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc) or "Not a settings change entry",
        )
    # Reuse the update schema so restored values pass the same range
    # validation as typed-in ones (a legacy row could predate a rule).
    data = StoreSettingsUpdate(**before).model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nothing to restore from this entry",
        )
    current = {key: getattr(get_store_settings(session, seed=False), key) for key in data}
    row = update_store_settings(session, data, actor_id=current_user.id, commit=False)
    after = {key: getattr(row, key) for key in data}
    audit_repo.log_and_commit(
        session,
        action="settings.store_restored",
        entity="settings",
        entity_id=str(entry.id),
        actor_id=current_user.id,
        before=current,
        after=after,
        ip_address=audit_repo.client_ip(request),
    )
    refresh_store_settings(session)
    return _read_model(session)

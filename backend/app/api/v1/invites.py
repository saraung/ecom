# app/api/v1/invites.py
"""Staff invitation flow (admin invites by email; invitee accepts by link).

- POST /admin/invites (+ list/resend/revoke): users.manage_roles.
- GET  /invites/accept?token=... : public pre-check (valid/email/roles).
- POST /invites/accept: public. Token proves email ownership, so:
    - new staffer (username+password supplied): account created with the
      email locked + verified, invited roles auto-assigned, session tokens
      returned immediately;
    - existing account: call authenticated as the matching email with no
      password fields to link the invited roles.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from sqlalchemy import select

from app.api.deps import SessionDep, require_perm
from app.core.config import settings
from app.core.security import hash_password
from app.models.staff_invite import StaffInvite, StaffInviteStatus
from app.models.user import User
from app.repositories import audit as audit_repo
from app.repositories import rbac as rbac_repo
from app.repositories import user as user_repo
from app.repositories import token as token_repo
from app.core.security import create_access_token
from app.schemas.invite import (
    InviteAcceptPreview,
    InviteAcceptRequest,
    InviteCreate,
    InviteRead,
)
from app.schemas.token import TokenPair
from app.services.email_outbox import enqueue_email
from html import escape


router = APIRouter(tags=["Staff Invites"])

INVITE_TTL_DAYS = 7


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _get_live_invite(session: SessionDep, token: str) -> StaffInvite | None:
    invite = session.execute(
        select(StaffInvite).where(
            StaffInvite.token_hash == _hash_token(token)
        )
    ).scalars().first()
    if invite is None or invite.status != StaffInviteStatus.PENDING:
        return None
    expires = invite.expires_at
    now = (
        datetime.now(expires.tzinfo)
        if getattr(expires, "tzinfo", None)
        else datetime.now(timezone.utc).replace(tzinfo=None)
    )
    if expires < now:
        invite.status = StaffInviteStatus.EXPIRED
        session.add(invite)
        session.commit()
        return None
    return invite


def _send_invite_email(email: str, token: str, role_slugs: list[str], *, session, invite) -> None:
    link = f"{settings.ADMIN_FRONTEND_URL}/accept-invite?token={token}"
    roles = escape(", ".join(role_slugs))
    enqueue_email(session, f"invite:{invite.id}:{invite.token_hash}", "send_email",
        expires_at=invite.expires_at,
        to=email,
        subject="You've been invited to join the store admin",
        html_body=f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
            <h2 style="color: #4F46E5;">Store admin invitation</h2>
            <p>Hello,</p>
            <p>You've been invited to join the store admin with role(s): <strong>{roles}</strong>.</p>
            <p><a href="{link}" style="display: inline-block; background: #4F46E5; color: #fff; padding: 12px 24px; border-radius: 8px; text-decoration: none;">Accept invitation</a></p>
            <p style="color: #6b7280; font-size: 14px;">This link expires in {INVITE_TTL_DAYS} days and can only be used once.</p>
            <p style="color: #6b7280; font-size: 14px;">If you didn't expect this, you can safely ignore this email.</p>
        </div>
        """,
    )


def _ip(request: Request | None) -> str | None:
    return audit_repo.client_ip(request)


# ============ ADMIN: manage invites ============

@router.post("/admin/invites", response_model=InviteRead, status_code=status.HTTP_201_CREATED)
def create_invite(
    data: InviteCreate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("users.manage_roles")),
):
    """Invite a staffer by email + roles (requires users.manage_roles).

    Guardrail: grant ⊆ held — no invited role may grant a permission the
    inviter does not hold themselves. A manager cannot mint an admin peer
    via invite, nor invite into powers they lack.
    """
    inviter_perms = set(rbac_repo.get_user_permissions(session, current_user.id))
    roles = []
    for slug in data.role_slugs:
        role = rbac_repo.get_role_by_slug(session, slug)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown role: {slug}",
            )
        role_keys = set(rbac_repo.get_role_permission_keys(session, role.id))
        escalating = rbac_repo.escalation_for_grant(inviter_perms, role_keys)
        if escalating:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{slug}' grants {sorted(escalating)} which you do "
                    "not hold — invite blocked (privilege escalation)"
                ),
            )
        roles.append(role)

    # One live invite per email — resend the existing one instead.
    live = session.execute(
        select(StaffInvite).where(
            StaffInvite.email == str(data.email),
            StaffInvite.status == StaffInviteStatus.PENDING,
        )
    ).scalars().first()
    if live is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A pending invite already exists for this email. Resend or revoke it.",
        )

    token = secrets.token_urlsafe(32)
    invite = StaffInvite(
        email=str(data.email),
        role_slugs=[r.slug for r in roles],
        invited_by=current_user.id,
        token_hash=_hash_token(token),
        status=StaffInviteStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS),
    )
    session.add(invite)
    audit_repo.log(
        session, action="invite.created", entity="invite",
        entity_id=invite.id, actor_id=current_user.id,
        after={"email": invite.email, "roles": invite.role_slugs},
        ip_address=_ip(request),
    )
    _send_invite_email(invite.email, token, invite.role_slugs, session=session, invite=invite)
    session.commit()
    session.refresh(invite)
    return invite


@router.get("/admin/invites", response_model=list[InviteRead])
def list_invites(
    session: SessionDep,
    current_user: User = Depends(require_perm("users.manage_roles")),
    status_filter: str | None = None,
):
    """List invites, newest first (requires users.manage_roles)."""
    from sqlalchemy import select

    statement = select(StaffInvite).order_by(StaffInvite.created_at.desc())
    if status_filter:
        statement = statement.where(StaffInvite.status == status_filter)
    return list(session.execute(statement).scalars().all())


@router.post("/admin/invites/{invite_id}/resend", response_model=InviteRead)
def resend_invite(
    invite_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("users.manage_roles")),
):
    """Rotate the token + expiry and re-send (requires users.manage_roles).

    Re-validates before rotating: invited roles must still exist, and the
    resender must still hold everything they grant (a demoted resender's
    stale invite cannot be revived into an escalation).
    """
    invite = session.get(StaffInvite, invite_id)
    if not invite or invite.status != StaffInviteStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending invite not found",
        )
    resender_perms = set(rbac_repo.get_user_permissions(session, current_user.id))
    for slug in invite.role_slugs:
        role = rbac_repo.get_role_by_slug(session, slug)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invited role no longer exists: {slug} — "
                    "revoke this invite and send a fresh one"
                ),
            )
        escalating = rbac_repo.escalation_for_grant(
            resender_perms,
            set(rbac_repo.get_role_permission_keys(session, role.id)),
        )
        if escalating:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{slug}' grants {sorted(escalating)} which you do "
                    "not hold — resend blocked (privilege escalation)"
                ),
            )
    token = secrets.token_urlsafe(32)
    invite.token_hash = _hash_token(token)
    invite.expires_at = datetime.now(timezone.utc) + timedelta(days=INVITE_TTL_DAYS)
    session.add(invite)
    audit_repo.log(
        session, action="invite.resent", entity="invite",
        entity_id=invite.id, actor_id=current_user.id,
        ip_address=_ip(request),
    )
    _send_invite_email(invite.email, token, invite.role_slugs, session=session, invite=invite)
    session.commit()
    session.refresh(invite)
    return invite


@router.delete("/admin/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("users.manage_roles")),
):
    """Revoke a pending invite (requires users.manage_roles)."""
    invite = session.get(StaffInvite, invite_id)
    if not invite or invite.status != StaffInviteStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pending invite not found",
        )
    invite.status = StaffInviteStatus.REVOKED
    session.add(invite)
    audit_repo.log(
        session, action="invite.revoked", entity="invite",
        entity_id=invite.id, actor_id=current_user.id,
        after={"email": invite.email},
        ip_address=_ip(request),
    )
    session.commit()
    return None


# ============ PUBLIC: accept ============

@router.get("/invites/accept", response_model=InviteAcceptPreview)
def preview_invite(token: str, session: SessionDep):
    """Pre-check an invite link (public, reveals email + roles only)."""
    invite = _get_live_invite(session, token)
    if invite is None:
        return InviteAcceptPreview(
            valid=False, message="This invitation link is invalid or expired."
        )
    return InviteAcceptPreview(
        valid=True, email=invite.email, role_slugs=invite.role_slugs
    )


@router.post("/invites/accept")
def accept_invite(
    data: InviteAcceptRequest,
    session: SessionDep,
    request: Request,
):
    """Accept an invite (public; token IS the email proof).

    New staffer: supply username+password (+optional full_name) → account
    created verified with invited roles, session tokens returned.
    Existing account: call authenticated as the invite email with no
    password fields → invited roles linked.
    """
    # Optional auth: resolve the caller without failing anonymous requests.
    caller: User | None = None
    try:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            from app.api.deps import get_current_user
            caller = get_current_user(session, auth.split(" ", 1)[1])
    except Exception:
        caller = None

    invite = _get_live_invite(session, data.token)
    if invite is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This invitation link is invalid or expired.",
        )
    roles = []
    for slug in invite.role_slugs:
        role = rbac_repo.get_role_by_slug(session, slug)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invited role no longer exists: {slug}",
            )
        roles.append(role)

    # The inviter's authority is re-checked at accept time: a pending invite
    # from a since-demoted (or deleted) inviter cannot escalate on arrival.
    # Invites minted before inviter tracking existed (invited_by NULL) skip
    # this check — they predate the guarantee either way.
    if invite.invited_by is not None:
        inviter = user_repo.get_user_by_id(session, invite.invited_by)
        inviter_perms = (
            set(rbac_repo.get_user_permissions(session, inviter.id))
            if inviter is not None and inviter.is_active
            else set()
        )
        for role in roles:
            escalating = rbac_repo.escalation_for_grant(
                inviter_perms,
                set(rbac_repo.get_role_permission_keys(session, role.id)),
            )
            if escalating:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        "The inviter no longer holds "
                        f"{sorted(escalating)} granted by role '{role.slug}' — "
                        "ask an administrator to send a fresh invite"
                    ),
                )
        if inviter is None or not inviter.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "The inviter is no longer an active staffer — ask an "
                    "administrator to send a fresh invite"
                ),
            )

    existing = user_repo.get_user_by_email(session, invite.email)
    if existing is not None:
        # Link path: must prove ownership — either the logged-in matching
        # account or a fresh password for it.
        if caller is not None and caller.id == existing.id:
            pass
        elif data.password:
            if not data.password or len(data.password) < 8:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password must be at least 8 characters",
                )
            existing.password_hash = hash_password(data.password)
            token_repo.invalidate_user_sessions(session, existing)
            if existing.auth_provider == "google":
                existing.auth_provider = "both"
            session.add(existing)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "An account already exists for this email. Sign in with "
                    "it and accept again, or set a password to claim it."
                ),
            )
        # Additive: accepting an invite grants roles, never strips the
        # ones the account already holds (an existing admin accepting a
        # staff invite must not be silently demoted).
        current_slugs = set(rbac_repo.get_user_role_slugs(session, existing.id))
        merged = {r.slug: r for r in roles}
        for slug in current_slugs:
            if slug not in merged:
                kept = rbac_repo.get_role_by_slug(session, slug)
                if kept is not None:
                    merged[slug] = kept
        rbac_repo.set_user_roles(
            session, existing, list(merged.values()), assigned_by=invite.invited_by, commit=False
        )
        invite.status = StaffInviteStatus.ACCEPTED
        invite.accepted_at = datetime.now(timezone.utc)
        session.add(invite)
        audit_repo.log(
            session, action="invite.accepted", entity="invite",
            entity_id=invite.id, actor_id=existing.id,
            after={"email": invite.email, "roles": invite.role_slugs},
            ip_address=_ip(request),
        )
        session.commit()
        return {"linked": True, "email": invite.email, "roles": invite.role_slugs}

    # Create path: username + password required.
    if not data.username or not data.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username and password are required to create your account",
        )
    if user_repo.get_user_by_username(session, data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )
    user = User(
        email=invite.email,
        username=data.username,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        phone=None,
        is_active=True,
        email_verified=True,  # invite link proves inbox control
        auth_provider="email",
    )
    session.add(user)
    session.flush()
    rbac_repo.set_user_roles(session, user, roles, assigned_by=invite.invited_by, commit=False)
    invite.status = StaffInviteStatus.ACCEPTED
    invite.accepted_at = datetime.now(timezone.utc)
    session.add(invite)
    audit_repo.log(
        session, action="invite.accepted", entity="invite",
        entity_id=invite.id, actor_id=user.id,
        after={"email": invite.email, "roles": invite.role_slugs},
        ip_address=_ip(request),
    )
    session.commit()

    from app.api.v1.auth import _issue_tokens
    return _issue_tokens(session, user, "admin").model_dump()

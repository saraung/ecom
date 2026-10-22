# app/api/v1/admin/roles.py
"""Dynamic RBAC management: permission catalog + role CRUD.

- The permission catalog is seeded, not created here — POST/DELETE on
  permissions are intentionally absent. Admins *assign* permissions to roles.
- Role reads are visible to anyone who can assign roles (users.manage_roles)
  or manage roles (roles.manage); writes need roles.manage.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import SessionDep, require_perm
from app.models.user import User
from app.repositories import rbac as rbac_repo
from app.repositories import user as user_repo
from app.repositories import audit as audit_repo
from app.schemas.rbac import (
    PermissionRead,
    RoleCreate,
    RolePermissionRead,
    RoleUpdate,
    UserRolesUpdate,
)

router = APIRouter(prefix="/admin", tags=["Admin Roles"])


def _role_read(session: SessionDep, role) -> RolePermissionRead:
    return RolePermissionRead(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        slug=role.slug,
        description=role.description,
        is_system=role.is_system,
        max_refund_amount=role.max_refund_amount,
        permissions=rbac_repo.get_role_permission_keys(session, role.id),
        user_count=rbac_repo.count_role_users(session, role.id),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


# ============ PERMISSIONS (catalog, read-only) ============

@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("roles.manage", "users.manage_roles", require_all=False)
    ),
):
    """List the seeded permission catalog grouped client-side by module."""
    return rbac_repo.list_permissions(session)


# ============ ROLES ============

@router.get("/roles", response_model=list[RolePermissionRead])
def list_roles(
    session: SessionDep,
    current_user: User = Depends(
        require_perm("roles.manage", "users.manage_roles", require_all=False)
    ),
):
    """List all roles with their granted permission keys + user counts."""
    return [_role_read(session, role) for role in rbac_repo.list_roles(session)]


@router.post("/roles", response_model=RolePermissionRead,
             status_code=status.HTTP_201_CREATED)
def create_role(
    data: RoleCreate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("roles.manage")),
):
    """Create a custom role from catalog permission keys.

    Grant ⊆ held: the new role may not grant permissions the creator does
    not hold themselves (a roles.manage-only holder cannot mint a role
    carrying settings.manage they lack).
    """
    slug = data.slug or data.name.strip().lower().replace(" ", "-")
    # Unknown keys are a validation error (400) and take precedence over
    # the escalation check below — same order as set_role_permissions.
    unknown = rbac_repo.validate_permission_keys(data.permission_keys)
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown permission keys: {', '.join(unknown)}",
        )
    creator_perms = set(rbac_repo.get_user_permissions(session, current_user.id))
    escalating = rbac_repo.escalation_for_grant(
        creator_perms, data.permission_keys
    )
    if escalating:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role would grant {sorted(escalating)} which you do not "
                "hold — creation blocked (privilege escalation)"
            ),
        )
    try:
        role = rbac_repo.create_role(
            session,
            name=data.name,
            slug=slug,
            description=data.description,
            permission_keys=data.permission_keys,
            created_by=current_user.id,
            max_refund_amount=data.max_refund_amount,
            commit=False,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    audit_repo.log_and_commit(
        session, action="role.created", entity="role", entity_id=role.id,
        actor_id=current_user.id,
        after={"name": role.name, "slug": role.slug,
               "permissions": data.permission_keys},
        ip_address=audit_repo.client_ip(request),
    )
    return _role_read(session, role)


@router.get("/roles/{role_id}", response_model=RolePermissionRead)
def get_role(
    role_id: UUID,
    session: SessionDep,
    current_user: User = Depends(
        require_perm("roles.manage", "users.manage_roles", require_all=False)
    ),
):
    role = rbac_repo.get_role_by_id(session, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    return _role_read(session, role)


@router.put("/roles/{role_id}", response_model=RolePermissionRead)
def update_role(
    role_id: UUID,
    data: RoleUpdate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("roles.manage")),
):
    """Rename a role and/or REPLACE its permission set."""
    role = rbac_repo.get_role_by_id(session, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    before = {
        "name": role.name,
        "permissions": rbac_repo.get_role_permission_keys(session, role.id),
    }

    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role name cannot be empty",
            )
        role.name = data.name.strip()
    if data.description is not None:
        role.description = data.description
    if "max_refund_amount" in data.model_fields_set:
        role.max_refund_amount = data.max_refund_amount
    if data.permission_keys is not None:
        unknown = rbac_repo.validate_permission_keys(data.permission_keys)
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown permission keys: {', '.join(unknown)}",
            )
        editor_perms = set(rbac_repo.get_user_permissions(session, current_user.id))
        escalating = rbac_repo.escalation_for_grant(
            editor_perms, data.permission_keys
        )
        if escalating:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role would grant {sorted(escalating)} which you do not "
                    "hold — update blocked (privilege escalation)"
                ),
            )
        if "users.manage_roles" in before["permissions"] and (
            "users.manage_roles" not in data.permission_keys
        ):
            # Stripping the key: the role's assignees must not be its last
            # holders, or the tenant loses its administrators.
            others = rbac_repo.user_ids_with_permission(
                session, "users.manage_roles", exclude_role_id=role.id
            )
            if rbac_repo.user_ids_with_role(session, role.id) and not others:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "Cannot strip users.manage_roles — this role's "
                        "assignees are its last holders"
                    ),
                )
        try:
            rbac_repo.set_role_permissions(
                session, role, data.permission_keys, commit=False
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
            )
    else:
        session.add(role)

    from datetime import datetime, timezone
    role.updated_at = datetime.now(timezone.utc)
    session.add(role)
    audit_repo.log_and_commit(
        session, action="role.updated", entity="role", entity_id=role.id,
        actor_id=current_user.id,
        before=before,
        after={"name": role.name,
               "permissions": rbac_repo.get_role_permission_keys(session, role.id),
               "max_refund_amount": str(role.max_refund_amount)
               if role.max_refund_amount is not None else None},
        ip_address=audit_repo.client_ip(request),
    )
    return _role_read(session, role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: UUID,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("roles.manage")),
):
    """Delete a custom role (system roles and in-use roles are protected)."""
    role = rbac_repo.get_role_by_id(session, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Role not found"
        )
    snapshot = {"name": role.name, "slug": role.slug}
    try:
        rbac_repo.delete_role(session, role, commit=False)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        )
    audit_repo.log_and_commit(
        session, action="role.deleted", entity="role", entity_id=role_id,
        actor_id=current_user.id, before=snapshot,
        ip_address=audit_repo.client_ip(request),
    )
    return None


# ============ USER <-> ROLE ASSIGNMENT ============

@router.get("/users/{user_id}/roles", response_model=list[str])
def get_user_roles(
    user_id: UUID,
    session: SessionDep,
    current_user: User = Depends(require_perm("users.view")),
):
    """Role slugs assigned to a user."""
    user = user_repo.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return rbac_repo.get_user_role_slugs(session, user_id)


@router.put("/users/{user_id}/roles", response_model=list[str])
def set_user_roles(
    user_id: UUID,
    data: UserRolesUpdate,
    session: SessionDep,
    request: Request,
    current_user: User = Depends(require_perm("users.manage_roles")),
):
    """REPLACE a user's role set with existing role slugs.

    Guardrails (shared with the invite path):
    - grant ⊆ held: no role in the new set may grant a permission the
      assigner does not hold themselves (privilege escalation block);
    - the change may not remove the last holder of ``users.manage_roles``
      (availability block — an unadministered tenant cannot recover).
    """
    user = user_repo.get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own roles",
        )
    assigner_perms = set(rbac_repo.get_user_permissions(session, current_user.id))
    roles = []
    new_keys: set[str] = set()
    for slug in data.role_slugs:
        role = rbac_repo.get_role_by_slug(session, slug)
        if role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown role: {slug}",
            )
        role_keys = set(rbac_repo.get_role_permission_keys(session, role.id))
        escalating = rbac_repo.escalation_for_grant(assigner_perms, role_keys)
        if escalating:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{slug}' grants {sorted(escalating)} which you do "
                    "not hold — assignment blocked (privilege escalation)"
                ),
            )
        new_keys |= role_keys
        roles.append(role)
    if rbac_repo.would_remove_last_holder(
        session, "users.manage_roles", user.id,
        still_grants="users.manage_roles" in new_keys,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Cannot remove the last holder of users.manage_roles — "
                "assign it to someone else first"
            ),
        )
    before = rbac_repo.get_user_role_slugs(session, user.id)
    rbac_repo.set_user_roles(
        session, user, roles, assigned_by=current_user.id, commit=False
    )
    audit_repo.log_and_commit(
        session, action="user.roles_assigned", entity="user", entity_id=user.id,
        actor_id=current_user.id,
        before={"roles": before},
        after={"roles": [role.slug for role in roles]},
        ip_address=audit_repo.client_ip(request),
    )
    return [role.slug for role in roles]

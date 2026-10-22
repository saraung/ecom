# scripts/seed_rbac.py
"""Idempotent RBAC seed: permissions catalog + 4 system roles + backfill.

Usage (from repo root ``/home/yatnam/FAST/Com``)::

    .venv/bin/python scripts/seed_rbac.py

Safe to re-run: inserts missing permissions/roles/links only, then ensures
every user has at least one role link derived from their legacy ``users.role``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlmodel import Session

from app.core.rbac_catalog import PERMISSIONS, SYSTEM_ROLES
from app.db.database import engine
from app.models.rbac import (
    Permission,
    Role,
    RolePermissionLink,
    UserRoleLink,
)
from app.models.user import User


def seed(session: Session) -> dict:
    # --- Permissions -----------------------------------------------------
    existing_keys = set(session.execute(select(Permission.key)).scalars().all())
    perms_by_key: dict[str, Permission] = {}
    new_perms = 0
    for key, label, module, description in PERMISSIONS:
        perm = None
        if key not in existing_keys:
            perm = Permission(
                key=key, label=label, module=module, description=description
            )
            session.add(perm)
            new_perms += 1
    session.flush()
    for perm in session.execute(select(Permission)).scalars().all():
        perms_by_key[perm.key] = perm

    # --- System roles ----------------------------------------------------
    new_roles = 0
    for slug, spec in SYSTEM_ROLES.items():
        role = session.execute(
            select(Role).where(Role.slug == slug)
        ).scalar_one_or_none()
        if role is None:
            role = Role(
                name=spec["name"],
                slug=slug,
                description=spec["description"],
                is_system=True,
                max_refund_amount=spec.get("max_refund_amount"),
            )
            session.add(role)
            session.flush()
            new_roles += 1
        # Sync the refund authority with the catalog (idempotent).
        if role.max_refund_amount != spec.get("max_refund_amount"):
            role.max_refund_amount = spec.get("max_refund_amount")
            session.add(role)
        # Sync the permission set to the catalog (idempotent replace).
        wanted = set(spec["permissions"])
        current = set(
            session.execute(
                select(Permission.key)
                .join(
                    RolePermissionLink,
                    RolePermissionLink.permission_id == Permission.id,
                )
                .where(RolePermissionLink.role_id == role.id)
            ).scalars().all()
        )
        for key in wanted - current:
            session.add(
                RolePermissionLink(
                    role_id=role.id, permission_id=perms_by_key[key].id
                )
            )
        for key in current - wanted:
            perm = perms_by_key[key]
            link = session.execute(
                select(RolePermissionLink).where(
                    RolePermissionLink.role_id == role.id,
                    RolePermissionLink.permission_id == perm.id,
                )
            ).scalar_one_or_none()
            if link is not None:
                session.delete(link)
    session.flush()

    # --- Backfill user -> role links from legacy users.role --------------
    roles_by_slug = {
        role.slug: role
        for role in session.execute(select(Role)).scalars().all()
    }
    linked_user_ids = set(
        session.execute(select(UserRoleLink.user_id)).scalars().all()
    )
    new_links = 0
    for user in session.execute(select(User)).scalars().all():
        if user.id in linked_user_ids:
            continue
        legacy = getattr(user.role, "value", user.role) or "customer"
        role = roles_by_slug.get(legacy, roles_by_slug.get("customer"))
        if role is None:
            continue
        session.add(UserRoleLink(user_id=user.id, role_id=role.id))
        new_links += 1

    session.commit()
    return {
        "new_permissions": new_perms,
        "new_roles": new_roles,
        "new_user_links": new_links,
    }


def main() -> None:
    with Session(engine) as session:
        result = seed(session)
    print(f"✅ RBAC seed done: {result}")


if __name__ == "__main__":
    main()

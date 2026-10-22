"""
Tests for RBAC assignment guardrails.

Covers:
  1. escalation_for_grant() pure subset semantics.
  2. would_remove_last_holder() availability semantics.
  3. PUT /admin/users/{id}/roles: subset block, happy-path grant, last-holder block.
  4. PUT /admin/users/{id}/role (legacy): same guards as the new path.
  5. POST/PUT /admin/roles: creators/editors cannot grant powers they lack.
  6. Stripping users.manage_roles from its last-granting role is blocked.
  7. Deleting/deactivating the last holder is blocked.
  8. Invite resend re-validates roles + resender authority (before any email).
  9. Invite accept is additive for existing users; demoted inviters blocked.

Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_rbac_guards.py -q
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.core.rbac_catalog import PERMISSION_KEYS
from app.models.rbac import Permission
from app.models.staff_invite import StaffInvite, StaffInviteStatus
from app.models.user import User
from app.repositories import rbac as rbac_repo
from app.schemas.admin import AdminUserUpdate
from app.schemas.rbac import RoleCreate, RoleUpdate, UserRolesUpdate


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        for key in PERMISSION_KEYS:
            s.add(Permission(key=key, label=key, module=key.split(".")[0]))
        s.commit()
        yield s


def _user(session, email, username):
    u = User(email=email, username=username)
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


def _role(session, slug, keys):
    return rbac_repo.create_role(
        session, name=slug.title(), slug=slug, description=None,
        permission_keys=list(keys),
    )


def _link(session, user, *roles):
    return rbac_repo.set_user_roles(session, user, list(roles))


def _stub(uid):
    return SimpleNamespace(id=uid)


# --- pure helpers ---

def test_1_escalation_subset_semantics():
    assert rbac_repo.escalation_for_grant({"a", "b"}, {"a"}) == set()
    assert rbac_repo.escalation_for_grant({"a"}, {"a", "b"}) == {"b"}
    assert rbac_repo.escalation_for_grant(None, {"a"}) == {"a"}
    assert rbac_repo.escalation_for_grant({"a"}, None) == set()


def test_2_last_holder_semantics(session):
    admin_role = _role(session, "superadmin", ["users.manage_roles", "users.view"])
    viewer_role = _role(session, "viewer", ["users.view"])
    alice = _user(session, "alice@x.io", "alice")
    bob = _user(session, "bob@x.io", "bob")
    _link(session, alice, admin_role)

    # Sole holder, losing the grant -> orphan.
    assert rbac_repo.would_remove_last_holder(
        session, "users.manage_roles", alice.id, still_grants=False
    ) is True
    # Non-holder can never orphan.
    assert rbac_repo.would_remove_last_holder(
        session, "users.manage_roles", bob.id, still_grants=False
    ) is False
    # Keeping the grant is always safe.
    assert rbac_repo.would_remove_last_holder(
        session, "users.manage_roles", alice.id, still_grants=True
    ) is False
    # With two holders, either may go.
    _link(session, bob, admin_role)
    assert rbac_repo.would_remove_last_holder(
        session, "users.manage_roles", alice.id, still_grants=False
    ) is False
    # Unrelated role assignment never orphans.
    _link(session, bob, viewer_role)
    assert rbac_repo.would_remove_last_holder(
        session, "users.manage_roles", bob.id, still_grants=False
    ) is False


# --- assignment endpoints ---

def test_3_set_roles_subset_and_last_holder(session):
    from app.api.v1.admin.roles import set_user_roles as api_set_roles

    hr_role = _role(session, "hr", ["users.manage_roles", "users.view"])
    staff_role = _role(session, "staffx", ["products.view"])
    view_role = _role(session, "viewx", ["users.view"])
    hr = _user(session, "hr@x.io", "hr")
    target = _user(session, "t@x.io", "t")
    other = _user(session, "o@x.io", "o")
    _link(session, hr, hr_role)

    # HR lacks products.view -> granting staffx is escalation (403).
    with pytest.raises(HTTPException) as exc:
        api_set_roles(
            target.id, UserRolesUpdate(role_slugs=["staffx"]),
            session, None, _stub(hr.id),
        )
    assert exc.value.status_code == 403

    # Granting only held powers works.
    assert api_set_roles(
        target.id, UserRolesUpdate(role_slugs=["viewx"]),
        session, None, _stub(hr.id),
    ) == ["viewx"]

    # A co-holder makes demotion safe: hr demotes `other`, then `other`
    # (now holding viewx only) attempts to demote hr — the last holder —
    # and the availability guard blocks it with 400.
    admin_role = _role(
        session, "adminx", ["users.manage_roles", "users.view", "products.view"]
    )
    _link(session, other, admin_role)
    assert api_set_roles(
        other.id, UserRolesUpdate(role_slugs=["viewx"]),
        session, None, _stub(hr.id),
    ) == ["viewx"]
    with pytest.raises(HTTPException) as exc2:
        api_set_roles(
            hr.id, UserRolesUpdate(role_slugs=["viewx"]),
            session, None, _stub(other.id),
        )
    assert exc2.value.status_code == 400


def test_4_legacy_path_escalation_blocked(session):
    from app.api.v1.admin.users import update_user_role as api_legacy_role

    hr_role = _role(session, "hr2", ["users.manage_roles", "users.view"])
    # Legacy endpoint only accepts legacy slugs (schema enum): a role
    # carrying the legacy "admin" slug plus powers hr lacks is escalation.
    _role(session, "admin", ["users.manage_roles", "settings.manage"])
    hr = _user(session, "hr2@x.io", "hr2")
    target = _user(session, "t2@x.io", "t2")
    _link(session, hr, hr_role)

    with pytest.raises(HTTPException) as exc:
        api_legacy_role(
            target.id, AdminUserUpdate(role="admin"), session, None, _stub(hr.id),
        )
    assert exc.value.status_code == 403
    # Unknown slug is still a 400 (enum passes, lookup fails).
    with pytest.raises(HTTPException) as exc2:
        api_legacy_role(
            target.id, AdminUserUpdate(role="staff"), session, None, _stub(hr.id),
        )
    assert exc2.value.status_code == 400


def test_5_role_create_update_subset(session):
    from app.api.v1.admin.roles import create_role as api_create
    from app.api.v1.admin.roles import update_role as api_update

    partial = _role(session, "partial", ["roles.manage", "users.view"])
    creator = _user(session, "c@x.io", "c")
    _link(session, creator, partial)

    with pytest.raises(HTTPException) as exc:
        api_create(
            RoleCreate(name="Sneaky", permission_keys=["settings.manage"]),
            session, None, _stub(creator.id),
        )
    assert exc.value.status_code == 403

    victim = _role(session, "victim", ["users.view"])
    with pytest.raises(HTTPException) as exc2:
        api_update(
            victim.id, RoleUpdate(permission_keys=["users.view", "settings.manage"]),
            session, None, _stub(creator.id),
        )
    assert exc2.value.status_code == 403
    # In-subset edits still work.
    out = api_update(
        victim.id, RoleUpdate(description="ok"),
        session, None, _stub(creator.id),
    )
    assert out.description == "ok"


def test_6_strip_last_granting_role_blocked(session):
    from app.api.v1.admin.roles import update_role as api_update

    sole = _role(session, "sole", ["users.manage_roles", "users.view"])
    boss = _user(session, "boss@x.io", "boss")
    editor = _user(session, "ed@x.io", "ed")
    _link(session, boss, sole)
    _link(session, editor, sole)
    with pytest.raises(HTTPException) as exc:
        api_update(
            sole.id, RoleUpdate(permission_keys=["users.view"]),
            session, None, _stub(editor.id),
        )
    assert exc.value.status_code == 400


def test_7_delete_deactivate_last_holder_blocked(session):
    from app.api.v1.admin.users import delete_user as api_delete
    from app.api.v1.admin.users import update_user_status as api_status

    adm = _role(session, "adm", ["users.manage_roles", "users.view"])
    boss = _user(session, "boss7@x.io", "boss7")
    other = _user(session, "other7@x.io", "other7")
    _link(session, boss, adm)

    with pytest.raises(HTTPException) as exc:
        api_delete(boss.id, session, None, _stub(other.id))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc2:
        api_status(boss.id, AdminUserUpdate(is_active=False), session, None, _stub(other.id))
    assert exc2.value.status_code == 400
    # Second holder present -> allowed (use fresh users to avoid orphans).
    _link(session, other, adm)
    api_status(boss.id, AdminUserUpdate(is_active=False), session, None, _stub(other.id))
    assert session.get(type(boss), boss.id).is_active is False


# --- invites ---

def _invite(session, email, slugs, inviter_id, token="tok123"):
    from app.api.v1 import invites as invites_api

    inv = StaffInvite(
        email=email, role_slugs=list(slugs), invited_by=inviter_id,
        token_hash=invites_api._hash_token(token),
        status=StaffInviteStatus.PENDING,
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv


def test_8_invite_accept_is_additive(session):
    from app.api.v1 import invites as invites_api
    from app.schemas.invite import InviteAcceptRequest

    admin_role = _role(session, "fulladmin", list(PERMISSION_KEYS))
    staff_role = _role(session, "staffer", ["products.view"])
    boss = _user(session, "boss8@x.io", "boss8")
    newcomer = _user(session, "new8@x.io", "new8")
    _link(session, boss, admin_role)
    _link(session, newcomer, staff_role)
    _invite(session, "new8@x.io", ["fulladmin"], boss.id)

    out = invites_api.accept_invite(
        InviteAcceptRequest(token="tok123", password="newpass123"),
        session, SimpleNamespace(headers={}),
    )
    assert out["linked"] is True
    slugs = set(rbac_repo.get_user_role_slugs(session, newcomer.id))
    # Union, not replace: pre-existing staffer role survives.
    assert slugs == {"staffer", "fulladmin"}


def test_9_invite_accept_blocked_for_demoted_inviter(session):
    from app.api.v1 import invites as invites_api
    from app.schemas.invite import InviteAcceptRequest

    admin_role = _role(session, "fulladmin9", list(PERMISSION_KEYS))
    staff_role = _role(session, "staffer9", ["products.view"])
    boss = _user(session, "boss9@x.io", "boss9")
    newcomer = _user(session, "new9@x.io", "new9")
    _link(session, boss, admin_role)
    _invite(session, "new9@x.io", ["staffer9"], boss.id)
    # Inviter loses everything before the invite is used.
    rbac_repo.set_user_roles(session, boss, [])

    with pytest.raises(HTTPException) as exc:
        invites_api.accept_invite(
            InviteAcceptRequest(token="tok123", password="newpass123"),
            session, SimpleNamespace(headers={}),
        )
    assert exc.value.status_code == 403
    assert rbac_repo.get_user_role_slugs(session, newcomer.id) == []


def test_10_resend_revalidates(session):
    from app.api.v1 import invites as invites_api

    admin_role = _role(session, "fulladmin10", list(PERMISSION_KEYS))
    boss = _user(session, "boss10@x.io", "boss10")
    helper = _user(session, "help10@x.io", "help10")
    _link(session, boss, admin_role)
    inv = _invite(session, "gone10@x.io", ["ghost-role"], boss.id)
    # Deleted role -> 400 before any email is attempted.
    with pytest.raises(HTTPException) as exc:
        invites_api.resend_invite(inv.id, session, None, _stub(helper.id))
    assert exc.value.status_code == 400

    staff_role = _role(session, "staffer10", ["products.view"])
    inv2 = _invite(session, "ok10@x.io", ["staffer10"], boss.id, token="tok456")
    # Resender holding nothing cannot revive a grant -> 403, no email.
    with pytest.raises(HTTPException) as exc2:
        invites_api.resend_invite(inv2.id, session, None, _stub(helper.id))
    assert exc2.value.status_code == 403

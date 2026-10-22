"""
Functional test for the admin per-user addresses endpoint.

Verifies:
  1. `get_user_addresses` (GET /admin/users/{id}/addresses) returns the
     TARGET user's addresses — NOT the current/admin user's own addresses.
  2. Returns an empty list for a user with no saved addresses.
  3. 404 for an unknown user.

Run:  PYTHONPATH=. python tests/test_admin_user_addresses.py
"""
from uuid import uuid4

from fastapi import HTTPException
from sqlmodel import SQLModel, Session, create_engine

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.address import Address

from app.api.v1.admin.users import get_user_addresses

ENGINE = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

ADMIN_ID = None
CUSTOMER_ID = None
CUSTOMER_NO_ADDR_ID = None


def _seed():
    global ADMIN_ID, CUSTOMER_ID, CUSTOMER_NO_ADDR_ID
    SQLModel.metadata.create_all(ENGINE)
    with Session(ENGINE) as s:
        admin = User(
            username="admin", email="admin@test.com", full_name="Admin",
            hashed_password="x", role=UserRole.admin, is_active=True,
        )
        s.add(admin)
        s.commit()
        s.refresh(admin)
        ADMIN_ID = admin.id
        # Admin has their OWN address — must NOT leak into customer results
        s.add(Address(
            user_id=admin.id, label="Admin Home", line1="0 Admin St", city="Pune",
            state="MH", postal_code="411001", country="IN", is_default=True,
        ))

        customer = User(
            username="customer", email="customer@test.com", full_name="Customer",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(customer)
        s.commit()
        s.refresh(customer)
        CUSTOMER_ID = customer.id
        s.add(Address(
            user_id=customer.id, label="Home", line1="1 Main St", city="Mumbai",
            state="MH", postal_code="400001", country="IN", is_default=True,
        ))
        s.add(Address(
            user_id=customer.id, label="Work", line1="2 Work St", city="Mumbai",
            state="MH", postal_code="400002", country="IN", is_default=False,
        ))

        no_addr = User(
            username="fresh", email="fresh@test.com", full_name="Fresh",
            hashed_password="x", role=UserRole.customer, is_active=True,
        )
        s.add(no_addr)
        s.commit()
        s.refresh(no_addr)
        CUSTOMER_NO_ADDR_ID = no_addr.id

        s.commit()


def setup_module():
    _ensure_setup()


def test_1_returns_target_users_addresses_only():
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        result = get_user_addresses(session=s, user_id=CUSTOMER_ID, current_user=admin)

    assert len(result) == 2, result
    labels = {a.label for a in result}
    assert labels == {"Home", "Work"}, labels
    assert all(a.user_id == CUSTOMER_ID for a in result)
    # The admin's own address must NOT appear
    assert all(a.label != "Admin Home" for a in result)
    print("  ✅ returns only the target user's addresses (2), admin's own excluded")


def test_2_empty_list_for_user_without_addresses():
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        result = get_user_addresses(session=s, user_id=CUSTOMER_NO_ADDR_ID, current_user=admin)
    assert result == [], result
    print("  ✅ empty list for a user with no addresses")


def test_3_404_for_unknown_user():
    with Session(ENGINE) as s:
        admin = s.get(User, ADMIN_ID)
        try:
            get_user_addresses(session=s, user_id=uuid4(), current_user=admin)
            assert False, "Expected HTTPException 404"
        except HTTPException as e:
            assert e.status_code == 404, e.status_code
            assert "User not found" in e.detail, e.detail
    print("  ✅ 404 raised for unknown user")


def _ensure_setup():
    global ADMIN_ID, CUSTOMER_ID, CUSTOMER_NO_ADDR_ID
    if ADMIN_ID is None:
        _seed()
        print(f"Seeded DB (admin={ADMIN_ID}, customer={CUSTOMER_ID}, fresh={CUSTOMER_NO_ADDR_ID})")


if __name__ == "__main__":
    _ensure_setup()
    test_1_returns_target_users_addresses_only()
    test_2_empty_list_for_user_without_addresses()
    test_3_404_for_unknown_user()
    print("\nAll admin-user-addresses tests passed ✅")

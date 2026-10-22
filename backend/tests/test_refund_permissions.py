from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.api.v1.admin.refunds import admin_cancel_order
from app.models.address import Address
from app.models.order import Order, OrderStatus
from app.models.rbac import Permission, Role, RolePermissionLink, UserRoleLink
from app.models.refund import Refund, RefundStatus
from app.models.user import User
from app.schemas.refund import AdminCancelRequest
from app.services import refund_service as service


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _role(s, user, key, limit=None):
    role = Role(name="Custom", slug=uuid4().hex, max_refund_amount=limit)
    permission = s.exec(select(Permission).where(Permission.key == key)).first()
    if permission is None:
        permission = Permission(key=key, label=key, module="orders")
        s.add(permission)
    s.add(role)
    s.flush()
    s.add_all([RolePermissionLink(role_id=role.id, permission_id=permission.id),
               UserRoleLink(role_id=role.id, user_id=user.id)])
    s.commit()


def _setup(s):
    operator = User(email="op@example.com", username="op", password_hash="x")
    buyer = User(email="buyer@example.com", username="buyer", password_hash="x")
    s.add_all([operator, buyer])
    s.flush()
    addr = Address(user_id=buyer.id, line1="Main", city="Mumbai", state="MH",
                   postal_code="400001", country="India")
    s.add(addr)
    s.flush()
    order = Order(order_number=uuid4().hex, user_id=buyer.id, shipping_address_id=addr.id,
                  billing_address_id=addr.id, subtotal=Decimal("100"), grand_total=Decimal("100"),
                  status=OrderStatus.CONFIRMED, payment_status="paid", payment_method="online")
    s.add(order)
    s.commit()
    _role(s, operator, "orders.update")
    return operator, order


def test_refund_now_denied_before_cancel_mutation(session):
    user, order = _setup(session)
    with pytest.raises(HTTPException) as exc:
        admin_cancel_order(order.id, AdminCancelRequest(reason="test", refund_choice="now"),
                           session, None, user)
    assert exc.value.status_code == 403
    session.commit()
    session.refresh(order)
    assert order.status == OrderStatus.CONFIRMED
    assert session.exec(select(Refund)).all() == []


def test_direct_request_and_execution_require_refund_grant(session):
    user, order = _setup(session)
    with pytest.raises(HTTPException) as exc:
        service.request_admin_refund(session, order, user, "test")
    assert exc.value.status_code == 403
    with pytest.raises(HTTPException) as exc:
        service.process_refund(session, order, OrderStatus.CONFIRMED, approved_by=user.id)
    assert exc.value.status_code == 403
    assert session.exec(select(Refund)).all() == []


def test_approval_cannot_bypass_service_permission(session):
    user, order = _setup(session)
    ledger = Refund(order_id=order.id, amount=Decimal("50"), idempotency_key="test",
                    status=RefundStatus.PENDING_APPROVAL, requested_by=order.user_id)
    session.add(ledger)
    session.commit()
    with pytest.raises(HTTPException) as exc:
        service.approve_refund(session, ledger, user)
    assert exc.value.status_code == 403
    assert ledger.status == RefundStatus.PENDING_APPROVAL


def test_unrelated_unlimited_role_does_not_expand_refund_limit(session):
    user, order = _setup(session)
    _role(session, user, "orders.refund", Decimal("50"))
    assert service.effective_refund_limit(session, user) == Decimal("50")
    assert service.refund_authorization(session, user, order, Decimal("100"))["requires_approval"]


def test_cancel_without_money_still_requires_only_order_update(session):
    user, order = _setup(session)
    result = admin_cancel_order(order.id, AdminCancelRequest(reason="test", refund_choice="later",
                               notify_customer=False), session, None, user)
    assert result["status"] == "cancelled"
    assert session.exec(select(Refund)).all() == []

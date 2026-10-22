from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.api.v1 import categories, coupons
from app.api.v1.admin import content, roles, users, products, reviews, settings, refunds
from app.core import store_settings
from app.core.rbac_catalog import PERMISSION_KEYS
from app.models.address import Address
from app.models.admin_audit import AdminAuditLog
from app.models.category import Category
from app.models.content_block import ContentBlock
from app.models.coupon import Coupon
from app.models.email_outbox import EmailOutbox
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.product import Product
from app.models.rbac import Permission, Role
from app.models.refund import Refund
from app.models.review import Review
from app.models.store_settings import StoreSettings
from app.models.user import User
from app.repositories import rbac
from app.schemas.admin import AdminUserUpdate
from app.schemas.category import CategoryCreate
from app.schemas.content import ContentBlockCreate, ContentBlockUpdate
from app.schemas.coupon import CouponCreate
from app.schemas.rbac import RoleCreate, RoleUpdate, UserRolesUpdate
from app.schemas.refund import AdminRefundRequest
from app.schemas.review import ReviewVisibilityUpdate
from app.schemas.store_settings import StoreSettingsUpdate


@pytest.fixture
def data():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    store_settings.invalidate_cache()
    with Session(engine) as s:
        s.add_all([Permission(key=key, label=key, module=key.split('.')[0]) for key in PERMISSION_KEYS])
        actor = User(email="audit@example.com", username="audit")
        target = User(email="target@example.com", username="target")
        block = ContentBlock(key="home.hero", title="Original")
        product = Product(name="Audit", slug="audit", price=Decimal("100"))
        s.add_all([actor, target, block, product, StoreSettings(id=1)])
        s.commit()
        admin_role = rbac.create_role(s, "Admin", "audit-admin", None, list(PERMISSION_KEYS))
        role = rbac.create_role(s, "Original", "audit-viewer", None, ["users.view"])
        rbac.set_user_roles(s, actor, [admin_role])
        rbac.set_user_roles(s, target, [role])
        review = Review(product_id=product.id, user_id=target.id, rating=5)
        address = Address(user_id=target.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        s.add_all([review, address])
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=target.id, shipping_address_id=address.id,
                      billing_address_id=address.id, subtotal=Decimal("100"), grand_total=Decimal("100"),
                      payment_method="online", status=OrderStatus.CANCELLED, payment_status="paid")
        s.add(order)
        s.flush()
        s.add(Payment(order_id=order.id, provider="razorpay", provider_payment_id="order_audit",
                      provider_payment_intent="pay_audit", amount=Decimal("100"), status=PaymentStatus.SUCCEEDED))
        s.commit()
        yield s, actor, target, block, product, role, review, order
    store_settings.invalidate_cache()
    engine.dispose()


@pytest.mark.parametrize("operation", [
    "content_create", "content_update", "content_delete", "category_create", "coupon_create",
    "role_create", "role_update", "role_delete", "role_assign", "user_status",
    "product_bulk", "review_hide", "review_delete", "settings_update", "refund_execute",
])
def test_audit_insert_failure_cannot_leave_business_mutation(data, operation, monkeypatch):
    s, actor, target, block, product, role, review, order = data
    if operation == "role_delete":
        rbac.set_user_roles(s, target, [])
    monkeypatch.setattr("app.services.refund_service.get_payment_service_for_payment", lambda p:
                        Mock(create_refund=Mock(return_value={"status": "processed", "refund_id": "rfnd_audit"})))
    actions = {
        "content_create": lambda: content.create_block(ContentBlockCreate(key="home.hero", title="New"), None, s, actor),
        "content_update": lambda: content.update_block(block.id, ContentBlockUpdate(title="Changed"), None, s, actor),
        "content_delete": lambda: content.delete_block(block.id, None, s, actor),
        "category_create": lambda: categories.create_category(CategoryCreate(name="New", slug="new"), s, None, actor),
        "coupon_create": lambda: coupons.create_coupon(CouponCreate(code="AUDIT", value=10), s, None, actor),
        "role_create": lambda: roles.create_role(RoleCreate(name="New", slug="new-role", permission_keys=["users.view"]), s, None, actor),
        "role_update": lambda: roles.update_role(role.id, RoleUpdate(name="Changed", permission_keys=[]), s, None, actor),
        "role_delete": lambda: roles.delete_role(role.id, s, None, actor),
        "role_assign": lambda: roles.set_user_roles(target.id, UserRolesUpdate(role_slugs=["audit-admin"]), s, None, actor),
        "user_status": lambda: users.update_user_status(target.id, AdminUserUpdate(is_active=False), s, None, actor),
        "product_bulk": lambda: products.bulk_update_product_status([product.id], False, s, None, actor),
        "review_hide": lambda: reviews.set_review_visibility(review.id, ReviewVisibilityUpdate(is_hidden=True), None, s, actor),
        "review_delete": lambda: reviews.delete_review(review.id, None, s, actor),
        "settings_update": lambda: settings.update_store_policy(StoreSettingsUpdate(tax_rate=0.25), None, s, actor),
        "refund_execute": lambda: refunds.refund_cancelled_order(order.id, AdminRefundRequest(reason="Return"), s, None, actor),
    }
    original_rate = s.get(StoreSettings, 1).tax_rate
    def fail(*args):
        raise RuntimeError("audit insert failed")
    event.listen(AdminAuditLog, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="audit insert failed"):
            actions[operation]()
    finally:
        event.remove(AdminAuditLog, "before_insert", fail)
    assert s.exec(select(AdminAuditLog)).all() == []
    assert len(s.exec(select(ContentBlock)).all()) == 1
    assert s.get(ContentBlock, block.id).title == "Original"
    assert s.exec(select(Category)).all() == []
    assert s.exec(select(Coupon)).all() == []
    assert len(s.exec(select(Role)).all()) == 2
    assert s.get(Role, role.id).name == "Original"
    assert rbac.get_role_permission_keys(s, role.id) == ["users.view"]
    if operation != "role_delete":
        assert rbac.get_user_role_slugs(s, target.id) == ["audit-viewer"]
    assert s.get(User, target.id).is_active is True
    assert s.get(Product, product.id).is_active is True
    assert s.get(Review, review.id).is_hidden is False
    assert s.get(StoreSettings, 1).tax_rate == original_rate
    assert s.get(Order, order.id).payment_status == "paid"
    assert s.exec(select(Refund)).all() == []
    assert s.exec(select(EmailOutbox)).all() == []


def test_settings_seed_and_cache_are_not_published_on_failed_audit(data):
    s, actor, *_ = data
    s.delete(s.get(StoreSettings, 1))
    s.commit()
    original = store_settings.get_store_settings()
    def fail(*args):
        raise RuntimeError("audit failed")
    event.listen(AdminAuditLog, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError):
            settings.update_store_policy(StoreSettingsUpdate(tax_rate=0.25), None, s, actor)
    finally:
        event.remove(AdminAuditLog, "before_insert", fail)
    assert s.get(StoreSettings, 1) is None
    assert store_settings.get_store_settings().tax_rate == original.tax_rate


def test_success_has_one_commit_for_mutation_and_audit(data):
    s, actor, _, block, *_ = data
    commits = []
    event.listen(s, "after_commit", lambda session: commits.append(True))
    content.update_block(block.id, ContentBlockUpdate(title="Changed"), None, s, actor)
    assert len(commits) == 1
    assert s.exec(select(AdminAuditLog)).one().after["title"] == "Changed"
    assert s.get(ContentBlock, block.id).title == "Changed"

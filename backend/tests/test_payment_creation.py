from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
import pytest
from sqlalchemy import event
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.api.v1 import payments as api
from app.models.address import Address
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.payment_creation import PaymentCreation
from app.models.user import User
from app.schemas.payment import PaymentCreateRequest
from app.services.payment_creation import create_or_reuse_intent
from app.services.razorpay_service import RazorpayPaymentService
from app.services.stripe_service import StripePaymentService


def seed(engine):
    with Session(engine) as s:
        user = User(email="creation@example.com", username="creation")
        s.add(user)
        s.flush()
        addr = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        s.add(addr)
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=user.id, shipping_address_id=addr.id,
                      billing_address_id=addr.id, subtotal=Decimal("100"), grand_total=Decimal("100"), payment_method="online")
        s.add(order)
        s.commit()
        return user.id, order.id


class Provider:
    provider_name = "razorpay"
    def __init__(self):
        self.creates = 0
        self.recoveries = 0
        self.remote = None
        self.lose_response = False
    def create_payment_intent(self, order, method, *, idempotency_key, currency):
        self.creates += 1
        self.remote = dict(client_secret="order_remote", payment_intent_id="order_remote",
                           order_id=str(order.id), amount="100", currency=currency, is_dummy=False)
        if self.lose_response:
            raise TimeoutError("response lost")
        return self.remote
    def recover_payment_creation(self, order, attempt):
        self.recoveries += 1
        return self.remote


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    ids = seed(engine)
    provider = Provider()
    monkeypatch.setattr(api, "get_payment_service", lambda: provider)
    monkeypatch.setattr("app.services.payment_creation.get_payment_service_for_payment", lambda p: provider)
    with Session(engine) as s:
        yield s, ids, provider
    engine.dispose()


def create(data):
    s, (uid, oid), _ = data
    return api.create_payment_intent(PaymentCreateRequest(order_id=oid), s, s.get(User, uid))


def test_repeated_requests_reuse_one_payment_and_recorded_response(db):
    first = create(db)
    assert create(db) == first
    s, _, provider = db
    assert provider.creates == 1 and provider.recoveries == 0
    assert len(s.exec(select(Payment)).all()) == 1
    assert s.exec(select(PaymentCreation)).one().state == "ready"


@pytest.mark.parametrize("state", [OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED,
                                    OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED])
def test_ineligible_orders_never_contact_provider(db, state):
    s, (_, oid), provider = db
    order = s.get(Order, oid)
    order.status = state
    s.add(order)
    s.commit()
    with pytest.raises(HTTPException) as exc:
        create(db)
    assert exc.value.status_code == 409
    assert provider.creates == 0


def test_expired_or_legacy_captured_order_cannot_create(db):
    s, (_, oid), provider = db
    order = s.get(Order, oid)
    order.placed_at = datetime.now(timezone.utc) - timedelta(days=1)
    s.add(order)
    s.commit()
    with pytest.raises(HTTPException, match="409"):
        create(db)
    order.placed_at = datetime.now(timezone.utc)
    s.add(order)
    s.add(Payment(order_id=oid, provider="razorpay", provider_payment_id="old", amount=Decimal("100"), status=PaymentStatus.SUCCEEDED))
    s.commit()
    with pytest.raises(HTTPException, match="409"):
        create(db)
    assert provider.creates == 0


def test_provider_success_then_lost_response_is_recovered_without_second_create(db):
    s, _, provider = db
    provider.lose_response = True
    with pytest.raises(HTTPException) as exc:
        create(db)
    assert exc.value.status_code == 503
    assert s.exec(select(PaymentCreation)).one().state == "submitting"
    assert s.exec(select(Payment)).all() == []
    assert create(db).payment_intent_id == "order_remote"
    assert provider.creates == provider.recoveries == 1


def test_final_commit_failure_leaves_durable_recoverable_attempt(db):
    s, _, provider = db
    def fail(session):
        if provider.remote:
            raise RuntimeError("final commit failed")
    event.listen(s, "before_commit", fail)
    with pytest.raises(RuntimeError):
        create(db)
    event.remove(s, "before_commit", fail)
    assert s.exec(select(PaymentCreation)).one().state == "submitting"
    create(db)
    assert provider.creates == 1
    assert len(s.exec(select(Payment)).all()) == 1


def test_unknown_creation_blocks_instead_of_blind_retry(db):
    s, (_, oid), provider = db
    s.add(PaymentCreation(order_id=oid, provider="razorpay", currency="INR", amount=Decimal("100"),
                          payment_method="online", state="submitting"))
    s.commit()
    with pytest.raises(HTTPException) as exc:
        create(db)
    assert exc.value.status_code == 503
    assert provider.creates == 0


def test_legacy_pending_payment_is_reused(db):
    s, (_, oid), provider = db
    s.add(Payment(order_id=oid, provider="razorpay", provider_payment_id="legacy", amount=Decimal("100")))
    s.commit()
    assert create(db).client_secret == "legacy"
    assert provider.creates == 0


def test_razorpay_recovery_uses_receipt_and_never_posts():
    service = RazorpayPaymentService()
    service.client = Mock()
    attempt = SimpleNamespace(creation_key="pa-test")
    service.client.order.all.return_value = {"items": [{"id": "order_recovered", "receipt": "pa-test", "amount": 10000, "currency": "INR"}]}
    response = service.recover_payment_creation(SimpleNamespace(id=uuid4()), attempt)
    assert response["payment_intent_id"] == "order_recovered"
    assert response["amount"] == Decimal("100")
    service.client.order.create.assert_not_called()
    service.client.order.all.return_value = {"items": []}
    assert service.recover_payment_creation(SimpleNamespace(id=uuid4()), attempt) is None


def test_stripe_native_key_currency_and_old_key_read_only_recovery(monkeypatch):
    service = StripePaymentService()
    service.is_configured = True
    # Existing adapter accepts Stripe's attribute + mapping access style.
    class Intent(dict):
        __getattr__ = dict.__getitem__
    monkeypatch.setattr("app.services.stripe_service.stripe.PaymentIntent.create",
                        send := Mock(return_value=Intent(id="pi_test", client_secret="secret", currency="jpy")))
    order = SimpleNamespace(id=uuid4(), order_number="test", grand_total=Decimal("100"))
    service.create_payment_intent(order, idempotency_key="stable", currency="JPY")
    assert send.call_args.kwargs["idempotency_key"] == "stable"
    assert send.call_args.kwargs["amount"] == 100
    assert send.call_args.kwargs["currency"] == "jpy"
    monkeypatch.setattr("app.services.stripe_service.stripe.PaymentIntent.search", search := Mock(return_value={"data": []}))
    attempt = SimpleNamespace(created_at=datetime.now(timezone.utc) - timedelta(days=2), creation_key="stable")
    assert service.recover_payment_creation(order, attempt) is None
    assert send.call_count == 1 and search.call_count == 1


def test_creation_migration(db):
    s, *_ = db
    engine = s.get_bind()
    s.close()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/r3f4a5b6c7d8_payment_creation_attempts.py"
    spec = importlib.util.spec_from_file_location("creation_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE payment_creations")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    assert "payment_creations" in __import__("sqlalchemy").inspect(engine).get_table_names()


def test_postgres_concurrent_creation_reuses_one_attempt(postgres_engine, monkeypatch):
    ids = seed(postgres_engine)
    provider = Provider()
    started, release, second_started = Event(), Event(), Event()
    original = provider.create_payment_intent
    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    provider.create_payment_intent = blocked
    monkeypatch.setattr("app.services.payment_creation.get_payment_service_for_payment", lambda p: provider)
    def call(second=False):
        if second:
            second_started.set()
        with Session(postgres_engine) as s:
            return create_or_reuse_intent(s, PaymentCreateRequest(order_id=ids[1]), s.get(User, ids[0]), lambda: provider)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(call)
        assert started.wait(10)
        second = pool.submit(call, True)
        assert second_started.wait(10)
        release.set()
        assert first.result(timeout=15) == second.result(timeout=15)
    assert provider.creates == 1
    with Session(postgres_engine) as s:
        assert len(s.exec(select(Payment)).all()) == len(s.exec(select(PaymentCreation)).all()) == 1

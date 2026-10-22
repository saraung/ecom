from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.util
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import event, inspect
from sqlmodel import SQLModel, Session, create_engine, select

import app.models  # noqa: F401
from app.api.v1.webhooks import _handle_refund_webhook
from app.models.address import Address
from app.models.email_outbox import EmailOutbox
from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.models.user import User
from app.services.email_outbox import enqueue_email, deliver_pending_emails
from app.services.email_service import email_service
from app.services.payment_settlement import settle_payment


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        user = User(email="purchase@example.com", username="mail", full_name="Purchase Name")
        s.add(user)
        s.flush()
        address = Address(user_id=user.id, line1="Street", city="City", state="State", postal_code="12345", country="India")
        s.add(address)
        s.flush()
        order = Order(order_number=str(uuid4()), user_id=user.id, shipping_address_id=address.id,
                      billing_address_id=address.id, payment_method="online", subtotal=Decimal("100"),
                      grand_total=Decimal("100"), customer_snapshot={"email": "purchase@example.com", "full_name": "Purchase Name"})
        s.add(order)
        s.flush()
        payment = Payment(order_id=order.id, provider="razorpay", provider_payment_id="order_mail",
                          amount=Decimal("100"), currency="INR")
        s.add(payment)
        s.commit()
        yield s, user, order, payment
    engine.dispose()


def test_gmail_confirmation_template_does_not_require_sendgrid(db, monkeypatch):
    s, user, order, _ = db
    monkeypatch.setattr(email_service, "client", None)
    monkeypatch.setattr(email_service, "provider", "gmail")
    send = Mock(return_value=True)
    monkeypatch.setattr(email_service, "_send_via_gmail", send)
    email_service.send_order_confirmation(order, user)
    assert send.call_count == 1


def test_settlement_and_payload_commit_together_without_provider_and_dedupe(db, monkeypatch):
    s, user, order, payment = db
    send = Mock(side_effect=AssertionError("network in commerce transaction"))
    monkeypatch.setattr(email_service, "_send_email", send)
    settle_payment(s, payment)
    settle_payment(s, payment)
    row = s.exec(select(EmailOutbox)).one()
    assert row.to_email == "purchase@example.com"
    assert row.sent_at is None and row.attempts == 0
    assert order.payment_status == "paid"
    user.email = "edited@example.com"
    s.add(user)
    s.commit()
    assert row.to_email == "purchase@example.com"
    send.assert_not_called()


def test_business_commit_failure_rolls_back_mail_too(db):
    s, _, order, payment = db
    def fail(session):
        raise RuntimeError("commit failed")
    event.listen(s, "before_commit", fail)
    with pytest.raises(RuntimeError):
        settle_payment(s, payment)
    event.remove(s, "before_commit", fail)
    assert s.exec(select(EmailOutbox)).all() == []
    assert s.get(Order, order.id).payment_status == "pending"


def test_retry_survives_new_session_and_success_is_not_resent(db):
    s, user, _, _ = db
    enqueue_email(s, "welcome", "send_welcome_email", user)
    s.commit()
    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    result = deliver_pending_emails(s, now=now, sender=lambda *args: False)
    assert result == {"sent": 0, "failed": 1}
    row = s.exec(select(EmailOutbox)).one()
    assert row.attempts == 1 and row.last_error
    sender = Mock(return_value=True)
    with Session(s.get_bind()) as fresh:
        assert deliver_pending_emails(fresh, now=now, sender=sender) == {"sent": 0, "failed": 0}
        assert deliver_pending_emails(fresh, now=now + timedelta(minutes=2), sender=sender)["sent"] == 1
        deliver_pending_emails(fresh, now=now + timedelta(hours=2), sender=sender)
    assert sender.call_count == 1


def test_expired_token_mail_is_not_delivered(db):
    s, user, _, _ = db
    now = datetime.now(timezone.utc)
    enqueue_email(s, "expired", "send_welcome_email", user, expires_at=now - timedelta(seconds=1))
    s.commit()
    sender = Mock()
    deliver_pending_emails(s, now=now, sender=sender)
    sender.assert_not_called()


def test_refund_completion_replay_queues_once(db):
    s, _, order, _ = db
    order.refund_id = "rfnd_mail"
    order.payment_status = "refund_initiated"
    order.status = OrderStatus.REFUNDED
    s.add(order)
    s.commit()
    _handle_refund_webhook(s, "refund.processed", {"id": "rfnd_mail"})
    _handle_refund_webhook(s, "refund.processed", {"id": "rfnd_mail"})
    assert len(s.exec(select(EmailOutbox)).all()) == 1


def test_outbox_migration_upgrade(db):
    s, *_ = db
    engine = s.get_bind()
    s.close()
    path = Path(__file__).resolve().parents[1] / "alembic/versions/q2e3f4a5b6c7_transactional_email_outbox.py"
    spec = importlib.util.spec_from_file_location("outbox_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE email_outbox")
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
    assert "email_outbox" in inspect(engine).get_table_names()

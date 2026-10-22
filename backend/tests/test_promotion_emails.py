"""
Tests for promotional broadcast email fan-out.

Covers:
  1. Feed broadcast still reaches push-enabled shoppers only (staff,
     inactive, push-off excluded) + header row is recorded.
  2. Email audience = feed audience further gated on the
     ``email_notifications_enabled`` toggle (the storefront/admin
     "Email Notifications" switch).
  3. ``send_promotion_email`` renders title/message/link + opt-out footer.
  4. Email outcome is recorded on the header and surfaced in history.
  5. Retract removes feed rows AND the header row.
  6. History sorts mixed legacy (naive timestamps) + header (aware) rows.

Run:  PYTHONPATH=. .venv/bin/python -m pytest tests/test_promotion_emails.py -q
"""
from datetime import datetime, timezone
from unittest import mock

import pytest
from sqlmodel import SQLModel, Session, create_engine, select

# Import all models so SQLModel.metadata is complete
import app.models  # noqa: F401
from app.models.user import User, UserRole
from app.models.notification import Notification, PromotionBroadcast
from app.repositories import notification as notification_repo
from app.services.email_service import email_service


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _user(s, email, role=UserRole.customer, active=True,
          push=True, email_opt=True):
    u = User(
        username=email.split("@")[0], email=email, full_name=email,
        password_hash="x", role=role, is_active=active,
        push_notifications_enabled=push,
        email_notifications_enabled=email_opt,
    )
    s.add(u)
    s.commit()
    s.refresh(u)
    return u


@pytest.fixture()
def seeded(session):
    """No RBAC grant rows → legacy role fallback path in the audience query."""
    shopper_on = _user(session, "on@shop.com")
    shopper_off = _user(session, "off@shop.com", email_opt=False)
    _user(session, "push-off@shop.com", push=False)
    _user(session, "inactive@shop.com", active=False)
    _user(session, "staffer@shop.com", role=UserRole.staff)
    return {"on": shopper_on, "off": shopper_off}


def test_1_feed_broadcast_reaches_shoppers_only_plus_header(session, seeded):
    broadcast_id, count = notification_repo.broadcast_promotion(
        session, title="Sale!", message="25% off", link="/sale",
        created_by=seeded["on"].id,
    )
    session.commit()
    assert count == 2, count  # on + off (both push-enabled shoppers)

    rows = session.exec(select(Notification)).all()
    got = {r.user_id for r in rows}
    assert got == {seeded["on"].id, seeded["off"].id}, got
    assert all(r.broadcast_id == broadcast_id for r in rows)

    header = session.get(PromotionBroadcast, broadcast_id)
    assert header is not None
    assert header.recipients_count == 2
    assert header.email_requested is False
    assert header.created_by == seeded["on"].id


def test_2_email_audience_honours_toggle(session, seeded):
    audience = notification_repo.promotion_email_audience(session)
    assert [u.email for u in audience] == ["on@shop.com"]


def test_3_promotion_email_template(session):
    with mock.patch.object(
        email_service, "_send_email", return_value=True
    ) as send:
        ok = email_service.send_promotion_email(
            "on@shop.com", "On", "Sale!", "25% off everything", "/sale"
        )
    assert ok is True
    to, subject, html, plain = send.call_args.args
    assert to == "on@shop.com"
    assert subject == "Sale!"
    assert "25% off everything" in html
    assert "Shop Now" in html and "/sale" in html
    assert "Settings → Notifications" in html
    assert "Settings → Notifications" in plain

    # No link → no CTA button, still sends.
    with mock.patch.object(
        email_service, "_send_email", return_value=True
    ) as send2:
        assert email_service.send_promotion_email(
            "on@shop.com", None, "Hi", "Hello", None
        ) is True
    assert "Shop Now" not in send2.call_args.args[2]
    assert "Hi there" in send2.call_args.args[2]


def test_4_email_outcome_recorded_and_in_history(session, seeded):
    broadcast_id, _ = notification_repo.broadcast_promotion(
        session, title="Sale!", message="25% off"
    )
    session.commit()
    notification_repo.record_broadcast_email_result(
        session, broadcast_id, sent=1, failed=0
    )
    session.commit()

    history = notification_repo.promotion_history(session)
    assert len(history) == 1
    item = history[0]
    assert item["id"] == broadcast_id
    assert item["recipients_count"] == 2
    assert item["email_requested"] is True
    assert item["emails_sent"] == 1
    assert item["emails_failed"] == 0


def test_5_retract_removes_rows_and_header(session, seeded):
    broadcast_id, _ = notification_repo.broadcast_promotion(
        session, title="Sale!", message="bye"
    )
    session.commit()
    deleted = notification_repo.retract_broadcast(session, broadcast_id)
    session.commit()
    assert deleted == 2
    assert session.get(PromotionBroadcast, broadcast_id) is None
    assert notification_repo.promotion_history(session) == []


def test_6_unknown_broadcast_email_result_is_noop(session):
    from uuid import uuid4
    notification_repo.record_broadcast_email_result(session, uuid4(), 1, 0)
    session.commit()  # must not raise


def test_7_history_mixes_header_and_legacy_rows(session, seeded):
    """Regression: legacy feed rows carry offset-NAIVE timestamps while
    header rows are offset-AWARE — sorting them together must not 500."""
    from datetime import timedelta
    from app.models.notification import NotificationType

    # Legacy broadcast: raw feed rows, naive timestamp, no header.
    legacy_id = __import__("uuid").uuid4()
    session.add(Notification(
        user_id=seeded["on"].id, type=NotificationType.PROMOTION,
        title="Old promo", message="old", broadcast_id=legacy_id,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None)
        - timedelta(days=20),
    ))
    session.commit()

    # New broadcast with header (aware timestamp).
    new_id, _ = notification_repo.broadcast_promotion(
        session, title="New promo", message="new"
    )
    session.commit()

    history = notification_repo.promotion_history(session)
    ids = [e["id"] for e in history]
    assert ids[0] == new_id  # newest first across both sources
    assert legacy_id in ids
    legacy = next(e for e in history if e["id"] == legacy_id)
    assert legacy["email_requested"] is False
    assert legacy["emails_sent"] == 0

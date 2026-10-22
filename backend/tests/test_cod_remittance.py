"""COD remittance reconciliation: parsing, matching, allocation and audit.

All remittance batches here are synthetic test data. No test calls Shiprocket.
"""
import os
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.core.config import settings
from app.models.address import Address
from app.models.admin_audit import AdminAuditLog
from app.models.cod_remittance import (
    CodRemittance,
    CodRemittanceItem,
    CodRemittanceItemStatus,
    CodRemittanceStatus,
)
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.product import Product, ProductVariant
from app.models.user import User
from app.schemas.cod_remittance import CodRemittanceItemInput
from app.services import cod_remittance as svc


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="cod-admin@example.com", username="cod-admin")
        session.add(user)
        session.flush()
        session.commit()
        user_id = user.id
    yield engine, user_id
    engine.dispose()


def make_order(engine, user_id, *, awb="AWB-1", number="ORD-1", total="1500.00",
               status=OrderStatus.DELIVERED, method="cod", collected=True):
    with Session(engine) as session:
        user = session.get(User, user_id)
        product = Product(name=f"P-{uuid4().hex[:6]}", slug=f"p-{uuid4().hex[:8]}", price=Decimal(total))
        session.add(product)
        session.flush()
        variant = ProductVariant(product_id=product.id, sku=f"S-{uuid4().hex[:8]}", stock=10)
        session.add(variant)
        session.flush()
        address = Address(user_id=user.id, line1="1 Main St", city="Mumbai", state="MH",
                          postal_code="400001", country="India")
        session.add(address)
        session.flush()
        order = Order(
            order_number=number,
            user_id=user.id,
            shipping_address_id=address.id,
            billing_address_id=address.id,
            subtotal=Decimal(total),
            grand_total=Decimal(total),
            payment_method=method,
            payment_status="cod_pending" if method == "cod" else "pending",
            status=status,
            awb_code=awb,
            shiprocket_order_id=f"SR-{number}",
        )
        session.add(order)
        session.flush()
        if collected and method == "cod" and status == OrderStatus.DELIVERED:
            order.payment_status = "paid"
            session.add(Payment(
                order_id=order.id,
                provider=PaymentProvider.COD,
                provider_payment_id=f"cod_{number}",
                amount=Decimal(total),
                currency="INR",
                status=PaymentStatus.SUCCEEDED,
                payment_method="cod",
            ))
        session.add(order)
        session.commit()
        return order.id


def admin(db):
    engine, user_id = db
    with Session(engine) as session:
        return session.get(User, user_id)


def line(awb=None, order_ref=None, cod="1500.00", deductions="30.00", net="1470.00",
         remitted=None, row_number=1):
    return {
        "row_number": row_number,
        "awb": awb,
        "order_ref": order_ref,
        "cod_amount": Decimal(cod),
        "deductions": Decimal(deductions),
        "net_amount": Decimal(net),
        "remitted_amount": Decimal(remitted if remitted is not None else net),
        "crf_id": None,
        "remittance_date": None,
        "utr": None,
        "raw_row": {"awb": awb, "order_ref": order_ref},
        "source_row": row_number,
    }


def create(db, crf="CRF-1", lines=None, ip_address=None):
    engine, _ = db
    with Session(engine) as session:
        return svc.create_batch(
            session, admin(db), crf_id=crf, remittance_date=date.today(),
            lines=lines or [line(awb="AWB-1")], source="manual", mapping={},
            ip_address=ip_address,
        )


# ---------------------------------------------------------------------------
# CSV parsing / mapping
# ---------------------------------------------------------------------------

def test_csv_parsing_handles_bom_currency_commas_and_semicolons():
    raw = (
        "\ufeffAWB Code;Order Number;COD Amount;Charges;Net Amount;CRF ID;Remittance Date\n"
        "AWB-9;ORD-9;\"₹1,500.00\";30.00;\"1,470.00\";CRF-9;2026-10-01\n"
    ).encode("utf-8")

    headers, rows = svc.parse_csv_bytes(raw)
    assert headers[0] == "AWB Code"
    mapping = svc.suggest_mapping(headers)
    assert mapping["awb"] == "AWB Code"
    assert mapping["order_ref"] == "Order Number"
    assert mapping["cod_amount"] == "COD Amount"
    assert mapping["deductions"] == "Charges"
    assert mapping["net_amount"] == "Net Amount"
    assert mapping["crf_id"] == "CRF ID"

    normalized = svc.normalize_rows(rows, mapping)
    assert len(normalized) == 1
    assert normalized[0]["awb"] == "AWB-9"
    assert normalized[0]["cod_amount"] == Decimal("1500.00")
    assert normalized[0]["net_amount"] == Decimal("1470.00")


def test_csv_without_awb_or_order_reference_is_rejected():
    raw = b"AWB,Order Number,COD Amount\n,,100\n"
    with Session(create_engine("sqlite:///:memory:")) as session:
        with pytest.raises(HTTPException) as exc:
            svc.preview_csv(session, raw)
    assert exc.value.status_code == 400


def test_template_and_fixture_are_labelled_synthetic():
    template = svc.template_csv()
    fixture = svc.fixture_csv()
    assert template.splitlines()[0] == "awb,order_number,cod_amount,deductions,net_amount,crf_id,remittance_date,utr"
    assert "SYNTHETIC - not real Shiprocket data" in fixture
    assert "SIM-AWB-1001" in fixture


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def test_preview_matches_by_awb_and_flags_unknown_mismatch_and_uncollected(db):
    engine, _ = db
    make_order(engine, _, awb="AWB-1", number="ORD-1", total="1500.00")
    make_order(engine, _, awb="AWB-2", number="ORD-2", total="1000.00")
    make_order(engine, _, awb="AWB-3", number="ORD-3", total="500.00", collected=False)

    raw = (
        "awb,order_number,cod_amount,deductions,net_amount\n"
        "AWB-1,ORD-1,1500.00,30.00,1470.00\n"
        "UNKNOWN,,700.00,0,700.00\n"
        "AWB-2,ORD-2,900.00,0,900.00\n"
        "AWB-3,ORD-3,500.00,0,500.00\n"
    ).encode()
    with Session(engine) as session:
        result = svc.preview_csv(session, raw)
    statuses = [row["match_status"] for row in result["rows"]]
    assert statuses == [
        CodRemittanceItemStatus.MATCHED.value,
        CodRemittanceItemStatus.ORDER_NOT_FOUND.value,
        CodRemittanceItemStatus.AMOUNT_MISMATCH.value,
        CodRemittanceItemStatus.CASH_NOT_COLLECTED.value,
    ]
    assert result["summary"]["matched"] == 1
    assert result["summary"]["flagged"] == 3


def test_preview_falls_back_to_order_number_and_shiprocket_reference(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-ORDER", number="ORD-REF")
    raw = b"awb,order_number,cod_amount,deductions,net_amount\n,ORD-REF,1500,0,1500\n"
    with Session(engine) as session:
        result = svc.preview_csv(session, raw)
    assert result["rows"][0]["match_status"] == CodRemittanceItemStatus.MATCHED.value
    assert result["rows"][0]["order_number"] == "ORD-REF"


# ---------------------------------------------------------------------------
# Batch creation / duplicate protection
# ---------------------------------------------------------------------------

def test_duplicate_crf_is_rejected_case_insensitively(db):
    create(db, "CRF-DUP")
    with pytest.raises(HTTPException) as exc:
        create(db, "CRF-DUP")
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException) as exc:
        create(db, "crf-dup")
    assert exc.value.status_code == 409


def test_same_awb_in_an_in_flight_batch_is_flagged_already_remitted(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", number="ORD-1")
    create(db, "CRF-FIRST")
    raw = b"awb,order_number,cod_amount,deductions,net_amount\nAWB-1,ORD-1,1500,0,1500\n"
    with Session(engine) as session:
        result = svc.preview_csv(session, raw)
    assert result["rows"][0]["match_status"] == CodRemittanceItemStatus.ALREADY_REMITTED.value


def test_create_batch_rejects_invalid_amounts_at_the_service_boundary(db):
    engine, _ = db
    raw_line = {
        "row_number": 1,
        "awb": "AWB-1",
        "order_ref": None,
        "cod_amount": Decimal("1500"),
        "deductions": Decimal("-100"),
        "net_amount": Decimal("1600"),
        "remitted_amount": Decimal("1600"),
        "crf_id": None,
    }
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.create_batch(
                session, admin(db), crf_id="CRF-DIRECT",
                remittance_date=date.today(), lines=[raw_line],
                source="manual", mapping={},
            )
    assert exc.value.status_code == 400


def test_manual_batch_totals_are_computed_server_side(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    detail = create(db, "CRF-MANUAL", [line(awb="AWB-1", cod="1500", deductions="30", net="1470")])
    assert detail["gross_cod"] == 1500.0
    assert detail["deductions_total"] == 30.0
    assert detail["net_expected"] == 1470.0
    assert detail["status"] == CodRemittanceStatus.PENDING.value
    assert detail["items"][0]["match_status"] == CodRemittanceItemStatus.MATCHED.value


# ---------------------------------------------------------------------------
# Confirmation / allocation / partial remittance
# ---------------------------------------------------------------------------

def test_confirm_allocates_once_and_never_creates_a_second_payment(db):
    engine, user_id = db
    order_id = make_order(engine, user_id, awb="AWB-1", total="1500")
    detail = create(db, "CRF-OK")
    with Session(engine) as session:
        result = svc.confirm_bank_receipt(
            session, admin(db), detail["id"], utr="UTR-1",
            bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
        )
    assert result["status"] == CodRemittanceStatus.RECONCILED.value
    with Session(engine) as session:
        order = session.get(Order, order_id)
        assert order.cod_remitted_amount == Decimal("1470.00")
        assert order.cod_remittance_status == "partial"
        assert len(session.exec(select(Payment).where(Payment.order_id == order_id)).all()) == 1
        assert session.exec(select(AdminAuditLog).where(AdminAuditLog.action == "cod.remittance.reconciled")).first()
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-2",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
        assert exc.value.status_code == 409


def test_second_instalment_completes_a_partially_remitted_order(db):
    engine, user_id = db
    order_id = make_order(engine, user_id, awb="AWB-1", total="200")
    first = create(db, "CRF-P1", [line(awb="AWB-1", cod="200", deductions="80", net="120")])
    with Session(engine) as session:
        svc.confirm_bank_receipt(
            session, admin(db), first["id"], utr="UTR-P1",
            bank_credit_amount=Decimal("120"), bank_credit_date=date.today(),
        )
    with Session(engine) as session:
        assert session.get(Order, order_id).cod_remittance_status == "partial"

    second = create(db, "CRF-P2", [line(awb="AWB-1", cod="200", deductions="120", net="80")])
    with Session(engine) as session:
        svc.confirm_bank_receipt(
            session, admin(db), second["id"], utr="UTR-P2",
            bank_credit_amount=Decimal("80"), bank_credit_date=date.today(),
        )
    with Session(engine) as session:
        order = session.get(Order, order_id)
        assert order.cod_remittance_status == "complete"
        assert order.cod_remitted_amount == Decimal("200.00")
        assert order.cod_remitted_at is not None
        assert len(session.exec(select(Payment)).all()) == 1


def test_confirmation_blocks_while_a_discrepancy_is_open(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    detail = create(db, "CRF-DISC", [
        line(awb="AWB-1", cod="1500", deductions="30", net="1470", row_number=1),
        line(awb="AWB-UNKNOWN", cod="500", deductions="0", net="500", row_number=2),
    ])
    assert detail["flagged_count"] == 1
    assert detail["status"] == CodRemittanceStatus.DISCREPANCY.value
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-D",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409

    unknown_item = next(item for item in detail["items"] if item["match_status"] == "order_not_found")
    with Session(engine) as session:
        resolved = svc.resolve_item(
            session, admin(db), detail["id"], unknown_item["id"], "exclude", "Not our shipment"
        )
    assert resolved["flagged_count"] == 0
    assert resolved["net_expected"] == 1470.0
    assert resolved["status"] == CodRemittanceStatus.PENDING.value

    with Session(engine) as session:
        result = svc.confirm_bank_receipt(
            session, admin(db), detail["id"], utr="UTR-D",
            bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
        )
    assert result["status"] == CodRemittanceStatus.RECONCILED.value


def test_admin_can_accept_an_amount_mismatch(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    raw = b"awb,order_number,cod_amount,deductions,net_amount\nAWB-1,ORD-1,1200,0,1200\n"
    with Session(engine) as session:
        preview = svc.preview_csv(session, raw)
        assert preview["rows"][0]["match_status"] == CodRemittanceItemStatus.AMOUNT_MISMATCH.value
        detail = svc.create_batch(
            session, admin(db), crf_id="CRF-ACCEPT", remittance_date=date.today(),
            lines=svc.normalize_rows([{
                "awb": "AWB-1", "order_number": "ORD-1", "cod_amount": "1200",
                "deductions": "0", "net_amount": "1200",
            }], preview["mapping"]),
            source="csv", mapping=preview["mapping"],
        )
        item = detail["items"][0]
        svc.resolve_item(session, admin(db), detail["id"], item["id"], "accept_match", "Confirmed with courier")
        result = svc.confirm_bank_receipt(
            session, admin(db), detail["id"], utr="UTR-A",
            bank_credit_amount=Decimal("1200"), bank_credit_date=date.today(),
        )
    assert result["status"] == CodRemittanceStatus.RECONCILED.value


def test_bank_difference_requires_explicit_acceptance(db):
    engine, user_id = db
    order_id = make_order(engine, user_id, awb="AWB-1", total="1500")
    detail = create(db, "CRF-DIFF")
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-X",
                bank_credit_amount=Decimal("1450"), bank_credit_date=date.today(),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["difference"] == -20.0

        result = svc.confirm_bank_receipt(
            session, admin(db), detail["id"], utr="UTR-X",
            bank_credit_amount=Decimal("1450"), bank_credit_date=date.today(),
            accept_difference=True, difference_reason="Courier deducted weight charges",
        )
    assert result["status"] == CodRemittanceStatus.RECONCILED.value
    assert result["difference"] == -20.0
    assert result["net_expected"] == 1470.0
    assert result["deductions_total"] == 30.0
    assert result["bank_credit_amount"] == 1450.0
    assert result["raw_meta"]["difference_reason"] == "Courier deducted weight charges"
    with Session(engine) as session:
        # The batch records the 20 shortfall; order allocation remains the
        # expected net (1470) rather than the bank credit.
        assert session.get(Order, order_id).cod_remitted_amount == Decimal("1470.00")


def test_voided_batch_cannot_be_confirmed(db):
    engine, _ = db
    detail = create(db, "CRF-VOID")
    with Session(engine) as session:
        svc.void_batch(session, admin(db), detail["id"], "Imported by mistake")
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-V",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Simulator / summary
# ---------------------------------------------------------------------------

def test_simulator_is_blocked_in_production_unless_enabled(db, monkeypatch):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "COD_REMITTANCE_SIMULATOR_ENABLED", False)
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.simulate_batch(session, admin(db))
    assert exc.value.status_code == 403

    monkeypatch.setattr(settings, "COD_REMITTANCE_SIMULATOR_ENABLED", True)
    with Session(engine) as session:
        result = svc.simulate_batch(session, admin(db))
    assert result["source"] == "simulator"
    assert result["synthetic"] is True
    assert result["crf_id"].startswith("SIM-")


def test_simulator_batch_is_labelled_and_can_be_reconciled(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    with Session(engine) as session:
        result = svc.simulate_batch(session, admin(db))
    assert "Synthetic development batch" in result["notes"]
    assert result["items"][0]["match_status"] == CodRemittanceItemStatus.MATCHED.value
    with Session(engine) as session:
        confirmed = svc.confirm_bank_receipt(
            session, admin(db), result["id"], utr="UTR-SIM",
            bank_credit_amount=Decimal(str(result["net_expected"])),
            bank_credit_date=date.today(),
        )
    assert confirmed["status"] == CodRemittanceStatus.RECONCILED.value


def test_summary_reports_collection_and_remittance_queues(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-C", number="ORD-C", total="500", collected=False)
    make_order(engine, user_id, awb="AWB-R", number="ORD-R", total="1500")
    with Session(engine) as session:
        summary = svc.get_summary(session)
    assert summary["awaiting_collection"]["count"] == 1
    assert summary["awaiting_collection"]["amount"] == 500.0
    assert summary["awaiting_remittance"]["count"] == 1
    assert summary["awaiting_remittance"]["amount"] == 1500.0
    assert summary["simulator_enabled"] is True


def test_cod_permissions_are_granted_to_manager_and_admin_only():
    from app.core.rbac_catalog import SYSTEM_ROLES

    assert {"cod.view", "cod.reconcile"} <= set(SYSTEM_ROLES["manager"]["permissions"])
    assert {"cod.view", "cod.reconcile"} <= set(SYSTEM_ROLES["admin"]["permissions"])
    assert "cod.view" not in SYSTEM_ROLES["staff"]["permissions"]
    assert "cod.reconcile" not in SYSTEM_ROLES["staff"]["permissions"]


def test_existing_shiprocket_simulator_delivers_before_collection_and_remittance(db):
    """Exercise the real simulator path instead of hand-writing delivered_at."""
    from app.api.v1.admin.cod import collect_cod_payment
    from app.api.v1.admin.orders import trigger_simulator_event
    from app.schemas.order import SimulatorTriggerWebhookRequest

    engine, user_id = db
    order_id = make_order(
        engine, user_id, awb="AWB-SIMULATED", number="ORD-SIMULATED",
        total="1500", status=OrderStatus.SHIPPED, collected=False,
    )
    with Session(engine) as session:
        delivered = trigger_simulator_event(
            order_id,
            SimulatorTriggerWebhookRequest(event="delivered", location="Customer Doorstep"),
            session,
            admin(db),
        )
        assert delivered["order_status"] == OrderStatus.DELIVERED.value
        # DELIVERED webhook auto-collects COD cash.
        assert delivered["payment_status"] == "paid"
    with Session(engine) as session:
        # Explicit collect after auto-collect is idempotently rejected.
        with pytest.raises(HTTPException) as exc:
            collect_cod_payment(order_id, session, admin(db), None)
        assert exc.value.status_code == 409

    with Session(engine) as session:
        batch = svc.simulate_batch(session, admin(db))
    assert batch["source"] == "simulator"
    assert batch["synthetic"] is True
    assert batch["items"][0]["order"]["id"] == str(order_id)


def test_flagged_in_flight_line_blocks_a_second_batch_from_claiming_the_order(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    create(db, "CRF-FLAGGED", [line(awb="AWB-1", cod="1200", deductions="0", net="1200")])
    raw = b"awb,order_number,cod_amount,deductions,net_amount\nAWB-1,ORD-1,1500,0,1500\n"
    with Session(engine) as session:
        preview = svc.preview_csv(session, raw)
    assert preview["rows"][0]["match_status"] == CodRemittanceItemStatus.ALREADY_REMITTED.value


def test_accept_match_rechecks_delivery_and_collection_rules(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-SHIPPED", total="1500",
               status=OrderStatus.SHIPPED, collected=False)
    detail = create(db, "CRF-NOT-DELIVERED", [line(awb="AWB-SHIPPED", cod="1500")])
    item = detail["items"][0]
    assert item["match_status"] == CodRemittanceItemStatus.NOT_DELIVERED.value
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.resolve_item(session, admin(db), detail["id"], item["id"], "accept_match")
    assert exc.value.status_code == 409


def test_accept_match_rejects_already_remitted_duplicate_and_not_cod_lines(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    make_order(engine, user_id, awb="AWB-ONLINE", number="ORD-ONLINE", total="1500",
               method="online", collected=False)

    first = create(db, "CRF-FIRST")
    second = create(db, "CRF-SECOND")
    second_item = second["items"][0]
    assert second_item["match_status"] == CodRemittanceItemStatus.ALREADY_REMITTED.value
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.resolve_item(
                session, admin(db), second["id"], second_item["id"], "accept_match"
            )
    assert exc.value.status_code == 409

    duplicate = create(db, "CRF-DUP-LINES", [
        line(awb="AWB-ONLINE", cod="1500", deductions="0", net="1500", row_number=1),
        line(awb="AWB-ONLINE", cod="1500", deductions="0", net="1500", row_number=2),
    ])
    duplicate_item = next(
        item for item in duplicate["items"]
        if item["match_status"] == CodRemittanceItemStatus.DUPLICATE.value
    )
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.resolve_item(
                session, admin(db), duplicate["id"], duplicate_item["id"], "accept_match"
            )
    assert exc.value.status_code == 409

    not_cod = create(db, "CRF-NOT-COD", [
        line(awb="AWB-ONLINE", cod="1500", deductions="0", net="1500")
    ])
    not_cod_item = not_cod["items"][0]
    assert not_cod_item["match_status"] == CodRemittanceItemStatus.NOT_COD.value
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.resolve_item(
                session, admin(db), not_cod["id"], not_cod_item["id"], "accept_match"
            )
    assert exc.value.status_code == 409


def test_confirm_refuses_zero_or_short_allocations_and_missing_orders(db):
    engine, user_id = db
    order_id = make_order(engine, user_id, awb="AWB-1", total="1500")

    zero = create(db, "CRF-ZERO")
    with Session(engine) as session:
        item = session.get(CodRemittanceItem, UUID(zero["items"][0]["id"]))
        item.remitted_amount = Decimal("0.00")
        session.add(item)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), zero["id"], utr="UTR-ZERO",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        batch = session.get(CodRemittance, UUID(zero["id"]))
        assert batch.status == CodRemittanceStatus.PENDING.value
        assert session.get(Order, order_id).cod_remitted_amount == Decimal("0.00")

    no_order = create(db, "CRF-NO-ORDER")
    with Session(engine) as session:
        item = session.get(CodRemittanceItem, UUID(no_order["items"][0]["id"]))
        item.order_id = None
        item.match_status = CodRemittanceItemStatus.MATCHED.value
        batch = session.get(CodRemittance, UUID(no_order["id"]))
        batch.status = CodRemittanceStatus.PENDING.value
        session.add(item)
        session.add(batch)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), no_order["id"], utr="UTR-NO-ORDER",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        assert session.get(CodRemittance, UUID(no_order["id"])).status == CodRemittanceStatus.PENDING.value

    under = create(db, "CRF-UNDER")
    with Session(engine) as session:
        item = session.get(CodRemittanceItem, UUID(under["items"][0]["id"]))
        item.match_status = CodRemittanceItemStatus.MATCHED.value
        item.remitted_amount = Decimal("100.00")
        batch = session.get(CodRemittance, UUID(under["id"]))
        batch.status = CodRemittanceStatus.PENDING.value
        batch.net_expected = Decimal("100.00")
        session.add(item)
        session.add(batch)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), under["id"], utr="UTR-UNDER",
                bank_credit_amount=Decimal("100"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        assert session.get(Order, order_id).cod_remitted_amount == Decimal("0.00")
        assert session.get(CodRemittance, UUID(under["id"])).status == CodRemittanceStatus.PENDING.value


def test_confirm_revalidates_order_state_and_collection(db):
    engine, user_id = db
    order_id = make_order(engine, user_id, awb="AWB-1", total="1500")
    detail = create(db, "CRF-REFUNDED")
    with Session(engine) as session:
        order = session.get(Order, order_id)
        order.status = OrderStatus.REFUNDED
        session.add(order)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-REFUNDED",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        order = session.get(Order, order_id)
        assert order.cod_remitted_amount == Decimal("0.00")
        assert session.get(CodRemittance, UUID(detail["id"])).status == CodRemittanceStatus.PENDING.value

    order_id = make_order(engine, user_id, awb="AWB-COLLECTED", number="ORD-COLLECTED",
                          total="1500")
    detail = create(db, "CRF-NO-COLLECTION", [line(awb="AWB-COLLECTED")])
    with Session(engine) as session:
        payment = session.exec(select(Payment).where(Payment.order_id == order_id)).one()
        payment.status = PaymentStatus.REFUNDED
        session.add(payment)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-NO-COLLECTION",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        assert session.get(Order, order_id).cod_remitted_amount == Decimal("0.00")


def test_confirm_rejects_stale_allocation_above_remaining_balance(db):
    engine, user_id = db
    order_id = make_order(engine, user_id, awb="AWB-1", total="1500")
    first = create(db, "CRF-PARTIAL")
    with Session(engine) as session:
        svc.confirm_bank_receipt(
            session, admin(db), first["id"], utr="UTR-PARTIAL",
            bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
        )

    second = create(db, "CRF-OVER")
    with Session(engine) as session:
        item = session.get(CodRemittanceItem, UUID(second["items"][0]["id"]))
        assert item.match_status == CodRemittanceItemStatus.AMOUNT_MISMATCH.value
        assert item.remitted_amount == Decimal("0.00")
        # Simulate a stale/corrupt pending batch that still claims the full line.
        item.match_status = CodRemittanceItemStatus.MATCHED.value
        item.remitted_amount = Decimal("1470.00")
        batch = session.get(CodRemittance, UUID(second["id"]))
        batch.status = CodRemittanceStatus.PENDING.value
        session.add(item)
        session.add(batch)
        session.commit()
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), second["id"], utr="UTR-OVER",
                bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        assert session.get(Order, order_id).cod_remitted_amount == Decimal("1470.00")
        assert session.get(CodRemittance, UUID(second["id"])).status == CodRemittanceStatus.PENDING.value


def test_confirm_is_atomic_across_orders(db):
    engine, user_id = db
    good_id = make_order(engine, user_id, awb="AWB-GOOD", number="ORD-GOOD", total="1500")
    stale_id = make_order(engine, user_id, awb="AWB-STALE", number="ORD-STALE", total="1500")
    detail = create(db, "CRF-ATOMIC", [
        line(awb="AWB-GOOD", row_number=1),
        line(awb="AWB-STALE", row_number=2),
    ])
    with Session(engine) as session:
        stale = session.get(Order, stale_id)
        stale.status = OrderStatus.RTO
        session.add(stale)
        session.commit()

    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.confirm_bank_receipt(
                session, admin(db), detail["id"], utr="UTR-ATOMIC",
                bank_credit_amount=Decimal("2940"), bank_credit_date=date.today(),
            )
    assert exc.value.status_code == 409
    with Session(engine) as session:
        assert session.get(Order, good_id).cod_remitted_amount == Decimal("0.00")
        assert session.get(Order, stale_id).cod_remitted_amount == Decimal("0.00")
        assert session.get(CodRemittance, UUID(detail["id"])).status == CodRemittanceStatus.PENDING.value


def test_void_then_reimport_same_crf_case_insensitively(db):
    detail = create(db, "CRF-VOID-REIMPORT")
    with Session(db[0]) as session:
        svc.void_batch(
            session, admin(db), detail["id"], "Corrected import",
            ip_address="198.51.100.7",
        )
    with Session(db[0]) as session:
        voided = session.exec(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "cod.remittance.voided"
            )
        ).all()
        assert any(
            log.after.get("note") == "Corrected import"
            and log.ip_address == "198.51.100.7"
            for log in voided
        )
    reimported = create(db, "crf-void-reimport")
    assert reimported["crf_id"] == "crf-void-reimport"
    with pytest.raises(HTTPException) as exc:
        create(db, "CRF-VOID-REIMPORT")
    assert exc.value.status_code == 409


def test_csv_rejects_negative_inconsistent_and_mixed_crf_amounts(db):
    engine, _ = db
    with Session(engine) as session:
        with pytest.raises(HTTPException) as exc:
            svc.preview_csv(
                session,
                b"awb,cod_amount,deductions,net_amount\nAWB-1,1500,-100,1600\n",
            )
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            svc.preview_csv(
                session,
                b"awb,cod_amount,deductions,net_amount\nAWB-1,1500,30,1480\n",
            )
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            svc.preview_csv(
                session,
                b"awb,cod_amount,deductions,net_amount,crf_id\n"
                b"AWB-1,1500,0,1500,CRF-A\nAWB-2,500,0,500,CRF-B\n",
            )
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            svc.preview_csv(
                session,
                b"awb,cod_amount,deductions,net_amount,remitted_amount\n"
                b"AWB-1,1500,0,1500,1400\n",
            )
        assert exc.value.status_code == 400

        with pytest.raises(HTTPException) as exc:
            svc.normalize_manual_items([
                CodRemittanceItemInput(
                    awb="AWB-1",
                    cod_amount=Decimal("1500"),
                    deductions=Decimal("0"),
                    net_amount=Decimal("1500"),
                    remitted_amount=Decimal("1400"),
                )
            ])
        assert exc.value.status_code == 400


def test_audit_records_resolution_notes_bank_difference_and_client_ip(db):
    engine, user_id = db
    make_order(engine, user_id, awb="AWB-1", total="1500")
    detail = create(db, "CRF-AUDIT", [
        line(awb="AWB-1", cod="1200", deductions="0", net="1200")
    ], ip_address="203.0.113.9")
    item = detail["items"][0]
    with Session(engine) as session:
        svc.resolve_item(
            session, admin(db), detail["id"], item["id"], "accept_match",
            "Checked with courier", ip_address="203.0.113.9",
        )
        svc.confirm_bank_receipt(
            session, admin(db), detail["id"], utr="UTR-AUDIT",
            bank_credit_amount=Decimal("1180"), bank_credit_date=date.today(),
            accept_difference=True, difference_reason="Courier weight charge",
            ip_address="203.0.113.9",
        )
    with Session(engine) as session:
        imported = session.exec(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "cod.remittance.imported"
            )
        ).all()
        assert any(
            log.after.get("crf_id") == "CRF-AUDIT"
            and log.ip_address == "203.0.113.9"
            for log in imported
        )
        resolved = session.exec(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "cod.remittance.item_resolved"
            )
        ).all()
        assert any(
            log.after.get("note") == "Checked with courier"
            and log.ip_address == "203.0.113.9"
            for log in resolved
        )
        reconciled = session.exec(
            select(AdminAuditLog).where(
                AdminAuditLog.action == "cod.remittance.reconciled"
            )
        ).all()
        assert any(
            log.after.get("difference_reason") == "Courier weight charge"
            and log.after.get("allocated") == "1200.00"
            and log.ip_address == "203.0.113.9"
            for log in reconciled
        )


@pytest.mark.skipif(
    not os.environ.get("REMEDIATION_TEST_DATABASE_URL"),
    reason="Set REMEDIATION_TEST_DATABASE_URL for isolated PostgreSQL concurrency checks",
)
def test_postgres_concurrent_imports_claim_an_order_once(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user = User(email="cod-pg@example.com", username="cod-pg")
    with Session(postgres_engine) as session:
        session.add(user)
        session.commit()
        user_id = user.id
    make_order(postgres_engine, user_id, awb="AWB-PG", total="1500")

    barrier = Barrier(2)

    def import_one(crf):
        with Session(postgres_engine) as session:
            actor = session.get(User, user_id)
            barrier.wait(timeout=10)
            return svc.create_batch(
                session, actor, crf_id=crf, remittance_date=date.today(),
                lines=[line(awb="AWB-PG")], source="manual", mapping={},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [
            pool.submit(import_one, "CRF-PG-A"),
            pool.submit(import_one, "CRF-PG-B"),
        ]
        details = [future.result(timeout=20) for future in results]

    statuses = sorted(detail["items"][0]["match_status"] for detail in details)
    assert statuses == [
        CodRemittanceItemStatus.ALREADY_REMITTED.value,
        CodRemittanceItemStatus.MATCHED.value,
    ]
    with Session(postgres_engine) as session:
        claims = session.exec(
            select(CodRemittanceItem).where(
                CodRemittanceItem.match_status == CodRemittanceItemStatus.MATCHED.value
            )
        ).all()
        assert len(claims) == 1


@pytest.mark.skipif(
    not os.environ.get("REMEDIATION_TEST_DATABASE_URL"),
    reason="Set REMEDIATION_TEST_DATABASE_URL for isolated PostgreSQL concurrency checks",
)
def test_postgres_concurrent_same_crf_returns_conflict(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user = User(email="cod-pg-crf@example.com", username="cod-pg-crf")
    with Session(postgres_engine) as session:
        session.add(user)
        session.commit()
        user_id = user.id
    make_order(postgres_engine, user_id, awb="AWB-PG-CRF", total="1500")

    barrier = Barrier(2)

    def import_same_crf():
        with Session(postgres_engine) as session:
            actor = session.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                svc.create_batch(
                    session,
                    actor,
                    crf_id="CRF-PG-SAME",
                    remittance_date=date.today(),
                    lines=[line(awb="AWB-PG-CRF")],
                    source="manual",
                    mapping={},
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(import_same_crf) for _ in range(2)]
        assert sorted(call.result(timeout=20) for call in calls) == [200, 409]
    with Session(postgres_engine) as session:
        active = session.exec(
            select(CodRemittance).where(
                CodRemittance.crf_key == "crf-pg-same",
                CodRemittance.status != CodRemittanceStatus.VOID.value,
            )
        ).all()
        assert len(active) == 1


@pytest.mark.skipif(
    not os.environ.get("REMEDIATION_TEST_DATABASE_URL"),
    reason="Set REMEDIATION_TEST_DATABASE_URL for isolated PostgreSQL concurrency checks",
)
def test_postgres_concurrent_confirm_allocates_once(postgres_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    user = User(email="cod-pg-confirm@example.com", username="cod-pg-confirm")
    with Session(postgres_engine) as session:
        session.add(user)
        session.commit()
        user_id = user.id
    order_id = make_order(postgres_engine, user_id, awb="AWB-PG-CONFIRM", total="1500")
    with Session(postgres_engine) as session:
        detail = svc.create_batch(
            session, session.get(User, user_id), crf_id="CRF-PG-CONFIRM",
            remittance_date=date.today(), lines=[line(awb="AWB-PG-CONFIRM")],
            source="manual", mapping={},
        )

    barrier = Barrier(2)

    def confirm():
        with Session(postgres_engine) as session:
            actor = session.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                svc.confirm_bank_receipt(
                    session, actor, detail["id"], utr="UTR-PG",
                    bank_credit_amount=Decimal("1470"), bank_credit_date=date.today(),
                )
                return 200
            except HTTPException as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        calls = [pool.submit(confirm) for _ in range(2)]
        assert sorted(call.result(timeout=20) for call in calls) == [200, 409]
    with Session(postgres_engine) as session:
        assert session.get(Order, order_id).cod_remitted_amount == Decimal("1470.00")
        assert len(session.exec(select(Payment).where(Payment.order_id == order_id)).all()) == 1

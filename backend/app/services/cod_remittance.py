"""COD remittance ingestion, matching and bank reconciliation.

The importer is deliberately provider-agnostic: Shiprocket does not publish a
COD remittance API or webhook, so batches arrive as a panel CSV export or as a
manual entry. Synthetic simulator batches are clearly flagged and only exist to
make local development possible without production remittance data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.core.config import settings
from app.models.cod_remittance import (
    CodRemittance,
    CodRemittanceItem,
    CodRemittanceItemStatus,
    CodRemittanceSource,
    CodRemittanceStatus,
)
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentProvider, PaymentStatus
from app.models.user import User
from app.repositories import audit as audit_repo

TEMPLATE_HEADERS = [
    "awb",
    "order_number",
    "cod_amount",
    "deductions",
    "net_amount",
    "crf_id",
    "remittance_date",
    "utr",
]

SYNTHETIC_NOTE = "SYNTHETIC - not real Shiprocket data"

MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_CSV_ROWS = 5_000

#: Flagged line statuses an administrator may explicitly accept after checking
#: the order. Everything else must be excluded: accepting a not-Cod order,
#: a duplicate, or an already-remitted claim would double-allocate a payout.
ACCEPTABLE_RESOLVE_STATUSES = {
    CodRemittanceItemStatus.AMOUNT_MISMATCH.value,
    CodRemittanceItemStatus.NOT_DELIVERED.value,
    CodRemittanceItemStatus.CASH_NOT_COLLECTED.value,
}

#: target field -> accepted header spellings (canonicalized: lowercase,
#: non-alphanumerics collapsed to single spaces).
HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "awb": ("awb", "awb code", "awb number", "awb no", "airway bill", "airway bill no"),
    "order_ref": (
        "order number",
        "order id",
        "order ref",
        "order reference",
        "reference",
        "reference order id",
    ),
    "cod_amount": (
        "cod amount",
        "cod",
        "collectable",
        "collectable amount",
        "gross",
        "gross cod",
        "cod collectable",
    ),
    "deductions": (
        "deductions",
        "deduction",
        "charges",
        "cod charges",
        "cod remittance charges",
        "remittance charges",
        "total deductions",
    ),
    "net_amount": (
        "net amount",
        "net",
        "remitted",
        "remitted amount",
        "remittance amount",
        "amount",
        "bank transfer amount",
    ),
    "remitted_amount": ("remitted amount", "amount remitted", "payout amount"),
    "crf_id": ("crf id", "crf", "remittance id", "remittance file id", "batch id", "payout id"),
    "remittance_date": ("remittance date", "date", "payout date", "credit date"),
    "utr": ("utr", "utr number", "utr no", "bank reference", "bank reference number"),
}

FLAGGED_STATUSES = {
    CodRemittanceItemStatus.AMOUNT_MISMATCH.value,
    CodRemittanceItemStatus.ORDER_NOT_FOUND.value,
    CodRemittanceItemStatus.NOT_COD.value,
    CodRemittanceItemStatus.NOT_DELIVERED.value,
    CodRemittanceItemStatus.CASH_NOT_COLLECTED.value,
    CodRemittanceItemStatus.ALREADY_REMITTED.value,
    CodRemittanceItemStatus.DUPLICATE.value,
}

STATUS_LABELS = {
    CodRemittanceStatus.PENDING.value: "Awaiting bank credit",
    CodRemittanceStatus.RECONCILED.value: "Reconciled",
    CodRemittanceStatus.DISCREPANCY.value: "Discrepancy",
    CodRemittanceStatus.VOID.value: "Void",
}

ITEM_STATUS_LABELS = {
    CodRemittanceItemStatus.MATCHED.value: "Matched",
    CodRemittanceItemStatus.AMOUNT_MISMATCH.value: "Amount mismatch",
    CodRemittanceItemStatus.ORDER_NOT_FOUND.value: "Order not found",
    CodRemittanceItemStatus.NOT_COD.value: "Not a COD order",
    CodRemittanceItemStatus.NOT_DELIVERED.value: "Not delivered",
    CodRemittanceItemStatus.CASH_NOT_COLLECTED.value: "Cash not collected",
    CodRemittanceItemStatus.ALREADY_REMITTED.value: "Already remitted",
    CodRemittanceItemStatus.DUPLICATE.value: "Duplicate line",
    CodRemittanceItemStatus.ADJUSTMENT.value: "Excluded adjustment",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def money(value: Any) -> Decimal:
    """Quantize to 2 places; None/garbage becomes 0."""
    if value is None or value == "":
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0.00")


def parse_money(value: Any) -> Decimal | None:
    """Parse CSV money cells (₹, thousands separators, blank cells)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = (
        text.replace("₹", "")
        .replace("$", "")
        .replace("€", "")
        .replace("£", "")
        .replace(",", "")
        .replace(" ", "")
    )
    text = re.sub(r"[^0-9.\-]", "", text)
    if text in ("", "-", ".", "-."):
        return None
    try:
        return money(Decimal(text))
    except InvalidOperation:
        return None


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _hash_line(awb: str | None, order_ref: str | None, cod: Decimal, deductions: Decimal,
               net: Decimal, remitted: Decimal) -> str:
    raw = "|".join([
        (awb or "").strip().upper(),
        (order_ref or "").strip().upper(),
        str(money(cod)),
        str(money(deductions)),
        str(money(net)),
        str(money(remitted)),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _derive_amounts(
    *,
    cod: Decimal | None,
    deductions: Decimal | None,
    net: Decimal | None,
    remitted: Decimal | None,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Fill blank amount cells and return a consistent four-tuple.

    ``net`` is the allocatable line amount. A separate ``remitted_amount``
    column, when present, must agree with it so a file cannot claim one
    expected amount while allocating another.
    """
    if deductions is None:
        deductions = (
            money((cod or 0) - (net or 0))
            if cod is not None and net is not None
            else Decimal("0.00")
        )
    if net is None and remitted is not None:
        net = money(remitted)
    if net is None and cod is not None:
        net = money(cod - deductions)
    if cod is None and net is not None:
        cod = money(net + deductions)
    cod = money(cod)
    deductions = money(deductions)
    net = money(net)
    remitted = money(remitted) if remitted is not None else net
    return cod, deductions, net, remitted


def _validate_amounts(
    label: str,
    cod: Decimal,
    deductions: Decimal,
    net: Decimal,
    remitted: Decimal,
) -> None:
    if any(value < Decimal("0.00") for value in (cod, deductions, net, remitted)):
        raise HTTPException(400, f"{label}: amounts cannot be negative")
    if cod - deductions != net:
        raise HTTPException(
            400,
            f"{label}: COD amount minus deductions must equal the net amount",
        )
    if net != remitted:
        raise HTTPException(
            400,
            f"{label}: net amount and remitted amount must agree",
        )


def _f(value: Decimal | None) -> float | None:
    return None if value is None else float(money(value))


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def simulator_enabled() -> bool:
    return (
        settings.ENVIRONMENT.lower() != "production"
        or bool(settings.COD_REMITTANCE_SIMULATOR_ENABLED)
    )


def parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# CSV parsing / column mapping
# ---------------------------------------------------------------------------

def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(400, "Could not decode the CSV file as text")


def parse_csv_bytes(data: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    if not data:
        raise HTTPException(400, "The uploaded CSV is empty")
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(413, "CSV is too large (max 5 MB)")
    text = _decode(data)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    headers = [(h or "").strip() for h in (reader.fieldnames or []) if (h or "").strip()]
    if not headers:
        raise HTTPException(400, "The CSV has no header row")

    rows: list[dict[str, Any]] = []
    for raw in reader:
        clean = {
            (key or "").strip(): (value.strip() if isinstance(value, str) else value)
            for key, value in raw.items()
            if key is not None
        }
        if not any(str(v).strip() for v in clean.values() if v is not None):
            continue
        if len(rows) >= MAX_CSV_ROWS:
            raise HTTPException(413, f"CSV has too many rows (max {MAX_CSV_ROWS:,})")
        rows.append(clean)
    if not rows:
        raise HTTPException(400, "The CSV has no data rows")
    return headers, rows


def suggest_mapping(headers: Iterable[str]) -> dict[str, str | None]:
    canonical = {_canonical(h): h for h in headers}
    result: dict[str, str | None] = {}
    for field, aliases in HEADER_ALIASES.items():
        found = None
        for alias in aliases:
            if alias in canonical:
                found = canonical[alias]
                break
        if found is None:
            for key, original in canonical.items():
                if any(alias in key or key in alias for alias in aliases):
                    found = original
                    break
        result[field] = found
    return result


def normalize_rows(rows: list[dict[str, Any]], mapping: dict[str, str | None]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=2):  # header is row 1
        def cell(field: str) -> Any:
            header = mapping.get(field)
            return row.get(header) if header else None

        awb = (str(cell("awb")).strip() if cell("awb") is not None else "") or None
        order_ref = (
            str(cell("order_ref")).strip() if cell("order_ref") is not None else ""
        ) or None
        if not awb and not order_ref:
            # Totals / blank separator rows are not remittance lines.
            continue

        cod, deductions, net, remitted = _derive_amounts(
            cod=parse_money(cell("cod_amount")),
            deductions=parse_money(cell("deductions")),
            net=parse_money(cell("net_amount")),
            remitted=parse_money(cell("remitted_amount")),
        )
        _validate_amounts(f"Row {index}", cod, deductions, net, remitted)

        normalized.append({
            "row_number": index,
            "awb": awb,
            "order_ref": order_ref,
            "cod_amount": cod,
            "deductions": deductions,
            "net_amount": net,
            "remitted_amount": remitted,
            "crf_id": (str(cell("crf_id")).strip() if cell("crf_id") is not None else "") or None,
            "remittance_date": parse_date(cell("remittance_date")),
            "utr": (str(cell("utr")).strip() if cell("utr") is not None else "") or None,
            "raw_row": {k: v for k, v in row.items() if k is not None},
            "source_row": index,
        })
    return normalized


def normalize_manual_items(items: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        awb = (item.awb or "").strip() or None
        order_ref = (item.order_number or "").strip() or None
        cod, deductions, net, remitted = _derive_amounts(
            cod=item.cod_amount,
            deductions=item.deductions or Decimal("0.00"),
            net=item.net_amount,
            remitted=item.remitted_amount,
        )
        _validate_amounts(f"Line {index}", cod, deductions, net, remitted)
        normalized.append({
            "row_number": index,
            "awb": awb,
            "order_ref": order_ref,
            "cod_amount": cod,
            "deductions": deductions,
            "net_amount": net,
            "remitted_amount": remitted,
            "crf_id": None,
            "remittance_date": None,
            "utr": None,
            "raw_row": {
                "awb": awb,
                "order_number": order_ref,
                "cod_amount": str(money(cod)),
                "deductions": str(money(deductions)),
                "net_amount": str(money(net)),
                "remitted_amount": str(money(remitted)),
                "source": "manual",
            },
            "source_row": index,
        })
    return normalized


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _find_order(session: Session, awb: str | None, order_ref: str | None) -> Order | None:
    if awb:
        found = session.exec(
            select(Order).where(func.lower(Order.awb_code) == awb.strip().lower())
        ).first()
        if found:
            return found
    if order_ref:
        ref = order_ref.strip()
        return session.exec(
            select(Order).where(
                or_(Order.order_number == ref, Order.shiprocket_order_id == ref)
            )
        ).first()
    return None


def _has_collected_cash(session: Session, order_id) -> bool:
    return session.exec(
        select(Payment.id).where(
            Payment.order_id == order_id,
            Payment.provider == PaymentProvider.COD,
            Payment.status == PaymentStatus.SUCCEEDED,
        )
    ).first() is not None


def _existing_remittance_item(
    session: Session,
    order_id,
    *,
    exclude_item_id: uuid.UUID | None = None,
) -> CodRemittanceItem | None:
    """An in-flight batch already claims this order.

    Reconciled batches are intentionally excluded: Instant/Early COD can pay an
    order out in more than one instalment, so a partially remitted order may
    legitimately appear in a later batch. ``cod_remittance_status == complete``
    remains the hard stop for fully paid orders.
    """
    statement = (
        select(CodRemittanceItem)
        .join(CodRemittance, CodRemittance.id == CodRemittanceItem.remittance_id)
        .where(
            CodRemittanceItem.order_id == order_id,
            CodRemittance.status.in_([
                CodRemittanceStatus.PENDING.value,
                CodRemittanceStatus.DISCREPANCY.value,
            ]),
            CodRemittanceItem.match_status != CodRemittanceItemStatus.ADJUSTMENT.value,
        )
    )
    if exclude_item_id is not None:
        statement = statement.where(CodRemittanceItem.id != exclude_item_id)
    return session.exec(statement).first()


def validate_lines(session: Session, lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Match parsed lines against COD orders without mutating anything."""
    seen_hashes: set[str] = set()
    seen_orders: set[str] = set()
    result: list[dict[str, Any]] = []

    for line in lines:
        awb = line.get("awb")
        order_ref = line.get("order_ref")
        cod = money(line.get("cod_amount"))
        deductions = money(line.get("deductions"))
        net = money(line.get("net_amount"))
        remitted = money(line.get("remitted_amount"))
        fingerprint = _hash_line(awb, order_ref, cod, deductions, net, remitted)
        # Storage hash includes the source row so two identical lines can both
        # be kept (flagged as duplicates) without violating the unique
        # (remittance_id, line_hash) constraint. Fingerprints still drive
        # duplicate detection above.
        line_hash = hashlib.sha256(
            f"{fingerprint}|{line.get('row_number') or line.get('source_row') or ''}".encode("utf-8")
        ).hexdigest()

        row = {
            **line,
            "order_id": None,
            "order_number": None,
            "order_status": None,
            "order_grand_total": None,
            "order_remaining": None,
            "match_status": CodRemittanceItemStatus.MATCHED.value,
            "match_note": None,
            "line_hash": line_hash,
            "remitted_amount": remitted,
        }

        if fingerprint in seen_hashes:
            row["match_status"] = CodRemittanceItemStatus.DUPLICATE.value
            row["match_note"] = "Identical line already appears earlier in this batch"
            row["remitted_amount"] = Decimal("0.00")
            result.append(row)
            continue
        seen_hashes.add(fingerprint)

        order = _find_order(session, awb, order_ref)
        if not order:
            row["match_status"] = CodRemittanceItemStatus.ORDER_NOT_FOUND.value
            row["match_note"] = "No order matches this AWB or order reference"
            row["remitted_amount"] = Decimal("0.00")
            result.append(row)
            continue

        row["order_id"] = str(order.id)
        row["order_number"] = order.order_number
        row["order_status"] = order.status.value if hasattr(order.status, "value") else str(order.status)
        row["order_grand_total"] = _f(order.grand_total)
        row["order_remaining"] = _f(money(order.grand_total) - money(order.cod_remitted_amount))

        if str(order.id) in seen_orders:
            row["match_status"] = CodRemittanceItemStatus.DUPLICATE.value
            row["match_note"] = "Another line in this file already claims this order"
            row["remitted_amount"] = Decimal("0.00")
            result.append(row)
            continue
        seen_orders.add(str(order.id))

        if order.payment_method != "cod":
            row["match_status"] = CodRemittanceItemStatus.NOT_COD.value
            row["match_note"] = "Order was not paid with Cash on Delivery"
        elif order.status != OrderStatus.DELIVERED:
            row["match_status"] = CodRemittanceItemStatus.NOT_DELIVERED.value
            row["match_note"] = f"Order status is {row['order_status']}; only delivered COD is remittable"
        elif not _has_collected_cash(session, order.id):
            row["match_status"] = CodRemittanceItemStatus.CASH_NOT_COLLECTED.value
            row["match_note"] = "Record the customer cash collection before reconciling remittance"
        elif order.cod_remittance_status == "complete":
            row["match_status"] = CodRemittanceItemStatus.ALREADY_REMITTED.value
            row["match_note"] = "Order is already fully remitted"
        elif _existing_remittance_item(session, order.id):
            row["match_status"] = CodRemittanceItemStatus.ALREADY_REMITTED.value
            row["match_note"] = "Order is already linked to another non-void remittance"
        else:
            expected = money(order.grand_total)
            remaining = max(Decimal("0.00"), expected - money(order.cod_remitted_amount))
            if abs(cod - expected) > Decimal("1.00"):
                row["match_status"] = CodRemittanceItemStatus.AMOUNT_MISMATCH.value
                row["match_note"] = (
                    f"Line COD {cod} differs from order total {expected}; "
                    "accept explicitly after checking charges or partial payout"
                )
                row["remitted_amount"] = Decimal("0.00")
            elif net <= Decimal("0.00"):
                row["match_status"] = CodRemittanceItemStatus.AMOUNT_MISMATCH.value
                row["match_note"] = "Net remittance amount is zero or negative"
                row["remitted_amount"] = Decimal("0.00")
            elif remaining <= Decimal("0.00"):
                row["match_status"] = CodRemittanceItemStatus.ALREADY_REMITTED.value
                row["match_note"] = "Order has no remaining COD to reconcile"
                row["remitted_amount"] = Decimal("0.00")
            elif net > remaining:
                row["match_status"] = CodRemittanceItemStatus.AMOUNT_MISMATCH.value
                row["match_note"] = (
                    f"Net remittance {net} exceeds the order's remaining COD {remaining}; "
                    "exclude this line or adjust the batch"
                )
                row["remitted_amount"] = Decimal("0.00")
            else:
                # Matched lines must be fully allocatable at confirmation. Never
                # silently cap a larger remittance at the remaining balance.
                row["remitted_amount"] = net

        if row["match_status"] != CodRemittanceItemStatus.MATCHED.value:
            row["remitted_amount"] = Decimal("0.00")
        result.append(row)

    return result


def summarize_lines(lines: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for line in lines:
        status = line.get("match_status", CodRemittanceItemStatus.MATCHED.value)
        counts[status] = counts.get(status, 0) + 1
    return {
        "rows": len(lines),
        "matched": counts.get(CodRemittanceItemStatus.MATCHED.value, 0),
        "flagged": sum(counts.get(status, 0) for status in FLAGGED_STATUSES),
        "counts": counts,
        "gross_cod": _f(sum((money(line.get("cod_amount")) for line in lines), Decimal("0.00"))),
        "deductions": _f(sum((money(line.get("deductions")) for line in lines), Decimal("0.00"))),
        "net_expected": _f(sum((money(line.get("net_amount")) for line in lines), Decimal("0.00"))),
    }


def _nonblank_crf_ids(lines: list[dict[str, Any]]) -> set[str]:
    return {
        str(line.get("crf_id")).strip().lower()
        for line in lines
        if str(line.get("crf_id") or "").strip()
    }


def preview_csv(session: Session, data: bytes, mapping: dict[str, str | None] | None = None) -> dict[str, Any]:
    headers, rows = parse_csv_bytes(data)
    suggested = suggest_mapping(headers)
    active = {k: v for k, v in (mapping or suggested).items() if v}
    normalized = normalize_rows(rows, active)
    if not normalized:
        raise HTTPException(400, "No remittance lines with an AWB or order number were found")
    if len(_nonblank_crf_ids(normalized)) > 1:
        raise HTTPException(
            400,
            "The CSV contains more than one CRF / batch reference; import each CRF separately",
        )
    validated = validate_lines(session, normalized)
    return {
        "headers": headers,
        "suggested_mapping": suggested,
        "mapping": active,
        "summary": summarize_lines(validated),
        "rows": [_preview_row(line) for line in validated],
    }


def _preview_row(line: dict[str, Any]) -> dict[str, Any]:
    return {
        "row_number": line.get("row_number"),
        "awb": line.get("awb"),
        "order_ref": line.get("order_ref"),
        "order_number": line.get("order_number"),
        "order_id": line.get("order_id"),
        "order_status": line.get("order_status"),
        "order_grand_total": line.get("order_grand_total"),
        "order_remaining": line.get("order_remaining"),
        "cod_amount": _f(line.get("cod_amount")),
        "deductions": _f(line.get("deductions")),
        "net_amount": _f(line.get("net_amount")),
        "remitted_amount": _f(line.get("remitted_amount")),
        "match_status": line.get("match_status"),
        "match_note": line.get("match_note"),
        "raw_row": line.get("raw_row") or {},
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _get_batch(session: Session, remittance_id: uuid.UUID | str, *, for_update: bool = False) -> CodRemittance:
    if isinstance(remittance_id, str):
        try:
            remittance_id = uuid.UUID(remittance_id)
        except ValueError as exc:
            raise HTTPException(404, "COD remittance batch not found") from exc
    statement = select(CodRemittance).where(CodRemittance.id == remittance_id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    batch = session.exec(statement).first()
    if not batch:
        raise HTTPException(404, "COD remittance batch not found")
    return batch


def batch_detail(session: Session, batch: CodRemittance) -> dict[str, Any]:
    items = session.exec(
        select(CodRemittanceItem)
        .where(CodRemittanceItem.remittance_id == batch.id)
        .order_by(CodRemittanceItem.created_at, CodRemittanceItem.id)
    ).all()

    item_rows = []
    for item in items:
        order = session.get(Order, item.order_id) if item.order_id else None
        item_rows.append({
            "id": str(item.id),
            "order_id": str(item.order_id) if item.order_id else None,
            "order_number": order.order_number if order else None,
            "awb": item.awb,
            "order_ref": item.order_ref,
            "cod_amount": _f(item.cod_amount),
            "deductions": _f(item.deductions),
            "net_amount": _f(item.net_amount),
            "remitted_amount": _f(item.remitted_amount),
            "match_status": item.match_status,
            "match_status_label": ITEM_STATUS_LABELS.get(item.match_status, item.match_status),
            "match_note": item.match_note,
            "raw_row": item.raw_row,
            "order": {
                "id": str(order.id),
                "order_number": order.order_number,
                "status": order.status.value if hasattr(order.status, "value") else str(order.status),
                "grand_total": _f(order.grand_total),
                "cod_remitted_amount": _f(order.cod_remitted_amount),
                "cod_remittance_status": order.cod_remittance_status,
            } if order else None,
        })

    flagged = sum(
        1 for item in items
        if item.match_status not in (
            CodRemittanceItemStatus.MATCHED.value,
            CodRemittanceItemStatus.ADJUSTMENT.value,
        )
    )
    matched_amount = sum(
        (money(item.remitted_amount) for item in items
         if item.match_status == CodRemittanceItemStatus.MATCHED.value),
        Decimal("0.00"),
    )

    return {
        "id": str(batch.id),
        "crf_id": batch.crf_id,
        "provider": batch.provider,
        "remittance_date": _iso(batch.remittance_date),
        "status": batch.status,
        "status_label": STATUS_LABELS.get(batch.status, batch.status),
        "gross_cod": _f(batch.gross_cod),
        "deductions_total": _f(batch.deductions_total),
        "net_expected": _f(batch.net_expected),
        "bank_credit_amount": _f(batch.bank_credit_amount),
        "utr": batch.utr,
        "bank_credit_date": _iso(batch.bank_credit_date),
        "bank_account_ref": batch.bank_account_ref,
        "difference": _f(batch.difference),
        "source": batch.source,
        "source_filename": batch.source_filename,
        "notes": batch.notes,
        "raw_meta": batch.raw_meta or {},
        "synthetic": bool((batch.raw_meta or {}).get("synthetic")),
        "imported_by": str(batch.imported_by) if batch.imported_by else None,
        "reconciled_by": str(batch.reconciled_by) if batch.reconciled_by else None,
        "reconciled_at": _iso(batch.reconciled_at),
        "created_at": _iso(batch.created_at),
        "updated_at": _iso(batch.updated_at),
        "item_count": len(items),
        "flagged_count": flagged,
        "matched_amount": _f(matched_amount),
        "can_confirm": (
            batch.status in (
                CodRemittanceStatus.PENDING.value,
                CodRemittanceStatus.DISCREPANCY.value,
            )
            and flagged == 0
            and matched_amount > Decimal("0.00")
            and matched_amount == money(batch.net_expected)
        ),
        "items": item_rows,
    }


def _active_batch_by_crf(session: Session, crf_id: str) -> CodRemittance | None:
    return session.exec(
        select(CodRemittance).where(
            CodRemittance.crf_key == crf_id.strip().lower(),
            CodRemittance.status != CodRemittanceStatus.VOID.value,
        )
    ).first()


def _lock_orders(session: Session, order_ids: set[uuid.UUID]) -> None:
    """Lock matched orders in a deterministic order.

    Imports and confirmations both acquire these row locks sorted by ``id`` so
    concurrent batches claiming overlapping orders wait instead of deadlocking.
    ``populate_existing`` is essential: after a wait the identity map may still
    hold a pre-wait copy of the order.
    """
    if not order_ids:
        return
    session.exec(
        select(Order)
        .where(Order.id.in_(order_ids))
        .order_by(Order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()


def create_batch(
    session: Session,
    user: User,
    *,
    crf_id: str,
    remittance_date: date,
    lines: list[dict[str, Any]],
    source: str,
    source_filename: str | None = None,
    notes: str | None = None,
    mapping: dict[str, str | None] | None = None,
    synthetic: bool = False,
    ip_address: str | None = None,
) -> dict[str, Any]:
    crf_id = (crf_id or "").strip()
    if not crf_id:
        raise HTTPException(400, "A CRF / batch reference is required")
    existing = _active_batch_by_crf(session, crf_id)
    if existing:
        raise HTTPException(
            409,
            f"An active COD remittance batch '{existing.crf_id}' already uses this "
            f"reference (status: {existing.status}). Void it first to re-import.",
        )
    if not lines:
        raise HTTPException(400, "A remittance batch needs at least one line")

    expected_crf = crf_id.lower()
    for line in lines:
        row_crf = str(line.get("crf_id") or "").strip()
        if row_crf and row_crf.lower() != expected_crf:
            raise HTTPException(
                400,
                f"Row {line.get('row_number') or line.get('source_row') or '?'}: "
                f"CRF '{row_crf}' does not match batch CRF '{crf_id}'",
            )
        _validate_amounts(
            f"Row {line.get('row_number') or line.get('source_row') or '?'}",
            money(line.get("cod_amount")),
            money(line.get("deductions")),
            money(line.get("net_amount")),
            money(line.get("remitted_amount")),
        )

    # First pass tells us which orders to lock. Re-running matching after the
    # locks are held closes the race where two imports both validate before
    # either inserts its claim.
    initial = validate_lines(session, lines)
    initial_order_ids = {
        uuid.UUID(line["order_id"])
        for line in initial
        if line.get("order_id")
    }
    _lock_orders(session, initial_order_ids)
    validated = validate_lines(session, lines)

    gross = sum((money(line.get("cod_amount")) for line in validated), Decimal("0.00"))
    deductions = sum((money(line.get("deductions")) for line in validated), Decimal("0.00"))
    net = sum((money(line.get("net_amount")) for line in validated), Decimal("0.00"))

    flagged_lines = sum(
        1 for line in validated
        if line.get("match_status") not in (
            CodRemittanceItemStatus.MATCHED.value,
            CodRemittanceItemStatus.ADJUSTMENT.value,
        )
    )
    batch = CodRemittance(
        crf_id=crf_id,
        crf_key=expected_crf,
        provider="shiprocket",
        remittance_date=remittance_date,
        status=(
            CodRemittanceStatus.DISCREPANCY.value
            if flagged_lines else CodRemittanceStatus.PENDING.value
        ),
        gross_cod=money(gross),
        deductions_total=money(deductions),
        net_expected=money(net),
        source=source,
        source_filename=source_filename,
        notes=notes,
        raw_meta={
            "mapping": mapping or {},
            "synthetic": bool(synthetic),
            "row_count": len(validated),
        },
        imported_by=user.id,
    )
    summary = summarize_lines(validated)

    try:
        session.add(batch)
        session.flush()

        for line in validated:
            session.add(CodRemittanceItem(
                remittance_id=batch.id,
                order_id=uuid.UUID(line["order_id"]) if line.get("order_id") else None,
                awb=line.get("awb"),
                order_ref=line.get("order_ref"),
                cod_amount=money(line.get("cod_amount")),
                deductions=money(line.get("deductions")),
                net_amount=money(line.get("net_amount")),
                remitted_amount=money(line.get("remitted_amount")),
                match_status=line.get("match_status") or CodRemittanceItemStatus.MATCHED.value,
                match_note=line.get("match_note"),
                line_hash=line["line_hash"],
                raw_row=line.get("raw_row") or {},
            ))

        audit_repo.log_and_commit(
            session,
            "cod.remittance.imported",
            "cod_remittance",
            batch.id,
            user.id,
            after={
                "crf_id": crf_id,
                "source": source,
                "source_filename": source_filename,
                "synthetic": bool(synthetic),
                "gross_cod": str(money(gross)),
                "net_expected": str(money(net)),
                "matched": summary["matched"],
                "flagged": summary["flagged"],
            },
            ip_address=ip_address,
        )
    except IntegrityError as exc:
        # The partial unique index (crf_key where status <> 'void') is the
        # cross-process guard. Convert its violation into the same 409 as the
        # pre-check instead of leaking a 500 when two imports race.
        session.rollback()
        existing = _active_batch_by_crf(session, crf_id)
        if existing:
            raise HTTPException(
                409,
                f"An active COD remittance batch '{existing.crf_id}' already uses this "
                f"reference (status: {existing.status}). Void it first to re-import.",
            ) from exc
        raise

    return batch_detail(session, batch)


def _recalculate_totals(session: Session, batch: CodRemittance) -> None:
    """Recompute batch totals from lines that are not explicitly excluded."""
    items = session.exec(
        select(CodRemittanceItem).where(CodRemittanceItem.remittance_id == batch.id)
    ).all()
    active = [
        item for item in items
        if item.match_status != CodRemittanceItemStatus.ADJUSTMENT.value
    ]
    batch.gross_cod = money(sum((money(item.cod_amount) for item in active), Decimal("0.00")))
    batch.deductions_total = money(sum((money(item.deductions) for item in active), Decimal("0.00")))
    batch.net_expected = money(sum((money(item.net_amount) for item in active), Decimal("0.00")))
    session.add(batch)


def list_batches(
    session: Session,
    *,
    page: int = 1,
    limit: int = 20,
    status: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    statement = select(CodRemittance)
    count_statement = select(func.count()).select_from(CodRemittance)
    if status:
        statement = statement.where(CodRemittance.status == status)
        count_statement = count_statement.where(CodRemittance.status == status)
    if search:
        term = f"%{search.strip()}%"
        condition = or_(
            CodRemittance.crf_id.ilike(term),
            CodRemittance.utr.ilike(term),
        )
        statement = statement.where(condition)
        count_statement = count_statement.where(condition)
    total = session.exec(count_statement).one()
    batches = session.exec(
        statement.order_by(CodRemittance.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    rows = []
    for batch in batches:
        detail = batch_detail(session, batch)
        rows.append({
            key: detail[key]
            for key in (
                "id", "crf_id", "provider", "remittance_date", "status", "status_label",
                "gross_cod", "deductions_total", "net_expected", "bank_credit_amount",
                "utr", "difference", "source", "synthetic", "item_count",
                "flagged_count", "created_at", "reconciled_at",
            )
        })
    return {
        "remittances": rows,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": max(1, (total + limit - 1) // limit),
    }


def resolve_item(
    session: Session,
    user: User,
    remittance_id: uuid.UUID,
    item_id: uuid.UUID,
    action: str,
    note: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    batch = _get_batch(session, remittance_id, for_update=True)
    if batch.status in (CodRemittanceStatus.RECONCILED.value, CodRemittanceStatus.VOID.value):
        raise HTTPException(409, "This remittance can no longer be edited")

    if isinstance(item_id, str):
        try:
            item_id = uuid.UUID(item_id)
        except ValueError as exc:
            raise HTTPException(404, "Remittance line not found in this batch") from exc
    item = session.get(CodRemittanceItem, item_id)
    if not item or item.remittance_id != batch.id:
        raise HTTPException(404, "Remittance line not found in this batch")

    before = {
        "match_status": item.match_status,
        "match_note": item.match_note,
        "remitted_amount": str(money(item.remitted_amount)),
    }

    if action == "exclude":
        item.match_status = CodRemittanceItemStatus.ADJUSTMENT.value
        item.match_note = note or "Excluded from reconciliation by an administrator"
        item.remitted_amount = Decimal("0.00")
    elif action == "accept_match":
        if item.match_status not in ACCEPTABLE_RESOLVE_STATUSES:
            raise HTTPException(
                409,
                f"Line status '{item.match_status}' cannot be accepted; exclude it instead",
            )
        if not item.order_id:
            raise HTTPException(400, "This line is not linked to an order; exclude it instead")
        order = session.exec(
            select(Order)
            .where(Order.id == item.order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).first()
        if not order:
            raise HTTPException(404, "Linked order no longer exists")
        if order.payment_method != "cod":
            raise HTTPException(409, "Linked order is not a COD order")
        if order.status != OrderStatus.DELIVERED:
            raise HTTPException(409, "COD remittance can only be accepted for a delivered order")
        if order.payment_status != "paid" or not _has_collected_cash(session, order.id):
            raise HTTPException(409, "Cash collection must be recorded before accepting this line")
        if order.cod_remittance_status == "complete":
            raise HTTPException(409, "Order is already fully remitted")
        if _existing_remittance_item(session, order.id, exclude_item_id=item.id):
            raise HTTPException(
                409,
                "This order is already claimed by another in-flight remittance line",
            )
        remaining = max(
            Decimal("0.00"),
            money(order.grand_total) - money(order.cod_remitted_amount),
        )
        if remaining <= Decimal("0.00"):
            raise HTTPException(409, "Order has no remaining COD to reconcile")
        amount = money(item.net_amount)
        if amount <= Decimal("0.00"):
            raise HTTPException(400, "Line net amount must be greater than zero")
        if amount > remaining:
            raise HTTPException(
                409,
                f"Line net {amount} exceeds the order's remaining COD {remaining}; "
                "exclude the line or adjust the batch",
            )
        item.match_status = CodRemittanceItemStatus.MATCHED.value
        item.remitted_amount = amount
        item.match_note = note or "Match accepted by an administrator"
    else:
        raise HTTPException(400, "Unknown resolution action")

    session.add(item)
    session.flush()
    remaining_flags = session.exec(
        select(CodRemittanceItem).where(
            CodRemittanceItem.remittance_id == batch.id,
            CodRemittanceItem.match_status.notin_([
                CodRemittanceItemStatus.MATCHED.value,
                CodRemittanceItemStatus.ADJUSTMENT.value,
            ]),
        )
    ).first()
    if not remaining_flags and batch.status == CodRemittanceStatus.DISCREPANCY.value:
        batch.status = CodRemittanceStatus.PENDING.value
    _recalculate_totals(session, batch)
    audit_repo.log_and_commit(
        session,
        "cod.remittance.item_resolved",
        "cod_remittance",
        batch.id,
        user.id,
        before=before,
        after={
            "item_id": str(item.id),
            "action": action,
            "note": note,
            "match_status": item.match_status,
            "match_note": item.match_note,
            "remitted_amount": str(money(item.remitted_amount)),
        },
        ip_address=ip_address,
    )
    return batch_detail(session, batch)


def confirm_bank_receipt(
    session: Session,
    user: User,
    remittance_id: uuid.UUID,
    *,
    utr: str,
    bank_credit_amount: Decimal,
    bank_credit_date: date,
    bank_account_ref: str | None = None,
    notes: str | None = None,
    accept_difference: bool = False,
    difference_reason: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    batch = _get_batch(session, remittance_id, for_update=True)
    if batch.status == CodRemittanceStatus.RECONCILED.value:
        raise HTTPException(409, "This remittance is already reconciled")
    if batch.status == CodRemittanceStatus.VOID.value:
        raise HTTPException(409, "This remittance was voided")

    items = session.exec(
        select(CodRemittanceItem)
        .where(CodRemittanceItem.remittance_id == batch.id)
        .order_by(CodRemittanceItem.id)
    ).all()
    open_items = [
        item for item in items
        if item.match_status not in (
            CodRemittanceItemStatus.MATCHED.value,
            CodRemittanceItemStatus.ADJUSTMENT.value,
        )
    ]
    if open_items:
        raise HTTPException(
            409,
            f"{len(open_items)} remittance line(s) still need a decision "
            "(accept or exclude) before confirming the bank credit",
        )

    matched_items = [
        item for item in items
        if item.match_status == CodRemittanceItemStatus.MATCHED.value
    ]
    if not matched_items:
        raise HTTPException(400, "No matched lines are available to allocate")
    if any(money(item.remitted_amount) <= Decimal("0.00") for item in matched_items):
        raise HTTPException(
            409,
            "Every matched line needs a positive allocation before confirmation",
        )

    utr = (utr or "").strip()
    if not utr:
        raise HTTPException(400, "Bank UTR / reference is required")
    credit = money(bank_credit_amount)
    if credit <= Decimal("0.00"):
        raise HTTPException(400, "Bank credit amount must be greater than zero")

    expected = money(batch.net_expected)
    matched_total = sum(
        (money(item.remitted_amount) for item in matched_items),
        Decimal("0.00"),
    )
    if matched_total != expected:
        raise HTTPException(
            409,
            f"Matched line total {matched_total} does not equal the expected net "
            f"{expected}; resolve or exclude lines before confirming",
        )

    difference = money(credit - expected)
    before = {
        "status": batch.status,
        "net_expected": str(expected),
        "bank_credit_amount": (
            str(money(batch.bank_credit_amount))
            if batch.bank_credit_amount is not None else None
        ),
        "utr": batch.utr,
    }
    reason = (difference_reason or "").strip()
    if abs(difference) > Decimal("0.01"):
        if not accept_difference:
            raise HTTPException(
                409,
                {
                    "message": "Bank credit does not match the expected remittance",
                    "expected": float(expected),
                    "bank_credit": float(credit),
                    "difference": float(difference),
                    "hint": "Resolve lines, then resubmit with accept_difference and a reason",
                },
            )
        if not reason:
            raise HTTPException(400, "A reason is required when accepting a bank difference")

    # Lock and revalidate every matched order before changing anything. A batch
    # must never be marked reconciled while an order has been refunded, cancelled,
    # re-collected, or has less remaining COD than the line claims.
    order_ids = [item.order_id for item in matched_items]
    if any(order_id is None for order_id in order_ids):
        raise HTTPException(409, "A matched line is no longer linked to an order")
    if len(set(order_ids)) != len(order_ids):
        raise HTTPException(409, "The batch contains multiple matched lines for one order")

    orders = session.exec(
        select(Order)
        .where(Order.id.in_(order_ids))
        .order_by(Order.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    orders_by_id = {order.id: order for order in orders}
    if len(orders_by_id) != len(order_ids):
        raise HTTPException(409, "One or more matched orders no longer exist")

    allocations: list[tuple[CodRemittanceItem, Order, Decimal]] = []
    for item in matched_items:
        order = orders_by_id[item.order_id]
        if order.payment_method != "cod":
            raise HTTPException(
                409, f"Order {order.order_number} is no longer a COD order"
            )
        if order.status != OrderStatus.DELIVERED:
            order_status = (
                order.status.value if hasattr(order.status, "value") else str(order.status)
            )
            raise HTTPException(
                409,
                f"Order {order.order_number} is {order_status}; COD remittance "
                "requires a delivered order",
            )
        if order.payment_status != "paid" or not _has_collected_cash(session, order.id):
            raise HTTPException(
                409,
                f"Order {order.order_number} no longer has a successful COD cash collection",
            )
        if order.cod_remittance_status == "complete":
            raise HTTPException(
                409, f"Order {order.order_number} is already fully remitted"
            )
        remaining = max(
            Decimal("0.00"),
            money(order.grand_total) - money(order.cod_remitted_amount),
        )
        amount = money(item.remitted_amount)
        if amount <= Decimal("0.00"):
            raise HTTPException(
                409, f"Matched line for order {order.order_number} has no allocation"
            )
        if amount != money(item.net_amount):
            raise HTTPException(
                409,
                f"Matched line for order {order.order_number} allocates {amount}, "
                f"but its line net is {money(item.net_amount)}; re-import or adjust the line",
            )
        if amount > remaining:
            raise HTTPException(
                409,
                f"Order {order.order_number} has only {remaining} remaining COD, "
                f"but the matched line allocates {amount}; exclude or adjust the line",
            )
        allocations.append((item, order, amount))

    now = datetime.now(timezone.utc)
    allocated = Decimal("0.00")
    for _item, order, amount in allocations:
        order.cod_remitted_amount = money(money(order.cod_remitted_amount) + amount)
        if order.cod_remitted_amount >= money(order.grand_total):
            order.cod_remittance_status = "complete"
            order.cod_remitted_at = now
        else:
            order.cod_remittance_status = "partial"
        session.add(order)
        allocated += amount

    if money(allocated) != matched_total:
        raise HTTPException(
            409,
            f"Allocated {allocated} but matched lines total {matched_total}; "
            "no orders were changed",
        )

    if abs(difference) > Decimal("0.01"):
        batch.raw_meta = {
            **(batch.raw_meta or {}),
            "bank_difference": str(difference),
            "difference_reason": reason,
        }
    # Keep net_expected/deductions_total as the original line totals. The bank
    # credit and accepted difference are recorded separately so a later reader
    # can still see what was expected versus what actually landed.
    batch.bank_credit_amount = credit
    batch.utr = utr
    batch.bank_credit_date = bank_credit_date
    batch.bank_account_ref = bank_account_ref
    batch.difference = difference
    if notes:
        batch.notes = notes
    batch.status = CodRemittanceStatus.RECONCILED.value
    batch.reconciled_by = user.id
    batch.reconciled_at = now
    session.add(batch)

    audit_repo.log_and_commit(
        session,
        "cod.remittance.reconciled",
        "cod_remittance",
        batch.id,
        user.id,
        before=before,
        after={
            "status": batch.status,
            "utr": batch.utr,
            "bank_credit_amount": str(credit),
            "bank_credit_date": bank_credit_date.isoformat(),
            "bank_account_ref": bank_account_ref,
            "net_expected": str(expected),
            "difference": str(difference),
            "difference_reason": reason if abs(difference) > Decimal("0.01") else None,
            "allocated": str(money(allocated)),
        },
        ip_address=ip_address,
    )
    return batch_detail(session, batch)


def void_batch(
    session: Session,
    user: User,
    remittance_id: uuid.UUID,
    note: str | None = None,
    ip_address: str | None = None,
) -> dict[str, Any]:
    batch = _get_batch(session, remittance_id, for_update=True)
    if batch.status == CodRemittanceStatus.RECONCILED.value:
        raise HTTPException(409, "Reconciled remittances cannot be voided")
    if batch.status == CodRemittanceStatus.VOID.value:
        return batch_detail(session, batch)
    before = {"status": batch.status}
    batch.status = CodRemittanceStatus.VOID.value
    if note:
        batch.notes = note
    session.add(batch)
    audit_repo.log_and_commit(
        session,
        "cod.remittance.voided",
        "cod_remittance",
        batch.id,
        user.id,
        before=before,
        after={"status": batch.status, "note": note},
        ip_address=ip_address,
    )
    return batch_detail(session, batch)


# ---------------------------------------------------------------------------
# Summary / simulator / CSV output
# ---------------------------------------------------------------------------

def get_summary(session: Session) -> dict[str, Any]:
    def count_sum(statement):
        row = session.exec(statement).one()
        if row is None:
            return 0, Decimal("0.00")
        return int(row[0] or 0), money(row[1] or 0)

    awaiting_collection_count, awaiting_collection_amount = count_sum(
        select(func.count(Order.id), func.coalesce(func.sum(Order.grand_total), 0))
        .where(
            Order.payment_method == "cod",
            Order.payment_status == "cod_pending",
            Order.status == OrderStatus.DELIVERED,
        )
    )
    awaiting_remittance_count, awaiting_remittance_amount = count_sum(
        select(
            func.count(Order.id),
            func.coalesce(func.sum(Order.grand_total - Order.cod_remitted_amount), 0),
        )
        .where(
            Order.payment_method == "cod",
            Order.payment_status == "paid",
            Order.status == OrderStatus.DELIVERED,
            Order.cod_remittance_status != "complete",
        )
    )
    pending_batches, pending_amount = count_sum(
        select(func.count(CodRemittance.id), func.coalesce(func.sum(CodRemittance.net_expected), 0))
        .where(CodRemittance.status == CodRemittanceStatus.PENDING.value)
    )
    discrepancy_batches, discrepancy_amount = count_sum(
        select(func.count(CodRemittance.id), func.coalesce(func.sum(CodRemittance.net_expected), 0))
        .where(CodRemittance.status == CodRemittanceStatus.DISCREPANCY.value)
    )

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    reconciled_count, reconciled_amount = count_sum(
        select(func.count(CodRemittance.id), func.coalesce(func.sum(CodRemittance.bank_credit_amount), 0))
        .where(
            CodRemittance.status == CodRemittanceStatus.RECONCILED.value,
            CodRemittance.reconciled_at >= month_start,
        )
    )
    open_discrepancies = session.exec(
        select(func.count(CodRemittanceItem.id))
        .join(CodRemittance, CodRemittance.id == CodRemittanceItem.remittance_id)
        .where(
            CodRemittance.status != CodRemittanceStatus.VOID.value,
            CodRemittanceItem.match_status.notin_([
                CodRemittanceItemStatus.MATCHED.value,
                CodRemittanceItemStatus.ADJUSTMENT.value,
            ]),
        )
    ).one()

    return {
        "awaiting_collection": {
            "count": awaiting_collection_count,
            "amount": _f(awaiting_collection_amount),
        },
        "awaiting_remittance": {
            "count": awaiting_remittance_count,
            "amount": _f(awaiting_remittance_amount),
        },
        "pending_batches": {
            "count": pending_batches,
            "amount": _f(pending_amount),
        },
        "discrepancy_batches": {
            "count": discrepancy_batches,
            "amount": _f(discrepancy_amount),
        },
        "reconciled_this_month": {
            "count": reconciled_count,
            "amount": _f(reconciled_amount),
        },
        "open_discrepancies": int(open_discrepancies or 0),
        "simulator_enabled": simulator_enabled(),
    }


def list_awaiting_remittance(
    session: Session, *, page: int = 1, limit: int = 15
) -> dict[str, Any]:
    """List delivered, cash-collected COD orders with a courier payout balance."""
    from sqlalchemy.orm import selectinload

    criteria = (
        Order.payment_method == "cod",
        Order.payment_status == "paid",
        Order.status == OrderStatus.DELIVERED,
        Order.cod_remittance_status != "complete",
    )
    count = session.exec(select(func.count(Order.id)).where(*criteria)).one()
    amount = session.exec(
        select(func.coalesce(func.sum(Order.grand_total - Order.cod_remitted_amount), 0))
        .where(*criteria)
    ).one()
    orders = session.exec(
        select(Order)
        .where(*criteria)
        .options(selectinload(Order.user))
        .order_by(Order.delivered_at.desc(), Order.placed_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).all()
    return {
        "orders": [
            {
                "id": str(order.id),
                "order_number": order.order_number,
                "customer": {
                    "full_name": (order.customer_snapshot or {}).get("full_name")
                    or (order.user.full_name if order.user else None),
                    "email": (order.customer_snapshot or {}).get("email")
                    or (order.user.email if order.user else None),
                },
                "grand_total": _f(order.grand_total),
                "remitted_amount": _f(order.cod_remitted_amount),
                "remaining_amount": _f(money(order.grand_total) - money(order.cod_remitted_amount)),
                "awb_code": order.awb_code,
                "courier_name": order.courier_name,
                "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            }
            for order in orders
        ],
        "total": int(count or 0),
        "total_amount": _f(amount or 0),
        "page": page,
        "limit": limit,
        "total_pages": max(1, (int(count or 0) + limit - 1) // limit),
    }


def simulate_batch(
    session: Session,
    user: User,
    *,
    max_orders: int = 5,
    deduction_percent: Decimal = Decimal("2"),
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Build a synthetic batch from delivered COD orders.

    This is a development aid. It never calls Shiprocket and is stored with
    ``source=simulator`` and ``raw_meta.synthetic=true`` so the UI can label it.
    """
    if not simulator_enabled():
        raise HTTPException(
            403,
            "Synthetic COD remittance is disabled in production. "
            "Set COD_REMITTANCE_SIMULATOR_ENABLED=true to opt in.",
        )

    candidates = session.exec(
        select(Order)
        .where(
            Order.payment_method == "cod",
            Order.payment_status == "paid",
            Order.status == OrderStatus.DELIVERED,
            Order.cod_remittance_status != "complete",
        )
        .order_by(Order.delivered_at.desc(), Order.placed_at.desc())
        .limit(max(1, min(max_orders, 25)))
    ).all()

    lines: list[dict[str, Any]] = []
    for order in candidates:
        if order.cod_remittance_status == "complete":
            continue
        if _existing_remittance_item(session, order.id):
            continue
        gross = money(order.grand_total)
        remaining = max(Decimal("0.00"), gross - money(order.cod_remitted_amount))
        if remaining <= Decimal("0.00"):
            continue
        deduction = max(
            Decimal("1.00"),
            money(remaining * deduction_percent / Decimal("100")),
        )
        deduction = min(deduction, remaining)
        net = money(remaining - deduction)
        if net <= Decimal("0.00"):
            continue
        lines.append({
            "row_number": len(lines) + 1,
            "awb": order.awb_code,
            "order_ref": order.order_number,
            "cod_amount": remaining,
            "deductions": deduction,
            "net_amount": net,
            "remitted_amount": net,
            "crf_id": None,
            "remittance_date": date.today(),
            "utr": None,
            "raw_row": {
                "awb": order.awb_code,
                "order_number": order.order_number,
                "cod_amount": str(remaining),
                "deductions": str(deduction),
                "net_amount": str(net),
                "source": "simulator",
            },
            "source_row": len(lines) + 1,
        })

    if not lines:
        raise HTTPException(
            400,
            "No delivered COD orders with recorded cash are waiting for remittance. "
            "Deliver and collect a COD order first.",
        )

    batch = create_batch(
        session,
        user,
        crf_id=f"SIM-{uuid.uuid4().hex[:8].upper()}",
        remittance_date=date.today(),
        lines=lines,
        source=CodRemittanceSource.SIMULATOR.value,
        source_filename=None,
        notes="Synthetic development batch — not a real Shiprocket remittance",
        mapping={},
        synthetic=True,
        ip_address=ip_address,
    )
    batch["synthetic"] = True
    return batch


def template_csv() -> str:
    return ",".join(TEMPLATE_HEADERS) + "\n"


def fixture_csv() -> str:
    rows = [
        TEMPLATE_HEADERS + ["data_note"],
        [
            "SIM-AWB-1001", "SIM-ORD-1001", "1500.00", "30.00", "1470.00",
            "SIM-CRF-0001", date.today().isoformat(), "SIMUTR0001", SYNTHETIC_NOTE,
        ],
        [
            "SIM-AWB-1002", "SIM-ORD-1002", "899.00", "18.00", "881.00",
            "SIM-CRF-0001", date.today().isoformat(), "SIMUTR0001", SYNTHETIC_NOTE,
        ],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerows(rows)
    return output.getvalue()


def batch_csv(session: Session, batch: CodRemittance) -> str:
    detail = batch_detail(session, batch)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "crf_id", "remittance_date", "status", "awb", "order_number",
        "cod_amount", "deductions", "net_amount", "remitted_amount",
        "match_status", "utr", "bank_credit_amount", "difference", "source",
    ])
    for item in detail["items"]:
        writer.writerow([
            detail["crf_id"],
            detail["remittance_date"],
            detail["status"],
            item["awb"] or "",
            item["order_number"] or item["order_ref"] or "",
            f"{item['cod_amount']:.2f}",
            f"{item['deductions']:.2f}",
            f"{item['net_amount']:.2f}",
            f"{item['remitted_amount']:.2f}",
            item["match_status"],
            detail["utr"] or "",
            f"{detail['bank_credit_amount']:.2f}" if detail["bank_credit_amount"] is not None else "",
            f"{detail['difference']:.2f}" if detail["difference"] is not None else "",
            detail["source"],
        ])
    return output.getvalue()

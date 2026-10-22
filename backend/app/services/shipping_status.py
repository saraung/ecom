# app/services/shipping_status.py
"""
Single source of truth for mapping Shiprocket's courier statuses onto our
``OrderStatus`` enum, and for building payloads in Shiprocket's real wire
format.

Why this module exists
----------------------
The mapping used to be written twice: once in the real webhook handler and once
in the admin "simulator" endpoint. The two copies had already drifted — the
simulator knew about NOC/exception states the webhook did not, and the webhook
mis-mapped the real Shiprocket status ``RTO IN TRANSIT`` to SHIPPED because it
substring-matched "IN TRANSIT" before checking RTO. Both sides now call
:func:`map_shiprocket_status`, so they cannot drift again.

The simulator builds payloads with :func:`build_tracking_webhook_payload`, which
emits the same ``{"data": {...}}`` envelope Shiprocket POSTs to a tracking
webhook. Going live is therefore a config change, not a code change: set
``SHIPPING_PROVIDER=shiprocket`` and point Shiprocket's panel at
``/api/v1/webhooks/shiprocket``.

Status vocabulary and codes
---------------------------
The *status strings* are taken from Shiprocket's own public pages — their order
tracker (shiprocket.in/blog/shipment-tracking) and their RTO terminology guide
(shiprocket.in/blog/return-to-origin-processing-terminology). Both are quoted in
``tests/test_shiprocket_shipping.py::test_14`` so a regression here is caught.

The numeric table is the published Shiprocket Postman collection's Shipments /
Tracking status table (12508904/TVCZbXSb), checked 2026-10-05. Order status codes
are a DIFFERENT namespace: e.g. order 26 is Return Delivered, shipment 26 is
Fulfilled. Never use order status codes as tracking codes. Human carrier labels
take precedence; unknown numeric codes remain unknown rather than being guessed.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.order import OrderStatus

# ---------------------------------------------------------------------------
# Shiprocket's numeric shipment_status codes
# ---------------------------------------------------------------------------
SHIPROCKET_STATUS_CODES: dict[int, str] = {
    1: "AWB ASSIGNED",
    2: "LABEL GENERATED",
    3: "PICKUP SCHEDULED",
    4: "PICKUP QUEUED",
    5: "MANIFEST GENERATED",
    6: "SHIPPED",
    7: "DELIVERED",
    8: "CANCELLED",
    9: "RTO INITIATED",
    10: "RTO DELIVERED",
    11: "PENDING",
    12: "LOST",
    13: "PICKUP ERROR",
    14: "RTO ACKNOWLEDGED",
    15: "PICKUP RESCHEDULED",
    16: "CANCELLATION REQUESTED",
    17: "OUT FOR DELIVERY",
    18: "IN TRANSIT",
    19: "OUT FOR PICKUP",
    20: "PICKUP EXCEPTION",
    21: "UNDELIVERED",
    22: "DELAYED",
    23: "PARTIAL DELIVERED",
    24: "DESTROYED",
    25: "DAMAGED",
    26: "FULFILLED",
    38: "REACHED AT DESTINATION",
    39: "MISROUTED",
    40: "RTO NDR",
    41: "RTO OFD",
    42: "PICKED UP",
    43: "SELF FULFILLED",
}

#: Human label -> the status code Shiprocket pairs it with, used by the simulator.
STATUS_CODE_BY_LABEL: dict[str, int] = {}
for _code, _label in SHIPROCKET_STATUS_CODES.items():
    STATUS_CODE_BY_LABEL.setdefault(_label, _code)
STATUS_CODE_BY_LABEL.update({"RETURN PICKUP GENERATED": 3, "RETURN PICKUP RESCHEDULED": 15,
    "RETURN OUT FOR PICKUP": 19, "RETURN PICKED UP": 42, "RETURN IN TRANSIT": 18,
    "RETURN OUT FOR DELIVERY": 17, "RETURN DELIVERED": 7, "RETURN PICKUP ERROR": 13,
    "RETURN PICKUP EXCEPTION": 20, "RETURN UNDELIVERED": 21, "RETURN CANCELLED": 8,
    # Human labels observed in courier scans mapped to the published shipment
    # status namespace used in simulator payloads.
    "RTO INITIATED": 9, "RTO IN TRANSIT": 18, "RTO DISPATCHED": 6,
    "RTO OFD": 41, "RTO DELIVERED": 10, "RTO ACKNOWLEDGED": 14})
# ---------------------------------------------------------------------------
# Ordered transition rules
# ---------------------------------------------------------------------------
# ORDER IS SIGNIFICANT — the first match wins. "RTO" must be tested before
# anything that could be a substring of it: real Shiprocket sends statuses like
# "RTO IN TRANSIT" and "RTO DELIVERED", both of which contain the substring
# "IN TRANSIT" / "DELIVERED". Matching those first would announce a returned
# parcel to the customer as shipped or delivered.
#
# Each rule is (needle, order_status, shipment_status_to_store).
# ``order_status = None`` means "record the scan, but do not move the order" —
# a courier-level event such as NOC or a pickup schedule that our order
# lifecycle does not model.
_STATUS_RULES: tuple[tuple[str, Optional[OrderStatus], str], ...] = (
    # --- RTO family first: every RTO label contains another status' substring.
    #     "RTO Acknowledged" is Shiprocker's own term for when the seller accepts
    #     the return (see their RTO terminology guide); the generic "RTO" rule
    #     below catches it, but naming it documents the flow.
    ("RTO", OrderStatus.RTO, "RTO"),
    # --- Happy path, in courier order.
    ("OUT FOR DELIVERY", OrderStatus.OUT_FOR_DELIVERY, "OUT FOR DELIVERY"),
    ("DELIVERED", OrderStatus.DELIVERED, "DELIVERED"),
    # Shiprocket's public tracker labels the pickup event "Order Picked" and its
    # own tracking payload uses "PICKED UP"; both mean the parcel left the
    # warehouse, which is what actually ships the order.
    ("PICKED UP", OrderStatus.SHIPPED, "IN TRANSIT"),
    ("ORDER PICKED", OrderStatus.SHIPPED, "IN TRANSIT"),
    ("PICKED", OrderStatus.SHIPPED, "IN TRANSIT"),
    ("SHIPPED", OrderStatus.SHIPPED, "IN TRANSIT"),
    ("IN TRANSIT", OrderStatus.SHIPPED, "IN TRANSIT"),
    ("DISPATCHED", OrderStatus.SHIPPED, "IN TRANSIT"),
    # --- Pickup scheduling: real, but not an order-status change. The order
    #     stays "processing" until the parcel actually leaves the warehouse.
    ("PICKUP SCHEDULED", None, "PICKUP_SCHEDULED"),
    ("PICKUP SUCCESSFUL", None, "PICKUP_SCHEDULED"),
    ("PICKUP ATTEMPTED", None, "PICKUP_SCHEDULED"),
    ("PICKUP OVERDUE", None, "PICKUP_SCHEDULED"),
    ("AWAITING PICKUP SCHEDULE", None, "AWAITING_PICKUP_SCHEDULE"),
    # --- Pre-pickup paperwork: still "processing" on our side.
    ("LABEL GENERATED", None, "LABEL_GENERATED"),
    ("MANIFEST GENERATED", None, "MANIFEST_GENERATED"),
    ("READY TO SHIP", None, "READY_TO_SHIP"),
    ("SHIPMENT GENERATED", None, "READY_TO_SHIP"),
    ("CONFIRMED", None, "CONFIRMED"),
    # Shiprocket's public tracker wording for the pre-courier milestones. These
    # never move the order; they just tell the admin where the parcel is queued.
    ("ORDER RECEIVED", None, "ORDER_RECEIVED"),
    # ORDER_CREATED is written by this app (not a Shiprocket status), but map it
    # so a round-trip through the parser never reports it as UNKNOWN.
    ("ORDER CREATED", None, "ORDER_CREATED"),
    ("AWB ASSIGNED", None, "AWB_ASSIGNED"),
    ("AWB GENERATED", None, "AWB_ASSIGNED"),
    ("REACHED DESTINATION", None, "OUT_FOR_DELIVERY"),
    # --- Exceptions: recorded on the timeline, order status left alone.
    ("NOC", None, "NOC"),
    ("LOST", None, "LOST"),
    ("DAMAGED", None, "DAMAGED"),
    ("NOT SERVICEABLE", None, "NOT_SERVICEABLE"),
    ("MISSORT", None, "MISSORT"),
    ("APPOINTMENT BOOKED", None, "OUT_FOR_DELIVERY"),
    ("ON HOLD", None, "ON_HOLD"),
    # --- Terminal / negative.
    ("CANCELLED", OrderStatus.CANCELLED, "CANCELLED"),
    ("KILLED", OrderStatus.CANCELLED, "CANCELLED"),
)

#: Once an order reaches one of these, later scans must not move it backwards.
#: Real couriers send out-of-order and duplicate scans, and Shiprocket retries
#: webhooks, so this is a correctness guard, not a nicety.
TERMINAL_ORDER_STATUSES: frozenset[OrderStatus] = frozenset(
    {OrderStatus.DELIVERED, OrderStatus.CANCELLED, OrderStatus.REFUNDED, OrderStatus.RTO}
)

#: A parcel handed back to the seller is restocked when it reaches the warehouse
#: ("RTO DELIVERED" / "3PL RTO DELIVERED"), not when the RTO merely starts.
RTO_DELIVERED_LABELS: frozenset[str] = frozenset(
    {"RTO DELIVERED", "3PL RTO DELIVERED"}
)


def normalize_status(value: Any) -> str:
    """Coerce any status representation to an upper-case label.

    Shiprocket is inconsistent about types: ``current_status`` is a string
    ("IN TRANSIT") but ``shipment_status`` is a numeric code (18) in the same
    payload. Calling ``.upper()`` on the raw value raises ``AttributeError`` on
    the int and 500s the webhook, which makes Shiprocket retry and eventually
    disable the endpoint — so normalise before any string operation.
    """
    if value is None or isinstance(value, bool):  # bool is an int subclass
        return ""
    if isinstance(value, (int, float)):
        try:
            return SHIPROCKET_STATUS_CODES.get(int(value), str(value))
        except (ValueError, OverflowError, TypeError):
            return str(value)
    return str(value).strip().upper()


def map_shiprocket_status(raw_status: Any) -> tuple[Optional[OrderStatus], str]:
    """Map a raw Shiprocket status onto ``(order_status, shipment_status)``.

    Returns ``(None, "UNKNOWN")`` when nothing matches, so an unrecognised
    courier status is recorded on the timeline instead of silently doing
    nothing — and, critically, never mis-moves the order.
    """
    label = normalize_status(raw_status)
    if not label:
        return None, "UNKNOWN"

    # Failed/partial delivery must not substring-match DELIVERED. RTO remains
    # on the original shipment and keeps its exact phase for presentation.
    if "RTO" in label:
        return OrderStatus.RTO, label
    if "UNDELIVERED" in label or "NOT DELIVERED" in label:
        return None, "UNDELIVERED"
    if "PARTIAL DELIVERED" in label or "PARTIAL_DELIVERED" in label:
        return None, "PARTIAL DELIVERED"
    if label in {"DELAYED", "MISROUTED", "DESTROYED", "PICKUP ERROR", "PICKUP EXCEPTION", "PICKUP RESCHEDULED", "OUT FOR PICKUP"}:
        return None, label

    for needle, order_status, shipment_status in _STATUS_RULES:
        if needle in label:
            return order_status, shipment_status
    return None, "UNKNOWN"


def is_rto_delivered(label: str) -> bool:
    """True when the RTO has physically arrived back at the warehouse."""
    return normalize_status(label) in RTO_DELIVERED_LABELS


def should_restore_stock(current: OrderStatus, label: str) -> bool:
    """Whether this scan means the parcel is back with the seller.

    Restocking is a one-way operation (stock is incremented, never decremented
    back), so it must be gated on the event *and* on not having already
    restocked this order — Shiprocket retries webhooks, and a duplicate
    "RTO DELIVERED" would otherwise inflate inventory.
    """
    if current == OrderStatus.DELIVERED:
        return False  # a delivered order is never restocked by a return
    return is_rto_delivered(label)


def normalize_location(raw: Any) -> str:
    """Flatten Shiprocket's ``location`` field to a single human-readable string.

    The tracking API nests location as an object::

        "location": {"location_id": 1, "name": "Delhi_Sez_GW",
                     "city": "New Delhi", "state": "Delhi",
                     "country": "India", "pincode": "110001"}

    while the tracking *webhook* sends a plain string. Storing the dict as-is
    makes the admin timeline render ``[object Object]``, so normalise both.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict):
        # Prefer the facility name, then fall back through the other parts so a
        # location carrying only a city still shows something useful.
        for key in ("name", "city", "state", "pincode", "location_id"):
            value = raw.get(key)
            if value:
                return str(value).strip()
    return str(raw).strip()


def build_tracking_webhook_payload(
    *,
    awb: str,
    current_status: str,
    shipment_status: Optional[int] = None,
    location: str = "Regional Processing Hub",
    activity: Optional[str] = None,
    order_id: Optional[str | int] = None,
    is_return: int = 0,
    label_generated: bool = False,
    manifest_generated: bool = False,
    pickup_scheduled: bool = False,
) -> dict[str, Any]:
    """Build a payload shaped exactly like Shiprocket's tracking webhook.

    The real webhook body is wrapped in a top-level ``data`` key and carries a
    pile of boolean flags plus both a human ``current_status`` and a numeric
    ``shipment_status``. The simulator sends this shape through the *same*
    handler production uses, which is what keeps the two honest: any parsing
    bug shows up in the simulator immediately instead of silently dropping live
    shipments.
    """
    label = normalize_status(current_status)
    code = (
        shipment_status
        if shipment_status is not None
        else STATUS_CODE_BY_LABEL.get(label)
    )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    is_rto = "RTO" in label
    detail = activity or f"Shipment status: {label}"

    return {
        "data": {
            "id": order_id,
            "awb": awb,
            "awb_code": awb,
            "is_label_generated": label_generated,
            "is_manifest_generated": manifest_generated,
            "is_pickup_scheduled": pickup_scheduled or label in {"PICKUP SCHEDULED", "RETURN PICKUP GENERATED"},
            "is_courier_awaiting": code in (1, 2, 3, 4, 5, 11),
            "is_fulfilment": False,
            "is_dropship": False,
            "is_return": is_return,
            "is_returned": label in RTO_DELIVERED_LABELS or bool(is_return) and label in {"DELIVERED", "RETURN DELIVERED", "RETURN_DELIVERED"},
            "is_delivered": label in {"DELIVERED", "RETURN DELIVERED", "RETURN_DELIVERED"},
            "is_cancelled": "CANCEL" in label or "KILLED" in label,
            "is_killed": "KILLED" in label,
            "current_status": label,
            "current_status_notes": detail,
            "shipment_status": code,
            "shipment_status_notes": detail,
            "activity": detail,
            "date": now,
            # The tracking *webhook* sends a plain string here, unlike the
            # tracking API which nests it as an object.
            "location": location,
            "is_early_intransit": False,
            "pickup_scheduled_date": None,
            "tracking_data": {
                "track_status": 1,
                "shipment_status": label,
                "shipment_track": [
                    {
                        "date": now,
                        "status": label,
                        "activity": detail,
                        "location": location,
                        "sr-status": str(code) if code is not None else "",
                        "sr-status-label": label,
                    }
                ],
            },
        }
    }


# ---------------------------------------------------------------------------
# Admin presentation: the fulfilment pipeline
# ---------------------------------------------------------------------------
# Why this exists
# ---------------
# `order.status` (pending/processing/shipped/...) is the *order* lifecycle, and
# `shipment_status` is the *courier's* raw vocabulary. The admin UI used to
# render `shipment_status` directly, so an order showed a bare "PICKUP_SCHEDULED"
# / "IN TRANSIT" / "NOC" pill with no indication of what it means or what to do
# next — and the status colours were hand-maintained in several JSX files that
# had already drifted apart.
#
# This collapses a shipment onto a small set of *stages* the UI can render
# consistently. The stages match what an operations person actually acts on, and
# mirror the milestones Shiprocket emails customers about (packed, picked,
# shipped, out for delivery, delivered).
#
# ``step`` is the position on the happy-path track (1-5) so the admin can draw a
# progress bar; ``None`` means the parcel is off the happy path (returned,
# cancelled, or stalled on an exception) and must not be drawn as progress.

STAGE_NOT_STARTED = "not_started"
STAGE_READY = "ready"
STAGE_PICKUP_SCHEDULED = "pickup_scheduled"
STAGE_PICKED_UP = "picked_up"
STAGE_IN_TRANSIT = "in_transit"
STAGE_OUT_FOR_DELIVERY = "out_for_delivery"
STAGE_DELIVERED = "delivered"
STAGE_RETURNED = "returned"
STAGE_EXCEPTION = "exception"
STAGE_CANCELLED = "cancelled"

#: stage -> (label, step on the happy path or None, tone for the UI).
#: ``tone`` is consumed by the frontend, so a new status is coloured correctly
#: everywhere at once instead of in each screen.
STAGE_PRESENTATION: dict[str, tuple[str, Optional[int], str]] = {
    STAGE_NOT_STARTED: ("Not Shipped", None, "neutral"),
    STAGE_READY: ("Ready to Ship", 1, "info"),
    STAGE_PICKUP_SCHEDULED: ("Pickup Scheduled", 2, "info"),
    STAGE_PICKED_UP: ("Picked Up", 3, "info"),
    STAGE_IN_TRANSIT: ("In Transit", 3, "info"),
    STAGE_OUT_FOR_DELIVERY: ("Out for Delivery", 4, "warning"),
    STAGE_DELIVERED: ("Delivered", 5, "success"),
    STAGE_RETURNED: ("Returned to Origin", None, "danger"),
    STAGE_EXCEPTION: ("Delivery Issue", None, "danger"),
    STAGE_CANCELLED: ("Shipment Cancelled", None, "neutral"),
}

#: Shipment statuses meaning "something is wrong, a human should look". These
#: are the ones worth surfacing loudly in the admin UI.
EXCEPTION_LABELS: frozenset[str] = frozenset(
    {"NOC", "UNDELIVERED", "PARTIAL DELIVERED", "DELAYED", "MISROUTED", "RTO NDR",
     "PICKUP ERROR", "PICKUP EXCEPTION", "LOST", "DAMAGED", "NOT SERVICEABLE", "MISSORT", "ON HOLD", "UNKNOWN"}
)

#: Statuses this app writes itself when an admin acts, mapped to stages. These
#: are the ONLY pre-courier states the real flow produces:
#:   create order   -> ORDER_CREATED
#:   assign AWB     -> AWB_ASSIGNED
#:   request pickup -> PICKUP_SCHEDULED
#: There is deliberately no LABEL_GENERATED / MANIFEST_GENERATED *stage*: those
#: endpoints only store a URL and never move `shipment_status`, so showing them
#: as a stage would misrepresent the flow.
LOCAL_STATUS_STAGES: dict[str, str] = {
    "ORDER_CREATED": STAGE_READY,
    "AWB_ASSIGNED": STAGE_READY,
    "LABEL_GENERATED": STAGE_READY,
    "MANIFEST_GENERATED": STAGE_READY,
    "READY_TO_SHIP": STAGE_READY,
    "CONFIRMED": STAGE_READY,
    "AWAITING_PICKUP_SCHEDULE": STAGE_READY,
    "ORDER_RECEIVED": STAGE_READY,
    "AWB_ASSIGNED": STAGE_READY,
    "ORDER_CREATED": STAGE_READY,
    "PICKUP SCHEDULED": STAGE_PICKUP_SCHEDULED,
    "PICKUP OVERDUE": STAGE_PICKUP_SCHEDULED,
    "IN TRANSIT": STAGE_IN_TRANSIT,
    "PICKED UP": STAGE_PICKED_UP,
    "OUT FOR DELIVERY": STAGE_OUT_FOR_DELIVERY,
    "DELIVERED": STAGE_DELIVERED,
    "RTO": STAGE_RETURNED,
    "CANCELLED": STAGE_CANCELLED,
    "KILLED": STAGE_CANCELLED,
}
def derive_shipment_stage(
    *,
    has_awb: bool,
    pickup_scheduled: bool,
    shipment_status: Optional[str] = None,
    order_status: Optional[str] = None,
) -> str:
    """Collapse a shipment's raw state into one presentable stage.

    The order's own status wins when it is further along than the courier
    status, because the order status drives customer-facing emails and
    notifications — the two must never disagree in a way that makes the UI
    look stuck.
    """
    raw = normalize_status(shipment_status)
    order_raw = normalize_status(order_status)

    # A courier exception is the most actionable fact we have, so it is checked
    # FIRST. Ordering matters: an order can still read "shipped" while the
    # courier has reported the parcel lost or a failed delivery attempt, and
    # burying that under "In Transit" hides a problem that costs money.
    if raw in EXCEPTION_LABELS:
        return STAGE_EXCEPTION

    if order_raw in ("CANCELLED", "REFUNDED"):
        return STAGE_CANCELLED
    if order_raw == "RTO":
        return STAGE_RETURNED
    if order_raw == "DELIVERED":
        return STAGE_DELIVERED
    if order_raw == "OUT FOR DELIVERY":
        return STAGE_OUT_FOR_DELIVERY
    if order_raw == "SHIPPED":
        # Picked-up and in-transit are one stage to an operator: the parcel is
        # with the courier. The label still distinguishes them.
        return STAGE_IN_TRANSIT

    if raw in LOCAL_STATUS_STAGES:
        return LOCAL_STATUS_STAGES[raw]

    # No courier status yet — fall back to what the admin has actually done.
    if pickup_scheduled:
        return STAGE_PICKUP_SCHEDULED
    if has_awb:
        return STAGE_READY
    return STAGE_NOT_STARTED


def shipment_stage_payload(
    *,
    has_awb: bool,
    pickup_scheduled: bool,
    shipment_status: Optional[str] = None,
    order_status: Optional[str] = None,
) -> dict[str, Any]:
    """Full stage descriptor for the admin UI (label, step, tone, raw status).

    ``step``/``tone`` let the UI draw a consistent progress bar and colour
    without re-deriving any of this logic in JavaScript.
    """
    stage = derive_shipment_stage(
        has_awb=has_awb,
        pickup_scheduled=pickup_scheduled,
        shipment_status=shipment_status,
        order_status=order_status,
    )
    label, step, tone = STAGE_PRESENTATION[stage]
    if stage == STAGE_RETURNED and not is_rto_delivered(shipment_status or ""):
        label = "Returning to Origin"
    return {
        "stage": stage,
        "label": label,
        "step": step,
        "tone": tone,
        # The courier's own words, kept for support/dispute conversations.
        "raw_status": normalize_status(shipment_status) or None,
        "is_exception": stage == STAGE_EXCEPTION,
    }


def simulation_state(order, returned=None) -> dict[str, Any]:
    """Actual before/after facts for simulator feedback, never provider promises."""
    result = {"order_status": order.status.value, "shipment_status": order.shipment_status,
              "payment_status": order.payment_status, "refund_amount": str(order.refund_amount),
              "stock_released": order.stock_released, "rto_stock_restored": order.rto_stock_restored,
              "forward_awb": order.awb_code}
    if returned is not None:
        result.update(return_status=returned.status.value, return_tracking_status=returned.tracking_status,
                      inspection_passed=returned.inspection_passed, return_awb=returned.tracking_number)
    return result

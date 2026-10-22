from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import hashlib
import random
import re

import httpx

from app.core.config import settings
from app.core.region import default_country, from_minor_units, minor_units
from app.models.order import Order

logger = logging.getLogger(__name__)

#: Shiprocket auth tokens are long-lived (~10 days per Shiprocket docs).
#: Refresh a day early so a borderline-expired token never 401s mid-dispatch.
TOKEN_REFRESH_LEAD = timedelta(days=1)
TOKEN_TTL = timedelta(days=10) - TOKEN_REFRESH_LEAD

#: Fallback parcel dimensions (cm) / weight (kg) when a variant has none stored.
DEFAULT_LENGTH_CM = 10
DEFAULT_BREADTH_CM = 10
DEFAULT_HEIGHT_CM = 10
DEFAULT_WEIGHT_KG = 0.5

#: Phone sent to Shiprocket when the customer never stored one.
FALLBACK_PHONE = "9999999999"


def parse_etd_max_days(etd: Optional[str]) -> Optional[int]:
    """Extract the upper bound of a courier ETD text ("3-4 Days" -> 4).

    Returns None when the text carries no day count, so callers can fall
    back to a default window instead of guessing.
    """
    if not etd:
        return None
    days = [int(n) for n in re.findall(r"\d+", etd)]
    return max(days) if days else None


#: Extra safety days added ON TOP of the courier ETD when an ETD is present.
#: Shiprocket's ETD ("3-4 Days") only counts from when the courier PICKS UP
#: the parcel — but at AWB assignment time the parcel is still at the
#: warehouse, and pickup can slip 1-2 days (next-day slots, weekend
#: dispatch). The buffer covers that gap so the promised date lands on or
#: before the printed date. The no-ETD +7-day fallback already absorbs the
#: gap, so it stays untouched.
ETA_BUFFER_DAYS = 2


def estimate_delivery_date(etd: Optional[str], *, default_days: int = 7) -> datetime:
    """ETA date from a courier ETD text, defaulting to +7 days.

    With an ETD: dispatch date + ETD max days + ``ETA_BUFFER_DAYS``.
    Without one: plain +``default_days`` fallback (no buffer doubled in).
    """
    days = parse_etd_max_days(etd)
    return datetime.now(timezone.utc) + timedelta(days=(days or 0) + ETA_BUFFER_DAYS if days else default_days)


class ShippingServiceInterface(ABC):
    def find_return_order(self, reference: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def get_return_order(self, order_id: str, reference: str) -> Dict[str, Any]:
        raise NotImplementedError

    def create_return_order(self, order: Order, reference: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def check_serviceability(
        self, pickup_pincode: str, delivery_pincode: str, weight: float, cod: bool
    ) -> List[Dict[str, Any]]:
        """List available couriers and rates"""
        pass

    @abstractmethod
    def create_order(self, order: Order) -> Dict[str, Any]:
        """Create adhoc order on Shiprocket"""
        pass

    @abstractmethod
    def assign_awb(self, shipment_id: str, courier_id: Optional[int] = None, *, is_return: bool = False) -> Dict[str, Any]:
        """Assign courier partner and generate AWB"""
        pass

    @abstractmethod
    def request_pickup(self, shipment_id: str) -> Dict[str, Any]:
        """Request courier pickup"""
        pass

    @abstractmethod
    def generate_label(self, shipment_id: str) -> Dict[str, Any]:
        """Generate shipping label link"""
        pass

    @abstractmethod
    def generate_manifest(self, shipment_id: str) -> Dict[str, Any]:
        """Generate manifest link"""
        pass

    @abstractmethod
    def get_tracking(self, awb_code: str) -> Dict[str, Any]:
        """Fetch tracking timeline"""
        pass

    @abstractmethod
    def cancel_shipment(self, shiprocket_order_id: str) -> Dict[str, Any]:
        """Cancel shipment on Shiprocket"""
        pass


class MockShiprocketService(ShippingServiceInterface):
    """
    High-fidelity simulator for Shiprocket.
    Provides realistic courier rates, generates genuine mock AWBs,
    and returns printable mock labels without incurring any courier charges.
    """

    MOCK_COURIERS = [
        {"courier_company_id": 10, "courier_name": "Delhivery Surface", "rate": Decimal("52.00"), "etd": "3-4 Days", "rating": 4.5, "cod": True},
        {"courier_company_id": 12, "courier_name": "Delhivery Express", "rate": Decimal("85.00"), "etd": "1-2 Days", "rating": 4.8, "cod": True},
        {"courier_company_id": 20, "courier_name": "Blue Dart Air", "rate": Decimal("110.00"), "etd": "1-2 Days", "rating": 4.9, "cod": True},
        {"courier_company_id": 35, "courier_name": "Shadowfax Local", "rate": Decimal("45.00"), "etd": "2-3 Days", "rating": 4.2, "cod": True},
        {"courier_company_id": 44, "courier_name": "DTDC Surface", "rate": Decimal("48.00"), "etd": "3-5 Days", "rating": 4.1, "cod": True},
    ]

    def check_serviceability(
        self, pickup_pincode: str, delivery_pincode: str, weight: float, cod: bool
    ) -> List[Dict[str, Any]]:
        weight_multiplier = Decimal(str(max(1.0, weight)))
        couriers = []
        for c in self.MOCK_COURIERS:
            couriers.append({
                "courier_company_id": c["courier_company_id"],
                "courier_name": c["courier_name"],
                "rate": round(c["rate"] * weight_multiplier, 2),
                "etd": c["etd"],
                "rating": c["rating"],
                "cod": c["cod"] if cod else True,
            })
        return couriers

    def create_order(self, order: Order) -> Dict[str, Any]:
        simulated_order_id = f"SR-ORD-{random.randint(100000, 999999)}"
        simulated_shipment_id = f"SR-SHP-{random.randint(100000, 999999)}"
        return {
            "order_id": simulated_order_id,
            "shipment_id": simulated_shipment_id,
            "status": "NEW",
            "status_code": 1,
            "message": "Simulated order successfully pushed to Shiprocket",
        }

    def find_return_order(self, reference: str) -> Optional[Dict[str, Any]]:
        # No external store in simulator mode. Deterministic IDs make recovery
        # survive service/process restarts without creating a second shipment.
        return self.get_return_order(f"SR-RET-{reference}", reference)

    def get_return_order(self, order_id: str, reference: str) -> Dict[str, Any]:
        if order_id != f"SR-RET-{reference}":
            raise ValueError("Return provider reference does not match")
        return {"order_id": order_id, "shipment_id": f"SR-RET-SHP-{reference}", "status": "RETURN PENDING"}

    def create_return_order(self, order: Order, reference: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return self.get_return_order(f"SR-RET-{reference}", reference)

    def assign_awb(self, shipment_id: str, courier_id: Optional[int] = None, *, is_return: bool = False) -> Dict[str, Any]:
        courier = next((c for c in self.MOCK_COURIERS if c["courier_company_id"] == courier_id), self.MOCK_COURIERS[0])
        awb_random = hashlib.sha256(shipment_id.encode()).hexdigest()[:16].upper() if is_return else random.randint(1000000000, 9999999999)
        prefix = courier["courier_name"][:3].upper()
        awb = f"{prefix}{awb_random}"
        return {
            "awb_code": awb,
            "courier_company_id": courier["courier_company_id"],
            "courier_name": courier["courier_name"],
            "status": "AWB_ASSIGNED",
            "message": f"AWB {awb} assigned via {courier['courier_name']}",
        }

    def request_pickup(self, shipment_id: str) -> Dict[str, Any]:
        return {
            "pickup_status": 1,
            "pickup_scheduled_date": datetime.now(timezone.utc).isoformat(),
            "message": "Pickup scheduled successfully for warehouse slot",
        }

    def generate_label(self, shipment_id: str) -> Dict[str, Any]:
        return {
            "label_url": f"/api/v1/admin/orders/shipping/simulated-label/{shipment_id}",
            "is_simulated": True,
        }

    def generate_manifest(self, shipment_id: str) -> Dict[str, Any]:
        return {
            "manifest_url": f"/api/v1/admin/orders/shipping/simulated-manifest/{shipment_id}",
            "is_simulated": True,
        }

    def get_tracking(self, awb_code: str) -> Dict[str, Any]:
        """Return a payload shaped like the real Shiprocket tracking response.

        Mirrors the live API: a ``tracking_data.shipment_track`` array whose
        entries carry ``date`` / ``status`` / ``activity`` / ``location`` plus the
        courier's ``sr-status`` and ``sr-status-label``. Note the *nested object*
        for ``location`` here, which is how the tracking API really responds —
        ``normalize_location`` flattens it, and this mock is what proves that
        path works end to end.

        Returns an EMPTY scan list. This mock has no courier behind it, so any
        scan it invented would be fiction: it previously hardcoded
        "In Transit - Shipment Received at Facility", which made a parcel still
        sitting in the warehouse (status PICKUP_SCHEDULED, nothing picked up)
        display as in-transit at a Delhi facility with a timestamp of "now".
        A fake scan that contradicts the real status is worse than no scan.

        Scans appear only once something actually reports them — via the
        simulator (which drives the real webhook) or a live Shiprocket webhook.
        """
        return {
            "tracking_data": {
                "track_status": 1,
                "shipment_status": "",
                "shipment_track": [],
            }
        }

    def cancel_shipment(self, shiprocket_order_id: str) -> Dict[str, Any]:
        return {
            "status_code": 200,
            "message": f"Shiprocket order {shiprocket_order_id} cancelled successfully",
        }


class RealShiprocketService(ShippingServiceInterface):
    """
    Live implementation communicating with official Shiprocket v1/external APIs.
    """

    BASE_URL = "https://apiv2.shiprocket.in/v1/external"
    _cached_token: Optional[str] = None
    _token_expiry: Optional[datetime] = None

    def _get_token(self) -> str:
        if self._cached_token and self._token_expiry and datetime.now(timezone.utc) < self._token_expiry:
            return self._cached_token

        if not settings.SHIPROCKET_EMAIL or not settings.SHIPROCKET_PASSWORD:
            raise ValueError("Shiprocket credentials are not configured.")

        resp = httpx.post(
            f"{self.BASE_URL}/auth/login",
            json={"email": settings.SHIPROCKET_EMAIL, "password": settings.SHIPROCKET_PASSWORD},
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise Exception(f"Failed to authenticate with Shiprocket: {resp.text}")

        data = resp.json()
        token = data.get("token")
        if not token:
            raise Exception(f"Shiprocket login returned no token: {resp.text[:500]}")
        self._cached_token = token
        # Cache until just before Shiprocket's ~10-day expiry so every
        # subsequent API call reuses the token instead of re-logging in.
        self._token_expiry = datetime.now(timezone.utc) + TOKEN_TTL
        return self._cached_token

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._get_token()}",
        }

    def _return_get(self, path: str, **params) -> Dict[str, Any]:
        response = httpx.get(f"{self.BASE_URL}/{path}", params=params, headers=self._headers(), timeout=15.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Invalid Shiprocket return lookup response")
        return data

    def get_return_order(self, order_id: str, reference: str) -> Dict[str, Any]:
        data = self._return_get(f"orders/show/{order_id}").get("data")
        if not isinstance(data, dict) or str(data.get("id")) != str(order_id) or str(data.get("channel_order_id")) != reference or data.get("is_return") not in (1, "1"):
            raise ValueError("Shiprocket order is not the matching reverse shipment")
        shipments = data.get("shipments")
        if isinstance(shipments, list) and len(shipments) == 1:
            shipments = shipments[0]
        if not isinstance(shipments, dict) or not shipments.get("id"):
            raise ValueError("Shiprocket return has no unique shipment")
        return {"order_id": str(data["id"]), "shipment_id": str(shipments["id"]),
                "awb_code": shipments.get("awb"), "courier_name": shipments.get("courier"), "status": data.get("status")}

    def find_return_order(self, reference: str) -> Optional[Dict[str, Any]]:
        matches = []
        # `search` is documented as AWB/channel_order_id search. Verify the
        # exact reference and reverse flag, never a substring or forward order.
        for page in range(1, 11):
            result = self._return_get("orders", search=reference, page=page, per_page=100)
            rows = result.get("data")
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ValueError("Invalid Shiprocket return search response")
            matches.extend(row for row in rows if str(row.get("channel_order_id")) == reference)
            pages = result.get("meta", {}).get("pagination", {}).get("total_pages")
            if (pages is not None and page >= int(pages)) or (pages is None and len(rows) < 100):
                break
        else:
            raise ValueError("Shiprocket return search could not be fully reconciled")
        if len(matches) > 1:
            raise ValueError("Multiple Shiprocket orders match this return reference")
        return self.get_return_order(str(matches[0]["id"]), reference) if matches else None

    def create_return_order(self, order: Order, reference: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        # Official return API: customer is pickup; registered warehouse is
        # destination. Return parcels are prepaid even for a collected COD sale.
        try:
            locations = self._return_get("settings/company/pickup")["data"]["shipping_address"]
            warehouses = [row for row in locations if row.get("pickup_location") == settings.SHIPROCKET_PICKUP_LOCATION and row.get("status") in (1, "1")]
            if len(warehouses) != 1:
                raise ValueError("Configure one active Shiprocket pickup location for return delivery")
            warehouse = warehouses[0]
            address, customer = order.shipping_details, order.customer_details
            if address is None:
                raise ValueError("Return purchase has no shipping address")
            names = (getattr(customer, "full_name", None) or "Customer").split()
            seller = (warehouse.get("name") or warehouse["pickup_location"]).split()
            payload = {"order_id": reference, "order_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "pickup_customer_name": names[0], "pickup_last_name": " ".join(names[1:]),
                "pickup_address": address.line1, "pickup_address_2": address.line2 or "",
                "pickup_city": address.city, "pickup_state": address.state, "pickup_country": address.country or default_country(),
                "pickup_pincode": address.postal_code, "pickup_email": getattr(customer, "email", None) or "customer@example.com",
                "pickup_phone": getattr(customer, "phone", None) or FALLBACK_PHONE,
                # The published example leaves this empty for a new customer
                # pickup address. A warehouse ID would select the wrong pickup.
                "pickup_location_id": "",
                "shipping_customer_name": seller[0], "shipping_last_name": " ".join(seller[1:]),
                "shipping_address": warehouse["address"], "shipping_address_2": warehouse.get("address_2") or "",
                "shipping_city": warehouse["city"], "shipping_state": warehouse["state"], "shipping_country": warehouse["country"],
                "shipping_pincode": warehouse["pin_code"], "shipping_email": warehouse["email"], "shipping_phone": warehouse["phone"],
                "order_items": items, "payment_method": "Prepaid", "sub_total": str(sum(Decimal(str(item["selling_price"])) * item["units"] for item in items)),
                "length": DEFAULT_LENGTH_CM, "breadth": DEFAULT_BREADTH_CM, "height": DEFAULT_HEIGHT_CM, "weight": DEFAULT_WEIGHT_KG}
            headers = self._headers()
        except Exception as exc:
            raise ReturnCreationRejected("Check the registered return warehouse and purchase address before retrying") from exc
        response = httpx.post(f"{self.BASE_URL}/orders/create/return", json=payload, headers=headers, timeout=15.0)
        if response.status_code in (400, 401, 403, 404, 405, 422):
            raise ReturnCreationRejected("Shiprocket rejected return creation; check account access and return address/item details")
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or not result.get("order_id") or not result.get("shipment_id"):
            raise ValueError("Shiprocket return creation outcome is unknown")
        return {"order_id": str(result["order_id"]), "shipment_id": str(result["shipment_id"]), "status": result.get("status")}

    def check_serviceability(
        self, pickup_pincode: str, delivery_pincode: str, weight: float, cod: bool
    ) -> List[Dict[str, Any]]:
        params = {
            "pickup_postcode": pickup_pincode,
            "delivery_postcode": delivery_pincode,
            "weight": str(weight),
            "cod": 1 if cod else 0,
        }
        resp = httpx.get(
            f"{self.BASE_URL}/courier/serviceability/",
            params=params,
            headers=self._headers(),
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise Exception(f"Shiprocket serviceability error: {resp.text}")

        data = resp.json()
        couriers = []
        raw_list = data.get("data", {}).get("available_courier_companies", [])
        for c in raw_list:
            couriers.append({
                "courier_company_id": c.get("courier_company_id"),
                "courier_name": c.get("courier_name"),
                "rate": Decimal(str(c.get("rate", 0))),
                "etd": c.get("etd", "N/A"),
                "rating": float(c.get("rating", 0.0)),
                "cod": bool(c.get("cod", 0)),
            })
        return couriers


    def create_order(self, order: Order) -> Dict[str, Any]:
        # NOTE: recipient name/phone live on User, not Address
        # (Address = label/line1/city/state/postal_code/country only).
        # Reading them off Address raises AttributeError and 500s every
        # real dispatch — the Mock never touches addresses, so tests
        # never caught it.
        customer = order.customer_details
        customer_name = (getattr(customer, "full_name", None) or "Customer").strip() or "Customer"
        name_parts = customer_name.split()
        customer_email = (getattr(customer, "email", None) or "customer@example.com")
        customer_phone = (
            getattr(customer, "phone", None) or FALLBACK_PHONE
        )
        shipping = order.shipping_details
        billing = order.billing_details or shipping
        if shipping is None:
            raise ValueError("Order has no shipping address.")

        order_items_payload = []
        # ProductVariant has no weight column today, so every parcel ships
        # at the default weight. When a weight column is added, sum it here.
        total_weight = DEFAULT_WEIGHT_KG
        for it in order.items or []:
            order_items_payload.append({
                "name": it.product_name,
                "sku": it.variant_sku or "SKU-DEFAULT",
                "units": it.quantity,
                "selling_price": str(it.unit_price),
                "discount": "0",
                "tax": "0",
                "hsn": 0,
            })
        if total_weight <= 0:
            total_weight = DEFAULT_WEIGHT_KG

        shipping_is_billing = billing is not None and billing.id == shipping.id
        payload = {
            "order_id": order.order_number,
            "order_date": order.placed_at.strftime("%Y-%m-%d %H:%M"),
            "pickup_location": settings.SHIPROCKET_PICKUP_LOCATION,
            "billing_customer_name": name_parts[0],
            "billing_last_name": " ".join(name_parts[1:]) or name_parts[0],
            "billing_address": billing.line1,
            "billing_address_2": billing.line2 or "",
            "billing_city": billing.city,
            "billing_pincode": billing.postal_code,
            "billing_state": billing.state,
            "billing_country": billing.country or default_country(),
            "billing_email": customer_email,
            "billing_phone": customer_phone,
            "shipping_customer_name": name_parts[0],
            "shipping_last_name": " ".join(name_parts[1:]) or name_parts[0],
            "shipping_address": shipping.line1,
            "shipping_address_2": shipping.line2 or "",
            "shipping_city": shipping.city,
            "shipping_pincode": shipping.postal_code,
            "shipping_state": shipping.state,
            "shipping_country": shipping.country or default_country(),
            "shipping_email": customer_email,
            "shipping_phone": customer_phone,
            "shipping_is_billing": shipping_is_billing,
            "order_items": order_items_payload,
            "payment_method": "COD" if order.payment_method == "cod" else "Prepaid",
            "sub_total": str(order.grand_total),
            "length": DEFAULT_LENGTH_CM,
            "breadth": DEFAULT_BREADTH_CM,
            "height": DEFAULT_HEIGHT_CM,
            "weight": round(total_weight, 2),
        }

        logger.info(
            "Shiprocket create_order order=%s items=%d weight=%s",
            order.order_number, len(order_items_payload), payload["weight"],
        )
        resp = httpx.post(
            f"{self.BASE_URL}/orders/create/adhoc",
            json=payload,
            headers=self._headers(),
            timeout=15.0,
        )
        if resp.status_code not in (200, 201):
            logger.error(
                "Shiprocket create_order failed order=%s status=%s body=%s",
                order.order_number, resp.status_code, resp.text[:1000],
            )
            raise Exception(f"Failed to create order on Shiprocket: {resp.text}")

        res = resp.json()
        logger.info(
            "Shiprocket create_order ok order=%s sr_order=%s shipment=%s",
            order.order_number, res.get("order_id"), res.get("shipment_id"),
        )
        return {
            "order_id": str(res.get("order_id")),
            "shipment_id": str(res.get("shipment_id")),
            "status": res.get("status", "NEW"),
            "status_code": res.get("status_code", 1),
            "message": "Order created on Shiprocket",
        }

    def assign_awb(self, shipment_id: str, courier_id: Optional[int] = None, *, is_return: bool = False) -> Dict[str, Any]:
        # Shiprocket's field is `courier_company_id`; `courier_id` is kept
        # as an accepted alias so callers using either name still work.
        payload: Dict[str, Any] = {"shipment_id": shipment_id}
        if is_return:
            payload["is_return"] = 1
        if courier_id:
            payload["courier_company_id"] = courier_id
            payload["courier_id"] = courier_id

        resp = httpx.post(
            f"{self.BASE_URL}/courier/assign/awb",
            json=payload,
            headers=self._headers(),
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise Exception(f"Failed to assign AWB on Shiprocket: {resp.text}")

        res = resp.json()
        # Shiprocket's assign-AWB response nests under response.data, but fall
        # back to the top level so a documented-but-flat variant still works.
        resp_data = res.get("response", {}).get("data", {}) or res
        awb_code = resp_data.get("awb_code") or res.get("awb_code")
        if not awb_code:
            logger.error(
                "Shiprocket assign_awb returned no awb_code shipment=%s body=%s",
                shipment_id, resp.text[:1000],
            )
            raise Exception(f"Shiprocket assigned no AWB: {resp.text[:500]}")
        return {
            "awb_code": awb_code,
            "courier_company_id": resp_data.get("courier_company_id"),
            "courier_name": resp_data.get("courier_name"),
            "status": "AWB_ASSIGNED",
            "message": "AWB assigned successfully",
        }

    def request_pickup(self, shipment_id: str) -> Dict[str, Any]:
        payload = {"shipment_id": [shipment_id]}
        resp = httpx.post(
            f"{self.BASE_URL}/courier/generate/pickup",
            json=payload,
            headers=self._headers(),
            timeout=15.0,
        )
        if resp.status_code in (400, 401, 403, 404, 405, 422):
            raise PickupRequestRejected("Shiprocket rejected pickup scheduling; check the reverse shipment and courier assignment")
        if resp.status_code != 200:
            raise Exception(f"Failed to request pickup: {resp.text}")
        return resp.json()

    def generate_label(self, shipment_id: str) -> Dict[str, Any]:
        payload = {"shipment_id": [shipment_id]}
        resp = httpx.post(
            f"{self.BASE_URL}/courier/generate/label",
            json=payload,
            headers=self._headers(),
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise Exception(f"Failed to generate label: {resp.text}")
        data = resp.json()
        # Shiprocket returns label_url top-level; keep the nested fallback.
        label_url = (
            data.get("label_url")
            or data.get("response", {}).get("label_url")
            or data.get("data", {}).get("label_url")
        )
        if not label_url:
            logger.error(
                "Shiprocket label missing label_url shipment=%s body=%s",
                shipment_id, resp.text[:1000],
            )
            raise Exception(f"Shiprocket returned no label_url: {resp.text[:500]}")
        return {"label_url": label_url, "is_simulated": False}

    def generate_manifest(self, shipment_id: str) -> Dict[str, Any]:
        payload = {"shipment_id": [shipment_id]}
        resp = httpx.post(
            f"{self.BASE_URL}/manifests/generate",
            json=payload,
            headers=self._headers(),
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise Exception(f"Failed to generate manifest: {resp.text}")
        data = resp.json()
        manifest_url = (
            data.get("manifest_url")
            or data.get("response", {}).get("manifest_url")
            or data.get("data", {}).get("manifest_url")
        )
        if not manifest_url:
            logger.error(
                "Shiprocket manifest missing manifest_url shipment=%s body=%s",
                shipment_id, resp.text[:1000],
            )
            raise Exception(f"Shiprocket returned no manifest_url: {resp.text[:500]}")
        return {"manifest_url": manifest_url, "is_simulated": False}

    def get_tracking(self, awb_code: str) -> Dict[str, Any]:
        resp = httpx.get(
            f"{self.BASE_URL}/courier/track/awb/{awb_code}",
            headers=self._headers(),
            timeout=15.0,
        )
        if resp.status_code != 200:
            raise Exception(f"Failed to fetch tracking: {resp.text}")
        return resp.json()

    def cancel_shipment(self, shiprocket_order_id: str) -> Dict[str, Any]:
        payload = {"ids": [int(shiprocket_order_id) if shiprocket_order_id.isdigit() else shiprocket_order_id]}
        resp = httpx.post(
            f"{self.BASE_URL}/orders/cancel",
            json=payload,
            headers=self._headers(),
            timeout=15.0,
        )
        return resp.json()


class ReturnCreationRejected(ValueError):
    """Definitively not submitted/accepted; safe to retry the same reference."""


class PickupRequestRejected(ValueError):
    """Definitively not accepted; safe to retry pickup scheduling."""


def get_shipping_service() -> ShippingServiceInterface:
    """Factory returning the active shipping provider"""
    if getattr(settings, "SHIPPING_PROVIDER", "simulator").lower() == "shiprocket":
        return RealShiprocketService()
    return MockShiprocketService()

import uuid
from abc import ABC, abstractmethod

from app.models.order import Order
from app.core.config import settings  # 👈 Use settings
from app.core.region import currency_code, provider_compat_error


class PaymentService(ABC):
    """Abstract base class for payment services"""
    requires_refund_reconciliation = True

    def create_refund_safely(self, payment_id, amount, notes, recorded_ids):
        """The gateway is the durable journal when local execution rolls back."""
        if not self.requires_refund_reconciliation:
            return self.create_refund(payment_id, amount, notes)
        state = self.get_charge_refund_state(payment_id)
        if state is None:
            return {"status": "unknown", "error": "Provider refund lookup unavailable"}
        refunds = state.get("refunds", [])
        own = [r for r in refunds if (r.get("receipt") == notes["refund_key"]
               or (r.get("notes") or {}).get("refund_key") == notes["refund_key"])]
        if len(own) > 1:
            return {"status": "unknown", "error": "Multiple gateway refunds match this request"}
        if own:
            from decimal import Decimal
            if Decimal(str(own[0]["amount"])) != Decimal(str(amount)):
                return {"status": "unknown", "error": "Recorded gateway refund amount differs"}
            return {"status": own[0]["status"], "refund_id": own[0]["id"],
                    "amount": own[0]["amount"], "recovered": True}
        accepted = {"processed", "pending", "succeeded", "processing", "requires_action"}
        if any(r.get("status") in accepted and r.get("id") not in recorded_ids for r in refunds):
            return {"status": "unknown", "error": "Unrecorded gateway refund requires reconciliation"}
        return self.create_refund(payment_id, amount, notes)
    
    @abstractmethod
    def create_payment_intent(self, order: Order, payment_method: str = "card", *, idempotency_key=None, currency=None) -> dict:
        pass
    
    @abstractmethod
    def confirm_payment(self, payment_intent_id: str) -> dict:
        pass
    
    @abstractmethod
    def handle_webhook(self, payload: dict, signature: str) -> dict:
        pass
    
    @abstractmethod
    def refund_payment(self, payment_id: str) -> dict:
        pass

    @abstractmethod
    def create_refund(
        self,
        payment_id: str,
        amount: float | None = None,
        notes: dict | None = None,
    ) -> dict:
        """Create a full or partial refund for a payment."""
        pass

    @abstractmethod
    def get_refund_status(self, refund_id: str) -> dict:
        """Fetch the status of a refund."""
        pass

    def get_charge_refund_state(self, payment_id: str) -> dict | None:
        """Provider-side truth for a charge/payment: total already refunded.

        Used to detect money moved OUTSIDE this app (e.g. dashboard refunds)
        when our ledger disagrees with the provider. Returns
        ``{"refunded_total": float, "currency": str, "refunds": [...]}`` or
        None when the provider cannot answer. Base returns None; providers
        with a refunds API override this.
        """
        return None

    def recover_payment_creation(self, order, attempt) -> dict | None:
        """Resolve an ambiguous creation; default refuses to create again."""
        return None

    def get_payment_intent(self, payment_id: str) -> dict | None:
        return None

    def cancel_payment_intent(self, payment_intent_id: str) -> dict:
        """Best-effort cancel of an unpaid provider PaymentIntent.

        Called by the abandoned-order sweep / failure webhooks so funds are
        never captured for an order we already cancelled. Providers without a
        cancel API (Razorpay orders auto-expire) simply skip.
        """
        return {"status": "skipped", "payment_intent_id": payment_intent_id, "is_dummy": False}

    def get_payment_id_for_order(self, razorpay_order_id: str) -> str | None:
        """Resolve the provider payment (pay_xxx) for an order id.

        Base implementation returns None; providers that support it override
        this. Currently only Razorpay implements it.
        """
        return None


class DummyPaymentService(PaymentService):
    """Dummy payment service for testing"""
    
    provider_name = "dummy"
    requires_refund_reconciliation = False

    def create_payment_intent(self, order, payment_method="card", *, idempotency_key=None, currency=None) -> dict:
        payment_id = f"dummy_pay_{idempotency_key or uuid.uuid4().hex[:12]}"
        return {
            "client_secret": f"{payment_id}_secret_dummy",
            "payment_intent_id": payment_id,
            "order_id": str(order.id),
            "amount": float(order.grand_total),
            "currency": currency or currency_code(),
            "is_dummy": True,
            "status": "succeeded",
            "message": "Dummy payment - no real money involved"
        }

    def recover_payment_creation(self, order, attempt):
        return self.create_payment_intent(order, attempt.payment_method,
                                         idempotency_key=attempt.creation_key, currency=attempt.currency)
    
    def confirm_payment(self, payment_intent_id: str) -> dict:
        return {
            "status": "succeeded",
            "payment_intent_id": payment_intent_id,
            "transaction_id": f"dummy_txn_{uuid.uuid4().hex[:12]}",
            "is_dummy": True,
            "message": "Dummy payment confirmed"
        }

    def get_payment_id_for_order(self, razorpay_order_id: str) -> str | None:
        return f"dummy_txn_{uuid.uuid4().hex[:12]}"
    
    def handle_webhook(self, payload, signature: str) -> dict:
        """Dummy webhook handler.

        Reads the event type from the JSON body so local testing can simulate
        any event (payment.succeeded, refund.processed, refund.failed, ...).
        Falls back to ``payment.succeeded`` when no event is provided.
        """
        import json

        body = {}
        if isinstance(payload, str):
            try:
                body = json.loads(payload or "{}")
            except json.JSONDecodeError:
                body = {}
        elif isinstance(payload, dict):
            body = payload

        event_type = body.get("event") or body.get("event_type") or "payment.succeeded"
        result = {
            "event_type": event_type,
            "data": body,
            "is_dummy": True,
        }
        if event_type == "payment.succeeded":
            result["payment_id"] = body.get("payment_intent_id")
            result["transaction_id"] = None
            result["payment_method"] = None
            result["refund_id"] = None
        elif event_type in ("refund.processed", "refund.failed"):
            refund_entity = body.get("refund") or body
            result["refund_id"] = refund_entity.get("id") if isinstance(refund_entity, dict) else None
            result["payment_id"] = refund_entity.get("payment_intent_id") if isinstance(refund_entity, dict) else None
            result["transaction_id"] = None
            result["payment_method"] = None
        return result
    
    def refund_payment(self, payment_id: str) -> dict:
        return {
            "status": "refunded",
            "payment_id": payment_id,
            "is_dummy": True
        }

    def create_refund(
        self,
        payment_id: str,
        amount: float | None = None,
        notes: dict | None = None,
    ) -> dict:
        refund_id = f"dummy_rfnd_{(notes or {}).get('refund_key') or uuid.uuid4().hex[:12]}"
        return {
            "status": "processed",
            "refund_id": refund_id,
            "payment_id": payment_id,
            "amount": float(amount or 0),
            "is_dummy": True,
            "message": "Dummy refund - no real money involved",
        }

    def get_refund_status(self, refund_id: str) -> dict:
        return {
            "refund_id": refund_id,
            "status": "processed",
            "is_dummy": True,
            "message": "Dummy refund status",
        }


def _service_for_provider(provider: str, historical: bool = False) -> PaymentService:
    """Instantiate the PSP for an explicit provider name (no global fallback).

    ``historical`` = routing a payment captured earlier (refunds/reconcile):
    skips the currency-compat gate, since that money was validly captured
    under its own gateway and must still be serviceable after the deployment
    moves on (e.g. Razorpay→Stripe still refunds old Razorpay payments).
    """
    is_production = settings.ENVIRONMENT == "production"

    print(f"Payment Provider requested: {provider}")
    print(f"Environment: {settings.ENVIRONMENT}")

    # Fail fast on gateway/currency combos that cannot settle (e.g. Razorpay
    # with EUR): a 2am provider rejection becomes a loud boot/request error
    # instead. Historical-payment routing is unaffected — each payment row
    # remembers its own (valid-at-the-time) gateway.
    compat_error = None if historical else provider_compat_error(provider)
    if compat_error is not None:
        if is_production:
            raise RuntimeError(compat_error)
        print(f"⚠️ {compat_error} — continuing anyway (non-production)")

    if not provider:
        # No provider configured — a configuration error, never silently pay.
        raise RuntimeError("PAYMENT_PROVIDER is not set")

    if provider == "dummy":
        if is_production:
            raise RuntimeError(
                "PAYMENT_PROVIDER is 'dummy' in production — customers would pay "
                "without any real money being collected. Set it to 'razorpay'."
            )
        print("Using DUMMY payment service")
        return DummyPaymentService()

    elif provider == "razorpay":
        try:
            from app.services.razorpay_service import RazorpayPaymentService
            service = RazorpayPaymentService()
            if hasattr(service, 'is_configured') and service.is_configured:
                print("✅ Using RAZORPAY payment service")
                return service
            if is_production:
                raise RuntimeError(
                    "Razorpay is not configured but ENVIRONMENT=production. "
                    "Refusing to fall back to dummy payments."
                )
            print("⚠️ Razorpay not configured. Falling back to DUMMY.")
            return DummyPaymentService()
        except RuntimeError:
            raise
        except Exception as e:
            if is_production:
                raise RuntimeError(f"Failed to initialize Razorpay: {str(e)}")
            print(f"❌ Error initializing Razorpay: {str(e)}")
            return DummyPaymentService()

    elif provider == "stripe":
        try:
            from app.services.stripe_service import StripePaymentService
            service = StripePaymentService()
            if hasattr(service, 'is_configured') and service.is_configured:
                print("✅ Using STRIPE payment service")
                return service
            if is_production:
                raise RuntimeError(
                    "Stripe is not configured but ENVIRONMENT=production. "
                    "Refusing to fall back to dummy payments."
                )
            print("⚠️ Stripe not configured. Falling back to DUMMY.")
            return DummyPaymentService()
        except RuntimeError:
            raise
        except Exception as e:
            if is_production:
                raise RuntimeError(f"Failed to initialize Stripe: {str(e)}")
            print(f"❌ Error initializing Stripe: {str(e)}")
            return DummyPaymentService()

    else:
        if is_production:
            raise RuntimeError(f"Unknown PAYMENT_PROVIDER: {provider}")
        print(f"Unknown provider: {provider}. Falling back to dummy.")
        return DummyPaymentService()


def get_payment_service(provider: str | None = None) -> PaymentService:
    """Factory function to get payment service.

    ``provider`` overrides the global ``settings.PAYMENT_PROVIDER`` — used by
    per-payment routing. When omitted, the global setting applies (legacy
    behaviour for charge-time paths that have no payment row yet).
    """
    return _service_for_provider(provider or settings.PAYMENT_PROVIDER)


def get_payment_service_for_payment(payment) -> PaymentService:
    """Route to the PSP that actually captured ``payment``.

    The global ``PAYMENT_PROVIDER`` setting only decides which gateway NEW
    checkouts use. A historical payment row remembers its own gateway in
    ``payment.provider`` — refunds / reconcile / status lookups MUST use that,
    otherwise a Razorpay ``order_xxx`` id gets sent to Stripe (``No such
    payment_intent``) or vice versa.

    - razorpay/stripe/dummy → that provider's service (with the usual
      not-configured → dummy fallback outside production).
    - cod → ValueError (no online money to move; callers map to 400).
    - unknown/legacy/empty → today's global default (backwards compatible).
    """
    raw = getattr(payment, "provider", None)
    try:
        from enum import Enum as _Enum
        name = raw.value if isinstance(raw, _Enum) else str(raw or "")
    except Exception:
        name = str(raw or "")
    name = (name or "").strip().lower()

    if name == "cod":
        raise ValueError("Cash on Delivery orders have no online payment to refund")
    if name in ("razorpay", "stripe", "dummy"):
        return _service_for_provider(name, historical=True)
    # Unknown / legacy rows — preserve today's behaviour.
    return get_payment_service()

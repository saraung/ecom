from app.services.payment_service import PaymentService
from app.core.config import settings
from app.core.region import currency_code, from_minor_units, minor_units

# Try to import razorpay
try:
    import razorpay
    RAZORPAY_AVAILABLE = True
except ImportError:
    RAZORPAY_AVAILABLE = False
    print("⚠️ Razorpay not installed. Install with: uv add razorpay")


class RazorpayPaymentService(PaymentService):
    """Razorpay payment service implementation."""
    provider_name = "razorpay"
    
    def __init__(self):
        self.key_id = settings.RAZORPAY_KEY_ID
        self.key_secret = settings.RAZORPAY_KEY_SECRET
        self.webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
        
        print(f"Razorpay Available: {RAZORPAY_AVAILABLE}")
        print(f"Razorpay Key ID: {self.key_id}")
        print(f"Razorpay Key Secret: {'***' if self.key_secret else 'None'}")
        
        if not RAZORPAY_AVAILABLE:
            print("❌ Razorpay library not installed. Falling back to dummy.")
            self.is_configured = False
            return
        
        if not self.key_id or not self.key_secret:
            print("❌ Razorpay keys not set. Falling back to dummy.")
            self.is_configured = False
            return
        
        self.is_configured = True
        try:
            self.client = razorpay.Client(auth=(self.key_id, self.key_secret))
            print(f"✅ Razorpay initialized with key: {self.key_id[:10]}...")
        except Exception as e:
            print(f"❌ Razorpay initialization failed: {str(e)}")
            self.is_configured = False

    def _production_raise(self, message):
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(message)
        return None
    
    def create_payment_intent(self, order, payment_method="card", *, idempotency_key=None, currency=None):
        """Create Razorpay order"""
        if not self.is_configured:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Razorpay is not configured but ENVIRONMENT=production. No dummy fallback.")
            from app.services.payment_service import DummyPaymentService
            print("⚠️ Using dummy payment (Razorpay not configured)")
            if idempotency_key:
                raise RuntimeError("Recorded Razorpay provider is unavailable")
            return DummyPaymentService().create_payment_intent(order, payment_method)
        
        try:
            amount_in_minor = minor_units(order.grand_total, currency=currency)

            razorpay_order = self.client.order.create({
                "amount": amount_in_minor,
                "currency": currency or currency_code(),
                "receipt": idempotency_key or order.order_number,
                "payment_capture": 1,
                "notes": {
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                }
            })
            
            print(f"✅ Razorpay order created: {razorpay_order['id']}")
            
            return {
                "client_secret": razorpay_order["id"],
                "payment_intent_id": razorpay_order["id"],
                "order_id": str(order.id),
                "amount": float(order.grand_total),
                "currency": currency or currency_code(),
                "is_dummy": False,
                "razorpay_order": razorpay_order,
            }
        except Exception as e:
            print(f"❌ Razorpay order creation failed: {str(e)}")
            if settings.ENVIRONMENT == "production" or idempotency_key:
                raise RuntimeError(f"Razorpay order creation failed: {str(e)}")
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().create_payment_intent(order, payment_method)

    def recover_payment_creation(self, order, attempt):
        # Razorpay exposes receipt filtering. A missing match is NOT evidence
        # that a timed-out POST failed: never issue another POST here.
        result = self.client.order.all({"receipt": attempt.creation_key, "count": 100})
        matches = [item for item in result.get("items", []) if item.get("receipt") == attempt.creation_key]
        if len(matches) != 1:
            return None
        remote = matches[0]
        return {"client_secret": remote["id"], "payment_intent_id": remote["id"],
                "order_id": str(order.id),
                "amount": from_minor_units(remote["amount"], currency=remote["currency"]),
                "currency": remote["currency"], "is_dummy": False}
    
    def confirm_payment(self, payment_intent_id):
        """Fetch Razorpay order status"""
        if not self.is_configured:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Razorpay is not configured but ENVIRONMENT=production. No dummy fallback.")
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().confirm_payment(payment_intent_id)
        
        try:
            order = self.client.order.fetch(payment_intent_id)
            if order["status"] == "paid":
                # The real instrument (card/upi/netbanking/wallet) was chosen
                # inside Razorpay's modal — read it back from the payment
                method = None
                try:
                    pays = self.client.order.payments(payment_intent_id)
                    items = pays.get("items", []) if isinstance(pays, dict) else (pays or [])
                    for p in items:
                        if p.get("status") in ("captured", "authorized"):
                            method = p.get("method")
                            break
                except Exception as pe:
                    print(f"⚠️ Could not read payment method from Razorpay: {pe}")
                return {"status": "succeeded", "payment_intent_id": payment_intent_id, "is_dummy": False, "method": method}
            elif order["status"] == "created":
                return {"status": "pending", "payment_intent_id": payment_intent_id, "is_dummy": False}
            else:
                return {"status": "failed", "payment_intent_id": payment_intent_id, "is_dummy": False}
        except Exception as e:
            print(f"❌ Razorpay order fetch failed: {str(e)}")
            return {"status": "failed", "payment_intent_id": payment_intent_id, "is_dummy": False, "error": str(e)}
    
    def handle_webhook(self, payload, signature):
        """Handle Razorpay webhook. `payload` must be the RAW request body (str)."""
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().handle_webhook(payload, signature)
        
        # Razorpay signs the raw body with HMAC-SHA256 -> sent in X-Razorpay-Signature
        if not self.webhook_secret:
            # Never accept unverified webhooks — a missing secret is a
            # misconfiguration, not a reason to process the event.
            print("❌ RAZORPAY_WEBHOOK_SECRET not set — rejecting unverified webhook")
            return {"event_type": "invalid_signature", "data": {}, "is_dummy": False}
        if not signature:
            print("❌ Webhook rejected: missing X-Razorpay-Signature header")
            return {"event_type": "invalid_signature", "data": {}, "is_dummy": False}
        try:
            self.client.utility.verify_webhook_signature(payload, signature, self.webhook_secret)
        except Exception as e:
            print(f"❌ Razorpay webhook signature verification failed: {str(e)}")
            return {"event_type": "invalid_signature", "data": {}, "is_dummy": False, "error": str(e)}
        
        try:
            import json
            event = json.loads(payload)
            return self._normalize_event(event.get("event"), event.get("payload", {}))
        except Exception as e:
            print(f"❌ Razorpay webhook payload parse failed: {str(e)}")
            return {"event_type": "invalid", "data": {}, "is_dummy": False, "error": str(e)}

    def _normalize_event(self, event_type, payload) -> dict:
        """Map a Razorpay event into the shared normalized webhook schema."""
        if event_type in ("payment.captured", "order.paid"):
            order_entity = (payload.get("order") or {}).get("entity") or {}
            pay_entity = (payload.get("payment") or {}).get("entity") or {}
            order_id = order_entity.get("id") or pay_entity.get("order_id")
            return {
                "event_type": "payment.succeeded",
                "payment_id": order_id,
                "transaction_id": pay_entity.get("id"),
                "payment_method": pay_entity.get("method"),
                "refund_id": None,
                "is_dummy": False,
                "data": payload,
            }

        if event_type in ("refund.processed", "refund.failed"):
            refund_entity = (payload.get("refund") or {}).get("entity") or {}
            return {
                "event_type": event_type,
                "payment_id": refund_entity.get("payment_id"),
                "transaction_id": None,
                "payment_method": None,
                "refund_id": refund_entity.get("id"),
                "is_dummy": False,
                "data": payload,
            }

        # Failed payment → webhooks.py cancels the unpaid order & restocks
        if event_type in ("payment.failed", "order.payment.failed"):
            pay_entity = (payload.get("payment") or {}).get("entity") or {}
            order_entity = (payload.get("order") or {}).get("entity") or {}
            return {
                "event_type": "payment.failed",
                "payment_id": pay_entity.get("order_id") or order_entity.get("id"),
                "transaction_id": pay_entity.get("id"),
                "payment_method": pay_entity.get("method"),
                "refund_id": None,
                "is_dummy": False,
                "data": payload,
            }

        # Any other event — acknowledged, no action
        return {
            "event_type": event_type or "unknown",
            "payment_id": None,
            "transaction_id": None,
            "payment_method": None,
            "refund_id": None,
            "is_dummy": False,
            "data": payload,
        }
    
    def refund_payment(self, payment_id):
        """Refund Razorpay payment"""
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().refund_payment(payment_id)

        try:
            refund = self.client.payment.refund(payment_id)
            return {"status": "refunded", "refund_id": refund["id"], "payment_id": payment_id, "is_dummy": False}
        except Exception as e:
            print(f"❌ Razorpay refund failed: {str(e)}")
            return {"status": "failed", "payment_id": payment_id, "is_dummy": False, "error": str(e)}

    def create_refund(self, payment_id, amount=None, notes=None):
        """
        Create a full or partial refund for a Razorpay payment.

        - payment_id: the Razorpay payment ID (pay_xxx) — NOT the order ID
        - amount:     amount in the configured currency (full units).
                      None = full refund
        - notes:      dict of notes stored against the refund
        """
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            print("⚠️ Using dummy refund (Razorpay not configured)")
            return DummyPaymentService().create_refund(payment_id, amount, notes)

        try:
            payload = {}
            if amount is not None:
                # Provider minor units (paise normally, whole units for
                # zero-decimal currencies).
                payload["amount"] = minor_units(amount)
            if notes:
                payload["notes"] = {k: str(v) for k, v in notes.items()}
                if notes.get("refund_key"):
                    payload["receipt"] = notes["refund_key"]

            refund = self.client.payment.refund(payment_id, payload)
            print(f"✅ Razorpay refund created: {refund['id']} (status: {refund.get('status')})")

            return {
                "status": refund.get("status"),  # processed | pending | failed
                "refund_id": refund["id"],
                "payment_id": payment_id,
                "amount": from_minor_units(refund.get("amount")),
                "is_dummy": False,
            }
        except Exception as e:
            print(f"❌ Razorpay refund failed: {str(e)}")
            # Transport/server errors do not prove that no money moved.
            definite = (isinstance(e, razorpay.errors.BadRequestError)
                        and not any(word in str(e).lower() for word in ("duplicate", "in progress")))
            return {"status": "failed" if definite else "unknown", "payment_id": payment_id,
                    "is_dummy": False, "error": str(e)}

    def get_charge_refund_state(self, payment_id: str) -> dict | None:
        """Refunded totals straight from Razorpay (catches dashboard-side refunds)."""
        if not self.is_configured:
            return None
        try:
            items = []
            skip = 0
            while True:
                page = self.client.payment.fetch_multiple_refund(payment_id, {"count": 100, "skip": skip}).get("items", [])
                items.extend(page)
                if len(page) < 100:
                    break
                skip += len(page)
            refunds = [
                {
                    "id": r.get("id"),
                    "amount": from_minor_units(r.get("amount"), currency=r.get("currency")),
                    "status": r.get("status", "unknown"),
                    "receipt": r.get("receipt"),
                    "notes": r.get("notes") if isinstance(r.get("notes"), dict) else {},
                }
                for r in items
            ]
            succeeded = [r for r in refunds if r["status"] in ("processed",)]
            payment = self.client.payment.fetch(payment_id)
            return {
                "charge_id": payment_id,
                "charge_total": from_minor_units(payment.get("amount")),
                "currency": str(payment.get("currency") or "").upper(),
                "refunded_total": round(sum(r["amount"] for r in succeeded), 2),
                "refunds": refunds,
            }
        except Exception as e:
            print(f"⚠️ Could not fetch Razorpay refund state for {payment_id}: {e}")
            return None

    def get_refund_status(self, refund_id):
        """Fetch a refund from Razorpay by its refund ID (rfnd_xxx)."""
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().get_refund_status(refund_id)

        try:
            refund = self.client.refund.fetch(refund_id)
            return {
                "refund_id": refund["id"],
                "payment_id": refund.get("payment_id"),
                "amount": from_minor_units(refund.get("amount")),
                "status": refund.get("status"),  # processed | pending | failed
                "is_dummy": False,
            }
        except Exception as e:
            print(f"❌ Razorpay refund fetch failed: {str(e)}")
            return {"status": "failed", "refund_id": refund_id, "is_dummy": False, "error": str(e)}

    def get_payment_id_for_order(self, razorpay_order_id):
        """
        Resolve the actual payment ID (pay_xxx) for a Razorpay order ID
        (order_xxx) by listing the order's payments. Returns None if the
        order has no captured/authorized payment.
        """
        if not self.is_configured:
            return None

        try:
            pays = self.client.order.payments(razorpay_order_id)
            items = pays.get("items", []) if isinstance(pays, dict) else (pays or [])
            for p in items:
                if p.get("status") in ("captured", "authorized"):
                    return p.get("id")
        except Exception as e:
            print(f"⚠️ Could not fetch payments for Razorpay order {razorpay_order_id}: {e}")
        return None

    def cancel_payment_intent(self, payment_intent_id: str) -> dict:
        """Razorpay has no public "cancel order" API — unpaid orders expire on
        their side and raise payment.failed webhooks. Nothing to do here."""
        return {"status": "skipped", "payment_intent_id": payment_intent_id, "is_dummy": False}

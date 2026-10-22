from app.services.payment_service import PaymentService
from app.core.config import settings
from app.core.region import from_minor_units, minor_units

# Try to import stripe
try:
    import stripe
    STRIPE_AVAILABLE = True
except ImportError:
    STRIPE_AVAILABLE = False
    print("⚠️ Stripe not installed. Install with: uv add stripe")


class StripePaymentService(PaymentService):
    """Stripe payment service implementation."""
    provider_name = "stripe"

    @staticmethod
    def _get(obj, key, default=None):
        """Read a field from a Stripe object/dict without knowing its access style."""
        if obj is None:
            return default
        try:
            return obj[key]
        except (KeyError, TypeError, IndexError):
            return getattr(obj, key, default)

    def __init__(self):
        self.secret_key = settings.STRIPE_SECRET_KEY
        self.publishable_key = settings.STRIPE_PUBLISHABLE_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self.currency = (settings.PAYMENT_CURRENCY or "INR").lower()

        print(f"Stripe Available: {STRIPE_AVAILABLE}")
        print(f"Stripe Secret Key: {'***' if self.secret_key else 'None'}")
        print(f"Stripe Webhook Secret: {'***' if self.webhook_secret else 'None'}")

        if not STRIPE_AVAILABLE:
            print("❌ Stripe library not installed. Falling back to dummy.")
            self.is_configured = False
            return

        if not self.secret_key:
            print("❌ Stripe secret key not set. Falling back to dummy.")
            self.is_configured = False
            return

        self.is_configured = True
        try:
            stripe.api_key = self.secret_key
            print(f"✅ Stripe initialized with key: {self.secret_key[:7]}...")
        except Exception as e:
            print(f"❌ Stripe initialization failed: {str(e)}")
            self.is_configured = False

    def _production_raise(self, message):
        if settings.ENVIRONMENT == "production":
            raise RuntimeError(message)
        return None

    def _amount_in_smallest_unit(self, amount) -> int:
        """Provider minor units via the regional helper (cents normally,
        whole units for zero-decimal currencies like JPY — where ×100
        would overcharge 100×)."""
        return minor_units(amount)

    def create_payment_intent(self, order, payment_method="card", *, idempotency_key=None, currency=None):
        """Create a Stripe PaymentIntent."""
        if not self.is_configured:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Stripe is not configured but ENVIRONMENT=production. No dummy fallback.")
            from app.services.payment_service import DummyPaymentService
            print("⚠️ Using dummy payment (Stripe not configured)")
            if idempotency_key:
                raise RuntimeError("Recorded Stripe provider is unavailable")
            return DummyPaymentService().create_payment_intent(order, payment_method)

        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=minor_units(order.grand_total, currency=currency),
                currency=(currency or self.currency).lower(),
                automatic_payment_methods={"enabled": True},
                metadata={
                    "order_id": str(order.id),
                    "order_number": order.order_number,
                    **({"creation_key": idempotency_key} if idempotency_key else {}),
                },
                **({"idempotency_key": idempotency_key} if idempotency_key else {}),
            )

            print(f"✅ Stripe PaymentIntent created: {payment_intent['id']}")

            return {
                "client_secret": payment_intent.client_secret,
                "payment_intent_id": payment_intent.id,
                "order_id": str(order.id),
                "amount": float(order.grand_total),
                "currency": payment_intent.currency.upper(),
                "is_dummy": False,
                "payment_intent": payment_intent,
            }
        except Exception as e:
            print(f"❌ Stripe PaymentIntent creation failed: {str(e)}")
            if settings.ENVIRONMENT == "production" or idempotency_key:
                raise RuntimeError(f"Stripe PaymentIntent creation failed: {str(e)}")
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().create_payment_intent(order, payment_method)

    def recover_payment_creation(self, order, attempt):
        from datetime import datetime, timedelta, timezone
        created = attempt.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        # Stripe may prune idempotency keys after 24h. Beyond that window,
        # recovery must be read-only rather than risk recreating a charge.
        if created < datetime.now(timezone.utc) - timedelta(hours=20):
            result = stripe.PaymentIntent.search(query=f"metadata['creation_key']:'{attempt.creation_key}'")
            matches = list(self._get(result, "data", []))
            if len(matches) != 1:
                return None
            remote = matches[0]
            return self._creation_response(remote, order.id)
        return self.create_payment_intent(order, attempt.payment_method,
                                         idempotency_key=attempt.creation_key, currency=attempt.currency)

    def _creation_response(self, intent, order_id):
        currency = self._get(intent, "currency").upper()
        return {"client_secret": self._get(intent, "client_secret"),
                "payment_intent_id": self._get(intent, "id"), "order_id": str(order_id),
                "amount": from_minor_units(
                    self._get(intent, "amount"), currency=currency), "currency": currency, "is_dummy": False}

    def get_payment_intent(self, payment_id):
        intent = stripe.PaymentIntent.retrieve(payment_id)
        return {"client_secret": self._get(intent, "client_secret")}

    def confirm_payment(self, payment_intent_id):
        """Fetch Stripe PaymentIntent status."""
        if not self.is_configured:
            if settings.ENVIRONMENT == "production":
                raise RuntimeError("Stripe is not configured but ENVIRONMENT=production. No dummy fallback.")
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().confirm_payment(payment_intent_id)

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            method = None
            pm_id = self._get(intent, "payment_method")
            if pm_id:
                try:
                    pm = stripe.PaymentMethod.retrieve(pm_id)
                    method = self._get(pm, "type")
                except Exception as pe:
                    print(f"⚠️ Could not read payment method from Stripe: {pe}")
            status = self._get(intent, "status")
            if status == "succeeded":
                return {"status": "succeeded", "payment_intent_id": payment_intent_id, "is_dummy": False, "method": method}
            elif status in ("processing", "requires_action", "requires_confirmation", "requires_capture"):
                return {"status": "pending", "payment_intent_id": payment_intent_id, "is_dummy": False}
            else:
                error = self._get(intent, "last_payment_error") or {}
                return {"status": "failed", "payment_intent_id": payment_intent_id, "is_dummy": False,
                        "error": self._get(error, "message")}
        except Exception as e:
            print(f"❌ Stripe PaymentIntent fetch failed: {str(e)}")
            return {"status": "failed", "payment_intent_id": payment_intent_id, "is_dummy": False, "error": str(e)}

    def handle_webhook(self, payload, signature):
        """Handle Stripe webhook. `payload` must be the RAW request body (str)."""
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().handle_webhook(payload, signature)

        if not self.webhook_secret:
            print("❌ STRIPE_WEBHOOK_SECRET not set — rejecting unverified webhook")
            return {"event_type": "invalid_signature", "data": {}, "is_dummy": False}
        if not signature:
            print("❌ Webhook rejected: missing Stripe-Signature header")
            return {"event_type": "invalid_signature", "data": {}, "is_dummy": False}
        try:
            event = stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
        except Exception as e:
            print(f"❌ Stripe webhook signature verification failed: {str(e)}")
            return {"event_type": "invalid_signature", "data": {}, "is_dummy": False, "error": str(e)}

        return self._normalize_event(event)

    def _normalize_event(self, event) -> dict:
        """Map a Stripe event into the shared normalized webhook schema."""
        g = self._get
        event_type = g(event, "type", "unknown")
        data = {}
        try:
            data = g(event, "data") or {}
            data = g(data, "object") or {}
        except Exception:
            data = {}

        if event_type == "payment_intent.succeeded":
            transaction_id = None
            latest_charge = g(data, "latest_charge")
            if latest_charge:
                try:
                    transaction_id = latest_charge if isinstance(latest_charge, str) else g(latest_charge, "id")
                except Exception:
                    transaction_id = None
            payment_method_types = g(data, "payment_method_types") or []
            return {
                "event_type": "payment.succeeded",
                "payment_id": g(data, "id"),
                "transaction_id": transaction_id,
                "payment_method": payment_method_types[0] if payment_method_types and isinstance(payment_method_types, list) else None,
                "refund_id": None,
                "is_dummy": False,
                "data": data,
            }

        if event_type == "charge.refunded":
            refunds = g(g(data, "refunds") or {}, "data") or []
            last = refunds[-1] if refunds else {}
            status = g(last, "status")
            return {
                "event_type": self._refund_event_type(status),
                "payment_id": g(data, "payment_intent"),
                "transaction_id": None,
                "payment_method": None,
                "refund_id": g(last, "id"),
                "is_dummy": False,
                "data": data,
            }

        if event_type == "refund.updated":
            status = g(data, "status")
            return {
                "event_type": self._refund_event_type(status),
                "payment_id": g(data, "payment_intent"),
                "transaction_id": None,
                "payment_method": None,
                "refund_id": g(data, "id"),
                "is_dummy": False,
                "data": data,
            }

        # Abandoned / failed intents → webhooks.py cancels the unpaid order & restocks
        if event_type in ("payment_intent.canceled", "payment_intent.payment_failed"):
            return {
                "event_type": "payment.cancelled" if event_type == "payment_intent.canceled" else "payment.failed",
                "payment_id": g(data, "id"),
                "transaction_id": None,
                "payment_method": None,
                "refund_id": None,
                "is_dummy": False,
                "data": data,
            }

        # Any other event — acknowledged, no action
        return {
            "event_type": "unknown",
            "payment_id": g(data, "id"),
            "transaction_id": None,
            "payment_method": None,
            "refund_id": None,
            "is_dummy": False,
            "data": data,
        }

    @staticmethod
    def _refund_event_type(status):
        if status == "succeeded":
            return "refund.processed"
        if status in ("failed", "canceled"):
            return "refund.failed"
        return "refund.pending"

    def refund_payment(self, payment_id):
        """Refund Stripe payment."""
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().refund_payment(payment_id)

        try:
            refund = stripe.Refund.create(payment_intent=payment_id)
            return {
                "status": "refunded" if refund.status == "succeeded" else refund.status,
                "refund_id": refund.id,
                "payment_id": payment_id,
                "is_dummy": False,
            }
        except Exception as e:
            print(f"❌ Stripe refund failed: {str(e)}")
            return {"status": "failed", "payment_id": payment_id, "is_dummy": False, "error": str(e)}

    def create_refund(self, payment_id, amount=None, notes=None):
        """
        Create a full or partial refund for a Stripe payment.

        - payment_id: the Stripe PaymentIntent ID (pi_xxx) or Charge ID (ch_xxx)
        - amount:     amount in the configured currency (full unit). None = full refund
        - notes:      dict of notes stored against the refund
        """
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            print("⚠️ Using dummy refund (Stripe not configured)")
            return DummyPaymentService().create_refund(payment_id, amount, notes)

        try:
            params = {}
            if amount is not None:
                params["amount"] = self._amount_in_smallest_unit(amount)
            if notes:
                params["metadata"] = {k: str(v) for k, v in notes.items()}

            # Stripe refunds accept exactly one of `payment_intent` (pi_xxx)
            # or `charge` (ch_xxx). Prefer whichever id is stored on the order:
            # `provider_payment_intent` holds a pi_xxx after /payments/confirm
            # but a ch_xxx when the order was settled by the webhook.
            if payment_id.startswith("ch_"):
                params["charge"] = payment_id
            else:
                params["payment_intent"] = payment_id

            refund = stripe.Refund.create(**params,
                **({"idempotency_key": notes["refund_key"]} if notes and notes.get("refund_key") else {}))
            created_status = getattr(refund, "status", "pending")
            print(f"✅ Stripe refund created: {refund.id} (status: {created_status})")

            return {
                "status": created_status,  # succeeded | pending | processing | requires_action | failed
                "refund_id": refund.id,
                "payment_id": payment_id,
                "amount": from_minor_units(refund.amount),
                "is_dummy": False,
            }
        except Exception as e:
            print(f"❌ Stripe refund failed: {str(e)}")
            definite = isinstance(e, stripe.InvalidRequestError)
            return {"status": "failed" if definite else "unknown", "payment_id": payment_id,
                    "is_dummy": False, "error": str(e)}

    def get_refund_status(self, refund_id):
        """Fetch a refund from Stripe by its refund ID (re_xxx)."""
        if not self.is_configured:
            from app.services.payment_service import DummyPaymentService
            return DummyPaymentService().get_refund_status(refund_id)

        try:
            refund = stripe.Refund.retrieve(refund_id)
            return {
                "refund_id": refund.id,
                "payment_id": refund.payment_intent,
                "amount": from_minor_units(refund.amount),
                "status": getattr(refund, "status", "pending"),  # succeeded | pending | processing | requires_action | failed
                "is_dummy": False,
            }
        except Exception as e:
            print(f"❌ Stripe refund fetch failed: {str(e)}")
            return {"status": "failed", "refund_id": refund_id, "is_dummy": False, "error": str(e)}

    def get_charge_refund_state(self, payment_id: str) -> dict | None:
        """Refunded totals straight from Stripe (catches dashboard-side refunds)."""
        if not self.is_configured:
            return None
        try:
            pid = payment_id or ""
            charge_id = pid
            if pid.startswith("pi_"):
                charge_id = self.get_payment_id_for_order(pid)
                if not charge_id:
                    return None
            charge = stripe.Charge.retrieve(charge_id)
            refunds = []
            for r in stripe.Refund.list(charge=charge_id, limit=100).auto_paging_iter():
                refunds.append({
                    "id": r.id,
                    "amount": from_minor_units(r.amount, currency=charge.currency),
                    "status": getattr(r, "status", "unknown"),
                    "notes": dict(getattr(r, "metadata", {}) or {}),
                })
            succeeded = [r for r in refunds if r["status"] in ("succeeded",)]
            return {
                "charge_id": charge.id,
                "charge_total": from_minor_units(charge.amount),
                "currency": str(charge.currency or "").upper(),
                "refunded_total": round(sum(r["amount"] for r in succeeded), 2),
                "refunds": refunds,
            }
        except Exception as e:
            print(f"⚠️ Could not fetch Stripe refund state for {payment_id}: {e}")
            return None

    def get_payment_id_for_order(self, payment_intent_id):
        """
        Resolve the actual Charge ID (ch_xxx) for a Stripe PaymentIntent
        (pi_xxx). Returns None if the intent has no successful charge.
        """
        if not self.is_configured:
            return None
    
        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            latest_charge = self._get(intent, "latest_charge")
            if latest_charge:
                return latest_charge if isinstance(latest_charge, str) else self._get(latest_charge, "id")
        except Exception as e:
            print(f"⚠️ Could not fetch charge for Stripe PaymentIntent {payment_intent_id}: {e}")
        return None

    def cancel_payment_intent(self, payment_intent_id):
        """Cancel an unpaid Stripe PaymentIntent (abandoned-order sweep)."""
        if not self.is_configured:
            return {"status": "skipped", "payment_intent_id": payment_intent_id, "is_dummy": False}

        try:
            intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            status = self._get(intent, "status")
            if status in ("requires_payment_method", "requires_confirmation", "requires_action", "requires_capture", "processing"):
                canceled = stripe.PaymentIntent.cancel(payment_intent_id)
                print(f"🗑️ Stripe PaymentIntent {payment_intent_id} cancelled (was {status})")
                return {"status": self._get(canceled, "status"), "payment_intent_id": payment_intent_id, "is_dummy": False}
            print(f"ℹ️ Skipped cancelling Stripe PaymentIntent {payment_intent_id} — status {status}")
            return {"status": "skipped", "payment_intent_id": payment_intent_id, "is_dummy": False}
        except Exception as e:
            print(f"❌ Stripe cancel failed: {e}")
            return {"status": "failed", "payment_intent_id": payment_intent_id, "is_dummy": False, "error": str(e)}

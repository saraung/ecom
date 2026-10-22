// src/components/orders/CancelOrderModal.jsx
import { useState, useEffect, useRef } from 'react';
import { AlertTriangle, CheckCircle2, RefreshCw, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { orderAPI } from '../../api/orders';
import { formatPrice, getRestockingFeePercentage } from '../../utils/format';
import { useModalA11y } from '../../hooks/useModalA11y';
import RefundBadge from './RefundBadge';

// ✅ Quick-pick reasons for POST /orders/{id}/cancel — the string is stored on the order
const QUICK_REASONS = [
  'Changed my mind',
  'Ordered by mistake',
  'Found a better price',
  'Delivery takes too long',
  'Duplicate order',
];

// ✅ Confirmation modal for cancelling an order (+ automatic refund for paid online orders).
//
//    props:
//      order       — order object (must have id, order_number, payment_status, grand_total)
//      onClose     — called when the user closes the modal
//      onCancelled — optional callback fired right after the backend confirms the
//                    cancellation (so the parent can silently refresh the order/list)
//
//    On success the modal switches to a confirmation view showing the refund summary —
//    refund amount (net of the applicable restocking fee — 5% for confirmed paid orders,
//    15% for processing), refund id and the live refund phase from the backend
//    (refund_initiated / refund_completed / refund_failed).
//    The success view auto-dismisses after a few seconds; the Done button closes immediately.
const CancelOrderModal = ({ order, onClose, onCancelled }) => {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null); // { message, refund|null } once cancelled
  const [countdown, setCountdown] = useState(0); // seconds left before the success view auto-closes

  // Escape closes, focus is trapped/restored, background scroll locked.
  const dialogRef = useModalA11y(onClose);

  // Only paid-online orders go through the refund flow inside cancel — COD/unpaid are just cancelled.
  // Restocking fee (%) the customer will see deducted — 5% confirmed/pending, 15% processing.
  const feePercent = getRestockingFeePercentage(order);

  // ✅ Number of seconds the success view stays visible before the modal auto-closes.
  const AUTO_CLOSE_SECONDS = 4;
  // Keep a ref to the latest onClose so the auto-close effect can call it without
  // restarting the timer when the parent re-renders (e.g. after the silent refetch).
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose; // sync on every render — never mutate a ref during render
  });
  useEffect(() => {
    if (!result) return;
    const timer = setInterval(() => {
      setCountdown((prev) => (prev > 1 ? prev - 1 : 0));
    }, 1000);
    const timeout = setTimeout(() => {
      clearInterval(timer);
      onCloseRef.current(); // auto-dismiss the modal after a successful cancellation
    }, AUTO_CLOSE_SECONDS * 1000);
    return () => {
      clearInterval(timer);
      clearTimeout(timeout);
    };
  }, [result]);

  const handleSubmit = async (e) => {
    e?.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      toast.error('Please select or enter a reason for cancellation');
      return;
    }

    try {
      setSubmitting(true);
      const response = await orderAPI.cancelOrder(order.id, trimmed);
      const data = response.data || {};
      const refund = data.refund || null;

      setResult({ message: data.message || 'Order cancelled successfully', refund });
      setCountdown(AUTO_CLOSE_SECONDS); // seed the live countdown so the Done button shows it immediately
      toast.success(
        refund?.amount != null
          ? `Order cancelled ✅ — ${formatPrice(refund.amount)} refund initiated.`
          : data.message || 'Order cancelled successfully'
      );
      if (onCancelled) onCancelled(data);
    } catch (err) {
      console.error('Error cancelling order:', err);
      // ✅ FastAPI error bodies: 400 → {detail: "…"}, 403 → {detail: "Not authorized"},
      //    404 → {detail: "Order not found"}, 422 → [{loc, msg, type}, …]
      const detail = err.response?.data?.detail;
      const message =
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail) && detail[0]?.msg
            ? detail[0].msg
            : 'Could not cancel this order right now. Please try again.';
      toast.error(message);
    } finally {
      setSubmitting(false);
    }
  };

  // ————————————— Success view — refund summary straight from the cancel response —————
  if (result) {
    const { refund } = result;
    return (
      <div className="fixed inset-0 bg-primary/50 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label="Order cancelled"
          className="bg-card rounded-2xl shadow-2xl max-w-md w-full p-6"
        >
          <div className="text-center">
            <div className="w-14 h-14 rounded-full tint-success flex items-center justify-center mx-auto mb-3">
              <CheckCircle2 size={28} className="text-success" />
            </div>
            <h3 className="text-xl font-bold text-foreground">Order Cancelled</h3>
            <p className="text-sm text-muted-foreground mt-1">{result.message}</p>
          </div>

          {refund ? (
            <div className="mt-5 bg-background rounded-xl p-4 space-y-2.5">
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Refund status</span>
                <RefundBadge paymentStatus={refund.payment_status} />
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Refund Amount</span>
                <span className="font-medium text-foreground">{formatPrice(refund.amount)}</span>
              </div>
              {Number(refund.restocking_fee) > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">
                    Restocking Fee ({refund.fee_percentage ?? feePercent}%)
                  </span>
                  <span className="font-medium text-foreground">
                    −{formatPrice(refund.restocking_fee)}
                  </span>
                </div>
              )}
              {refund.message && (
                <p className="text-xs text-muted-foreground border-t border-border pt-2.5">
                  {refund.message}
                </p>
              )}
              {refund.refund_id && (
                <p className="text-xs text-muted-foreground">Refund ID: {refund.refund_id}</p>
              )}
            </div>
          ) : (
            <p className="mt-5 text-sm text-muted-foreground bg-background rounded-xl p-4">
              No payment was processed for this order, so no refund applies.
            </p>
          )}

          <button
            type="button"
            onClick={onClose}
            className="mt-5 w-full bg-primary text-primary-foreground px-4 py-2.5 rounded-xl hover:bg-primary-hover transition font-medium"
          >
            Done{countdown > 0 ? ` (auto-closes in ${countdown}s)` : ''}
          </button>
        </div>
      </div>
    );
  }

  // ————————————— Confirm + reason form —————————————
  return (
      <div className="fixed inset-0 bg-primary/50 backdrop-blur-sm flex items-center justify-center z-50 p-4 animate-fade-in">
        <div
          ref={dialogRef}
          role="dialog"
          aria-modal="true"
          aria-label="Cancel order"
          className="bg-card rounded-2xl shadow-2xl max-w-md w-full p-6"
        >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-xl font-bold text-foreground">Cancel Order</h3>
            <p className="text-sm text-muted-foreground mt-0.5">Order {order.order_number}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-muted transition"
            aria-label="Close"
          >
            <X size={24} className="text-muted-foreground" />
          </button>
        </div>

        <div className="mt-4 alert-warning rounded-xl p-4 flex gap-3">
          <AlertTriangle size={18} className="text-warning flex-shrink-0 mt-0.5" />
          <p className="text-sm">
            This action cannot be undone.
            {feePercent > 0
              ? ` A ${feePercent}% restocking fee will be applied and your refund will be initiated automatically.`
              : ' No payment was captured for this order, so it will be cancelled immediately.'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-3">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">
              Reason for cancellation <span className="text-destructive">*</span>
            </label>
            <div className="flex flex-wrap gap-2 mb-3">
              {QUICK_REASONS.map((quick) => (
                <button
                  type="button"
                  key={quick}
                  onClick={() => setReason(quick)}
                  className={`text-xs px-3 py-1.5 rounded-full border transition ${
                    reason === quick
                      ? 'border-destructive tint-danger font-medium'
                      : 'border-border bg-background text-muted-foreground hover:border-border'
                  }`}
                >
                  {quick}
                </button>
              ))}
            </div>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Tell us why you're cancelling…"
              rows={3}
              className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-ring focus:border-transparent resize-none"
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="flex-1 btn-danger px-4 py-2.5 rounded-xl font-medium disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {submitting ? (
                <>
                  <RefreshCw size={18} className="animate-spin" /> Cancelling…
                </>
              ) : (
                'Cancel Order'
              )}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-2.5 border border-border text-muted-foreground rounded-xl hover:bg-background transition font-medium"
            >
              Keep Order
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CancelOrderModal;

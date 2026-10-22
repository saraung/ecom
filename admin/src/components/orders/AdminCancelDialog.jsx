// src/components/orders/AdminCancelDialog.jsx
/**
 * Unified admin cancel: the status change and the money decision are one
 * audited action (POST /admin/orders/{id}/cancel).
 *
 * - COD / unpaid  → cancel + restock only, no money moves.
 * - Paid online   → "refund now" runs the refund pipeline (executes within
 *   the caller's role limit, otherwise stages an approval for a different
 *   admin) or "refund later" leaves the balance open and flagged.
 */
import React, { useState } from 'react';
import { Loader, XCircle } from 'lucide-react';
import toast from 'react-hot-toast';
import { adminCancelOrder } from '../../api/refunds';

/** One key per dialog session — a retry of the same attempt can't double-refund. */
const genKey = () => (
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
);

const AdminCancelDialog = ({ order, open, onClose, onDone }) => {
  const [reason, setReason] = useState('');
  const [refundChoice, setRefundChoice] = useState('later');
  const [idempotencyKey, setIdempotencyKey] = useState(genKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  if (!open) return null;

  // Only a captured payment can move money — COD is restock-only.
  const isPaidOnline =
    order?.payment_method !== 'cod' && order?.payment_status === 'paid';

  // Closing always resets the dialog so the next open starts clean and gets
  // a fresh idempotency key.
  const close = () => {
    setReason('');
    setRefundChoice('later');
    setError('');
    setIdempotencyKey(genKey());
    onClose?.();
  };

  const submit = async () => {
    if (!reason.trim()) {
      setError('A cancellation reason is required — it is written to the audit log.');
      return;
    }
    setError('');
    setBusy(true);
    try {
      const res = await adminCancelOrder(order.id, {
        reason: reason.trim(),
        refund_choice: isPaidOnline ? refundChoice : 'later',
        restock: true,
        notify_customer: true,
        idempotency_key: idempotencyKey,
      });
      const refund = res.data?.refund;
      if (refund?.requires_approval) {
        toast.success('Order cancelled — refund is pending a second admin');
      } else if (refund?.processed) {
        toast.success('Order cancelled and refunded');
      } else {
        toast.success('Order cancelled');
      }
      onDone?.(res.data);
      close();
    } catch (err) {
      const detail = err.response?.data?.detail;
      // A provider mismatch arrives as a structured object (409): the
      // cancel itself did NOT persist (nothing committed), so surface the
      // message plainly — sync happens from the Refunds tab afterwards.
      setError(
        typeof detail === 'string'
          ? detail
          : detail?.message || 'Could not cancel this order.'
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
      onClick={close}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Cancel order ${order?.order_number || ''}`}
        className="bg-card rounded-xl border border-border p-6 w-full max-w-md shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="font-semibold flex items-center gap-2 text-foreground">
          <XCircle size={18} className="text-destructive" />
          Cancel {order?.order_number || 'order'}
        </h2>
        <p className="text-xs text-muted-foreground mt-1">
          Stock is restored and the customer is notified.
        </p>

        {error && (
          <div
            role="alert"
            aria-live="assertive"
            className="bg-destructive/10 text-destructive p-3 rounded-lg mt-3 text-sm"
          >
            {error}
          </div>
        )}

        <label
          htmlFor="admin-cancel-reason"
          className="block text-sm font-medium text-muted-foreground mt-4 mb-1"
        >
          Reason (required, audited)
        </label>
        <textarea
          id="admin-cancel-reason"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={3}
          maxLength={500}
          placeholder="e.g. customer requested cancellation"
          className="w-full border border-input rounded-lg p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        />

        {isPaidOnline ? (
          <fieldset className="mt-4 text-sm space-y-2">
            <legend className="text-sm font-medium text-muted-foreground mb-1">
              Refund
            </legend>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="refund-choice"
                checked={refundChoice === 'later'}
                onChange={() => setRefundChoice('later')}
              />
              Cancel only — refund later
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="refund-choice"
                checked={refundChoice === 'now'}
                onChange={() => setRefundChoice('now')}
              />
              Cancel + refund now (refund pipeline)
            </label>
            <p className="text-xs text-muted-foreground">
              Refunds above your role limit — or on an order you placed
              yourself — wait for a second admin to approve.
            </p>
          </fieldset>
        ) : (
          <p className="text-xs text-muted-foreground mt-3">
            Unpaid / COD order — cancel and restock only, no money moves.
          </p>
        )}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={close}
            className="px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted transition"
          >
            Close
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="px-4 py-2 bg-destructive text-white rounded-lg text-sm hover:opacity-90 transition disabled:opacity-60 flex items-center gap-2"
          >
            {busy ? <Loader className="animate-spin" size={15} /> : null}
            {busy ? 'Cancelling…' : 'Confirm cancel'}
          </button>
        </div>
      </div>
    </div>
  );
};

export default AdminCancelDialog;


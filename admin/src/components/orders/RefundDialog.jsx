// src/components/orders/RefundDialog.jsx
/**
 * Standalone refund without cancelling (POST /admin/orders/{id}/refund).
 *
 * Covers cancelled-but-unrefunded cleanup and post-delivery returns —
 * orders the unified cancel dialog can no longer reach. Amount defaults
 * to the full remaining balance; partial refunds allowed. Executes within
 * the caller's role limit, otherwise stages a pending approval that shows
 * up on the Refunds page for a different admin.
 */
import React, { useState } from 'react';
import { Loader, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { issueOrderRefund, reconcileOrderRefunds } from '../../api/refunds';
import { formatPrice } from '../../utils/format';

/** One key per dialog session — a retry of the same attempt can't double-refund. */
const genKey = () => (
  typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
);

const fmt = (n) => formatPrice(n);

const RefundDialog = ({ order, open, onClose, onDone }) => {
  const remaining = Math.max(0, Number(order?.grand_total || 0) - Number(order?.refund_amount || 0));
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [idempotencyKey, setIdempotencyKey] = useState(genKey);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // Provider/ledger mismatch (409 code "provider_mismatch"): money moved
  // outside the app, so retrying is pointless — offer record sync instead.
  const [mismatch, setMismatch] = useState(null);
  const [syncing, setSyncing] = useState(false);

  if (!open) return null;

  const close = () => {
    setAmount('');
    setReason('');
    setError('');
    setMismatch(null);
    setIdempotencyKey(genKey());
    onClose?.();
  };

  const submit = async () => {
    if (!reason.trim()) {
      setError('A refund reason is required — it is written to the audit log.');
      return;
    }
    const parsed = amount === '' ? null : Number(amount);
    if (parsed !== null && (!Number.isFinite(parsed) || parsed <= 0)) {
      setError('Amount must be a positive number.');
      return;
    }
    if (parsed !== null && parsed > remaining) {
      setError(`Amount cannot exceed the remaining balance of ${fmt(remaining)}.`);
      return;
    }
    setError('');
    setBusy(true);
    try {
      const res = await issueOrderRefund(order.id, {
        reason: reason.trim(),
        amount: parsed,
        idempotency_key: idempotencyKey,
      });
      const body = res.data || {};
      if (body.requires_approval) {
        toast.success('Refund staged — a different admin must approve it on the Refunds page.');
      } else {
        toast.success(body.message || 'Refund executed.');
      }
      close();
      onDone?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === 'object' && detail.code === 'provider_mismatch') {
        setMismatch(detail);
        setError('');
      } else {
        setError(typeof detail === 'string' ? detail : 'Could not issue the refund.');
      }
    } finally {
      setBusy(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await reconcileOrderRefunds(order.id);
      const body = res.data || {};
      toast.success(
        `Records synced — ${body.synced_rows || 0} external refund(s) recorded. ` +
        `Remaining: ${fmt(body.remaining)}.`
      );
      close();
      onDone?.();
    } catch (err) {
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Could not sync records.');
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={close} />
      <div className="relative bg-card rounded-xl shadow-xl border border-border w-full max-w-md p-6">
        <h2 className="text-lg font-bold text-foreground flex items-center gap-2">
          <RefreshCw size={18} />
          Issue Refund
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Order #{order?.order_number} · remaining refundable balance{' '}
          <span className="font-semibold text-foreground">{fmt(remaining)}</span>
        </p>

        {mismatch ? (
          <div role="alert" className="bg-warning/10 border border-warning/30 text-foreground p-3 rounded-lg mt-4 text-sm space-y-2">
            <p>{mismatch.message}</p>
            <p className="text-muted-foreground">
              {mismatch.provider} shows {formatPrice(mismatch.provider_refunded)} refunded
              ({formatPrice(mismatch.provider_remaining)} left) but our books say{' '}
              {formatPrice(mismatch.recorded_refunded)}. No retry will succeed
              until the records agree.
            </p>
            <button
              type="button"
              onClick={handleSync}
              disabled={syncing}
              className="px-4 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 flex items-center gap-2"
            >
              {syncing ? <Loader className="animate-spin" size={16} /> : null}
              Sync records from {mismatch.provider}
            </button>
          </div>
        ) : error ? (
          <div role="alert" className="bg-destructive/10 text-destructive p-3 rounded-lg mt-4 text-sm">
            {error}
          </div>
        ) : null}

        <div className="mt-4">
          <label htmlFor="refund-amount" className="block text-sm font-medium text-muted-foreground mb-1">
            Amount (blank = full remaining balance)
          </label>
          <input
            id="refund-amount"
            type="number"
            min="0"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={String(remaining)}
            className="w-full px-3 py-2 border border-input rounded-lg bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>

        <div className="mt-3">
          <label htmlFor="refund-reason" className="block text-sm font-medium text-muted-foreground mb-1">
            Reason <span className="text-destructive">*</span>
          </label>
          <textarea
            id="refund-reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Returned item received in good condition"
            className="w-full px-3 py-2 border border-input rounded-lg bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent resize-none"
          />
        </div>

        <p className="text-xs text-muted-foreground mt-3">
          Above your role&apos;s refund limit (or on your own order), this stages a
          pending approval instead of executing.
        </p>

        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={close}
            disabled={busy}
            className="px-4 py-1.5 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy}
            className="px-4 py-1.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors text-sm font-medium flex items-center gap-2 disabled:opacity-50"
          >
            {busy && <Loader className="animate-spin" size={16} />}
            Issue Refund
          </button>
        </div>
      </div>
    </div>
  );
};

export default RefundDialog;

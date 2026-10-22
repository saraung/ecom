// src/pages/Cod/CodRemittanceDetail.jsx
/**
 * One courier remittance batch: line decisions, bank receipt confirmation,
 * void and CSV export. This page never calls the payment collection endpoint.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeft,
  Banknote,
  CheckCircle2,
  Download,
  Loader,
  RefreshCw,
  ShieldAlert,
  Truck,
  XCircle,
} from 'lucide-react';
import toast from 'react-hot-toast';
import {
  confirmCodRemittance,
  downloadCodRemittance,
  getCodRemittance,
  resolveCodRemittanceItem,
  saveBlob,
  voidCodRemittance,
} from '../../api/cod';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import { formatDate, formatPrice } from '../../utils/format';
import {
  apiErrorMessage,
  canAcceptItem,
  openItemCount,
  signedDifference,
  todayInputValue,
} from '../../utils/cod';
import PageSkeleton from '../../components/ui/PageSkeleton';
import {
  BatchStatusBadge,
  EmptyState,
  ItemStatusBadge,
  Modal,
  SourceBadge,
  SummaryCard,
} from '../../components/cod/CodShared';

const CodRemittanceDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const canReconcile = canDo(user, 'cod.reconcile', 'manager');

  const [batch, setBatch] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const [resolveTarget, setResolveTarget] = useState(null);
  const [resolveNote, setResolveNote] = useState('');

  const [bankOpen, setBankOpen] = useState(false);
  const [bankForm, setBankForm] = useState({
    utr: '',
    amount: '',
    date: todayInputValue(),
    accountRef: '',
    notes: '',
    acceptDifference: false,
    reason: '',
  });
  const [differenceInfo, setDifferenceInfo] = useState(null);
  const [bankError, setBankError] = useState('');

  const [voidOpen, setVoidOpen] = useState(false);
  const [voidNote, setVoidNote] = useState('');

  const fetchBatch = useCallback(() => getCodRemittance(id), [id]);
  const applyBatch = useCallback((data) => {
    setBatch(data);
    setError('');
  }, []);

  const load = useCallback(async () => {
    try {
      const response = await fetchBatch();
      applyBatch(response.data);
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not load this remittance batch'));
    } finally {
      setLoading(false);
    }
  }, [fetchBatch, applyBatch]);

  useEffect(() => {
    let active = true;
    fetchBatch()
      .then((response) => {
        if (active) applyBatch(response.data);
      })
      .catch((err) => {
        if (active) setError(apiErrorMessage(err, 'Could not load this remittance batch'));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [fetchBatch, applyBatch]);

  const refresh = () => {
    setLoading(true);
    load();
  };

  const openBankDialog = () => {
    setBankForm({
      utr: batch?.utr || '',
      amount: batch?.net_expected != null ? String(batch.net_expected) : '',
      date: todayInputValue(),
      accountRef: batch?.bank_account_ref || '',
      notes: '',
      acceptDifference: false,
      reason: '',
    });
    setDifferenceInfo(null);
    setBankError('');
    setBankOpen(true);
  };

  const resolve = async () => {
    if (!resolveTarget) return;
    try {
      setBusy(true);
      const response = await resolveCodRemittanceItem(id, {
        item_id: resolveTarget.item.id,
        action: resolveTarget.action,
        note: resolveNote.trim() || null,
      });
      setBatch(response.data);
      setResolveTarget(null);
      setResolveNote('');
      toast.success(resolveTarget.action === 'exclude' ? 'Line excluded' : 'Line accepted and matched');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not resolve this line'));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    setBankError('');
    if (!bankForm.utr.trim()) {
      setBankError('Bank UTR / reference is required.');
      return;
    }
    if (!bankForm.amount || Number(bankForm.amount) <= 0) {
      setBankError('Bank credit amount must be greater than zero.');
      return;
    }
    if (!bankForm.date) {
      setBankError('Bank credit date is required.');
      return;
    }
    if (bankForm.acceptDifference && !bankForm.reason.trim()) {
      setBankError('A reason is required when accepting a bank difference.');
      return;
    }
    try {
      setBusy(true);
      const response = await confirmCodRemittance(id, {
        utr: bankForm.utr.trim(),
        bank_credit_amount: Number(bankForm.amount),
        bank_credit_date: bankForm.date,
        bank_account_ref: bankForm.accountRef.trim() || null,
        notes: bankForm.notes.trim() || null,
        accept_difference: bankForm.acceptDifference,
        difference_reason: bankForm.reason.trim() || null,
      });
      setBatch(response.data);
      setBankOpen(false);
      toast.success('Bank receipt confirmed and COD allocated');
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail && typeof detail === 'object' && detail.difference != null) {
        setDifferenceInfo(detail);
        setBankError(detail.message || 'Bank credit differs from the expected remittance.');
      } else {
        setBankError(apiErrorMessage(err, 'Could not confirm the bank receipt'));
      }
    } finally {
      setBusy(false);
    }
  };

  const removeBatch = async () => {
    try {
      setBusy(true);
      const response = await voidCodRemittance(id, voidNote.trim() || null);
      setBatch(response.data);
      setVoidOpen(false);
      setVoidNote('');
      toast.success('Batch voided');
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Could not void this batch'));
    } finally {
      setBusy(false);
    }
  };

  const exportCsv = async () => {
    try {
      const response = await downloadCodRemittance(id);
      saveBlob(response.data, `cod-remittance-${batch?.crf_id || id}.csv`);
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Export failed'));
    }
  };

  if (loading) return <PageSkeleton type="cod-detail" />;
  if (error || !batch) {
    return (
      <div className="text-center py-12">
        <p className="text-sm text-destructive">{error || 'Batch not found'}</p>
        <button
          type="button"
          onClick={() => navigate('/cod')}
          className="mt-3 px-3 py-2 border border-input rounded-lg text-sm hover:bg-muted"
        >
          Back to COD reconciliation
        </button>
      </div>
    );
  }

  const openCount = openItemCount(batch);
  const editable = batch.status === 'pending' || batch.status === 'discrepancy';
  const matchedAmount = Number(batch.matched_amount || 0);
  const expectedAmount = Number(batch.net_expected || 0);
  const canConfirm = canReconcile && editable && openCount === 0
    && matchedAmount > 0
    && Math.abs(matchedAmount - expectedAmount) < 0.005;

  return (
    <div className="space-y-5">
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-3">
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => navigate('/cod')}
            className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1 mb-2"
          >
            <ArrowLeft size={14} /> Back to COD reconciliation
          </button>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-foreground break-all">{batch.crf_id}</h1>
            <BatchStatusBadge status={batch.status} />
            <SourceBadge source={batch.source} synthetic={batch.synthetic} />
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Remittance date {formatDate(batch.remittance_date)} · {batch.item_count} line(s)
            {batch.utr ? ` · UTR ${batch.utr}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={refresh}
            className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1.5 hover:bg-muted"
          >
            <RefreshCw size={15} /> Refresh
          </button>
          <button
            type="button"
            onClick={exportCsv}
            className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1.5 hover:bg-muted"
          >
            <Download size={15} /> Export CSV
          </button>
          {canReconcile && editable && (
            <>
              <button
                type="button"
                onClick={openBankDialog}
                disabled={!canConfirm}
                title={openCount > 0 ? 'Resolve every flagged line first' : 'Confirm the bank credit'}
                className="px-3 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium flex items-center gap-1.5 disabled:opacity-50"
              >
                <Banknote size={15} /> Confirm bank receipt
              </button>
              <button
                type="button"
                onClick={() => setVoidOpen(true)}
                className="px-3 py-2 border border-destructive/40 text-destructive rounded-lg text-sm flex items-center gap-1.5 hover:bg-destructive/5"
              >
                <XCircle size={15} /> Void
              </button>
            </>
          )}
        </div>
      </div>

      {batch.synthetic && (
        <div className="rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning flex items-start gap-2">
          <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
          <p>
            <strong>Synthetic development batch.</strong> This was generated locally from test COD orders. It is not
            a real Shiprocket remittance and must not be used as production finance data.
          </p>
        </div>
      )}

      {openCount > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive flex items-start gap-2">
          <ShieldAlert size={16} className="flex-shrink-0 mt-0.5" />
          <p>
            {openCount} line{openCount === 1 ? '' : 's'} still need a decision. Accept the match (after checking the
            amount) or exclude the line before confirming the bank receipt.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <SummaryCard label="Gross COD" value={formatPrice(batch.gross_cod)} icon={Truck} />
        <SummaryCard label="Deductions" value={formatPrice(batch.deductions_total)} hint="Charges withheld by courier" />
        <SummaryCard label="Net expected" value={formatPrice(batch.net_expected)} icon={Banknote} tone="text-info" />
        <SummaryCard
          label="Bank credit"
          value={batch.bank_credit_amount == null ? '—' : formatPrice(batch.bank_credit_amount)}
          hint={batch.utr ? `UTR ${batch.utr}` : 'Awaiting confirmation'}
          icon={CheckCircle2}
          tone="text-success"
        />
        <SummaryCard
          label="Difference"
          value={batch.difference == null ? '—' : signedDifference(batch.difference, (n) => formatPrice(n))}
          hint={batch.raw_meta?.difference_reason || 'Bank credit − expected'}
          icon={AlertTriangle}
          tone={batch.difference ? 'text-warning' : 'text-muted-foreground'}
        />
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
        <h2 className="font-semibold text-foreground mb-3">Bank receipt</h2>
        {batch.status === 'reconciled' ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
            <div>
              <p className="text-xs text-muted-foreground">UTR / reference</p>
              <p className="font-medium break-all">{batch.utr || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Credit date</p>
              <p className="font-medium">{formatDate(batch.bank_credit_date)}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Bank account ref</p>
              <p className="font-medium break-all">{batch.bank_account_ref || '—'}</p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Reconciled at</p>
              <p className="font-medium">{formatDate(batch.reconciled_at)}</p>
            </div>
            {batch.raw_meta?.difference_reason && (
              <div className="sm:col-span-2 lg:col-span-4 rounded-lg bg-warning/10 border border-warning/30 px-3 py-2 text-xs">
                <strong>Accepted difference:</strong> {batch.raw_meta.difference_reason}
                {batch.raw_meta?.bank_difference && ` (${signedDifference(batch.raw_meta.bank_difference, (n) => formatPrice(n))})`}
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {batch.status === 'void'
              ? 'This batch was voided; nothing was allocated.'
              : 'No bank credit has been confirmed for this batch yet.'}
          </p>
        )}
      </div>

      <div className="bg-card rounded-xl shadow-sm border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h2 className="font-semibold text-foreground">Remittance lines</h2>
          <p className="text-xs text-muted-foreground">
            Matched amounts are allocated to orders only when the bank receipt is confirmed. A line never creates a
            Payment record.
          </p>
        </div>
        <div className="hidden lg:block overflow-x-auto">
          <table className="w-full min-w-[1050px]">
            <thead className="bg-muted">
              <tr>
                {['AWB / order', 'Order', 'COD', 'Deductions', 'Net', 'Allocate', 'Status', 'Decision'].map((label) => (
                  <th key={label} className="px-3 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {batch.items.map((item) => (
                <tr key={item.id} className="hover:bg-muted/40 align-top">
                  <td className="px-3 py-3 text-sm">
                    <div className="font-medium">{item.awb || '—'}</div>
                    {item.order_ref && <div className="text-xs text-muted-foreground">{item.order_ref}</div>}
                  </td>
                  <td className="px-3 py-3 text-sm">
                    {item.order ? (
                      <Link to={`/orders/${item.order.id}`} className="text-primary hover:underline font-medium">
                        {item.order.order_number}
                      </Link>
                    ) : '—'}
                    {item.order && (
                      <div className="text-xs text-muted-foreground">
                        {item.order.status} · {formatPrice(item.order.cod_remitted_amount)} / {formatPrice(item.order.grand_total)} remitted
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3 text-sm">{formatPrice(item.cod_amount)}</td>
                  <td className="px-3 py-3 text-sm text-muted-foreground">{formatPrice(item.deductions)}</td>
                  <td className="px-3 py-3 text-sm">{formatPrice(item.net_amount)}</td>
                  <td className="px-3 py-3 text-sm font-medium">{formatPrice(item.remitted_amount)}</td>
                  <td className="px-3 py-3 max-w-xs">
                    <ItemStatusBadge status={item.match_status} />
                    {item.match_note && <p className="text-xs text-muted-foreground mt-1">{item.match_note}</p>}
                  </td>
                  <td className="px-3 py-3">
                    {canReconcile && editable && item.match_status !== 'matched' && item.match_status !== 'adjustment' ? (
                      <div className="flex flex-col gap-1.5">
                        {canAcceptItem(item) && (
                          <button
                            type="button"
                            onClick={() => { setResolveTarget({ item, action: 'accept_match' }); setResolveNote(''); }}
                            className="px-2.5 py-1.5 border border-input rounded-lg text-xs hover:bg-muted whitespace-nowrap"
                          >
                            Accept match
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => { setResolveTarget({ item, action: 'exclude' }); setResolveNote(''); }}
                          className="px-2.5 py-1.5 border border-destructive/40 text-destructive rounded-lg text-xs hover:bg-destructive/5 whitespace-nowrap"
                        >
                          Exclude
                        </button>
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile / narrow screens: card layout instead of a horizontally scrolling table. */}
        <div className="lg:hidden divide-y divide-border">
          {batch.items.map((item) => (
            <div key={item.id} className="p-4 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground break-all">{item.awb || '—'}</p>
                  {item.order_ref && (
                    <p className="text-xs text-muted-foreground break-all">{item.order_ref}</p>
                  )}
                </div>
                <div className="shrink-0">
                  <ItemStatusBadge status={item.match_status} />
                </div>
              </div>

              {item.order ? (
                <div className="text-sm">
                  <Link to={`/orders/${item.order.id}`} className="text-primary hover:underline font-medium">
                    {item.order.order_number}
                  </Link>
                  <p className="text-xs text-muted-foreground">
                    {item.order.status} · {formatPrice(item.order.cod_remitted_amount)} / {formatPrice(item.order.grand_total)} remitted
                  </p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No linked order</p>
              )}

              <div className="grid grid-cols-2 gap-x-3 gap-y-2 text-xs">
                <div>
                  <p className="text-muted-foreground">COD</p>
                  <p className="font-medium text-foreground">{formatPrice(item.cod_amount)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Deductions</p>
                  <p className="text-foreground">{formatPrice(item.deductions)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Net</p>
                  <p className="font-medium text-foreground">{formatPrice(item.net_amount)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Allocate</p>
                  <p className="font-medium text-foreground">{formatPrice(item.remitted_amount)}</p>
                </div>
              </div>

              {item.match_note && <p className="text-xs text-muted-foreground">{item.match_note}</p>}

              {canReconcile && editable && item.match_status !== 'matched' && item.match_status !== 'adjustment' && (
                <div className="flex flex-col gap-2">
                  {canAcceptItem(item) && (
                    <button
                      type="button"
                      onClick={() => { setResolveTarget({ item, action: 'accept_match' }); setResolveNote(''); }}
                      className="w-full px-3 py-2 border border-input rounded-lg text-xs hover:bg-muted"
                    >
                      Accept match
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => { setResolveTarget({ item, action: 'exclude' }); setResolveNote(''); }}
                    className="w-full px-3 py-2 border border-destructive/40 text-destructive rounded-lg text-xs hover:bg-destructive/5"
                  >
                    Exclude
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>

        {batch.items.length === 0 && <EmptyState title="This batch has no lines" />}
      </div>

      <Modal
        open={!!resolveTarget}
        title={resolveTarget?.action === 'exclude' ? 'Exclude this line?' : 'Accept the matched amount?'}
        subtitle={resolveTarget ? `${resolveTarget.item.awb || resolveTarget.item.order_ref || 'Line'} · ${formatPrice(resolveTarget.item.net_amount)} net` : ''}
        onClose={() => { if (!busy) setResolveTarget(null); }}
      >
        <p className="text-sm text-muted-foreground">
          {resolveTarget?.action === 'exclude'
            ? 'The line stays in the audit trail but allocates nothing. Use this for courier adjustments or shipments that are not yours.'
            : 'This links the line to the order and allocates the full net amount. If it exceeds the order’s remaining COD, the line cannot be accepted — exclude it instead. Check the order total and courier charges first.'}
        </p>
        <label className="block text-xs font-medium text-muted-foreground mt-4">
          Note (optional)
          <textarea
            value={resolveNote}
            onChange={(event) => setResolveNote(event.target.value)}
            rows={2}
            maxLength={500}
            className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setResolveTarget(null)}
            disabled={busy}
            className="px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={resolve}
            disabled={busy}
            className={`px-4 py-2 rounded-lg text-sm font-medium text-white disabled:opacity-50 inline-flex items-center gap-2 ${
              resolveTarget?.action === 'exclude' ? 'bg-destructive' : 'bg-primary'
            }`}
          >
            {busy && <Loader size={15} className="animate-spin" />}
            {resolveTarget?.action === 'exclude' ? 'Exclude line' : 'Accept match'}
          </button>
        </div>
      </Modal>

      <Modal
        open={bankOpen}
        title="Confirm bank receipt"
        subtitle={`Expected net ${formatPrice(batch.net_expected)} for ${batch.crf_id}`}
        onClose={() => { if (!busy) setBankOpen(false); }}
      >
        <div className="space-y-3">
          <label className="block text-xs font-medium text-muted-foreground">
            Bank UTR / reference
            <input
              type="text"
              value={bankForm.utr}
              onChange={(event) => setBankForm((current) => ({ ...current, utr: event.target.value }))}
              maxLength={120}
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <label className="block text-xs font-medium text-muted-foreground">
              Amount credited
              <input
                type="number"
                min="0"
                step="0.01"
                value={bankForm.amount}
                onChange={(event) => setBankForm((current) => ({ ...current, amount: event.target.value }))}
                className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
              />
            </label>
            <label className="block text-xs font-medium text-muted-foreground">
              Credit date
              <input
                type="date"
                value={bankForm.date}
                onChange={(event) => setBankForm((current) => ({ ...current, date: event.target.value }))}
                className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
              />
            </label>
          </div>
          <label className="block text-xs font-medium text-muted-foreground">
            Bank account reference (optional)
            <input
              type="text"
              value={bankForm.accountRef}
              onChange={(event) => setBankForm((current) => ({ ...current, accountRef: event.target.value }))}
              maxLength={120}
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>
          <label className="block text-xs font-medium text-muted-foreground">
            Notes (optional)
            <textarea
              value={bankForm.notes}
              onChange={(event) => setBankForm((current) => ({ ...current, notes: event.target.value }))}
              rows={2}
              className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
            />
          </label>

          {differenceInfo && (
            <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning space-y-1">
              <p className="font-semibold">Bank credit does not match the expected remittance.</p>
              <p>
                Expected {formatPrice(differenceInfo.expected)}, received {formatPrice(differenceInfo.bank_credit)},
                difference {signedDifference(differenceInfo.difference, (n) => formatPrice(n))}.
                Tick the box below and give a reason to accept it.
              </p>
            </div>
          )}

          <label className="flex items-start gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={bankForm.acceptDifference}
              onChange={(event) => setBankForm((current) => ({ ...current, acceptDifference: event.target.checked }))}
              className="mt-0.5 rounded border-input"
            />
            <span>Accept a difference between the expected net and the bank credit.</span>
          </label>
          {bankForm.acceptDifference && (
            <label className="block text-xs font-medium text-muted-foreground">
              Reason for the difference
              <input
                type="text"
                value={bankForm.reason}
                onChange={(event) => setBankForm((current) => ({ ...current, reason: event.target.value }))}
                maxLength={500}
                placeholder="e.g. Courier weight/COD charges deducted at payout"
                className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
              />
            </label>
          )}

          {bankError && (
            <p className="text-xs text-destructive flex items-start gap-1.5">
              <AlertTriangle size={14} className="flex-shrink-0 mt-0.5" /> {bankError}
            </p>
          )}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setBankOpen(false)}
            disabled={busy}
            className="px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={confirm}
            disabled={busy}
            className="px-4 py-2 bg-primary text-primary-foreground rounded-lg text-sm font-medium inline-flex items-center gap-2 disabled:opacity-50"
          >
            {busy && <Loader size={15} className="animate-spin" />}
            Confirm and allocate
          </button>
        </div>
      </Modal>

      <Modal
        open={voidOpen}
        title="Void this remittance batch?"
        subtitle={batch.crf_id}
        onClose={() => { if (!busy) setVoidOpen(false); }}
      >
        <p className="text-sm text-muted-foreground">
          The batch stays in the audit trail but no lines will be allocated. Reconciled batches cannot be voided.
        </p>
        <label className="block text-xs font-medium text-muted-foreground mt-4">
          Void reason (optional)
          <input
            type="text"
            value={voidNote}
            onChange={(event) => setVoidNote(event.target.value)}
            maxLength={1000}
            placeholder="e.g. Imported by mistake"
            className="mt-1 w-full px-3 py-2 border border-input rounded-lg text-sm bg-card"
          />
        </label>
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setVoidOpen(false)}
            disabled={busy}
            className="px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={removeBatch}
            disabled={busy}
            className="px-4 py-2 bg-destructive text-white rounded-lg text-sm font-medium inline-flex items-center gap-2 disabled:opacity-50"
          >
            {busy && <Loader size={15} className="animate-spin" />}
            Void batch
          </button>
        </div>
      </Modal>
    </div>
  );
};

export default CodRemittanceDetail;

// src/pages/Refunds/Refunds.jsx
/**
 * Refund ledger (requires orders.refund).
 *
 * Rows are written by the refund pipeline: an admin cancel with "refund now"
 * either executes inside the actor's role limit, or lands here as
 * pending_approval for a DIFFERENT admin to approve / reject.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { CheckCircle, Eye, Loader, RefreshCw } from 'lucide-react';
import toast from 'react-hot-toast';
import { approveRefund, getMyRefundAuthority, getRefunds, getRefundsAttention, rejectRefund } from '../../api/refunds';
import RefundDialog from '../../components/orders/RefundDialog';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { formatPrice, formatDate } from '../../utils/format';

const ITEMS_PER_PAGE = 15;

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending_approval', label: 'Pending approval' },
  { value: 'executed', label: 'Executed' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'failed', label: 'Failed' },
];

const STATUS_BADGE = {
  pending_approval: 'bg-warning/20 text-warning',
  executed: 'bg-success/15 text-success',
  rejected: 'bg-destructive/15 text-destructive',
  failed: 'bg-destructive/15 text-destructive',
};

const badgeClass = (status) => STATUS_BADGE[status] || 'bg-muted text-foreground';

const Refunds = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const returnPath = `${location.pathname}${location.search}`;
  const navigateToOrder = (orderId) => navigate(`/orders/${orderId}`, { state: { from: returnPath } });
  const navigateToReturn = (returnId) => navigate(`/returns/${returnId}`, { state: { from: returnPath } });
  const [searchParams] = useSearchParams();
  const { user } = useAuth();
  const allowed = canDo(user, 'orders.refund', 'manager');

  const [loading, setLoading] = useState(true);
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [acting, setActing] = useState(null);
  // Row id whose reject note is being typed; null = no reject dialog.
  const [rejectId, setRejectId] = useState(null);
  const [note, setNote] = useState('');
  // 'action' = orders holding captured money with no refund in flight;
  // 'ledger' = every recorded money movement.
  const [tab, setTab] = useState('action');
  const [attention, setAttention] = useState([]);
  const [attentionCount, setAttentionCount] = useState(0);
  const [refundTarget, setRefundTarget] = useState(null);
  const [pendingCount, setPendingCount] = useState(0);
  const [confirmState, setConfirmState] = useState(null);
  // Viewer's own approval ceiling (null = unlimited). Display-only gating
  // for the Approve button — the server re-checks on every approve.
  const [myLimit, setMyLimit] = useState(null);
  const [myUnlimited, setMyUnlimited] = useState(false);

  // Whether this viewer may approve a given pending row: unlimited, or the
  // row amount fits their ceiling. Reject stays available (no money moves).
  const canApproveRow = (row) => {
    if (row.status !== 'pending_approval') return false;
    if (myUnlimited) return true;
    if (myLimit === null) return true; // authority unknown — let server decide
    return Number(row.amount) <= Number(myLimit);
  };

  // Deep-link support (e.g. the pending banner on OrderDetail navigates to
  // /refunds?status=pending_approval): land on the ledger tab pre-filtered.
  // Runs once on mount — afterwards the user owns tab/filter state.
  useEffect(() => {
    const wanted = searchParams.get('status');
    if (wanted && STATUS_OPTIONS.some((o) => o.value === wanted)) {
      setStatus(wanted);
      setTab('ledger');
      setPage(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const [ledgerRes, attentionRes] = await Promise.all([
        getRefunds({
          page,
          limit: ITEMS_PER_PAGE,
          status_filter: status || undefined,
        }),
        getRefundsAttention(),
      ]);
      setRows(ledgerRes.data?.refunds || []);
      setTotal(ledgerRes.data?.total || 0);
      setTotalPages(ledgerRes.data?.total_pages || 1);
      setAttention(attentionRes.data?.orders || []);
      setAttentionCount(attentionRes.data?.count || 0);
      try {
        const pendingRes = await getRefunds({ page: 1, limit: 1, status_filter: 'pending_approval' });
        setPendingCount(pendingRes.data?.total || 0);
      } catch {
        // Non-fatal: the badge just stays hidden.
      }
      try {
        const authRes = await getMyRefundAuthority();
        setMyUnlimited(!!authRes.data?.unlimited);
        setMyLimit(authRes.data?.max_refund_amount ?? null);
      } catch {
        // Non-fatal: buttons stay enabled, server decides on click.
      }
    } catch {
      toast.error('Failed to load refunds');
    } finally {
      setLoading(false);
    }
  }, [page, status]);

  useEffect(() => {
    if (allowed) load();
  }, [allowed, load]);

  const handleApprove = (row) => {
    setConfirmState({ kind: 'approve', row });
  };

  const runConfirmed = async () => {
    const row = confirmState?.row;
    if (!row) {
      setConfirmState(null);
      return;
    }
    try {
      setActing(row.id);
      await approveRefund(row.id);
      toast.success('Refund approved');
      load();
    } catch (err) {
      // A 400 here is usually the four-eyes rule (same admin who requested
      // it) or approval authority (amount above your role's refund limit).
      toast.error(err.response?.data?.detail || 'Could not approve this refund');
    } finally {
      setActing(null);
      setConfirmState(null);
    }
  };

  const handleReject = async () => {
    try {
      setActing(rejectId);
      await rejectRefund(rejectId, note || null);
      toast.success('Refund rejected — no money moved');
      setRejectId(null);
      setNote('');
      load();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Could not reject this refund');
    } finally {
      setActing(null);
    }
  };

  if (!allowed) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        You don&apos;t have permission to view the refund ledger.
      </div>
    );
  }

  if (loading) return <PageSkeleton type="refunds" />;


  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-6">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Refunds</h1>
          <p className="text-sm text-muted-foreground">
            {total} refund{total === 1 ? '' : 's'} — pending rows need a second admin
          </p>
        </div>
        <div className="flex gap-2">
          <label htmlFor="refund-status" className="sr-only">
            Filter refunds by status
          </label>
          <select
            id="refund-status"
            value={status}
            onChange={(e) => { setStatus(e.target.value); setPage(1); }}
            className="border border-input rounded-lg px-3 py-2 text-sm bg-card text-foreground"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value || 'all'} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={load}
            className="px-3 py-2 border border-input rounded-lg text-sm flex items-center gap-1 hover:bg-muted transition"
          >
            <RefreshCw size={15} />
            Refresh
          </button>
        </div>
      </div>

      <div className="flex gap-2 border-b border-border overflow-x-auto mb-6">
        <button
          type="button"
          onClick={() => setTab('action')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
            tab === 'action'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Action needed
          {attentionCount > 0 && (
            <span className="ml-2 px-2 py-0.5 rounded-full text-xs bg-warning/20 text-warning">
              {attentionCount}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => setTab('ledger')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
            tab === 'ledger'
              ? 'border-primary text-primary'
              : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Ledger
          {pendingCount > 0 && (
            <span className="ml-2 px-2 py-0.5 rounded-full text-xs bg-warning/20 text-warning">
              {pendingCount} pending
            </span>
          )}
        </button>
      </div>

      {tab === 'action' ? (
      <div className="bg-card rounded-xl border border-border overflow-hidden">
        {/* Desktop: table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full min-w-[760px]">
            <thead className="bg-muted border-b border-border">
              <tr>
                {['Order', 'Customer', 'Total', 'Refunded', 'Remaining', 'Actions'].map((head, i) => (
                  <th
                    key={head}
                    className={`text-left px-4 py-3 text-xs uppercase text-muted-foreground${i === 5 ? ' text-right' : ''}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {attention.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    Nothing needs action — every paid order&apos;s money is accounted for.
                  </td>
                </tr>
              )}
              {attention.map((item) => (
                <tr key={item.order_id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => navigateToOrder(item.order_id)}
                      className="text-primary text-sm flex items-center gap-1 hover:underline"
                    >
                      <Eye size={13} />
                      {item.order_number}
                    </button>
                    <p className="text-xs text-muted-foreground capitalize mt-0.5">{item.status}</p>
                    {(item.cancellation_reason || item.cancelled_at) && (
                      <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-[220px]" title={item.cancellation_reason || ''}>
                        {item.cancellation_reason || 'No reason given'}
                        {item.cancelled_at && (
                          <> · {formatDate(item.cancelled_at, { day: 'numeric', month: 'short' })}</>
                        )}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground truncate max-w-[180px]">
                    {item.customer_name || item.customer_email || '—'}
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold text-foreground">
                    {formatPrice(item.grand_total)}
                  </td>
                  <td className="px-4 py-3 text-sm text-muted-foreground">
                    {formatPrice(item.refunded)}
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold text-warning">
                    {formatPrice(item.remaining)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => setRefundTarget({
                        id: item.order_id,
                        order_number: item.order_number,
                        grand_total: item.grand_total,
                        refund_amount: item.refunded,
                      })}
                      className="px-3 py-1 bg-primary text-primary-foreground rounded text-xs"
                    >
                      Issue Refund…
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile: stacked cards (Figma admin-kit pattern) */}
        <div className="md:hidden divide-y divide-border">
          {attention.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              Nothing needs action — every paid order&apos;s money is accounted for.
            </p>
          )}
          {attention.map((item) => (
            <div key={item.order_id} className="p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => navigateToOrder(item.order_id)}
                  className="text-primary text-sm font-medium flex items-center gap-1 hover:underline min-w-0"
                >
                  <Eye size={13} className="shrink-0" />
                  <span className="truncate">{item.order_number}</span>
                </button>
                <span className="text-xs text-muted-foreground capitalize shrink-0">{item.status}</span>
              </div>
              {(item.cancellation_reason || item.cancelled_at) && (
                <p className="text-xs text-muted-foreground">
                  {item.cancellation_reason || 'No reason given'}
                  {item.cancelled_at && (
                    <> · {formatDate(item.cancelled_at, { day: 'numeric', month: 'short' })}</>
                  )}
                </p>
              )}
              <p className="text-xs text-muted-foreground truncate">
                {item.customer_name || item.customer_email || '—'}
              </p>
              <div className="flex items-center justify-between text-sm pt-1">
                <span className="text-muted-foreground">Total {formatPrice(item.grand_total)}</span>
                <span className="text-muted-foreground">Refunded {formatPrice(item.refunded)}</span>
                <span className="font-semibold text-warning">Left {formatPrice(item.remaining)}</span>
              </div>
              <button
                type="button"
                onClick={() => setRefundTarget({
                  id: item.order_id,
                  order_number: item.order_number,
                  grand_total: item.grand_total,
                  refund_amount: item.refunded,
                })}
                className="w-full mt-1 px-3 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium"
              >
                Issue Refund…
              </button>
            </div>
          ))}
        </div>
      </div>
      ) : (
      <div className="bg-card rounded-xl border border-border overflow-hidden">
        {/* Desktop: table */}
        <div className="overflow-x-auto hidden md:block">
          <table className="w-full min-w-[760px]">
            <thead className="bg-muted border-b border-border">
              <tr>
                {['Order', 'Amount', 'Status', 'Requested by', 'Reason', 'Actions'].map((head, i) => (
                  <th
                    key={head}
                    className={`text-left px-4 py-3 text-xs uppercase text-muted-foreground${i === 5 ? ' text-right' : ''}`}
                  >
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-sm text-muted-foreground">
                    No refunds match this filter.
                  </td>
                </tr>
              )}
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => row.return_request_id ? navigateToReturn(row.return_request_id) : navigateToOrder(row.order_id)}
                      className="text-primary text-sm flex items-center gap-1 hover:underline"
                    >
                      <Eye size={13} />
                      {row.order_number || String(row.order_id).slice(0, 8)}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-sm font-semibold text-foreground">
                    {formatPrice(row.amount)}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-1 rounded-full text-xs ${badgeClass(row.status)}`}>
                      {row.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground truncate max-w-[160px]">
                    {row.requester_email || '—'}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground truncate max-w-[200px]">
                    {row.reason || '—'}
                    {row.manual_transfer_reference && <p className="mt-1 font-mono text-xs" title={row.manual_transfer_reference}>COD repayment: {row.manual_transfer_reference}</p>}
                  </td>
                  <td className="px-4 py-3">
                    {row.status === 'pending_approval' ? (
                      <div className="flex gap-2 justify-end">
                        <button
                          type="button"
                          disabled={acting === row.id || !canApproveRow(row)}
                          title={
                            canApproveRow(row)
                              ? 'Approve and execute this refund'
                              : `Above your ${formatPrice(myLimit)} approval authority — an admin must approve`
                          }
                          onClick={() => handleApprove(row)}
                          className="px-3 py-1 bg-success/15 text-success rounded text-xs flex items-center gap-1 disabled:opacity-60"
                        >
                          {acting === row.id
                            ? <Loader className="animate-spin" size={13} />
                            : <CheckCircle size={13} />}
                          Approve
                        </button>
                        <button
                          type="button"
                          onClick={() => setRejectId(row.id)}
                          className="px-3 py-1 bg-destructive/10 text-destructive rounded text-xs"
                        >
                          Reject
                        </button>
                      </div>
                    ) : (
                      <p className="text-right text-xs text-muted-foreground">
                        {row.error || row.provider_status || 'No action needed'}
                      </p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile: stacked cards */}
        <div className="md:hidden divide-y divide-border">
          {rows.length === 0 && (
            <p className="px-4 py-10 text-center text-sm text-muted-foreground">
              No refunds match this filter.
            </p>
          )}
          {rows.map((row) => (
            <div key={row.id} className="p-4 space-y-2">
              <div className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => row.return_request_id ? navigateToReturn(row.return_request_id) : navigateToOrder(row.order_id)}
                  className="text-primary text-sm font-medium flex items-center gap-1 hover:underline min-w-0"
                >
                  <Eye size={13} className="shrink-0" />
                  <span className="truncate">{row.order_number || String(row.order_id).slice(0, 8)}</span>
                </button>
                <span className={`px-2 py-1 rounded-full text-xs shrink-0 ${badgeClass(row.status)}`}>
                  {row.status.replace('_', ' ')}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="font-semibold text-foreground">{formatPrice(row.amount)}</span>
                <span className="text-xs text-muted-foreground truncate ml-2">{row.requester_email || '—'}</span>
              </div>
              {row.reason && (
                <p className="text-xs text-muted-foreground">{row.reason}</p>
              )}
              {row.manual_transfer_reference && <p className="text-xs font-mono text-muted-foreground wrap-break-word">COD repayment: {row.manual_transfer_reference}</p>}
              {row.status === 'pending_approval' ? (
                <div className="flex gap-2 pt-1">
                  <button
                    type="button"
                    disabled={acting === row.id || !canApproveRow(row)}
                    title={
                      canApproveRow(row)
                        ? 'Approve and execute this refund'
                        : `Above your ${formatPrice(myLimit)} approval authority — an admin must approve`
                    }
                    onClick={() => handleApprove(row)}
                    className="flex-1 px-3 py-2.5 bg-success/15 text-success rounded-lg text-sm font-medium flex items-center justify-center gap-1 disabled:opacity-60"
                  >
                    {acting === row.id
                      ? <Loader className="animate-spin" size={14} />
                      : <CheckCircle size={14} />}
                    Approve
                  </button>
                  <button
                    type="button"
                    onClick={() => setRejectId(row.id)}
                    className="flex-1 px-3 py-2.5 bg-destructive/10 text-destructive rounded-lg text-sm font-medium"
                  >
                    Reject
                  </button>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  {row.error || row.provider_status || 'No action needed'}
                </p>
              )}
            </div>
          ))}
        </div>


        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((page - 1) * ITEMS_PER_PAGE) + 1} -{' '}
              {Math.min(page * ITEMS_PER_PAGE, total)} of {total} refunds
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-muted-foreground">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
      )}

      {refundTarget && (
        <RefundDialog
          order={refundTarget}
          open={!!refundTarget}
          onClose={() => setRefundTarget(null)}
          onDone={() => { setRefundTarget(null); load(); }}
        />
      )}

      {rejectId && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
          onClick={() => { setRejectId(null); setNote(''); }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Reject refund"
            className="bg-card rounded-xl border border-border p-6 w-full max-w-md shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-semibold text-foreground">Reject this refund?</h2>
            <p className="text-xs text-muted-foreground mt-1">
              No money moves and the requester sees the note in the ledger.
            </p>
            <label htmlFor="reject-note" className="sr-only">
              Rejection note
            </label>
            <textarea
              id="reject-note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={3}
              placeholder="Why is this refund being rejected?"
              className="mt-3 w-full border border-input rounded-lg p-2 text-sm bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => { setRejectId(null); setNote(''); }}
                className="px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={acting === rejectId}
                className="px-4 py-2 bg-destructive text-white rounded-lg text-sm disabled:opacity-60"
              >
                Reject refund
              </button>
            </div>
          </div>
        </div>
      )}
      <ConfirmDialog
        open={!!confirmState}
        busy={confirmState ? acting === confirmState.row.id : false}
        title="Approve refund?"
        message={confirmState ? `Approve the refund of ${formatPrice(confirmState.row.amount)} for ${confirmState.row.order_number || 'this order'}?` : ''}
        confirmLabel="Approve"
        cancelLabel="Cancel"
        tone="danger"
        onConfirm={runConfirmed}
        onClose={() => { if (acting !== confirmState?.row?.id) setConfirmState(null); }}
      />
    </div>
  );
};

export default Refunds;

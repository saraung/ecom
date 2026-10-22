import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle, CreditCard, LoaderCircle, PackageOpen, RefreshCw, Truck } from 'lucide-react';
import toast from 'react-hot-toast';
import { returnAPI } from '../../api/returns';
import ReturnEvidence from '../../components/returns/ReturnEvidence';
import { useAuth } from '../../context/AuthContext';
import { formatDate, formatPrice } from '../../utils/format';
import { createReturnLoader, hasReturnPermission, returnActions, returnError, RETURN_STATUS_LABELS, runReturnAction } from '../../utils/returns';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import PageSkeleton from '../../components/ui/PageSkeleton';

const inputClass = 'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground';
const buttonClass = 'inline-flex items-center justify-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-semibold hover:bg-muted disabled:opacity-50';
const primaryClass = `${buttonClass} bg-primary text-primary-foreground hover:bg-primary/90`;
const cardClass = 'rounded-xl border border-border bg-card p-4 sm:p-6';
const formatDateTime = (value) => formatDate(value, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const historyStatusClass = (status) => ({
  return_shipped: 'bg-warning/15 text-warning',
  received: 'bg-success/15 text-success',
  refunded: 'bg-success/15 text-success',
}[status] || 'bg-muted text-muted-foreground');

export default function ReturnDetail() {
  const { id } = useParams();
  return <ReturnDetailPage key={id} id={id} />;
}

function ReturnDetailPage({ id }) {
  const location = useLocation();
  const requestedReturnPath = location.state?.from;
  const returnPath = typeof requestedReturnPath === 'string'
    && requestedReturnPath.startsWith('/refunds')
    && !requestedReturnPath.startsWith('//')
    ? requestedReturnPath
    : '/returns';
  const orderDetailReturnPath = `${location.pathname}${location.search}`;
  const { user } = useAuth();
  const [row, setRow] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [acting, setActing] = useState(null);
  const [note, setNote] = useState('');
  const [outcome, setOutcome] = useState('');
  const [tracking, setTracking] = useState('');
  const [courier, setCourier] = useState('');
  const [provider, setProvider] = useState('manual');
  const [reference, setReference] = useState('');
  const [confirmState, setConfirmState] = useState(null);
  const currentId = useRef(id);
  const actionLock = useRef(false);
  const allowed = hasReturnPermission(user, 'orders.view');
  const loader = useMemo(() => createReturnLoader({ load: returnAPI.detail,
    onStart: () => { setLoading(true); setError(null); },
    onResult: (data) => { setRow(data); setLoading(false); },
    onError: (failure) => { setRow(null); setError(returnError(failure)); setLoading(false); },
  }), []);
  useEffect(() => {
    currentId.current = id;
    if (allowed) loader.run(id);
    return () => { currentId.current = null; loader.cancel(); };
  }, [id, allowed, loader]);
  const perform = async (action, input = {}) => {
    if (actionLock.current) return;
    actionLock.current = true;
    const target = id;
    try {
      loader.cancel();
      setActing(action);
      const response = await runReturnAction(returnAPI, row, user, action, input);
      if (currentId.current !== target) return;
      setRow(response.data); setNote(''); setOutcome('');
      toast.success(action === 'refund' && response.data.refund?.requires_approval ? 'Refund queued for a different authorized admin' : 'Return updated');
    } catch (failure) {
      if (currentId.current === target) {
        toast.error(returnError(failure));
        if (action === 'createShipment') await loader.run(id);
      }
    }
    finally { actionLock.current = false; if (currentId.current === target) setActing(null); }
  };
  const runConfirmed = async () => {
    try {
      if (confirmState?.kind === 'refund') {
        await perform('refund', { manual_transfer_reference: reference });
      } else if (confirmState?.kind === 'cancel') {
        await perform('cancel', { note: 'Return cancelled by admin before shipping' });
      }
    } finally {
      setConfirmState(null);
    }
  };
  if (!allowed) return <p role="alert" className="p-5 text-destructive">You do not have permission to view product returns.</p>;
  const header = <div className="flex items-center justify-between gap-4"><Link to={returnPath} className={`${buttonClass} shrink-0`}><ArrowLeft size={17} /> {returnPath.startsWith('/refunds') ? 'Refunds' : 'Returns'}</Link><button type="button" className={buttonClass} disabled={loading || !!acting} onClick={() => loader.run(id)}><RefreshCw size={17} className={loading ? 'animate-spin' : ''} /> Refresh</button></div>;
  if (loading || row && row.id !== id) return <PageSkeleton type="return-detail" />;
  if (error || !row) return <div className="space-y-5">{header}<div role="alert" className={`${cardClass} text-destructive`}>{error || 'Return not found.'}</div></div>;
  const actions = returnActions(row, user);
  const busy = !!acting;
  const milestones = [['Requested', row.created_at], ['Approved', row.approved_at], ['Return shipped', row.shipped_at],
    ['Received', row.received_at], ['Inspected', row.inspected_at], ['Refund requested', row.refund_requested_at], ['Refunded', row.refunded_at]];
  const actionButton = (action, label, input = {}, destructive = false) => <button type="button" className={destructive ? `${buttonClass} text-destructive` : primaryClass} disabled={busy} onClick={() => perform(action, input)}>{acting === action && <LoaderCircle size={16} className="animate-spin" />}{label}</button>;
  return <div className="space-y-6">
    {header}
    <div className={cardClass}><div className="flex flex-wrap justify-between gap-4"><div><h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-3"><PackageOpen size={25} /> {row.return_number}</h1><p className="text-sm text-muted-foreground mt-2">Order <Link to={`/orders/${row.order_id}`} state={{ from: orderDetailReturnPath }} className="text-primary hover:underline">{row.order_number}</Link> · Requested {formatDateTime(row.created_at)}</p></div><span className="self-start rounded-full bg-primary-soft px-4 py-2 text-sm font-semibold text-primary">{RETURN_STATUS_LABELS[row.status]}</span></div><div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 mt-6">{milestones.map(([label, date]) => <div key={label} className={`rounded-lg p-3 border ${date ? 'border-primary/20 bg-primary-soft/40' : 'border-border bg-muted/30'}`}><p className="text-xs font-semibold flex items-center gap-1">{date && <CheckCircle size={12} />} {label}</p><p className="text-[10px] text-muted-foreground mt-1">{date ? formatDateTime(date) : 'Not recorded'}</p></div>)}</div></div>
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
      <div className="lg:col-span-2 space-y-6">
        <section className={cardClass}><h2 className="font-semibold mb-4">Returned items</h2><div className="divide-y divide-border">{row.items.map((item) => <div key={item.order_item_id} className="py-3 first:pt-0 flex justify-between gap-4"><div><p className="font-semibold text-sm">{item.product_name}</p><p className="text-xs text-muted-foreground mt-1">{item.variant_sku} · Quantity {item.quantity}</p><p className="text-xs text-muted-foreground mt-1">{Object.entries(item.variant_attributes || {}).map(([key, value]) => `${key}: ${value}`).join(' · ')}</p></div><p className="text-sm font-medium whitespace-nowrap">{formatPrice(item.amount)}</p></div>)}</div><div className="mt-4 border-t border-border pt-4"><p className="text-sm font-semibold">Reason: {row.reason_label}</p><p className="mt-2 text-sm text-muted-foreground whitespace-pre-wrap wrap-break-word">{row.description || 'No additional description.'}</p></div></section>
        <section className={cardClass}><h2 className="font-semibold">Evidence photos <span className="text-sm font-normal text-muted-foreground">({row.evidence.length})</span></h2><p className="text-xs text-muted-foreground mt-1 mb-4">Authenticated, private evidence. Click a photo to view it at full size.</p>{row.evidence.length ? <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">{row.evidence.map((image) => <ReturnEvidence key={image.id} returnId={row.id} image={image} />)}</div> : <p className="text-sm text-muted-foreground">No photos were provided.</p>}</section>
        {(actions.includes('approve') || actions.includes('receive') || actions.includes('inspection')) && <section className={cardClass}>
          <h2 className="font-semibold mb-3">{row.status === 'requested' ? 'Review request' : row.status === 'received' || row.status === 'inspection' ? 'Inspect returned items' : 'Confirm physical receipt'}</h2>
          <label className="text-sm font-medium">Customer-visible note<textarea className={`${inputClass} mt-2 min-h-24 resize-y`} maxLength={1000} disabled={busy} value={note} placeholder={row.status === 'requested' ? 'Return instructions, approval note, or reason for rejection…' : 'Describe what was received and the inspection outcome…'} onChange={(event) => setNote(event.target.value)} /></label>
          {actions.includes('approve') && <div className="flex flex-wrap gap-3 mt-4">{actionButton('approve', 'Approve return', { note })}{actionButton('reject', 'Reject return', { note }, true)}</div>}
          {actions.includes('receive') && <div className="mt-4"><p className="text-xs text-muted-foreground mb-3">Confirm only after the selected items physically arrive. This does not refund or restock them.</p>{actionButton('receive', 'Confirm received', { note })}</div>}
          {actions.includes('inspection') && <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); perform('inspection', { note, passed: outcome === 'pass' }); }}><label className="text-sm font-medium">Inspection outcome<select className={`${inputClass} mt-2`} value={outcome} required disabled={busy} onChange={(event) => setOutcome(event.target.value)}><option value="">Choose outcome</option><option value="pass">Passed — eligible for refund review</option><option value="fail">Failed — refund blocked</option></select></label><p className="text-xs text-muted-foreground">An inspection note is required. Inventory disposition is handled separately.</p><button type="submit" className={primaryClass} disabled={busy}>{acting === 'inspection' && <LoaderCircle size={16} className="animate-spin" />} Save inspection</button></form>}
        </section>}
        <section id="return-activity" className={cardClass}><h2 className="font-semibold mb-4">Status and activity history</h2><ol className="border-l border-border ml-2 pl-5 space-y-5">{row.history.map((entry, index) => <li key={`${entry.created_at}-${index}`}><p className="text-sm font-semibold">{entry.action.replaceAll('_', ' ')} <span className={`ml-1 inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ${historyStatusClass(entry.to_status)}`}>→ {RETURN_STATUS_LABELS[entry.to_status]}</span></p><p className="text-xs text-muted-foreground mt-1">{formatDateTime(entry.created_at)}</p>{entry.note && <p className="text-sm mt-2 whitespace-pre-wrap wrap-break-word">{entry.note}</p>}{entry.details?.status && <p className="text-xs text-muted-foreground mt-1">{entry.details.status} · {entry.details.location}</p>}</li>)}</ol></section>
      </div>
      <aside className="space-y-6">
        <section className={cardClass}><h2 className="font-semibold mb-3">Customer</h2><p className="text-sm font-medium">{row.customer?.name || 'Customer'}</p><p className="text-sm text-muted-foreground wrap-break-word mt-1">{row.customer?.email}</p>{hasReturnPermission(user, 'users.view') && <Link to={`/users/${row.user_id}`} className="inline-block text-sm text-primary mt-3 hover:underline">View customer</Link>}</section>
        <section className={cardClass}><h2 className="font-semibold flex items-center gap-2 mb-4"><CreditCard size={18} /> Refund</h2><p className="text-2xl font-bold">{formatPrice(row.refund_amount)}</p>{Number(row.return_fee) > 0 && <p className="text-xs text-muted-foreground mt-1">Retained return fee: {formatPrice(row.return_fee)}</p>}<p className="text-xs text-muted-foreground mt-2">Captured item value after discounts and tax. Outbound shipping and COD fees are excluded.</p><p className="text-xs mt-3">Method: {row.payment_method === 'cod' ? 'Recorded manual COD repayment' : 'Original payment provider'}</p>
          {row.inspection_passed !== null && <p className={`text-sm mt-3 ${row.inspection_passed ? 'text-success' : 'text-destructive'}`}>Inspection {row.inspection_passed ? 'passed' : 'failed'}</p>}
          {row.refund?.manual_transfer_reference && <p className="text-xs mt-3 wrap-break-word">Repayment reference: <span className="font-mono">{row.refund.manual_transfer_reference}</span></p>}
          {row.refund && <div className="rounded-lg bg-muted p-3 mt-4 text-xs space-y-2"><p>Ledger: {row.refund.status.replaceAll('_', ' ')}</p>{row.refund.provider_status && <p>Provider: {row.refund.provider_status}</p>}{row.refund.provider_refund_id && <p className="font-mono wrap-break-word">{row.refund.provider_refund_id}</p>}{row.refund.requires_approval && <p>A different admin with sufficient authority must approve on the Refunds page.</p>}{hasReturnPermission(user, 'orders.refund') && <Link className="inline-block text-primary hover:underline" to={`/refunds?status=${row.refund.requires_approval ? 'pending_approval' : row.refund.status}`}>Open existing refund ledger</Link>}</div>}
          {actions.includes('refund') && <form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); setConfirmState({ kind: 'refund' }); }}>
            {row.payment_method === 'cod' && <label className="text-xs font-medium">Actual repayment reference<input className={`${inputClass} mt-2`} value={reference} minLength={3} maxLength={200} required disabled={busy} placeholder="Bank transfer / cash receipt reference" onChange={(event) => setReference(event.target.value)} /><span className="block text-muted-foreground mt-2">This records an actual repayment; it does not initiate a bank transfer. Existing refund authority/second-admin checks apply.</span></label>}
            <button type="submit" className={`${primaryClass} w-full`} disabled={busy}>{acting === 'refund' && <LoaderCircle size={16} className="animate-spin" />}{row.payment_method === 'cod' ? 'Record repayment' : 'Request refund'}</button>
          </form>}
          {!actions.includes('refund') && !['refund_pending', 'refunded', 'rejected', 'cancelled'].includes(row.status) && <p className="text-xs text-muted-foreground mt-4">Refund action requires received items, passed inspection and orders.refund permission.</p>}
        </section>
        <section className={cardClass}><h2 className="font-semibold flex items-center gap-2 mb-3"><Truck size={18} /> Return shipping</h2>
          {row.shiprocket_order_id && <dl className="text-xs space-y-2 mb-4"><div><dt className="text-muted-foreground">Reverse Shiprocket order</dt><dd className="font-mono wrap-break-word">{row.shiprocket_order_id}</dd></div><div><dt className="text-muted-foreground">Reverse shipment</dt><dd className="font-mono wrap-break-word">{row.shiprocket_shipment_id}</dd></div></dl>}
           {row.tracking_number ? <div className="text-sm space-y-2"><p>{row.courier_name}</p><p className="font-mono wrap-break-word">{row.tracking_number}</p><p className="text-xs text-muted-foreground">{row.tracking_provider} · {row.tracking_status || (row.status === 'approved' ? (row.pickup_requested_at ? 'Pickup requested · awaiting courier pickup' : 'AWB assigned · pickup not requested') : 'Awaiting tracking scans')}</p><a href="#return-activity" className={`${buttonClass} text-primary`}>Track return history</a>{actions.includes('sync') && actionButton('sync', 'Sync provider tracking')}</div> : <p className="text-sm text-muted-foreground">{row.shiprocket_order_id ? 'Reverse shipment saved. Assign its AWB to start tracking.' : row.shipping_requested_at ? 'Creation is awaiting reconciliation with Shiprocket.' : 'No return shipment created.'}</p>}
          {row.shipping_reference && <p className="text-xs text-muted-foreground mt-3 wrap-break-word">Provider reference: <span className="font-mono">{row.shipping_reference}</span></p>}
           {actions.includes('createShipment') && <div className="mt-4 space-y-3">{actionButton('createShipment', row.tracking_number && !row.pickup_requested_at ? 'Request return pickup' : row.shiprocket_order_id ? 'Assign return AWB' : row.shipping_requested_at ? 'Reconcile Shiprocket Return' : 'Create Shiprocket Return')}<p className="text-xs text-muted-foreground">The pickup request schedules the courier. Return shipped begins only after a pickup or in-transit scan; carrier delivery confirms receipt only.</p></div>}
          {actions.includes('tracking') && <details className="mt-4"><summary className="cursor-pointer text-sm text-muted-foreground">Manual tracking fallback</summary><form className="mt-4 space-y-3" onSubmit={(event) => { event.preventDefault(); perform('tracking', { tracking_number: tracking, courier_name: courier, provider }); }}><label className="text-xs font-medium">Courier<input className={`${inputClass} mt-1`} value={courier} maxLength={100} required disabled={busy} onChange={(event) => setCourier(event.target.value)} /></label><label className="block text-xs font-medium">Return AWB / tracking number<input className={`${inputClass} mt-1`} value={tracking} maxLength={100} required disabled={busy} onChange={(event) => setTracking(event.target.value)} /></label><label className="block text-xs font-medium">Tracking integration<select className={`${inputClass} mt-1`} value={provider} disabled={busy} onChange={(event) => setProvider(event.target.value)}><option value="manual">Manual courier</option><option value="shiprocket">Existing Shiprocket return AWB</option></select></label><p className="text-xs text-muted-foreground">For a separately booked carrier return, attach its own tracking number.</p><button type="submit" className={buttonClass} disabled={busy}>Attach tracking</button></form></details>}
        </section>
        {row.decision_note && <section className={cardClass}><h2 className="font-semibold mb-2">Decision note</h2><p className="text-sm whitespace-pre-wrap wrap-break-word">{row.decision_note}</p></section>}
        {row.inspection_note && <section className={cardClass}><h2 className="font-semibold mb-2">Inspection note</h2><p className="text-sm whitespace-pre-wrap wrap-break-word">{row.inspection_note}</p></section>}
        {actions.includes('cancel') && <button type="button" className={`${buttonClass} w-full text-destructive`} disabled={busy} onClick={() => { setConfirmState({ kind: 'cancel' }); }}>Cancel return request</button>}
      </aside>
    </div>
    <ConfirmDialog
      open={!!confirmState}
      busy={busy}
      title={confirmState?.kind === 'cancel' ? 'Cancel return request?' : row.payment_method === 'cod' ? 'Record repayment?' : 'Request refund?'}
      message={confirmState?.kind === 'cancel' ? 'Cancel this return before it is shipped?' : row.payment_method === 'cod' ? 'Record this actual manual COD repayment? No money will be sent by the API.' : `Request the inspected return refund of ${formatPrice(row.refund_amount)}?`}
      confirmLabel={confirmState?.kind === 'cancel' ? 'Cancel return' : row.payment_method === 'cod' ? 'Record repayment' : 'Request refund'}
      cancelLabel="Back"
      tone="danger"
      onConfirm={runConfirmed}
      onClose={() => { if (!busy) setConfirmState(null); }}
    />
  </div>;
}

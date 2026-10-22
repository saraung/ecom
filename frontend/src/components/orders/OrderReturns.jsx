import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CheckCircle, ChevronDown, ChevronUp, ImagePlus, LoaderCircle, PackageOpen, RefreshCw, X } from 'lucide-react';
import toast from 'react-hot-toast';
import { returnAPI } from '../../api/returns';
import { formatDateTime, formatPrice } from '../../utils/format';
import { buildCustomerReturnHistory, buildReturnPayload, createReturnSubmitter, createReturnWorkspaceLoader, estimateReturn, returnError, RETURN_STATUS_LABELS, validateReturnFiles } from '../../utils/returns';

const inputClass = 'w-full rounded-xl border border-border bg-background px-3 py-2.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/30';
const buttonClass = 'inline-flex items-center justify-center gap-2 rounded-full border border-border px-4 py-2 text-sm font-semibold transition-colors hover:bg-muted disabled:opacity-50';
const CUSTOMER_HISTORY_TONES = {
  request: 'bg-info-soft text-info-soft-foreground',
  approved: 'bg-primary-soft text-primary-soft-foreground',
  pickup: 'bg-warning-soft text-warning-soft-foreground',
  in_transit: 'bg-accent-soft text-accent-soft-foreground',
  success: 'bg-success-soft text-success-soft-foreground',
  refund: 'bg-warning-soft text-warning-soft-foreground',
  neutral: 'bg-muted text-muted-foreground',
};

function EvidenceImage({ returnId, image }) {
  const [url, setUrl] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let objectUrl;
    returnAPI.evidence(returnId, image.id).then(({ data }) => {
      if (!active) return;
      objectUrl = URL.createObjectURL(data);
      setUrl(objectUrl);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [returnId, image.id]);
  return url ? <a href={url} target="_blank" rel="noreferrer" className="block rounded-xl overflow-hidden border border-border" aria-label="Open return evidence photo">
    <img src={url} alt="Return evidence" className="h-24 w-24 object-cover" />
  </a> : <div className="h-24 w-24 rounded-xl bg-muted flex items-center justify-center text-xs text-muted-foreground text-center p-2">{failed ? 'Photo unavailable' : 'Loading photo…'}</div>;
}

function LocalPreview({ file }) {
  const [preview, setPreview] = useState(null);
  useEffect(() => {
    const reader = new FileReader();
    reader.onload = () => setPreview({ file, url: reader.result });
    reader.readAsDataURL(file);
    return () => { reader.onload = null; if (reader.readyState === FileReader.LOADING) reader.abort(); };
  }, [file]);
  return preview?.file === file ? <img src={preview.url} alt={file.name} className="h-20 w-20 rounded-xl object-cover border border-border" /> : null;
}

function ReturnCard({ row, expanded, onToggle, onAction, busy, policy }) {
  const [tracking, setTracking] = useState('');
  const [courier, setCourier] = useState('');
  const tone = row.status === 'refunded' ? 'bg-success/15 text-success' : ['rejected', 'cancelled'].includes(row.status) ? 'bg-muted text-muted-foreground' : 'bg-primary-soft text-primary';
  const customerHistory = buildCustomerReturnHistory(row.history);
  return <article className="rounded-2xl border border-border overflow-hidden">
    <button type="button" onClick={onToggle} aria-expanded={expanded} className="w-full flex items-center justify-between gap-3 p-4 text-left hover:bg-muted/40">
      <span className="min-w-0"><span className="block text-sm font-bold">{row.return_number}</span><span className="text-xs text-muted-foreground">{row.reason_label} · {formatPrice(row.refund_amount)}</span></span>
      <span className="flex items-center gap-2 shrink-0"><span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>{RETURN_STATUS_LABELS[row.status] || row.status}</span>{expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}</span>
    </button>
    {expanded && <div className="p-4 pt-0 space-y-4 text-sm">
      <ul className="space-y-2">{row.items.map((item) => <li key={item.order_item_id} className="flex justify-between gap-3"><span>{item.product_name}<span className="block text-xs text-muted-foreground">{item.variant_sku} · Quantity {item.quantity}</span></span><span>{formatPrice(item.amount)}</span></li>)}</ul>
      {row.description && <p className="whitespace-pre-wrap wrap-break-word text-muted-foreground">{row.description}</p>}
      {Number(row.return_fee) > 0 && <p className="text-muted-foreground">Return fee: {formatPrice(row.return_fee)}</p>}
      {row.decision_note && <div className="rounded-xl bg-muted p-3"><strong>Review note</strong><p className="mt-1 whitespace-pre-wrap wrap-break-word">{row.decision_note}</p></div>}
      {row.inspection_note && <div className="rounded-xl bg-muted p-3"><strong>Inspection</strong><p className="mt-1 whitespace-pre-wrap wrap-break-word">{row.inspection_note}</p></div>}
      {!!row.evidence.length && <div><p className="text-xs font-bold uppercase text-muted-foreground mb-2">Private evidence</p><div className="flex flex-wrap gap-2">{row.evidence.map((image) => <EvidenceImage key={image.id} returnId={row.id} image={image} />)}</div></div>}
      {row.status === 'requested' && policy && row.evidence.length < policy.max_images && <label className={`${buttonClass} cursor-pointer`}><ImagePlus size={16} /> Add photos<input type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only" disabled={busy} onChange={(event) => {
        const files = Array.from(event.target.files || []);
        event.target.value = '';
        if (!files.length) return;
        try { validateReturnFiles(files, policy, row.evidence.length); onAction(row, 'upload', files); } catch (error) { toast.error(returnError(error)); }
      }} /></label>}
      {row.tracking_number && <p className="rounded-xl bg-muted p-3"><strong>{row.courier_name}</strong><span className="block mt-1 font-mono wrap-break-word">{row.tracking_number}</span>{row.tracking_status && <span className="block text-muted-foreground mt-1">{row.tracking_status}</span>}</p>}
       {row.status === 'approved' && !row.tracking_number && <form className="rounded-xl border border-border p-3 space-y-2" onSubmit={(event) => { event.preventDefault(); onAction(row, 'tracking', { tracking_number: tracking.trim(), courier_name: courier.trim() }); }}>
        <p className="font-semibold">Sending your return?</p><p className="text-xs text-muted-foreground">Follow the review instructions above. Add your courier and tracking number after sending the parcel.</p>
        <input className={inputClass} placeholder="Courier name" aria-label="Return courier" value={courier} maxLength={100} required disabled={busy} onChange={(event) => setCourier(event.target.value)} />
        <input className={inputClass} placeholder="Tracking number" aria-label="Return tracking number" value={tracking} pattern="[A-Za-z0-9][A-Za-z0-9._-]*" maxLength={100} required disabled={busy} onChange={(event) => setTracking(event.target.value)} />
        <button type="submit" className={buttonClass} disabled={busy}>Save tracking</button>
      </form>}
      {row.status === 'refund_pending' && <p className="rounded-xl bg-primary-soft p-3">{row.refund?.requires_approval ? 'Your refund is awaiting authorized approval.' : 'Your refund has been accepted and is being processed.'}</p>}
      {row.status === 'refunded' && <p className="flex items-center gap-2 text-success"><CheckCircle size={17} /> Refund completed: {formatPrice(row.refund_amount)}</p>}
      {row.payment_method === 'cod' && !['refunded', 'rejected', 'cancelled'].includes(row.status) && <p className="text-xs text-muted-foreground">Cash-on-delivery repayment is handled manually after inspection and authorization.</p>}
       <div><h4 className="text-xs font-bold uppercase text-muted-foreground mb-3">Return history</h4><ol className="space-y-4 border-l border-border pl-4">{customerHistory.map((entry, index) => <li key={`${entry.key}-${entry.created_at}-${index}`}><p><span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${CUSTOMER_HISTORY_TONES[entry.tone] || CUSTOMER_HISTORY_TONES.neutral}`}>{entry.label}</span></p><time className="mt-1 block text-xs text-muted-foreground">{formatDateTime(entry.created_at)}</time>{entry.note && <p className="mt-1 whitespace-pre-wrap wrap-break-word text-muted-foreground">{entry.note}</p>}{entry.location && <p className="mt-1 text-xs text-muted-foreground">Courier update · {entry.location}</p>}</li>)}</ol></div>
      {['requested', 'approved'].includes(row.status) && <button type="button" className={`${buttonClass} text-destructive`} disabled={busy} onClick={() => { if (window.confirm('Cancel this return request?')) onAction(row, 'cancel'); }}>Cancel return request</button>}
    </div>}
  </article>;
}

export default function OrderReturns({ orderId, onOrderChange }) {
  const [workspace, setWorkspace] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [quantities, setQuantities] = useState({});
  const [reason, setReason] = useState('');
  const [description, setDescription] = useState('');
  const [files, setFiles] = useState([]);
  const [key, setKey] = useState(() => crypto.randomUUID());
  const submitter = useRef(createReturnSubmitter(returnAPI)).current;
  const loader = useMemo(() => createReturnWorkspaceLoader({ api: returnAPI,
    onStart: (silent) => { if (!silent) setLoading(true); setError(null); },
    onResult: (result) => { setWorkspace(result); setLoading(false); },
    onError: (failure) => { setError(returnError(failure)); setLoading(false); },
  }), []);
  const load = useCallback((silent = false) => loader.run(orderId, page, silent), [loader, orderId, page]);
  useEffect(() => { load(); return () => loader.cancel(); }, [load, loader]);
  const polling = workspace?.listing.returns.some((row) => ['refund_pending', 'return_shipped'].includes(row.status) || (row.status === 'approved' && row.pickup_requested_at));
  useEffect(() => {
    if (!polling || formOpen || busy) return;
    const timer = setInterval(() => load(true), 30000);
    return () => clearInterval(timer);
  }, [polling, formOpen, busy, load]);
  const eligibility = workspace?.eligibility;
  const estimate = estimateReturn(eligibility, quantities);
  const openForm = () => { setKey(crypto.randomUUID()); setQuantities({}); setReason(''); setDescription(''); setFiles([]); setFormOpen(true); };
  const submit = async (event) => {
    event.preventDefault();
    if (busy) return;
    try {
      const body = buildReturnPayload({ eligibility, quantities, reason, description, files, key });
      setBusy(true);
      const response = await submitter(orderId, body, files);
      toast.success('Return request submitted');
      setExpanded(response.data.id);
      setFormOpen(false);
      setFiles([]);
      if (page !== 1) setPage(1); else await load(true);
      onOrderChange?.();
    } catch (failure) { toast.error(returnError(failure)); } finally { setBusy(false); }
  };
  const onAction = async (row, action, data) => {
    if (busy) return;
    try {
      setBusy(true);
      await returnAPI[action](row.id, data);
      toast.success(action === 'cancel' ? 'Return request cancelled' : action === 'tracking' ? 'Tracking saved' : 'Photos added');
      await load(true);
      onOrderChange?.();
    } catch (failure) { toast.error(returnError(failure)); } finally { setBusy(false); }
  };
  return <section className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-8" aria-labelledby="returns-title">
    <div className="flex items-center justify-between gap-3 mb-4"><div className="flex items-center gap-3"><PackageOpen className="text-primary" size={23} /><div><h3 id="returns-title" className="text-base font-extrabold">Product returns</h3><p className="text-xs text-muted-foreground mt-1">Return delivered items and track their review</p></div></div><button type="button" className={buttonClass} aria-label="Refresh returns" disabled={busy || loading} onClick={() => { load(true); onOrderChange?.(); }}><RefreshCw size={16} /></button></div>
    {loading ? <p className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle size={17} className="animate-spin" /> Loading returns…</p> : error ? <div role="alert" className="rounded-xl bg-destructive/10 p-4 text-sm"><p>{error}</p><button type="button" className={`${buttonClass} mt-3`} onClick={() => load()}>Retry</button></div> : <>
      {!formOpen && <div className="mb-5">{eligibility?.eligible ? <button type="button" className={`${buttonClass} bg-primary text-primary-foreground hover:bg-primary/90`} disabled={busy} onClick={openForm}>Request a return</button> : <p className="text-sm text-muted-foreground">{eligibility?.ineligible_reason || 'All eligible quantities are already requested or returned.'}</p>}</div>}
      {formOpen && <form onSubmit={submit} className="rounded-2xl border border-border p-4 sm:p-5 mb-5 space-y-5">
        <div className="flex justify-between items-center gap-3"><h4 className="font-bold">Choose items to return</h4><button type="button" aria-label="Close return form" disabled={busy} onClick={() => { setFormOpen(false); setFiles([]); }}><X size={19} /></button></div>
        {eligibility.items.map((item) => <div key={item.order_item_id} className="flex items-start gap-3 rounded-xl bg-muted/40 p-3">
          <input type="checkbox" className="mt-1 accent-primary" checked={Object.hasOwn(quantities, item.order_item_id)} disabled={!item.eligible || busy} aria-label={`Return ${item.product_name}`} onChange={(event) => setQuantities((previous) => { const next = { ...previous }; if (event.target.checked) next[item.order_item_id] = 1; else delete next[item.order_item_id]; return next; })} />
          <div className="min-w-0 flex-1"><p className="font-semibold text-sm">{item.product_name}</p><p className="text-xs text-muted-foreground mt-1">{item.variant_sku} · {item.available_quantity} available of {item.purchased_quantity} purchased</p>{!item.eligible && <p className="text-xs text-muted-foreground mt-1">{item.ineligible_reason}</p>}</div>
          {Object.hasOwn(quantities, item.order_item_id) && <label className="text-xs text-muted-foreground">Quantity<input type="number" className={`${inputClass} mt-1 max-w-20`} value={quantities[item.order_item_id]} min={1} max={item.available_quantity} step={1} required disabled={busy} onChange={(event) => setQuantities((previous) => ({ ...previous, [item.order_item_id]: event.target.value }))} /></label>}
        </div>)}
        <label className="block text-sm font-semibold">Reason<select className={`${inputClass} mt-2`} value={reason} required disabled={busy} onChange={(event) => setReason(event.target.value)}><option value="">Choose a reason</option>{eligibility.reasons.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}</select></label>
        <label className="block text-sm font-semibold">Details {reason === 'other' ? '(required)' : '(optional)'}<textarea className={`${inputClass} mt-2 min-h-24 resize-y`} value={description} maxLength={2000} minLength={reason === 'other' ? 10 : undefined} required={reason === 'other'} disabled={busy} placeholder="Tell us what happened and which selected items are affected." onChange={(event) => setDescription(event.target.value)} /></label>
        <div><label className={`${buttonClass} cursor-pointer`}><ImagePlus size={17} /> Add evidence photos<input type="file" multiple accept="image/jpeg,image/png,image/webp" className="sr-only" disabled={busy} onChange={(event) => {
          const next = [...files, ...Array.from(event.target.files || [])]; event.target.value = '';
          try { validateReturnFiles(next, eligibility.policy); setFiles(next); } catch (failure) { toast.error(returnError(failure)); }
        }} /></label><p className="text-xs text-muted-foreground mt-2">{eligibility.policy.required_photo_reasons.includes(reason) ? 'At least one photo is required for this reason.' : 'Photos are optional for this reason.'} Up to {eligibility.policy.max_images} images, {Math.round(eligibility.policy.max_image_bytes / 1024 / 1024)} MB each. Photos are private.</p>
          {!!files.length && <div className="flex flex-wrap gap-3 mt-3">{files.map((file, index) => <div key={`${file.name}-${index}`} className="relative"><LocalPreview file={file} /><button type="button" className="absolute -top-2 -right-2 rounded-full p-1 bg-card border border-border" disabled={busy} aria-label={`Remove photo ${index + 1}`} onClick={() => setFiles((previous) => previous.filter((_, position) => position !== index))}><X size={13} /></button></div>)}</div>}
        </div>
        <div className="rounded-xl bg-primary-soft/50 p-4"><p className="text-sm font-semibold">Estimated refund: {formatPrice(estimate.amount)}</p>{estimate.fee > 0 && <p className="text-xs mt-1">Return fee: {formatPrice(estimate.fee)}</p>}<p className="text-xs text-muted-foreground mt-2">Based on purchased items after discounts and tax; outbound shipping and COD fees are excluded. Refunds follow approval, receipt and inspection.{eligibility.policy.window_days && ` Return window: ${eligibility.policy.window_days} days after delivery.`}</p></div>
        <button type="submit" className={`${buttonClass} bg-primary text-primary-foreground hover:bg-primary/90 w-full sm:w-auto`} disabled={busy}>{busy && <LoaderCircle size={16} className="animate-spin" />}{busy ? 'Submitting…' : 'Submit return request'}</button>
      </form>}
      <div className="space-y-3">{workspace.listing.returns.map((row) => <ReturnCard key={row.id} row={row} expanded={expanded === row.id} onToggle={() => setExpanded((previous) => previous === row.id ? null : row.id)} onAction={onAction} busy={busy} policy={eligibility?.policy} />)}</div>
      {!workspace.listing.total && !formOpen && <p className="text-xs text-muted-foreground mt-4">No return requests for this order yet.</p>}
      {workspace.listing.total_pages > 1 && <div className="flex justify-between items-center mt-4 text-xs text-muted-foreground"><button className={buttonClass} disabled={page <= 1 || busy} onClick={() => setPage((previous) => previous - 1)}>Previous</button><span>{page} / {workspace.listing.total_pages}</span><button className={buttonClass} disabled={page >= workspace.listing.total_pages || busy} onClick={() => setPage((previous) => previous + 1)}>Next</button></div>}
    </>}
  </section>;
}

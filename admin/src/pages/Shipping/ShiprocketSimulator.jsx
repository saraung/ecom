import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Truck,
  RefreshCw,
  Package,
  AlertTriangle,
  Undo2,
  ChevronDown,
  Search,
  ArrowRight,
  CircleDashed,
} from 'lucide-react';
import {
  getSimulatorShipments,
  triggerSimulatorEvent,
  resolveShipmentStage,
  SHIPROCKET_LIFECYCLE,
  SHIPROCKET_RTO_EVENTS,
  SHIPROCKET_EXCEPTION_EVENTS
} from '../../api/orders';
import FulfilmentStage from '../../components/orders/FulfilmentStage';
import { Link } from 'react-router-dom';
import { returnAPI } from '../../api/returns';
import { useAuth } from '../../context/AuthContext';
import { createReturnLoader, hasReturnPermission, loadSimulatorShipments, RETURN_SHIPPING_EVENTS, RETURN_STATUS_LABELS, returnError, runReturnSimulatorEvent } from '../../utils/returns';
import toast from 'react-hot-toast';

/* Small trigger button shared by every event group. */
const EventButton = ({ step, disabled, busy, onFire, toneClass }) => (
  <button
    disabled={disabled}
    onClick={onFire}
    title={`Shiprocket sends: ${step.status}`}
    className={`inline-flex items-center gap-1 px-2.5 py-1.5 text-[11px] font-medium rounded-lg border transition-all disabled:opacity-40 disabled:cursor-not-allowed ${toneClass}`}
  >
    {busy ? <CircleDashed size={12} className="animate-spin" /> : null}
    {step.label}
    <ArrowRight size={11} className="opacity-50" />
  </button>
);

const TransitionSummary = ({ outcome, returnFlow = false }) => {
  if (!outcome?.before || !outcome?.after) return null;
  const before = outcome.before;
  const after = outcome.after;
  const effects = outcome.effects || {};
  const statusLabel = returnFlow ? 'Return' : 'Order';
  const facts = returnFlow
    ? [[`${statusLabel} status`, `${before.return_status} → ${after.return_status}`],
      ['Tracking', `${before.tracking_status || '—'} → ${after.tracking_status || '—'}`]]
    : [['Order status', `${before.order_status} → ${after.order_status}`],
      ['Courier status', `${before.shipment_status || '—'} → ${after.shipment_status || '—'}`]];
  const effectLabels = returnFlow
    ? [[effects.return_received_now, 'Return marked received; inspection is still required'],
      [effects.inspection_unchanged, 'Inspection unchanged'], [effects.refund_unchanged, 'Refund unchanged'],
      [effects.forward_awb_preserved, 'Original forward AWB preserved']]
    : [[effects.rto_started, 'Original order entered RTO'], [effects.rto_stock_restored_now, 'Original items restocked once'],
      [effects.money_changed === false, 'Payment/refund unchanged'], [effects.forward_awb_preserved, 'Forward AWB preserved']];
  return <div className="rounded-lg border border-border bg-muted/40 p-3 text-[11px] space-y-2">
    <p className="font-semibold text-foreground">Actual application transition</p>
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-muted-foreground">{facts.map(([label, value]) => <p key={label}><span className="font-medium text-foreground">{label}:</span> {value}</p>)}</div>
    <ul className="space-y-1 text-muted-foreground">{effectLabels.filter(([visible]) => visible).map(([, label]) => <li key={label}>✓ {label}</li>)}</ul>
  </div>;
};

const ShiprocketSimulator = () => {
  const { user } = useAuth();
  const [shipments, setShipments] = useState([]);
  const [returnShipments, setReturnShipments] = useState([]);
  const [returnProvider, setReturnProvider] = useState('');
  const [activeTab, setActiveTab] = useState('forward');
  const [forwardError, setForwardError] = useState(null);
  const [reverseError, setReverseError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(null);
  const [query, setQuery] = useState('');
  // Order whose webhook payload is expanded.
  const [inspectId, setInspectId] = useState(null);
  // Last webhook body per order, so re-opening "payload" still shows it.
  const [payloads, setPayloads] = useState({});
  const [outcomes, setOutcomes] = useState({});
  const [justMoved, setJustMoved] = useState(null);

  const canViewReturns = hasReturnPermission(user, 'orders.view') && hasReturnPermission(user, 'shipping.manage');
  const loader = useMemo(() => createReturnLoader({
    load: async (allowed) => ({ data: await loadSimulatorShipments({
      loadForward: getSimulatorShipments, loadReturns: returnAPI.simulatorShipments, canViewReturns: allowed,
    }) }),
    onStart: () => setLoading(true),
    onResult: ({ forward, reverse }) => {
      setShipments(forward.shipments);
      setReturnShipments(reverse.shipments);
      setReturnProvider(reverse.provider);
      setForwardError(forward.error);
      setReverseError(reverse.error);
      setLoading(false);
    },
    onError: (failure) => {
      setShipments([]); setReturnShipments([]);
      setForwardError(returnError(failure)); setReverseError(returnError(failure)); setLoading(false);
    },
  }), []);
  const fetchShipments = useCallback(() => loader.run(canViewReturns), [loader, canViewReturns]);
  useEffect(() => {
    fetchShipments();
    return () => loader.cancel();
  }, [fetchShipments, loader]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return shipments;
    return shipments.filter((s) =>
      [s.order_number, s.awb_code, s.courier_name, s.shiprocket_order_id]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q))
    );
  }, [shipments, query]);

  const handleTrigger = async (orderId, step, location) => {
    try {
      setTriggering(`${orderId}-${step.event}`);
      const res = await triggerSimulatorEvent(orderId, {
        event: step.event,
        location,
        activity: step.status
      });
      const r = res.data || {};
      // Remember the exact body Shiprocket would POST for this order.
      if (r.simulated_payload) {
        setPayloads((prev) => ({ ...prev, [orderId]: r.simulated_payload }));
        setInspectId(orderId);
      }
      setOutcomes((prev) => ({ ...prev, [orderId]: r }));
      if (r.status_changed) {
        setJustMoved(orderId);
        setTimeout(() => setJustMoved((id) => (id === orderId ? null : id)), 2500);
      }
      toast.success(
        r.status_changed
          ? `Moved to ${String(r.order_status).replace(/_/g, ' ')}`
          : `Recorded: ${step.status} (status unchanged)`
      );
      fetchShipments();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to trigger event');
    } finally {
      setTriggering(null);
    }
  };

  const fire = (s, step, location) => () => handleTrigger(s.order_id, step, location);
  const busy = (s, step) => triggering === `${s.order_id}-${step.event}`;
  const filteredReturns = useMemo(() => {
    const q = query.trim().toLowerCase();
    return returnShipments.filter((s) => !q || [s.return_number, s.order_number, s.awb_code, s.courier_name, s.shiprocket_order_id]
      .filter(Boolean).some((value) => String(value).toLowerCase().includes(q)));
  }, [returnShipments, query]);
  const handleReturnTrigger = async (shipment, step) => {
    const key = `return:${shipment.return_id}`;
    try {
      setTriggering(`${key}-${step.event}`);
      const response = await runReturnSimulatorEvent(returnAPI, shipment, step, 'Return Warehouse Hub');
       const result = response.data;
       setPayloads((prev) => ({ ...prev, [key]: result.simulated_payload }));
       setOutcomes((prev) => ({ ...prev, [key]: result }));
      setInspectId(key);
      toast.success(result.status_changed ? `Return ${RETURN_STATUS_LABELS[result.return_status]}` : `Recorded: ${step.status}`);
      await fetchShipments();
    } catch (error) { toast.error(error.response?.data?.detail || error.message || 'Failed to trigger return event'); }
    finally { setTriggering(null); }
  };

  // No max-width wrapper (unlike ProductDetail's max-w-6xl): <main> already
  // pads the content, so capping it here just left dead space on the right of
  // the grid. Full width lets the cards use the whole main area.
  // Card grid scales 1 / 2 / 3 per row (same scale as RoleList) so cards keep a
  // readable width instead of becoming two very wide, half-empty ones on xl.
  return (
    <div className="space-y-5">
      {/* Header: title + search + refresh only. */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground flex items-center gap-2 flex-wrap">
            <Truck size={20} className="text-primary shrink-0" />
            <span className="break-words">Shiprocket Simulator</span>
            <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-purple-500/15 text-purple-600 dark:text-purple-400 shrink-0">
              Test only
            </span>
          </h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Fire tracking events at forward or customer-return shipments — same handler production uses.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <div className="relative w-full sm:w-auto">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search order / return / AWB…"
              className="w-full sm:w-52 pl-8 pr-3 py-2 text-sm bg-card border border-border rounded-lg text-foreground placeholder:text-muted-foreground/70 focus:outline-none focus:ring-2 focus:ring-primary/30"
            />
          </div>
          <button
            onClick={fetchShipments}
            className="flex items-center justify-center gap-2 px-3.5 py-2.5 sm:py-2 text-sm bg-card border border-border hover:bg-muted text-foreground rounded-lg transition-colors"
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      <div role="tablist" aria-label="Shipment type" className="flex flex-wrap gap-2 border-b border-border pb-3">
        <button id="outbound-tab" role="tab" aria-selected={activeTab === 'forward'} aria-controls="outbound-panel"
          onClick={() => setActiveTab('forward')} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${activeTab === 'forward' ? 'border-primary bg-primary-soft text-primary' : 'border-border bg-card text-muted-foreground hover:bg-muted'}`}>
          Outbound orders ({loading ? '…' : forwardError ? 'unavailable' : shipments.length})
        </button>
        <button id="returns-tab" role="tab" aria-selected={activeTab === 'returns'} aria-controls="returns-panel"
          disabled={!canViewReturns} title={!canViewReturns ? 'Requires orders.view and shipping.manage permissions' : undefined}
          onClick={() => setActiveTab('returns')} className={`rounded-lg border px-4 py-2 text-sm font-semibold disabled:opacity-50 ${activeTab === 'returns' ? 'border-primary bg-primary-soft text-primary' : 'border-border bg-card text-muted-foreground hover:bg-muted'}`}>
          Customer returns ({loading ? '…' : reverseError ? 'unavailable' : returnShipments.length})
        </button>
      </div>

      {loading && (
        <div className="bg-card rounded-xl border border-border shadow-sm p-12 text-center text-muted-foreground text-sm">
          Loading shipments…
        </div>
      )}
      {!loading && activeTab === 'forward' && <section id="outbound-panel" role="tabpanel" aria-labelledby="outbound-tab">
      {forwardError ? <div role="alert" className="rounded-xl border border-destructive/30 bg-card p-5 text-sm text-destructive">Could not load outbound shipments: {forwardError}</div> : shipments.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sm p-12 text-center space-y-2">
          <Package size={28} className="mx-auto text-muted-foreground/60" />
          <p className="text-foreground font-medium">No forward shipments yet</p>
          <p className="text-xs text-muted-foreground">
            Open an <b>Order Detail</b> page, click <b>Ship with Shiprocket</b>, assign an AWB — it appears here.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-card rounded-xl border border-border shadow-sm p-10 text-center text-sm text-muted-foreground">
          No shipments match “{query}”.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((s) => {
            const stage = resolveShipmentStage(s);
            const noAwb = !s.awb_code;
            const payload = payloads[s.order_id];
            const open = inspectId === s.order_id;
            return (
              <div
                key={s.order_id}
                className={`bg-card rounded-xl border shadow-sm p-4 flex flex-col gap-3 transition-colors ${
                  justMoved === s.order_id ? 'border-success/60' : 'border-border'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-semibold text-foreground text-sm truncate">
                      {s.order_number || s.shiprocket_order_id}
                    </div>
                    <div className="text-[11px] text-muted-foreground">
                      {s.user_name}
                      {s.user_name ? ' · ' : ''}
                      <span className="capitalize">{s.payment_status}</span>
                    </div>
                    <div className="text-[11px] text-muted-foreground font-mono truncate mt-0.5">
                      {s.courier_name || 'No courier'} · {s.awb_code || 'No AWB yet'}
                    </div>
                  </div>
                  <span className="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-muted text-muted-foreground font-medium">
                    {s.tracking_scans_count} scan{s.tracking_scans_count === 1 ? '' : 's'}
                  </span>
                </div>

                {noAwb && (
                  <p className="text-[11px] text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/30 rounded-lg px-2.5 py-1.5">
                    Assign an AWB on the order page first — events need one.
                  </p>
                )}

                <div className="min-h-[86px]">
                  <FulfilmentStage stage={stage} />
                </div>

                {/* Triggers — grouped Journey / Return / Exception. */}
                <div className="space-y-2.5 pt-1 border-t border-border/60">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                      <Package size={11} /> Journey
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {SHIPROCKET_LIFECYCLE.map((step) => (
                        <EventButton
                          key={step.key}
                          step={step}
                          disabled={noAwb}
                          busy={busy(s, step)}
                          onFire={fire(s, step, 'Delhi Logistics Hub')}
                          toneClass={
                            step.key === 'delivered'
                              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/20'
                              : 'border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 hover:bg-blue-500/20'
                          }
                        />
                      ))}
                    </div>
                  </div>
                   <div>
                     <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                       <Undo2 size={11} /> Failed delivery → Outbound RTO
                     </div>
                     <p className="text-[11px] text-muted-foreground mb-1.5">This is the original parcel returning to your warehouse. It is separate from a customer return shipment.</p>
                    <div className="flex flex-wrap gap-1.5">
                      {SHIPROCKET_RTO_EVENTS.map((step) => (
                        <EventButton
                          key={step.key}
                          step={step}
                          disabled={noAwb}
                          busy={busy(s, step)}
                          onFire={fire(s, step, 'Warehouse Dock')}
                          toneClass="border-destructive/30 bg-destructive/10 text-destructive hover:bg-destructive/20"
                        />
                      ))}
                    </div>
                  </div>
                   <div>
                     <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1">
                       <AlertTriangle size={11} /> Delivery exception / NDR
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {SHIPROCKET_EXCEPTION_EVENTS.map((step) => (
                        <EventButton
                          key={step.key}
                          step={step}
                          disabled={noAwb}
                          busy={busy(s, step)}
                          onFire={fire(s, step, 'Customer City Hub')}
                          toneClass="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20"
                        />
                      ))}
                    </div>
                  </div>
                </div>

                <TransitionSummary outcome={outcomes[s.order_id]} />

                {payload && (
                  <div className="pt-1">
                    <button
                      onClick={() => setInspectId(open ? null : s.order_id)}
                      className="text-[11px] text-primary hover:underline font-medium flex items-center gap-1"
                    >
                      <ChevronDown size={12} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
                      {open ? 'Hide' : 'Show'} webhook payload
                    </button>
                    {open && (
                      <pre className="mt-1.5 text-[10px] font-mono leading-relaxed bg-muted/60 border border-border rounded-lg p-2.5 overflow-x-auto max-h-48 text-foreground/80">
                        {JSON.stringify(payload, null, 2)}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      </section>}
      {!loading && activeTab === 'returns' && <section id="returns-panel" role="tabpanel" aria-labelledby="returns-tab" className="space-y-3">
        <h2 className="text-lg font-semibold flex items-center gap-2"><Undo2 size={18} /> Customer return shipments</h2>
        <p className="text-xs text-muted-foreground">Independent reverse AWBs. Delivery confirms received only; inspection, inventory disposition and refunds remain explicit actions.</p>
        <Link to="/returns" className="inline-block text-sm font-medium text-primary hover:underline">View all return requests</Link>
        {returnProvider && returnProvider.toLowerCase() !== 'simulator' && <p className="text-xs text-muted-foreground">Live provider selected. Return event simulation is disabled.</p>}
        {reverseError ? <div role="alert" className="rounded-xl border border-destructive/30 bg-card p-5 text-sm text-destructive">Could not load customer return shipments: {reverseError}</div> : !canViewReturns ? <p className="text-sm text-muted-foreground">Return shipments require orders.view and shipping.manage permissions.</p> : !filteredReturns.length ? <p className="text-sm text-muted-foreground">{returnShipments.length ? 'No returns match this search.' : 'No Shiprocket return shipments yet. Approve a return and use Create Shiprocket Return, or attach its existing Shiprocket return AWB, on the return detail page.'}</p> : <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filteredReturns.map((shipment) => {
            const key = `return:${shipment.return_id}`;
            const payload = payloads[key];
            const open = inspectId === key;
            return <div key={key} className="bg-card rounded-xl border border-border shadow-sm p-4 space-y-3">
              <div className="flex justify-between gap-2"><Link to={`/returns/${shipment.return_id}`} className="text-primary text-sm font-semibold hover:underline">{shipment.return_number}</Link><span className="text-[11px] rounded-full bg-purple-500/15 px-2 py-0.5 text-purple-600 dark:text-purple-400">Reverse return</span></div>
              <p className="text-xs text-muted-foreground">{shipment.order_number} · {shipment.user_name}</p>
              <p className="text-xs font-mono wrap-break-word">{shipment.courier_name || 'No courier'} · {shipment.awb_code || 'Assign return AWB on the return page'}</p>
              {shipment.shiprocket_order_id ? <p className="text-xs text-muted-foreground">Reverse order {shipment.shiprocket_order_id} · Shipment {shipment.shiprocket_shipment_id}</p> : <p className="text-xs text-muted-foreground">Attached Shiprocket return AWB</p>}
              <div className="text-xs space-y-1"><p className="font-medium">{shipment.reason_label}</p><ul className="text-muted-foreground space-y-1">{shipment.items?.map((item, index) => <li key={index}>{item.product_name} · Return quantity {item.quantity}</li>)}</ul></div>
              <p className="text-sm font-medium">{RETURN_STATUS_LABELS[shipment.return_status]} <span className="font-normal text-xs text-muted-foreground">· {shipment.tracking_status || 'Awaiting scans'} · {shipment.tracking_scans_count} scans</span></p>
              <div className="flex flex-wrap gap-1.5 border-t border-border pt-3">{RETURN_SHIPPING_EVENTS.map((step) => <EventButton key={step.key} step={step}
                disabled={!shipment.awb_code || !!triggering || returnProvider.toLowerCase() !== 'simulator' || !hasReturnPermission(user, 'orders.update')}
                busy={triggering === `${key}-${step.event}`} onFire={() => handleReturnTrigger(shipment, step)}
                 toneClass="border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400 hover:bg-purple-500/20" />)}</div>
              <TransitionSummary outcome={outcomes[key]} returnFlow />
              {payload && <div><button onClick={() => setInspectId(open ? null : key)} className="text-xs text-primary hover:underline">{open ? 'Hide' : 'Show'} return webhook payload</button>{open && <pre className="mt-2 text-[10px] bg-muted border border-border rounded-lg p-2 overflow-x-auto max-h-48">{JSON.stringify(payload, null, 2)}</pre>}</div>}
            </div>;
          })}
        </div>}
      </section>}
    </div>
  );
};

export default ShiprocketSimulator;

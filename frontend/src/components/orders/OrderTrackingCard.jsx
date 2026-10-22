// src/components/orders/OrderTrackingCard.jsx
// Customer-facing shipment tracking.
//
// The stage is computed by the backend (`shipment_stage` on the order payload)
// and mirrors the admin view exactly, so a customer can never see "Out for
// Delivery" here while the admin sees the parcel still at the hub. Scans come
// from the real webhook timeline — nothing here is invented, so an order
// awaiting pickup shows an honest "waiting for pickup" rather than a
// fabricated in-transit event.
import React, { useState } from 'react';
import { Truck, MapPin, Clock, ChevronDown, ChevronUp, Package, AlertTriangle, Undo2, CheckCircle2, ExternalLink } from 'lucide-react';
import { formatDateTime, formatDay } from '../../utils/format';

// Customer-facing journey. Deliberately NOT the warehouse pipeline:
// Amazon / Flipkart / Shiprocket's own tracker show
//   Ordered → Packed → Shipped → Out for Delivery → Delivered
// and NEVER internal states like "Ready to Ship" or "Pickup Scheduled".
// Those are warehouse admin concerns; showing them confuses customers
// ("my order is ready, why isn't it moving?"). We map step 1 = order
// placed, step 2 = packed (confirmed/processing), steps 3-5 from the
// courier. Shiprocket's own words (shiprocket.in/shipment-tracking):
// Order Received → Order Picked → In Transit → Out For Delivery →
// Reached Destination.
const TRACK = [
  { step: 1, label: 'Ordered' },
  { step: 2, label: 'Packed' },
  { step: 3, label: 'Shipped' },
  { step: 4, label: 'Out for Delivery' },
  { step: 5, label: 'Delivered' },
];

// Backend stage (1..5 warehouse rail) → customer step (1..5 journey rail).
// The difference: backend steps 1 (ready) and 2 (pickup scheduled) both mean
// "we're packing it" to a customer, so they collapse into Packed.
const toCustomerStep = (stage) => {
  if (!stage) return 0;
  if (stage.step == null) return 0; // off-path: pill only, no rail
  if (stage.step <= 2) return 2; // ready / pickup scheduled → Packed
  return stage.step; // 3,4,5 line up 1:1
};

// Tailwind-only: this app styles components directly, not via admin CSS vars.
const TONES = {
  neutral: 'bg-muted text-muted-foreground border-border',
  info: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  success: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  danger: 'bg-destructive/15 text-destructive border-destructive/30',
};

const OFF_PATH = {
  returned: { Icon: Undo2, hint: 'This parcel could not be delivered and is being returned to us. Any refund is handled automatically.' },
  exception: { Icon: AlertTriangle, hint: 'The courier reported a problem with this delivery. Our team is looking into it.' },
  cancelled: { Icon: AlertTriangle, hint: 'This shipment was cancelled.' },
};

const formatEtaDate = (value) => {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return formatDay(value);
};

/** Amazon-style headline for the current journey step. */
const headlineFor = (order, currentStep, etaLabel) => {
  const status = order?.status;
  if (status === 'delivered') return 'Delivered';
  if (status === 'out_for_delivery') return 'Arriving today';
  if (status === 'cancelled') return 'Order cancelled';
  if (status === 'rto') return 'Returning to seller';
  if (status === 'refunded') return 'Order refunded';
  if (currentStep <= 2) return etaLabel ? `Arriving by ${etaLabel}` : 'Order confirmed';
  if (currentStep === 3) return etaLabel ? `Arriving by ${etaLabel}` : 'On the way';
  return etaLabel ? `Arriving by ${etaLabel}` : 'On the way';
};

/** Normalise the backend's tracking_data (a JSON list, or a {scans} wrapper). */
const extractScans = (order) => {
  const t = order?.tracking_data;
  if (Array.isArray(t)) return t;
  if (t && typeof t === 'object' && Array.isArray(t.scans)) return t.scans;
  return [];
};
const OrderTrackingCard = ({ order }) => {
  const [expanded, setExpanded] = useState(false);

  const stage = order?.shipment_stage;
  const awb = order?.awb_code;

  const scans = extractScans(order);
  // Unshipped orders have nothing to show; an early return before any hooks
  // would be a hooks-order bug, so this is a null render instead.
  if (!order || !awb || !stage) return null;

  const offPath = OFF_PATH[stage.stage];
  // Destructure the icon rather than using <offPath.Icon/>, which React does
  // not treat as a component reference.
  const StageIcon = offPath ? offPath.Icon : stage.stage === 'delivered' ? CheckCircle2 : Package;
  const tone = TONES[stage.tone] || TONES.neutral;
  // Customer journey step: an unshipped order is always at least Packed
  // (the parcel exists), even if the warehouse rail hasn't started.
  const currentStep = Math.max(toCustomerStep(stage), 2);
  // Newest first for the customer — that is the scan they care about.
  const recent = [...scans].reverse().slice(0, 5);
  // Deep-link to Shiprocket's public tracker — the "tracking link" real
  // stores give. Works with AWB or order id; no login needed.
  const trackingUrl = awb
    ? `https://www.shiprocket.in/shipment-tracking/?awb=${encodeURIComponent(awb)}`
    : null;

  return (
    <section className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-8">
      {/* Amazon-style headline: "Arriving by Fri, 3 Oct" / "Arriving today". */}
      {(() => {
        const etaLabel = formatEtaDate(order.expected_delivery_date);
        const headline = headlineFor(order, currentStep, etaLabel);
        const HeadIcon = offPath ? StageIcon : currentStep >= 5 ? CheckCircle2 : Truck;
        return (
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div className="flex items-center gap-3 min-w-0">
              <span className="w-10 h-10 rounded-full bg-primary-soft flex items-center justify-center shrink-0">
                <HeadIcon size={18} className="text-primary" />
              </span>
              <div className="min-w-0">
                <p className="text-base sm:text-lg font-extrabold text-foreground m-0 leading-tight">{headline}</p>
                {etaLabel && order?.status !== 'delivered' && !offPath && (
                  <p className="text-xs text-muted-foreground font-medium m-0 mt-0.5">
                    Expected delivery {etaLabel}
                    {order.courier_name ? ` · via ${order.courier_name}` : ''}
                  </p>
                )}
              </div>
            </div>
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border ${tone}`}>
              <StageIcon size={13} />
              {stage.label}
            </span>
          </div>
        );
      })()}

      {/* Courier + AWB + external tracking link — what real stores give. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        <div className="p-3.5 rounded-2xl border border-border bg-muted/40">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground m-0">Courier</p>
          <p className="text-sm font-semibold text-foreground m-0 mt-1">{order.courier_name || 'To be assigned'}</p>
        </div>
        <div className="p-3.5 rounded-2xl border border-border bg-muted/40">
          <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground m-0">AWB / Tracking No.</p>
          <p className="text-sm font-bold font-mono text-primary m-0 mt-1 break-all">{awb}</p>
          {trackingUrl && (
            <a
              href={trackingUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline mt-1.5"
            >
              <ExternalLink size={11} /> Track on courier site
            </a>
          )}
        </div>
      </div>

      {/* Off-happy-path parcels get a plain explanation, never a progress bar
          claiming a returned parcel is "60% delivered". */}
      {offPath ? (
        <div className="p-4 rounded-2xl border border-border bg-muted/30 flex items-start gap-3">
          <StageIcon size={18} className="text-destructive shrink-0 mt-0.5" />
          <p className="text-sm text-foreground m-0 leading-relaxed">{offPath.hint}</p>
        </div>
      ) : (
        <div className="flex items-start gap-1 mb-1" role="list" aria-label="Delivery progress">
          {TRACK.map((t) => {
            const done = currentStep >= t.step;
            const isCurrent = currentStep === t.step;
            return (
              <div key={t.step} className="flex-1 flex flex-col gap-1.5" role="listitem">
                <div className={`h-1.5 rounded-full transition-colors ${done ? 'bg-primary' : 'bg-muted'}`} />
                <span
                  className={`text-[10px] leading-tight pr-1 ${
                    isCurrent ? 'text-foreground font-bold' : done ? 'text-muted-foreground' : 'text-muted-foreground/60'
                  }`}
                >
                  {t.label}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Scan timeline — only ever real events reported by the courier. */}
      <div className="mt-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground m-0">
            Latest Activity
          </h3>
          {scans.length > 5 && (
            <button
              onClick={() => setExpanded((v) => !v)}
              className="inline-flex items-center gap-1 text-[11px] font-bold text-primary hover:underline bg-transparent border-0 cursor-pointer p-0"
            >
              {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {expanded ? 'Show less' : `Show all ${scans.length}`}
            </button>
          )}
        </div>

        {scans.length === 0 ? (
          <p className="text-sm text-muted-foreground m-0">
            Your parcel is packed and waiting for the courier pickup. The first update appears here once it is collected.
          </p>
        ) : (
          <ol className="list-none p-0 m-0 space-y-4">
            {(expanded ? [...scans].reverse() : recent).map((s, i) => (
              <li key={`${s.date}-${i}`} className="relative pl-6">
                <span
                  className={`absolute left-0 top-1.5 w-2.5 h-2.5 rounded-full border-2 border-card ${
                    i === 0 ? 'bg-primary ring-4 ring-primary/20' : 'bg-muted-foreground/50'
                  }`}
                />
                <p className="text-sm font-semibold text-foreground m-0 leading-snug">
                  {s.activity || s.status}
                </p>
                <p className="text-xs text-muted-foreground m-0 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                  {s.location && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin size={11} /> {s.location}
                    </span>
                  )}
                  {s.date && (
                    <span className="inline-flex items-center gap-1">
                      <Clock size={11} /> {formatDateTime(s.date)}
                    </span>
                  )}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>

    </section>
  );
};

export default OrderTrackingCard;

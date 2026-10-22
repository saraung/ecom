// src/utils/format.js
// ✅ Shared formatters & display maps — badge colors are THEME tokens
//    (defined in src/styles/theme.css), so re-skinning = edit 1 file.
//    Money is serialized as strings ("2653.92") — parse with Number().
//
// Money/date formatting is implemented once in @ecom/shared/format and
// parameterised with this app's region store. The order/payment display maps
// below stay local: they are storefront vocabulary, not shared with admin.

import { getRegion } from './region';
import { createFormatters } from '@ecom/shared/format';

const formatters = createFormatters(getRegion);

export const {
  formatPrice,
  formatShort,
  formatNumber,
  currencySymbol,
  taxLabel,
  storeCountry,
  formatDate,
  formatDateTime,
  formatDay,
} = formatters;

/** Public support phone for receipts and help copy (may be empty). */
export const supportPhone = () => getRegion().supportPhone;

// ✅ Order status enum: pending | confirmed | processing | shipped | out_for_delivery |
//    delivered | cancelled | rto | refunded
//    ⚠️ Every value the backend can persist must appear here — an unlisted status
//    silently falls back to an untinted grey pill in OrderStatusBadge.
export const ORDER_STATUS_STYLES = {
  pending: 'badge badge-warning',
  confirmed: 'badge badge-accent',
  processing: 'badge tint-info',
  shipped: 'badge tint-info',
  out_for_delivery: 'badge tint-info', // last leg before delivery — same family as shipped
  delivered: 'badge badge-success',
  cancelled: 'badge badge-danger',
  rto: 'badge tint-danger', // returned to origin (failed delivery) — distinct from cancelled
  refunded: 'badge badge-neutral',
};

// ✅ Display labels for the order status enum (single source of truth).
//    CSS `capitalize` cannot split snake_case, so a raw "out_for_delivery" would
//    render as "Out_for_delivery" — always render statuses through this map.
export const ORDER_STATUS_LABELS = {
  pending: 'Pending',
  confirmed: 'Confirmed',
  processing: 'Processing',
  shipped: 'Shipped',
  out_for_delivery: 'Out for Delivery',
  delivered: 'Delivered',
  cancelled: 'Cancelled',
  rto: 'Returned to Origin',
  refunded: 'Refunded',
};

// ✅ Payment status: pending | paid | cod_pending | failed | refund_initiated |
//    refund_completed | refund_failed (+ legacy "refunded")
export const PAYMENT_STATUS_LABELS = {
  cod_pending: 'Pay on Delivery',
  pending: 'Payment Pending',
  paid: 'Paid',
  failed: 'Failed',
  refund_initiated: 'Refund Processing',
  refund_completed: 'Refund Completed',
  refund_failed: 'Refund Failed',
  refunded: 'Refunded', // ⚠️ legacy value — the backend no longer writes it
};

// ✅ Refund-phase badge labels (single source of truth for the UI).
//    The legacy "refunded" value is treated as a completed refund.
export const REFUND_PAYMENT_STATUS_LABELS = {
  refund_initiated: '⏳ Refund Processing',
  refund_completed: '✅ Refund Completed',
  refund_failed: '❌ Refund Failed',
  refunded: '✅ Refund Completed', // legacy
};

// ✅ Refund-phase pill colors, matching REFUND_PAYMENT_STATUS_LABELS keys
export const REFUND_PAYMENT_STATUS_STYLES = {
  refund_initiated: 'badge badge-warning',
  refund_completed: 'badge badge-success',
  refund_failed: 'badge badge-danger',
  refunded: 'badge badge-success',
};

// ✅ Every payment status that means "a refund already happened / is in progress".
//    Orders in any of these states can never be cancelled again.
export const REFUND_PAYMENT_STATUSES = [
  'refund_initiated',
  'refund_completed',
  'refund_failed',
  'refunded',
];

// ✅ Order states the backend still accepts for POST /orders/{id}/cancel
export const CANCELLABLE_ORDER_STATUSES = ['pending', 'confirmed', 'processing'];

// ✅ Client-side "can I cancel this order?" hint. The backend enforces the real rules —
//    this only decides whether to show/hide the Cancel Order button.
export const canCancelOrder = (order) => {
  if (!order) return false;
  if (order.status === 'cancelled') return false;
  if (REFUND_PAYMENT_STATUSES.includes(order.payment_status)) return false;
  return CANCELLABLE_ORDER_STATUSES.includes(order.status);
};

// ✅ An unpaid online order can be resumed via /checkout?repay=<order_id>
export const canPayOrder = (order) =>
  !!order &&
  order.payment_method !== 'cod' &&
  order.status === 'pending' &&
  order.payment_status === 'pending';

// ✅ Payment method: cod | online (can be null)
export const PAYMENT_METHOD_LABELS = {
  cod: 'Cash on Delivery',
  online: 'Online',
};

// ✅ Cancellation & restocking-fee policy — single source of truth for the customer-facing
//    wording used on the orders and checkout pages. The backend enforces the real rules;
//    these numbers simply tell customers what to expect when they cancel.
export const CANCELLATION_POLICY = {
  // Order statuses after which cancellation is no longer allowed at all
  // (covers both Cash on Delivery and Online payment orders).
  nonCancellableStatuses: [
    'shipped',
    'out_for_delivery',
    'delivered',
    'cancelled',
    'rto',
    'refunded',
  ],
  // Applicable restocking fee (%) by order status for orders paid online.
  // COD orders carry no fee (nothing was captured).
  fees: { online: { pending: 5, confirmed: 5, processing: 15 } },
  summary: [
    'You can cancel your order before it ships.',
    'For paid online orders, a 5% restocking fee applies (15% while your order is being processed).',
    'Once an order has shipped, it can no longer be cancelled — for both Cash on Delivery and Online payment orders.',
  ],
};

// ✅ Pre-cancellation estimate of the restocking fee (%) a customer will be charged.
//    Returns 0 for COD / unpaid orders (no money was captured to refund).
//    The backend is authoritative — this is only used to inform the user up front.
export const getRestockingFeePercentage = (order) => {
  if (!order || order.payment_status !== 'paid') return 0;
  return CANCELLATION_POLICY.fees.online[order.status] ?? 0;
};

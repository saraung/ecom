// src/components/orders/RefundBadge.jsx
import { REFUND_PAYMENT_STATUS_LABELS, REFUND_PAYMENT_STATUS_STYLES } from '../../utils/format';

// ✅ Colored pill for the refund phase of a cancelled order.
//    Single source of truth: order.payment_status from GET /orders or GET /orders/{id}.
//
//      refund_initiated  → 🟡 Refund Processing
//      refund_completed  → 🟢 Refund Completed
//      refund_failed     → 🔴 Refund Failed
//      refunded (legacy) → treated as Refund Completed
//      anything else     → renders nothing (pending / paid / cod_pending / failed)
const RefundBadge = ({ paymentStatus, className = '' }) => {
  if (!REFUND_PAYMENT_STATUS_STYLES[paymentStatus]) return null;

  return (
    <span
      className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold ${
        REFUND_PAYMENT_STATUS_STYLES[paymentStatus]
      } ${className}`}
    >
      {REFUND_PAYMENT_STATUS_LABELS[paymentStatus]}
    </span>
  );
};

export default RefundBadge;
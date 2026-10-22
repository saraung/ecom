// src/components/orders/OrderStatusBadge.jsx
import { ORDER_STATUS_LABELS, ORDER_STATUS_STYLES } from '../../utils/format';

// ✅ Colored pill for an order status
//    (pending | confirmed | processing | shipped | out_for_delivery | delivered |
//     cancelled | rto | refunded)
//    The label is always resolved through ORDER_STATUS_LABELS: CSS `capitalize`
//    cannot split snake_case, so raw values like "out_for_delivery" would leak.
//    Unknown statuses still fall back to the raw value + an untinted pill.
const OrderStatusBadge = ({ status, className = '' }) => (
  <span
    className={`inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold capitalize ${
      ORDER_STATUS_STYLES[status] || 'bg-muted text-muted-foreground'
    } ${className}`}
  >
    {ORDER_STATUS_LABELS[status] || status}
  </span>
);

export default OrderStatusBadge;

// src/components/orders/OrderTotals.jsx
import { formatPrice, taxLabel } from '../../utils/format';

// ✅ Totals breakdown straight from the order response (money strings parsed with Number()).
//    Renders only the rows — the parent provides the card/heading.
//
//    props:
//      order  — order object with subtotal/discount_total/tax_total/shipping_total/grand_total
//      codFee — optional COD handling fee (POST /checkout OrderRead includes cod_fee;
//               the full order from GET /orders does not)
const OrderTotals = ({ order, codFee = 0 }) => {
  const paymentRef = order.transaction_id || (order.payment_method === 'cod' ? order.order_number : null);

  return (
    <div className="text-sm">
    <div className="flex justify-between py-1.5">
      <span className="text-muted-foreground">Subtotal</span>
      <span className="font-medium text-foreground">{formatPrice(order.subtotal)}</span>
    </div>
    {Number(order.discount_total) > 0 && (
      <div className="flex justify-between py-1.5 text-success font-bold">
        <span>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}</span>
        <span className="font-medium">−{formatPrice(order.discount_total)}</span>
      </div>
    )}
    <div className="flex justify-between py-1.5">
      <span className="text-muted-foreground">Tax ({taxLabel()})</span>
      <span className="font-medium text-foreground">{formatPrice(order.tax_total)}</span>
    </div>
    <div className="flex justify-between py-1.5">
      <span className="text-muted-foreground">Shipping</span>
      <span className="font-medium text-success">
        {Number(order.shipping_total) === 0 ? 'Free' : formatPrice(order.shipping_total)}
      </span>
    </div>
    {Number(codFee) > 0 && (
      <div className="flex justify-between py-1.5">
        <span className="text-muted-foreground">COD Handling Fee</span>
        <span className="font-medium text-foreground">{formatPrice(codFee)}</span>
      </div>
    )}
    {paymentRef && (
      <div className="flex justify-between py-1.5 gap-3">
        <span className="text-muted-foreground shrink-0">
          {order.transaction_id ? 'Transaction ID' : 'Payment Reference'}
        </span>
        <span className="font-medium text-foreground text-right break-all">{paymentRef}</span>
      </div>
    )}
    <div className="border-t border-border pt-3 mt-2 flex justify-between items-center">
      <span className="font-extrabold text-foreground tracking-tight">Grand Total</span>
      <span className="font-extrabold text-foreground">{formatPrice(order.grand_total)}</span>
    </div>
  </div>
  );
};

export default OrderTotals;
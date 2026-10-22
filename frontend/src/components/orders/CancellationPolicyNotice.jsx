// src/components/orders/CancellationPolicyNotice.jsx
import { Info } from 'lucide-react';
import { CANCELLATION_POLICY } from '../../utils/format';

// ✅ Professional, reusable cancellation & restocking-fee notice shown on the orders
//    and checkout pages so customers know the cost/rules of cancelling before they act.
//
//    variants:
//      "full"    — titled card with a bulleted list (OrderDetail, Checkout)
//      "compact" — one-line hint with an info icon (OrderCard list)
const CancellationPolicyNotice = ({ variant = 'full', className = '' }) => {
  if (variant === 'compact') {
    return (
      <div className={`flex items-start gap-1.5 text-xs text-muted-foreground ${className}`}>
        <Info size={12} className="flex-shrink-0 mt-0.5 text-muted-foreground" />
        <span>
          Cancellations allowed before shipping. A 5% restocking fee applies on paid online
          orders (15% while processing). No cancellations possible after shipping.
        </span>
      </div>
    );
  }

  return (
    <div
      className={`bg-info-soft border border-info/30 rounded-xl p-4 text-sm ${className}`}
    >
      <div className="flex gap-2.5">
        <Info size={16} className="text-info flex-shrink-0 mt-0.5" />
        <div className="text-muted-foreground">
          <p className="font-semibold text-foreground mb-1">
            Cancellation &amp; Restocking Policy
          </p>
          <ul className="list-disc list-inside space-y-0.5 text-xs text-muted-foreground">
            {CANCELLATION_POLICY.summary.map((line, idx) => (
              <li key={idx}>{line}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};

export default CancellationPolicyNotice;
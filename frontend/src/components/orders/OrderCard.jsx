import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  formatPrice,
  formatDateTime,
  PAYMENT_STATUS_LABELS,
  PAYMENT_METHOD_LABELS,
  canCancelOrder,
  canPayOrder,
} from '../../utils/format';
import OrderStatusBadge from './OrderStatusBadge';
import OrderItemsList from './OrderItemsList';
import RefundBadge from './RefundBadge';
import CancelOrderModal from './CancelOrderModal';
import CancellationPolicyNotice from './CancellationPolicyNotice';

const PREVIEW_ITEMS = 2;

const OrderCard = ({ order, onOrderStatusChanged }) => {
  const [displayOrder, setDisplayOrder] = useState(order);
  const [prevOrder, setPrevOrder] = useState(order);
  const [showCancelModal, setShowCancelModal] = useState(false);

  if (order !== prevOrder) {
    setPrevOrder(order);
    setDisplayOrder(order);
  }

  const items = Array.isArray(displayOrder.items) ? displayOrder.items : [];
  const address = displayOrder.shipping_address;
  const canCancel = canCancelOrder(displayOrder);

  return (
    <div className="bg-card rounded-[2rem] border border-border shadow-[0_10px_30px_rgba(0,0,0,0.02)] dark:shadow-[0_10px_30px_rgba(0,0,0,0.2)] overflow-hidden transition-colors duration-700">
      {/* Header */}
      <div className="flex flex-wrap justify-between items-start gap-3 p-5 sm:p-6 border-b border-border">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <span className="text-base font-extrabold tracking-wide text-foreground">
              {displayOrder.order_number}
            </span>
            <OrderStatusBadge status={displayOrder.status} />
          </div>
          <div className="text-xs sm:text-sm text-muted-foreground font-medium mt-1.5">
            Placed {formatDateTime(displayOrder.placed_at)}
            {displayOrder.payment_method &&
              ` · ${PAYMENT_METHOD_LABELS[displayOrder.payment_method] || displayOrder.payment_method}`}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-extrabold text-foreground whitespace-nowrap tracking-tight">
            {formatPrice(displayOrder.grand_total)}
          </div>
          <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-1">
            {PAYMENT_STATUS_LABELS[displayOrder.payment_status] || displayOrder.payment_status || '—'}
          </div>
          <RefundBadge paymentStatus={displayOrder.payment_status} className="mt-1.5" />
        </div>
      </div>

      {/* Items */}
      {items.length > 0 && (
        <div className="px-5 sm:px-6 py-4">
          <OrderItemsList items={items} maxItems={PREVIEW_ITEMS} />
        </div>
      )}

      {/* Footer */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 px-5 sm:px-6 py-4 bg-primary-soft/50 border-t border-border">
        <div className="flex items-center gap-2 text-[13px] text-muted-foreground font-medium min-w-0">
          <span aria-hidden="true">📍</span>
          <span className="truncate">
            {address
              ? [address.line1, address.city, address.state].filter(Boolean).join(', ')
              : 'Shipping address unavailable'}
          </span>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          {canPayOrder(displayOrder) && (
            <Link
              to={`/checkout?repay=${displayOrder.id}`}
              className="inline-flex items-center justify-center h-11 px-5 rounded-full text-xs font-bold uppercase tracking-widest leading-none text-primary border border-border hover:bg-primary-soft transition-colors"
            >
              💳 Pay Now
            </Link>
          )}
          {canCancel && (
            <button
              type="button"
              onClick={() => setShowCancelModal(true)}
              className="inline-flex items-center justify-center h-11 px-5 rounded-full text-xs font-bold uppercase tracking-widest leading-none text-destructive border border-destructive/30 hover:bg-destructive-soft transition-colors"
            >
              Cancel Order
            </button>
          )}
          <Link
            to={`/orders/${displayOrder.id}`}
            className="group inline-flex items-center justify-center h-11 gap-2 rounded-full bg-primary text-primary-foreground px-6 text-xs font-bold uppercase tracking-widest leading-none shadow-lg shadow-sm hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-300 ease-out"
          >
            View Details
            <span className="inline-block transition-transform duration-300 ease-out group-hover:translate-x-0.5">→</span>
          </Link>
        </div>
      </div>

      {canCancel && (
        <div className="px-5 sm:px-6 pb-4 pt-1">
          <CancellationPolicyNotice variant="compact" />
        </div>
      )}

      {showCancelModal && (
        <CancelOrderModal
          order={displayOrder}
          onClose={() => setShowCancelModal(false)}
          onCancelled={onOrderStatusChanged}
        />
      )}
    </div>
  );
};

export default OrderCard;
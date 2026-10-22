import React, { useState, useEffect, useRef } from 'react';
import { Link, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { useReactToPrint } from 'react-to-print';
import { orderAPI } from '../../api/orders';
import { OrderDetailSkeleton } from '../../components/common/Skeleton';
import {
  formatDateTime,
  formatDay,
  formatPrice,
  ORDER_STATUS_LABELS,
  PAYMENT_STATUS_LABELS,
  PAYMENT_METHOD_LABELS,
  REFUND_PAYMENT_STATUSES,
  canCancelOrder,
  canPayOrder,
  taxLabel,
  storeCountry,
  supportPhone,
} from '../../utils/format';
import {
  OrderStatusBadge,
  OrderItemsList,
  OrderTotals,
  RefundBadge,
  CancelOrderModal,
  CancellationPolicyNotice,
} from '../../components/orders';
import OrderTrackingCard from '../../components/orders/OrderTrackingCard';
import OrderReturns from '../../components/orders/OrderReturns';

const UUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const OrderDetail = () => {
  const { id } = useParams();
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [refundStatusLoading, setRefundStatusLoading] = useState(false);

  const printRef = useRef();

  const fetchOrder = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      setError(null);
      const response = UUID_REGEX.test(id)
        ? await orderAPI.getOrderById(id)
        : await orderAPI.getOrderByNumber(id);
      setOrder(response.data);
    } catch (err) {
      console.error('Error fetching order:', err);
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Failed to load order');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchOrder();
  }, [id]);

  const checkRefundStatus = async () => {
    try {
      setRefundStatusLoading(true);
      const response = await orderAPI.getRefundStatus(order.id);
      const refund = response.data || {};
      setOrder((prev) => ({
        ...prev,
        ...(refund.refund_id ? { refund_id: refund.refund_id } : {}),
        ...(refund.refund_amount != null ? { refund_amount: refund.refund_amount } : {}),
        ...(refund.restocking_fee != null ? { restocking_fee: refund.restocking_fee } : {}),
        ...(refund.fee_percentage != null ? { fee_percentage: refund.fee_percentage } : {}),
        ...(refund.payment_status ? { payment_status: refund.payment_status } : {}),
      }));
      toast.success(refund.message || 'Refund status is up to date');
    } catch (err) {
      console.error('Error checking refund status:', err);
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Could not check the refund status');
    } finally {
      setRefundStatusLoading(false);
    }
  };

  const handlePrint = useReactToPrint({
    contentRef: printRef,
    pageStyle: `
      @page {
        size: 80mm auto;
        margin: 5mm;
      }
      @media print {
        body {
          margin: 0;
          padding: 0;
          background: var(--card) !important;
          -webkit-print-color-adjust: exact;
          print-color-adjust: exact;
        }
        .screen-only {
          display: none !important;
        }
      }
    `,
    onPrintError: (error) => toast.error('Print failed: ' + error.message),
  });

  if (loading) {
    return <OrderDetailSkeleton />;
  }

  if (error || !order) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background transition-colors duration-700 px-4 py-10">
        <div className="w-full max-w-md text-center p-8 sm:p-10 bg-card rounded-[2.5rem] shadow-[0_20px_50px_rgba(0,0,0,0.05)] border border-border">
          <div className="text-4xl mb-4" aria-hidden="true">⚠️</div>
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-foreground">
            Could not load this order
          </h2>
          <p className="text-sm text-muted-foreground font-medium mt-2 mb-8">
            {error || 'Order not found'}
          </p>
          <div className="flex flex-col sm:flex-row justify-center gap-3">
            <button
              onClick={fetchOrder}
              className="bg-primary text-primary-foreground px-10 py-4 rounded-full text-sm font-bold uppercase tracking-widest hover:scale-105 hover:-translate-y-0.5 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl"
            >
              Try Again
            </button>
            <Link
              to="/orders"
              className="inline-flex items-center justify-center bg-card text-foreground border border-border px-10 py-4 rounded-full text-sm font-bold uppercase tracking-widest hover:-translate-y-0.5 hover:bg-primary-soft transition-all duration-300 ease-out shadow-sm"
            >
              My Orders
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const shipping = order.shipping_address;
  const billing = order.billing_address || order.shipping_address;
  const items = Array.isArray(order.items) ? order.items : [];
  const user = order.user;

  // ---------- PROFESSIONAL RECEIPT CONTENT ----------
  const ReceiptContent = () => (
    <div
      style={{
        width: '80mm',
        maxWidth: '100%',
        margin: '0 auto',
        padding: '4mm 2mm',
        fontFamily: "'Courier New', Courier, monospace",
        fontSize: '10pt',
        lineHeight: 1.4,
        color: 'var(--foreground)',
        background: 'var(--card)',
      }}
    >
      {/* ── Store Header ── */}
      <div style={{ textAlign: 'center', marginBottom: '2mm' }}>
        <div style={{ fontSize: '16pt', fontWeight: 'bold', letterSpacing: '1px', marginBottom: '1mm', color: 'var(--primary)' }}>
          YOUR STORE
        </div>
        <div style={{ fontSize: '8pt', color: 'var(--muted-foreground)', lineHeight: 1.3 }}>
          <div>123 Market Street, Sector 5</div>
          <div>Maharashtra, {storeCountry()} - 400001</div>
          {supportPhone() && <div>Phone: {supportPhone()}</div>}
          {taxLabel() === 'GST' && <div>GSTIN: 27AABCU9603R1ZM</div>}
        </div>
      </div>

      <div style={{ borderTop: '2px dashed var(--primary)', margin: '3mm 0' }} />

      {/* ── Receipt Title ── */}
      <div style={{ textAlign: 'center', fontSize: '11pt', fontWeight: 'bold', letterSpacing: '2px', marginBottom: '2mm', color: 'var(--primary)' }}>
        SALES RECEIPT
      </div>

      <div style={{ borderTop: '1px dashed var(--border)', margin: '2mm 0' }} />

      {/* ── Order Info ── */}
      <div style={{ marginBottom: '2mm' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Order #:</span>
          <span style={{ fontWeight: 'bold' }}>{order.order_number}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Date:</span>
          <span>{formatDateTime(order.placed_at)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Status:</span>
          <span style={{ fontWeight: 'bold' }}>
            {ORDER_STATUS_LABELS[order.status] || order.status}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Payment:</span>
          <span>{PAYMENT_METHOD_LABELS[order.payment_method] || order.payment_method || '—'}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Payment Status:</span>
          <span>{PAYMENT_STATUS_LABELS[order.payment_status] || order.payment_status || '—'}</span>
        </div>
        {order.transaction_id && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Txn ID:</span>
            <span style={{ fontWeight: 'bold' }}>{order.transaction_id}</span>
          </div>
        )}
        {!order.transaction_id && order.payment_method === 'cod' && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Payment Ref:</span>
            <span>{order.order_number}</span>
          </div>
        )}
        {order.coupon_code && (
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>Coupon:</span>
            <span style={{ fontWeight: 'bold', color: 'var(--success)' }}>{order.coupon_code}</span>
          </div>
        )}
      </div>

      <div style={{ borderTop: '1px dashed var(--border)', margin: '2mm 0' }} />

      {/* ── Items ── */}
      <div style={{ marginBottom: '2mm' }}>
        <div style={{ fontWeight: 'bold', fontSize: '9pt', letterSpacing: '1px', marginBottom: '2mm', textAlign: 'center', color: 'var(--primary)' }}>
          ITEMS PURCHASED
        </div>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '9pt', tableLayout: 'fixed' }}>
          <thead>
            <tr style={{ borderBottom: '1px dashed var(--primary)' }}>
              <th style={{ textAlign: 'left', padding: '1mm 0', fontWeight: 'bold', width: '42%' }}>Item</th>
              <th style={{ textAlign: 'center', padding: '1mm 0', fontWeight: 'bold', width: '10%' }}>Qty</th>
              <th style={{ textAlign: 'right', padding: '1mm 0', fontWeight: 'bold', width: '24%' }}>Price</th>
              <th style={{ textAlign: 'right', padding: '1mm 0', fontWeight: 'bold', width: '24%' }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, idx) => (
              <tr key={idx}>
                <td style={{ padding: '1mm 0', verticalAlign: 'top' }}>
                  <div style={{ fontWeight: 'bold', overflowWrap: 'anywhere' }}>{item.name}</div>
                  {item.variant_sku && (
                    <div style={{ fontSize: '7.5pt', color: 'var(--muted-foreground)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>SKU: {item.variant_sku}</div>
                  )}
                </td>
                <td style={{ textAlign: 'center', padding: '1mm 0' }}>{item.quantity}</td>
                <td style={{ textAlign: 'right', padding: '1mm 0', fontSize: '8.5pt', fontVariantNumeric: 'tabular-nums' }}>{formatPrice(item.unit_price ?? item.price ?? 0)}</td>
                <td style={{ textAlign: 'right', padding: '1mm 0', fontWeight: 'bold', fontSize: '8.5pt', fontVariantNumeric: 'tabular-nums' }}>
                  {formatPrice((item.unit_price ?? item.price ?? 0) * item.quantity)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ borderTop: '1px dashed var(--border)', margin: '2mm 0' }} />

      {/* ── Totals ── */}
      <div style={{ marginBottom: '2mm' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1mm 0' }}>
          <span>Subtotal</span>
          <span>{formatPrice(order.subtotal)}</span>
        </div>
        {Number(order.discount_total) > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1mm 0', color: 'var(--destructive)' }}>
            <span>Discount</span>
            <span>- {formatPrice(order.discount_total)}</span>
          </div>
        )}
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1mm 0' }}>
          <span>Tax ({taxLabel()})</span>
          <span>{formatPrice(order.tax_total)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1mm 0' }}>
          <span>Shipping</span>
          <span>{Number(order.shipping_total) === 0 ? 'FREE' : formatPrice(order.shipping_total)}</span>
        </div>
        {Number(order.cod_fee) > 0 && (
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1mm 0' }}>
            <span>COD Fee</span>
            <span>{formatPrice(order.cod_fee)}</span>
          </div>
        )}

        <div style={{ borderTop: '2px dashed var(--primary)', margin: '2mm 0' }} />

        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '1mm 0', fontSize: '13pt', fontWeight: 'bold', color: 'var(--primary)' }}>
          <span>TOTAL</span>
          <span>{formatPrice(order.grand_total)}</span>
        </div>
      </div>

      <div style={{ borderTop: '2px dashed var(--primary)', margin: '2mm 0' }} />

      {/* ── Shipping Address ── */}
      <div style={{ marginBottom: '2mm' }}>
        <div style={{ fontWeight: 'bold', fontSize: '9pt', letterSpacing: '1px', marginBottom: '1.5mm', color: 'var(--primary)' }}>
          SHIP TO
        </div>
        {shipping ? (
          <div style={{ fontSize: '9pt', lineHeight: 1.4 }}>
            {user?.full_name && <div style={{ fontWeight: 'bold' }}>{user.full_name}</div>}
            <div>{shipping.line1}</div>
            {shipping.line2 && <div>{shipping.line2}</div>}
            <div>{shipping.city}, {shipping.state} {shipping.postal_code}</div>
            <div>{shipping.country}</div>
            {user?.phone && <div>Ph: {user.phone}</div>}
          </div>
        ) : (
          <div style={{ fontSize: '9pt', color: 'var(--muted-foreground)' }}>Not available</div>
        )}
      </div>

      {/* ── Billing Address (only if different) ── */}
      {billing && shipping && (
        billing.line1 !== shipping.line1 ||
        billing.city !== shipping.city ||
        billing.postal_code !== shipping.postal_code
      ) && (
        <div style={{ marginBottom: '2mm' }}>
          <div style={{ fontWeight: 'bold', fontSize: '9pt', letterSpacing: '1px', marginBottom: '1.5mm', color: 'var(--primary)' }}>
            BILL TO
          </div>
          <div style={{ fontSize: '9pt', lineHeight: 1.4 }}>
            <div>{billing.line1}</div>
            {billing.line2 && <div>{billing.line2}</div>}
            <div>{billing.city}, {billing.state} {billing.postal_code}</div>
            <div>{billing.country}</div>
          </div>
        </div>
      )}

      <div style={{ borderTop: '1px dashed var(--border)', margin: '2mm 0' }} />

      {/* ── Footer ── */}
      <div style={{ textAlign: 'center', fontSize: '8pt', color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
        <div style={{ fontWeight: 'bold', fontSize: '10pt', color: 'var(--foreground)', marginBottom: '1.5mm' }}>
          Thank you for your purchase!
        </div>
        <div>For any queries, contact us at support@yourstore.com</div>
        {supportPhone() && <div>or call {supportPhone()} (Mon-Sat, 10AM - 7PM)</div>}
        <div style={{ marginTop: '2mm', fontSize: '7.5pt', color: 'var(--muted-foreground)' }}>
          Items can be returned within 7 days of delivery.
        </div>
        <div style={{ marginTop: '3mm', fontSize: '7pt', color: 'var(--muted-foreground)', opacity: 0.6 }}>
          This is a computer-generated receipt. No signature required.
        </div>
      </div>
    </div>
  );

  // Hero timeline: Ordered (always done) + one "next milestone" card.
  // Just-confirmed orders show "Arriving by …" — NEVER a "Delivered ✅"
  // box before delivery. Shipped-but-undelivered shows the real ship date.
  const etaLabel = order.expected_delivery_date
    ? formatDay(order.expected_delivery_date)
    : null;
  const timelineSteps = [
    { label: 'Ordered', value: order.placed_at, icon: '🕐', done: !!order.placed_at },
    order.delivered_at
      ? { label: 'Delivered', value: order.delivered_at, icon: '✅', done: true }
      : order.shipped_at
        ? {
            label: order.status === 'out_for_delivery' ? 'Out for Delivery' : 'Shipped',
            value: order.shipped_at, icon: '🚚', done: true,
            hint: etaLabel ? `Arriving by ${etaLabel}` : null,
          }
        : {
            label: 'Arriving by',
            value: null, icon: '📦', done: false,
            hint: etaLabel ?? (order.courier_etd ? `In ${order.courier_etd}` : 'Will update once dispatched'),
          },
  ];

  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        {/* Header with print button */}
        <div className="flex flex-wrap items-center justify-between gap-4 mb-8 sm:mb-10 border-b border-border pb-6">
          <Link
            to="/orders"
            className="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
          >
            ← Back to My Orders
          </Link>
          <button
            onClick={handlePrint}
            className="inline-flex items-center gap-2 bg-card text-foreground border border-border px-6 py-3 rounded-full text-xs font-bold uppercase tracking-widest hover:-translate-y-0.5 hover:bg-primary-soft transition-all duration-300 ease-out shadow-sm"
          >
            Print Receipt
          </button>
        </div>

        {/* Hidden printable component – rendered off-screen */}
        <div style={{ position: 'absolute', left: '-9999px', top: 0, zIndex: -1, width: '80mm' }}>
          <div ref={printRef}>
            <ReceiptContent />
          </div>
        </div>

        {/* ====== Normal view (only visible on screen) ====== */}
        <div className="screen-only">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 lg:gap-8">
            {/* ── Left column ── */}
            <div className="lg:col-span-2 space-y-6">
              {/* 1. Hero: order number + status + timeline */}
              <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-8">
                <div className="flex flex-wrap justify-between items-start gap-4">
                  <div>
                    <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground">
                      {order.order_number}
                    </h1>
                    <p className="text-sm text-muted-foreground font-medium mt-1.5">
                      Placed {formatDateTime(order.placed_at)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-3">
                    <OrderStatusBadge status={order.status} className="px-3 py-1" />
                    {canCancelOrder(order) && (
                      <button
                        onClick={() => setShowCancelModal(true)}
                        className="inline-flex items-center justify-center h-10 px-5 rounded-full text-xs font-bold uppercase tracking-widest leading-none text-destructive border border-destructive/30 hover:bg-destructive-soft transition-colors"
                      >
                        Cancel Order
                      </button>
                    )}
                  </div>
                </div>

                {canCancelOrder(order) && <CancellationPolicyNotice className="mt-5" />}

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-6">
                  {timelineSteps.map((step) => (
                    <div
                      key={step.label}
                      className={`flex items-center gap-3 p-4 rounded-2xl border transition-colors duration-700 ${
                        step.done
                          ? 'bg-primary-soft/50 border-border'
                          : 'bg-transparent border-border/50'
                      }`}
                    >
                      <span className="text-2xl shrink-0" aria-hidden="true">{step.icon}</span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground m-0">
                          {step.label}
                        </p>
                        <p className="text-sm font-medium text-foreground m-0 mt-0.5 leading-snug wrap-break-word">
                          {step.hint ? (
                            <span className={step.done ? '' : 'text-muted-foreground'}>{step.hint}</span>
                          ) : step.value ? (
                            formatDateTime(step.value)
                          ) : (
                            '—'
                          )}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Live shipment tracking — only renders once the order has an
                    AWB, so unshipped orders are unaffected. */}
                <div className="mt-6">
                  <OrderTrackingCard order={order} />
                </div>

                {order.updated_at && (
                  <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mt-5">
                    Last updated {formatDateTime(order.updated_at)}
                  </p>
                )}
              </div>

              {/* 2. Items + Order Summary (merged) */}
              <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-8">
                <div className="flex items-center justify-between mb-5">
                  <h3 className="text-base font-extrabold text-foreground tracking-tight m-0">Items</h3>
                  <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    {items.length} item{items.length === 1 ? '' : 's'}
                  </span>
                </div>
                <OrderItemsList items={items} showSku />
                <div className="border-t border-border mt-6 pt-6">
                  <OrderTotals order={order} />
                </div>
              </div>
              {(order.status === 'delivered' || order.delivered_at) && <OrderReturns key={order.id} orderId={order.id} onOrderChange={() => fetchOrder(true)} />}
            </div>

            {/* ── Right column ── */}
            <div className="space-y-6">
              {/* 3. Payment & Refund (merged) */}
              <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-6">
                <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground mb-4">Payment</h3>
                <dl className="m-0 space-y-3 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted-foreground">Method</dt>
                    <dd className="font-medium text-foreground text-right">
                      {PAYMENT_METHOD_LABELS[order.payment_method] || order.payment_method || '—'}
                    </dd>
                  </div>
                  <div className="flex justify-between items-center gap-3">
                    <dt className="text-muted-foreground">Status</dt>
                    <dd className="font-medium text-foreground text-right flex items-center gap-2 justify-end">
                      {PAYMENT_STATUS_LABELS[order.payment_status] || order.payment_status || '—'}
                      {REFUND_PAYMENT_STATUSES.includes(order.payment_status) && (
                        <RefundBadge paymentStatus={order.payment_status} />
                      )}
                    </dd>
                  </div>
                  {order.transaction_id && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Transaction ID</dt>
                      <dd className="font-medium text-foreground text-right break-all">{order.transaction_id}</dd>
                    </div>
                  )}
                  {!order.transaction_id && order.payment_method === 'cod' && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground">Payment Reference</dt>
                      <dd className="font-medium text-foreground text-right break-all">{order.order_number}</dd>
                    </div>
                  )}
                  {order.coupon_code && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-muted-foreground flex items-center gap-1">Coupon</dt>
                      <dd className="font-medium text-success">{order.coupon_code}</dd>
                    </div>
                  )}
                </dl>

                {canPayOrder(order) && (
                  <Link
                    to={`/checkout?repay=${order.id}`}
                    className="mt-5 block w-full text-center h-11 rounded-full bg-primary text-primary-foreground text-xs font-bold uppercase tracking-widest leading-[2.75rem] hover:bg-primary-hover transition-colors"
                  >
                    💳 Pay Now
                  </Link>
                )}

                {REFUND_PAYMENT_STATUSES.includes(order.payment_status) && (
                  <div className="mt-5 pt-5 border-t border-border">
                    <div className="flex items-center gap-2 mb-3">
                      <span className="text-sm font-extrabold uppercase tracking-widest text-foreground">Refund</span>
                    </div>
                    <dl className="m-0 space-y-2.5 text-sm">
                      {order.refund_amount != null && (
                        <div className="flex justify-between gap-3">
                          <dt className="text-muted-foreground">Refund Amount</dt>
                          <dd className="font-medium text-foreground text-right">{formatPrice(order.refund_amount)}</dd>
                        </div>
                      )}
                      {Number(order.restocking_fee) > 0 && (
                        <div className="flex justify-between gap-3">
                          <dt className="text-muted-foreground">
                            Restocking Fee {order.fee_percentage != null ? `(${order.fee_percentage}%)` : ''}
                          </dt>
                          <dd className="font-medium text-foreground text-right">−{formatPrice(order.restocking_fee)}</dd>
                        </div>
                      )}
                      {order.refund_id && (
                        <div className="flex justify-between gap-3">
                          <dt className="text-muted-foreground shrink-0">Refund ID</dt>
                          <dd className="font-medium text-foreground text-right break-all">{order.refund_id}</dd>
                        </div>
                      )}
                    </dl>

                    {order.payment_status === 'refund_initiated' && (
                      <p className="mt-4 text-xs font-medium text-warning bg-warning-soft/40 px-3 py-2 rounded-xl">
                        Your refund is being processed. It will reach your account within 5 business days.
                      </p>
                    )}
                    {order.payment_status === 'refund_completed' && (
                      <p className="mt-4 text-xs font-medium text-success bg-success-soft/40 px-3 py-2 rounded-xl">
                        Your refund has been completed.
                      </p>
                    )}
                    {order.payment_status === 'refund_failed' && (
                      <p className="mt-4 text-xs font-medium text-destructive bg-destructive-soft/40 px-3 py-2 rounded-xl">
                        Your refund failed. Please contact support for assistance.
                      </p>
                    )}

                    {(order.payment_status === 'refund_initiated' || order.payment_status === 'refund_failed') && (
                      <button
                        onClick={checkRefundStatus}
                        disabled={refundStatusLoading}
                        className="w-full mt-4 inline-flex items-center justify-center h-11 rounded-full border border-border bg-card text-foreground text-xs font-bold uppercase tracking-widest disabled:opacity-60 disabled:cursor-not-allowed hover:-translate-y-0.5 hover:bg-primary-soft transition-all duration-300 ease-out"
                      >
                        {refundStatusLoading ? 'Checking…' : 'Check Refund Status'}
                      </button>
                    )}
                  </div>
                )}
              </div>

              {/* 4. Addresses & Contact (merged) */}
              <div className="bg-card rounded-4xl border border-border shadow-sm p-5 sm:p-6">
                <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground mb-4 flex items-center gap-2">
                  <span aria-hidden="true">📍</span> Shipping Address
                </h3>
                {shipping ? (
                  <div className="text-sm text-muted-foreground leading-relaxed space-y-0.5">
                    {shipping.label && (
                      <span className="inline-block bg-primary-soft text-primary-soft-foreground px-2.5 py-1 rounded-full mb-2 text-[10px] font-bold uppercase tracking-wider">
                        {shipping.label}
                      </span>
                    )}
                    {shipping.full_name && <p className="font-bold text-foreground m-0">{shipping.full_name}</p>}
                    <p className="m-0">{shipping.line1}</p>
                    {shipping.line2 && <p className="m-0">{shipping.line2}</p>}
                    <p className="m-0">{[shipping.city, shipping.state, shipping.postal_code].filter(Boolean).join(', ')}</p>
                    {shipping.country && <p className="m-0">{shipping.country}</p>}
                    {user?.phone && <p className="m-0 mt-1">{user.phone}</p>}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">Not available</p>
                )}

                {billing && shipping && (
                  billing.line1 !== shipping.line1 ||
                  billing.city !== shipping.city ||
                  billing.postal_code !== shipping.postal_code
                ) && (
                  <div className="mt-5 pt-5 border-t border-border">
                    <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground mb-4 flex items-center gap-2">
                      <span aria-hidden="true">📍</span> Billing Address
                    </h3>
                    <div className="text-sm text-muted-foreground leading-relaxed space-y-0.5">
                      {billing.full_name && <p className="font-bold text-foreground m-0">{billing.full_name}</p>}
                      <p className="m-0">{billing.line1}</p>
                      {billing.line2 && <p className="m-0">{billing.line2}</p>}
                      <p className="m-0">{[billing.city, billing.state, billing.postal_code].filter(Boolean).join(', ')}</p>
                      {billing.country && <p className="m-0">{billing.country}</p>}
                    </div>
                  </div>
                )}

                {user && (user.full_name || user.email || user.phone) && (
                  <div className="mt-5 pt-5 border-t border-border">
                    <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground mb-3">Contact</h3>
                    <div className="text-sm space-y-0.5">
                      {user.full_name && <p className="font-bold text-foreground m-0">{user.full_name}</p>}
                      {user.email && <p className="m-0 text-muted-foreground">{user.email}</p>}
                      {user.phone && <p className="m-0 text-muted-foreground">{user.phone}</p>}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {showCancelModal && (
          <CancelOrderModal
            order={order}
            onClose={() => setShowCancelModal(false)}
            onCancelled={() => fetchOrder(true)}
          />
        )}
      </div>
    </div>
  );
};

export default OrderDetail;

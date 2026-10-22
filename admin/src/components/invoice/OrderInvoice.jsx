// src/components/invoice/OrderInvoice.jsx
import React from 'react';
import { formatPrice, formatDate } from '../../utils/format';

const formatDateTime = (value) => {
  if (!value) return '—';
  return formatDate(value, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getPaymentStatus = (order) =>
  (order.payment_status || 'pending').toLowerCase();

const getPaymentLabel = (order) => {
  const status = getPaymentStatus(order);
  const labels = {
    paid: 'PAID',
    cod_pending: 'COD — PENDING',
    pending: 'PENDING',
    failed: 'FAILED',
    refund_initiated: 'REFUND INITIATED',
    refund_completed: 'REFUNDED',
    refund_failed: 'REFUND FAILED',
    refunded: 'REFUNDED',
  };
  return labels[status] || status.replace(/_/g, ' ').toUpperCase();
};

const OrderInvoice = ({ order }) => {
  const company = 'EC Store';
  const items = Array.isArray(order.items) ? order.items : [];
  const ship = order.shipping_address || {};
  const subtotal = order.subtotal || 0;
  const discount = order.discount_total || order.discount || 0;
  const itemSubtotal = subtotal + discount;
  const tax = order.tax_total || order.tax || 0;
  const shipping = order.shipping_total || order.shipping || 0;
  const codFee = order.cod_fee || 0;
  const total = order.grand_total || order.total || 0;

  const styles = {
    page: {
      fontFamily: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
      color: '#111827',
      background: '#ffffff',
      maxWidth: '720px',
      margin: '0 auto',
      padding: '28px',
      fontSize: '13px',
      lineHeight: 1.4,
    },
    header: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      borderBottom: '3px solid #111827',
      paddingBottom: '14px',
      marginBottom: '16px',
    },
    brand: { fontSize: '20px', fontWeight: 800, letterSpacing: '0.5px' },
    brandSub: { fontSize: '10px', color: '#6b7280', marginTop: '2px' },
    invoiceTitle: {
      textAlign: 'right',
      fontSize: '26px',
      fontWeight: 800,
      letterSpacing: '3px',
      color: '#111827',
      lineHeight: 1.1,
    },
    invoiceNo: { fontSize: '12px', color: '#374151', marginTop: '4px' },
    grid: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '4px 24px',
      marginBottom: '16px',
    },
    cellLabel: { fontSize: '9px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.5px' },
    cellValue: { fontSize: '12px', fontWeight: 600, marginTop: '2px' },
    addresses: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '16px',
      marginBottom: '18px',
    },
    addrBlock: { border: '1px solid #e5e7eb', borderRadius: '8px', padding: '10px 12px' },
    addrTitle: { fontSize: '10px', textTransform: 'uppercase', color: '#6b7280', letterSpacing: '0.5px', marginBottom: '6px' },
    addrName: { fontWeight: 700, fontSize: '13px' },
    addrLine: { fontSize: '12px', color: '#374151', marginTop: '1px' },
    table: { width: '100%', borderCollapse: 'collapse', marginBottom: '14px' },
    th: {
      textAlign: 'left',
      fontSize: '9px',
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
      color: '#6b7280',
      borderBottom: '2px solid #e5e7eb',
      padding: '5px 8px',
    },
    thRight: { textAlign: 'right', borderBottom: '2px solid #e5e7eb', padding: '5px 8px', fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.5px', color: '#6b7280' },
    td: { padding: '6px 8px', borderBottom: '1px solid #f3f4f6', fontSize: '12px' },
    tdRight: { padding: '6px 8px', borderBottom: '1px solid #f3f4f6', fontSize: '12px', textAlign: 'right' },
    itemName: { fontWeight: 600 },
    itemMeta: { fontSize: '10px', color: '#6b7280' },
    totals: { display: 'flex', justifyContent: 'flex-end', marginBottom: '12px' },
    totalsBox: { width: '250px' },
    totalRow: { display: 'flex', justifyContent: 'space-between', fontSize: '12px', padding: '2px 0' },
    grandRow: {
      display: 'flex',
      justifyContent: 'space-between',
      fontSize: '15px',
      fontWeight: 800,
      borderTop: '2px solid #111827',
      marginTop: '4px',
      paddingTop: '6px',
    },
    paymentBox: {
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      padding: '10px 12px',
      marginBottom: '12px',
    },
    paymentLabel: { fontSize: '9px', textTransform: 'uppercase', letterSpacing: '0.5px', color: '#6b7280' },
    paymentValue: { fontSize: '13px', fontWeight: 700, marginTop: '2px' },
    badge: {
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: '999px',
      fontSize: '10px',
      fontWeight: 700,
      letterSpacing: '0.5px',
      border: '1.5px solid',
      marginTop: '3px',
    },
    footer: {
      borderTop: '1px solid #e5e7eb',
      paddingTop: '8px',
      textAlign: 'center',
      fontSize: '10px',
      color: '#6b7280',
    },
  };

  const paid = ['paid', 'cod_pending'].includes(getPaymentStatus(order));
  const badgeColor = paid
    ? { borderColor: '#16a34a', color: '#16a34a' }
    : { borderColor: '#d97706', color: '#d97706' };

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <div style={styles.brand}>{company}</div>
          <div style={styles.brandSub}>E-commerce order invoice</div>
        </div>
        <div style={styles.invoiceTitle}>
          INVOICE
          <div style={styles.invoiceNo}>#{order.order_number}</div>
        </div>
      </div>

      {/* Meta */}
      <div style={styles.grid}>
        <div>
          <div style={styles.cellLabel}>Order Date</div>
          <div style={styles.cellValue}>{formatDateTime(order.placed_at || order.created_at)}</div>
        </div>
        <div>
          <div style={styles.cellLabel}>Payment Status</div>
          <div style={styles.cellValue}>
            <span style={{ ...styles.badge, ...badgeColor }}>{getPaymentLabel(order)}</span>
          </div>
        </div>
        <div>
          <div style={styles.cellLabel}>Payment Method</div>
          <div style={styles.cellValue}>{(order.payment_method || 'Not specified').toUpperCase()}</div>
        </div>
        <div>
          <div style={styles.cellLabel}>Transaction ID</div>
          <div style={styles.cellValue}>{order.transaction_id || '—'}</div>
        </div>
      </div>

      {/* Addresses */}
      <div style={styles.addresses}>
        <div style={styles.addrBlock}>
          <div style={styles.addrTitle}>Billed To</div>
          <div style={styles.addrName}>
            {order.user?.full_name || ship.full_name || 'Guest'}
          </div>
          <div style={styles.addrLine}>{order.user?.email || '—'}</div>
          <div style={styles.addrLine}>{order.user?.phone || ship.phone || ''}</div>
        </div>
        <div style={styles.addrBlock}>
          <div style={styles.addrTitle}>Ship To</div>
          <div style={styles.addrName}>{ship.full_name || '—'}</div>
          <div style={styles.addrLine}>{ship.line1 || ship.address_line1 || ''}</div>
          {ship.line2 && <div style={styles.addrLine}>{ship.line2}</div>}
          <div style={styles.addrLine}>
            {[ship.city, ship.state, ship.postal_code || ship.pincode].filter(Boolean).join(', ')}
          </div>
          {ship.country && <div style={styles.addrLine}>{ship.country}</div>}
          {ship.phone && <div style={styles.addrLine}>Phone: {ship.phone}</div>}
        </div>
      </div>

      {/* Items */}
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>#</th>
            <th style={styles.th}>Item</th>
            <th style={styles.th}>Qty</th>
            <th style={styles.thRight}>Unit Price</th>
            <th style={styles.thRight}>Amount</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={item.id ?? item.product_id ?? index}>
              <td style={styles.td}>{index + 1}</td>
              <td style={styles.td}>
                <div style={styles.itemName}>{item.product_name}</div>
                {item.variant_sku && <div style={styles.itemMeta}>SKU: {item.variant_sku}</div>}
              </td>
              <td style={styles.td}>{item.quantity}</td>
              <td style={styles.tdRight}>{formatPrice(item.unit_price)}</td>
              <td style={styles.tdRight}>{formatPrice(item.unit_price * item.quantity)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Totals */}
      <div style={styles.totals}>
        <div style={styles.totalsBox}>
          <div style={styles.totalRow}>
            <span>Item Subtotal</span>
            <span>{formatPrice(itemSubtotal)}</span>
          </div>
          {discount > 0 && (
            <div style={styles.totalRow}>
              <span>{order.coupon_code ? `Coupon Discount (${order.coupon_code})` : 'Discount'}</span>
              <span>-{formatPrice(discount)}</span>
            </div>
          )}
          <div style={styles.totalRow}>
            <span>Subtotal</span>
            <span>{formatPrice(subtotal)}</span>
          </div>
          {tax > 0 && (
            <div style={styles.totalRow}>
              <span>Tax</span>
              <span>{formatPrice(tax)}</span>
            </div>
          )}
          {shipping > 0 && (
            <div style={styles.totalRow}>
              <span>Shipping</span>
              <span>{formatPrice(shipping)}</span>
            </div>
          )}
          {codFee > 0 && (
            <div style={styles.totalRow}>
              <span>COD Fee</span>
              <span>{formatPrice(codFee)}</span>
            </div>
          )}
          <div style={styles.grandRow}>
            <span>Total Paid</span>
            <span>{formatPrice(total)}</span>
          </div>
        </div>
      </div>

      {/* Coupon / payment summary */}
      {(order.coupon_code || paid) && (
        <div style={styles.paymentBox}>
          {order.coupon_code && (
            <div>
              <div style={styles.paymentLabel}>Coupon Applied</div>
              <div style={styles.paymentValue}>{order.coupon_code}</div>
            </div>
          )}
          {paid && (
            <div style={{ marginTop: order.coupon_code ? '10px' : 0 }}>
              <div style={styles.paymentLabel}>Collection Status</div>
              <div style={styles.paymentValue}>
                {getPaymentStatus(order) === 'cod_pending' ? 'Cash on delivery — pending collection' : 'Payment received'}
              </div>
            </div>
          )}
        </div>
      )}

      <div style={styles.footer}>
        Thank you for your business! For order related enquiries, contact support with invoice #{order.order_number}.
      </div>
    </div>
  );
};

export default OrderInvoice;
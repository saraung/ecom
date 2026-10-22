// src/components/invoice/PackingSlip.jsx
import React from 'react';
import { formatDate } from '../../utils/format';

const PackingSlip = ({ order }) => {
  const company = 'EC Store';
  const items = Array.isArray(order.items) ? order.items : [];
  const ship = order.shipping_address || {};
  const totalItems = items.reduce((sum, item) => sum + (item.quantity || 0), 0);

  const styles = {
    page: {
      fontFamily: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
      color: '#111827',
      background: '#ffffff',
      maxWidth: '700px',
      margin: '0 auto',
      padding: '40px',
      fontSize: '14px',
      lineHeight: 1.5,
    },
    header: {
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'flex-start',
      borderBottom: '3px solid #111827',
      paddingBottom: '20px',
      marginBottom: '24px',
    },
    brand: { fontSize: '22px', fontWeight: 800, letterSpacing: '0.5px' },
    brandSub: { fontSize: '11px', color: '#6b7280', marginTop: '2px' },
    title: {
      textAlign: 'right',
      fontSize: '26px',
      fontWeight: 800,
      letterSpacing: '3px',
      color: '#111827',
      lineHeight: 1.1,
    },
    meta: { fontSize: '13px', color: '#374151', marginTop: '6px' },
    addrBlock: {
      border: '1px solid #e5e7eb',
      borderRadius: '8px',
      padding: '14px 16px',
      marginBottom: '24px',
    },
    addrTitle: {
      fontSize: '11px',
      textTransform: 'uppercase',
      color: '#6b7280',
      letterSpacing: '0.5px',
      marginBottom: '8px',
    },
    addrName: { fontWeight: 700, fontSize: '15px' },
    addrLine: { fontSize: '13px', color: '#374151', marginTop: '2px' },
    table: { width: '100%', borderCollapse: 'collapse', marginBottom: '20px' },
    th: {
      textAlign: 'left',
      fontSize: '10px',
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
      color: '#6b7280',
      borderBottom: '2px solid #e5e7eb',
      padding: '8px 10px',
    },
    thRight: {
      textAlign: 'right',
      borderBottom: '2px solid #e5e7eb',
      padding: '8px 10px',
      fontSize: '10px',
      textTransform: 'uppercase',
      letterSpacing: '0.5px',
      color: '#6b7280',
    },
    td: { padding: '10px', borderBottom: '1px solid #f3f4f6', fontSize: '13px' },
    tdRight: {
      padding: '10px',
      borderBottom: '1px solid #f3f4f6',
      fontSize: '13px',
      textAlign: 'right',
      fontWeight: 700,
    },
    itemName: { fontWeight: 600 },
    itemMeta: { fontSize: '11px', color: '#6b7280' },
    summary: {
      display: 'flex',
      justifyContent: 'space-between',
      fontSize: '13px',
      padding: '8px 0 0',
      borderTop: '1px solid #e5e7eb',
      marginBottom: '28px',
      fontWeight: 700,
    },
    checkRow: {
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: '24px',
      marginBottom: '24px',
    },
    checkBox: {
      borderTop: '2px solid #e5e7eb',
      paddingTop: '6px',
      fontSize: '12px',
      color: '#6b7280',
      lineHeight: '2.4',
    },
    notice: {
      border: '1px dashed #9ca3af',
      borderRadius: '8px',
      padding: '10px 14px',
      fontSize: '12px',
      color: '#4b5563',
      marginBottom: '28px',
    },
    footer: {
      borderTop: '1px solid #e5e7eb',
      paddingTop: '14px',
      textAlign: 'center',
      fontSize: '11px',
      color: '#6b7280',
    },
  };

  return (
    <div style={styles.page}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <div style={styles.brand}>{company}</div>
          <div style={styles.brandSub}>E-commerce order packing slip</div>
        </div>
        <div>
          <div style={styles.title}>PACKING SLIP</div>
          <div style={styles.meta}>Order #{order.order_number}</div>
          <div style={styles.meta}>{formatDate(order.placed_at || order.created_at)}</div>
          <div style={styles.meta}>Order ID: {order.id}</div>
        </div>
      </div>

      {/* Ship to */}
      <div style={styles.addrBlock}>
        <div style={styles.addrTitle}>Ship To</div>
        <div style={styles.addrName}>{ship.full_name || '—'}</div>
        <div style={styles.addrLine}>{ship.line1 || ship.address_line1 || ''}</div>
        {ship.line2 && <div style={styles.addrLine}>{ship.line2}</div>}
        <div style={styles.addrLine}>
          {[ship.city, ship.state, ship.postal_code || ship.pincode].filter(Boolean).join(', ')}
        </div>
        {(ship.country || ship.phone) && (
          <div style={styles.addrLine}>
            {[ship.country, ship.phone ? `Phone: ${ship.phone}` : ''].filter(Boolean).join(' • ')}
          </div>
        )}
      </div>

      {/* Items */}
      <table style={styles.table}>
        <thead>
          <tr>
            <th style={styles.th}>#</th>
            <th style={styles.th}>Item</th>
            <th style={styles.thRight}>Qty</th>
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
              <td style={styles.tdRight}>{item.quantity}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Summary + verification */}
      <div style={styles.summary}>
        <span>Total Items</span>
        <span>{totalItems}</span>
      </div>

      <div style={styles.checkRow}>
        <div style={styles.checkBox}>
          Number of packages: ____________
          <br />
          Packed by: ____________
        </div>
        <div style={styles.checkBox}>
          Date / Time: ____________
          <br />
          Verified by: ____________
        </div>
      </div>

      <div style={styles.notice}>
        Please verify the contents against this slip before sealing. Do not include prices in
        this package.
      </div>

      <div style={styles.footer}>
        {company} — Internal packing document. Not an invoice.
      </div>
    </div>
  );
};

export default PackingSlip;
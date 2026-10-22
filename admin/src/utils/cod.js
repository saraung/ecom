// src/utils/cod.js
// Pure helpers for the COD reconciliation UI. Kept free of React so they can
// be unit-tested with `node --test`.

export const BATCH_STATUS_LABELS = {
  pending: 'Awaiting bank credit',
  reconciled: 'Reconciled',
  discrepancy: 'Discrepancy',
  void: 'Void',
};

export const ITEM_STATUS_LABELS = {
  matched: 'Matched',
  amount_mismatch: 'Amount mismatch',
  order_not_found: 'Order not found',
  not_cod: 'Not a COD order',
  not_delivered: 'Not delivered',
  cash_not_collected: 'Cash not collected',
  already_remitted: 'Already remitted',
  duplicate: 'Duplicate line',
  adjustment: 'Excluded adjustment',
};

export const BATCH_BADGE = {
  pending: 'bg-warning/15 text-warning',
  reconciled: 'bg-success/15 text-success',
  discrepancy: 'bg-destructive/15 text-destructive',
  void: 'bg-muted text-muted-foreground',
};

export const ITEM_BADGE = {
  matched: 'bg-success/15 text-success',
  amount_mismatch: 'bg-warning/15 text-warning',
  order_not_found: 'bg-destructive/15 text-destructive',
  not_cod: 'bg-destructive/15 text-destructive',
  not_delivered: 'bg-warning/15 text-warning',
  cash_not_collected: 'bg-warning/15 text-warning',
  already_remitted: 'bg-info/15 text-info',
  duplicate: 'bg-destructive/15 text-destructive',
  adjustment: 'bg-muted text-muted-foreground',
};

export const batchStatusLabel = (status) => BATCH_STATUS_LABELS[status] || status || '—';
export const itemStatusLabel = (status) => ITEM_STATUS_LABELS[status] || status || '—';
export const batchBadgeClass = (status) => BATCH_BADGE[status] || 'bg-muted text-foreground';
export const itemBadgeClass = (status) => ITEM_BADGE[status] || 'bg-muted text-foreground';

/** Number of lines still requiring an accept/exclude decision. */
export const openItemCount = (batch) =>
  (batch?.items || []).filter(
    (item) => item.match_status !== 'matched' && item.match_status !== 'adjustment'
  ).length;

/**
 * Line statuses the backend will accept as a manual match. Everything else
 * (not-Cod, order-not-found, duplicate, already-remitted) must be excluded.
 */
export const ACCEPTABLE_ITEM_STATUSES = [
  'amount_mismatch',
  'not_delivered',
  'cash_not_collected',
];

export const canAcceptItem = (item) =>
  Boolean(item?.order_id) && ACCEPTABLE_ITEM_STATUSES.includes(item?.match_status);

export const todayInputValue = (now = new Date()) => {
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
  return local.toISOString().slice(0, 10);
};

export const emptyManualRow = () => ({
  awb: '',
  order_number: '',
  cod_amount: '',
  deductions: '0',
  net_amount: '',
});

/** Client-side pre-flight checks; the server remains authoritative. */
export const validateManualForm = ({ crfId, remittanceDate, rows }) => {
  const errors = [];
  if (!String(crfId || '').trim()) errors.push('CRF / batch reference is required.');
  if (!remittanceDate) errors.push('Remittance date is required.');
  if (!Array.isArray(rows) || rows.length === 0) {
    errors.push('Add at least one remittance line.');
    return errors;
  }
  rows.forEach((row, index) => {
    const label = `Line ${index + 1}`;
    if (!String(row.awb || '').trim() && !String(row.order_number || '').trim()) {
      errors.push(`${label}: enter an AWB or an order number.`);
    }
    const cod = Number(row.cod_amount);
    if (row.cod_amount !== '' && (!Number.isFinite(cod) || cod < 0)) {
      errors.push(`${label}: COD amount must be zero or more.`);
    }
    const deductions = Number(row.deductions || 0);
    if (!Number.isFinite(deductions) || deductions < 0) {
      errors.push(`${label}: deductions must be zero or more.`);
    }
    const net = Number(row.net_amount);
    if (row.net_amount !== '' && (!Number.isFinite(net) || net < 0)) {
      errors.push(`${label}: net amount must be zero or more.`);
    }
    if (
      row.cod_amount !== '' &&
      row.net_amount !== '' &&
      Number.isFinite(cod) &&
      Number.isFinite(net) &&
      Number.isFinite(deductions) &&
      Math.abs(cod - deductions - net) > 0.01
    ) {
      errors.push(`${label}: COD minus deductions must equal the net amount.`);
    }
  });
  return errors;
};

/** Build the backend payload, omitting blank optional fields. */
export const buildManualPayload = ({ crfId, remittanceDate, notes, rows }) => ({
  crf_id: String(crfId).trim(),
  remittance_date: remittanceDate,
  notes: String(notes || '').trim() || null,
  items: rows.map((row) => ({
    awb: String(row.awb || '').trim() || null,
    order_number: String(row.order_number || '').trim() || null,
    cod_amount: row.cod_amount === '' ? null : Number(row.cod_amount),
    deductions: row.deductions === '' ? 0 : Number(row.deductions),
    net_amount: row.net_amount === '' ? null : Number(row.net_amount),
  })),
});

/** e.g. "+₹20.00" / "−₹20.00"; 0 renders as an em dash. */
export const signedDifference = (value, formatter = (n) => String(n)) => {
  const amount = Number(value || 0);
  if (Math.abs(amount) < 0.005) return '—';
  return `${amount > 0 ? '+' : '−'}${formatter(Math.abs(amount))}`;
};


/** Normalise FastAPI error bodies (string or structured 409 details). */
export const apiErrorMessage = (err, fallback = 'Something went wrong') => {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (detail && typeof detail === 'object') {
    if (typeof detail.message === 'string' && detail.message.trim()) return detail.message;
    return Object.values(detail).filter((v) => typeof v === 'string').join(' ') || fallback;
  }
  return err?.message || fallback;
};

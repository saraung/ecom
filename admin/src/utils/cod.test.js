import test from 'node:test';
import assert from 'node:assert/strict';
import {
  apiErrorMessage,
  batchBadgeClass,
  buildManualPayload,
  canAcceptItem,
  emptyManualRow,
  itemStatusLabel,
  openItemCount,
  signedDifference,
  todayInputValue,
  validateManualForm,
} from './cod.js';

test('manual form requires a reference and an AWB or order number', () => {
  const errors = validateManualForm({
    crfId: '',
    remittanceDate: '',
    rows: [{ ...emptyManualRow() }],
  });
  assert.ok(errors.some((e) => /CRF/.test(e)));
  assert.ok(errors.some((e) => /date/.test(e)));
  assert.ok(errors.some((e) => /AWB or an order number/.test(e)));
});

test('manual form checks COD minus deductions equals net', () => {
  const base = { crfId: 'CRF-1', remittanceDate: '2026-10-20' };
  assert.deepEqual(validateManualForm({
    ...base,
    rows: [{ awb: 'AWB-1', cod_amount: '1500', deductions: '30', net_amount: '1470' }],
  }), []);
  const errors = validateManualForm({
    ...base,
    rows: [{ awb: 'AWB-1', cod_amount: '1500', deductions: '30', net_amount: '1400' }],
  });
  assert.ok(errors.some((e) => /must equal the net amount/.test(e)));
});

test('manual payload trims references and converts numeric strings', () => {
  assert.deepEqual(buildManualPayload({
    crfId: '  CRF-9 ',
    remittanceDate: '2026-10-20',
    notes: '  ',
    rows: [{ awb: ' AWB-9 ', order_number: '', cod_amount: '1500.5', deductions: '', net_amount: '1500.5' }],
  }), {
    crf_id: 'CRF-9',
    remittance_date: '2026-10-20',
    notes: null,
    items: [{
      awb: 'AWB-9',
      order_number: null,
      cod_amount: 1500.5,
      deductions: 0,
      net_amount: 1500.5,
    }],
  });
});

test('open discrepancy count ignores matched and excluded lines', () => {
  const batch = { items: [
    { match_status: 'matched' },
    { match_status: 'adjustment' },
    { match_status: 'order_not_found' },
    { match_status: 'amount_mismatch' },
  ] };
  assert.equal(openItemCount(batch), 2);
  assert.equal(openItemCount({}), 0);
});

test('only backend-acceptable line statuses expose an Accept action', () => {
  for (const status of ['amount_mismatch', 'not_delivered', 'cash_not_collected']) {
    assert.equal(canAcceptItem({ order_id: 'order-1', match_status: status }), true);
  }
  for (const status of ['not_cod', 'order_not_found', 'already_remitted', 'duplicate', 'matched']) {
    assert.equal(canAcceptItem({ order_id: 'order-1', match_status: status }), false);
  }
  assert.equal(canAcceptItem({ match_status: 'amount_mismatch' }), false);
  assert.equal(canAcceptItem(null), false);
});

test('badges fall back safely for unknown statuses', () => {
  assert.equal(batchBadgeClass('reconciled'), 'bg-success/15 text-success');
  assert.equal(batchBadgeClass('mystery'), 'bg-muted text-foreground');
  assert.equal(itemStatusLabel('already_remitted'), 'Already remitted');
  assert.equal(itemStatusLabel('mystery'), 'mystery');
});

test('signed difference shows direction and treats zero as an em dash', () => {
  assert.equal(signedDifference(20, (n) => `₹${n.toFixed(2)}`), '+₹20.00');
  assert.equal(signedDifference(-20, (n) => `₹${n.toFixed(2)}`), '−₹20.00');
  assert.equal(signedDifference(0.001), '—');
});

test('today input value uses local calendar date', () => {
  const now = new Date(2026, 9, 20, 23, 30, 0);
  assert.equal(todayInputValue(now), '2026-10-20');
});


test('API error helper reads string and structured FastAPI details', () => {
  assert.equal(apiErrorMessage({ response: { data: { detail: 'Nope' } } }), 'Nope');
  assert.equal(
    apiErrorMessage({ response: { data: { detail: { message: 'Bank differs', difference: -20 } } } }),
    'Bank differs'
  );
  assert.equal(apiErrorMessage({}, 'Fallback'), 'Fallback');
});

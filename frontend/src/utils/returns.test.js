import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCustomerReturnHistory, buildReturnPayload, createReturnSubmitter, createReturnWorkspaceLoader, estimateReturn, loadReturnWorkspace, validateReturnFiles } from './returns.js';

const eligibility = {
  eligible: true,
  items: [{ order_item_id: 'first', eligible: true, available_quantity: 3, remaining_merchandise_amount: '318.60' },
    { order_item_id: 'second', eligible: true, available_quantity: 1, remaining_merchandise_amount: '212.40' },
    { order_item_id: 'blocked', eligible: false, available_quantity: 1, remaining_merchandise_amount: '50.00' }],
  reasons: ['damaged', 'wrong_product', 'defective', 'missing_accessory', 'wrong_variant', 'changed_mind', 'other'].map((value) => ({ value })),
  policy: { max_images: 6, max_image_bytes: 1024, required_photo_reasons: [], fee_percent: 0 },
};
const input = (extra = {}) => ({ eligibility, quantities: { first: 1 }, reason: 'damaged', description: 'Arrived damaged', files: [], key: 'stable-request', ...extra });

test('customer selects partial quantities and multiple purchased items with all supported reasons', () => {
  for (const { value } of eligibility.reasons) {
    const data = buildReturnPayload(input({ reason: value, quantities: { first: 2, second: 1 } }));
    assert.deepEqual(data.items, [{ order_item_id: 'first', quantity: 2 }, { order_item_id: 'second', quantity: 1 }]);
    assert.equal(data.reason, value);
    assert.equal(data.idempotency_key, 'stable-request');
  }
  assert.deepEqual(estimateReturn(eligibility, { first: 2, second: 1 }), { amount: 424.8, fee: 0 });
});

test('invalid or ineligible quantities and incomplete Other reason block submission', () => {
  for (const quantities of [{}, { first: 4 }, { first: -1 }, { first: 1.5 }, { blocked: 1 }, { unknown: 1 }]) {
    assert.throws(() => buildReturnPayload(input({ quantities })));
  }
  assert.throws(() => buildReturnPayload(input({ reason: 'other', description: '  short  ' })), /explain Other/);
  assert.throws(() => buildReturnPayload(input({ eligibility: { ...eligibility, eligible: false } })));
});

test('evidence requirements come from the backend policy and multiple bounded images are accepted', () => {
  const png = new File(['image'], 'photo.png', { type: 'image/png' });
  assert.doesNotThrow(() => buildReturnPayload(input({ files: [png, png] })));
  const required = { ...eligibility, policy: { ...eligibility.policy, required_photo_reasons: ['damaged'] } };
  assert.throws(() => buildReturnPayload(input({ eligibility: required })), /photo is required/);
  assert.doesNotThrow(() => buildReturnPayload(input({ eligibility: required, reason: 'changed_mind' })));
  assert.throws(() => validateReturnFiles([new File(['<svg>'], 'photo.svg', { type: 'image/svg+xml' })], eligibility.policy), /JPEG/);
  assert.throws(() => validateReturnFiles([new File(['x'.repeat(1025)], 'photo.jpg', { type: 'image/jpeg' })], eligibility.policy), /size limit/);
  assert.throws(() => validateReturnFiles([png, png], eligibility.policy, 5), /at most/);
});

test('captured fee estimates use net merchandise value and reject invalid selections', () => {
  const policy = { ...eligibility, policy: { ...eligibility.policy, fee_percent: 10 } };
  assert.deepEqual(estimateReturn(policy, { first: 1 }), { amount: 95.58, fee: 10.62 });
  assert.deepEqual(estimateReturn(policy, { first: 9, blocked: 1 }), { amount: 0, fee: 0 });
});

test('customer return history keeps milestones and folds internal and duplicate courier events', () => {
  const history = buildCustomerReturnHistory([
    { action: 'requested', to_status: 'requested', created_at: '1', note: 'Wrong bag received' },
    { action: 'approved', to_status: 'approved', created_at: '2', note: 'Return is verified' },
    { action: 'shipping_created', to_status: 'approved', created_at: '3' },
    { action: 'tracking_attached', to_status: 'approved', created_at: '4' },
    { action: 'pickup_request_started', to_status: 'approved', created_at: '5' },
    { action: 'pickup_requested', to_status: 'approved', created_at: '6' },
    { action: 'return_shipped', to_status: 'return_shipped', created_at: '7', details: { status: 'RETURN PICKED UP', location: 'Hub' } },
    { action: 'tracking_scan', to_status: 'return_shipped', created_at: '8', details: { status: 'RETURN PICKED UP', location: 'Hub' } },
    { action: 'tracking_scan', to_status: 'return_shipped', created_at: '9', details: { status: 'RETURN IN TRANSIT', location: 'Hub' } },
    { action: 'tracking_scan', to_status: 'return_shipped', created_at: '10', details: { status: 'RETURN IN TRANSIT', location: 'Hub' } },
    { action: 'tracking_scan', to_status: 'received', created_at: '11', details: { status: 'RETURN DELIVERED', location: 'Warehouse' } },
    { action: 'inspection_passed', to_status: 'inspection', created_at: '12', note: 'Received in good condition' },
    { action: 'refund_requested', to_status: 'refund_pending', created_at: '13' },
    { action: 'refunded', to_status: 'refunded', created_at: '14' },
  ]);

  assert.deepEqual(history.map((entry) => entry.label), [
    'Return requested', 'Return approved', 'Pickup scheduled', 'Picked up', 'In transit',
    'Received', 'Inspection completed', 'Refund processing', 'Refund completed',
  ]);
  assert.equal(history.find((entry) => entry.key === 'requested').note, 'Wrong bag received');
  assert.equal(history.find((entry) => entry.key === 'received').location, 'Warehouse');
});

test('parallel submission coalesces and failed-network retry keeps the exact submission key and photos', async () => {
  let calls = 0;
  const forms = [];
  const api = { create: async (id, form) => {
    calls += 1;
    forms.push(form);
    if (calls === 1) throw new Error('Network response lost');
    return { data: { id: 'existing-return', status: 'requested' } };
  } };
  const submit = createReturnSubmitter(api);
  const photo = new File(['image'], 'photo.png', { type: 'image/png' });
  const data = buildReturnPayload(input({ files: [photo] }));
  const first = submit('order', data, [photo]);
  assert.equal(submit('order', data, [photo]), first);
  await assert.rejects(first, /response lost/);
  const result = await submit('order', data, [photo]);
  assert.equal(result.data.id, 'existing-return');
  assert.equal(calls, 2);
  assert.equal(forms[0].get('data'), forms[1].get('data'));
  assert.equal(JSON.parse(forms[1].get('data')).idempotency_key, 'stable-request');
  assert.equal(forms[1].getAll('files').length, 1);
});

test('workspace loads owned order eligibility and status history together and exposes load failures', async () => {
  const calls = [];
  const api = { eligibility: async (id) => { calls.push(id); return { data: eligibility }; },
    list: async (id, page) => { calls.push([id, page]); return { data: { returns: [{ status: 'refund_pending', history: ['received', 'inspection'] }] } }; } };
  const result = await loadReturnWorkspace(api, 'owned-order', 2);
  assert.deepEqual(calls, ['owned-order', ['owned-order', 2]]);
  assert.equal(result.listing.returns[0].status, 'refund_pending');
  api.list = async () => { throw new Error('Cannot load history'); };
  await assert.rejects(loadReturnWorkspace(api, 'owned-order', 1), /Cannot load history/);
});

test('late customer order/page results and unmounted errors cannot overwrite current returns', async () => {
  const pending = new Map();
  const results = [];
  const failures = [];
  const api = { eligibility: async () => ({ data: eligibility }), list: (id) => new Promise((resolve, reject) => pending.set(id, { resolve, reject })) };
  const loader = createReturnWorkspaceLoader({ api, onStart: () => {}, onResult: (value) => results.push(value.listing), onError: (error) => failures.push(error) });
  const first = loader.run('old-order', 1);
  const second = loader.run('current-order', 1);
  pending.get('current-order').resolve({ data: { returns: ['current'] } });
  await second;
  pending.get('old-order').resolve({ data: { returns: ['old'] } });
  await first;
  assert.deepEqual(results, [{ returns: ['current'] }]);
  const unmounted = loader.run('unmounted', 1);
  loader.cancel();
  pending.get('unmounted').reject(new Error('late error'));
  await unmounted;
  assert.deepEqual(failures, []);
});

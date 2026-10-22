import test from 'node:test';
import assert from 'node:assert/strict';
import { createReturnLoader, hasReturnPermission, loadSimulatorShipments, returnActions, runReturnAction, RETURN_SHIPPING_EVENTS, runReturnSimulatorEvent } from './returns.js';

const admin = { role: 'admin', permissions: ['orders.view', 'orders.update', 'orders.refund', 'shipping.manage'] };
const requested = { id: 'return-id', status: 'requested', payment_method: 'online' };
const inspected = { ...requested, status: 'inspection', inspection_passed: true, received_at: '2026-10-05T12:00:00Z' };

test('empty and read-only grants cannot expose admin money or lifecycle actions', () => {
  assert.equal(hasReturnPermission({ role: 'admin', permissions: [] }, 'orders.refund'), false);
  assert.deepEqual(returnActions(requested, { role: 'admin', permissions: [] }), []);
  assert.deepEqual(returnActions(requested, { permissions: ['orders.view'] }), []);
  assert.ok(!returnActions(inspected, { permissions: ['orders.view', 'orders.update'] }).includes('refund'));
  assert.ok(returnActions(inspected, admin).includes('refund'));
});

test('only the legal next return actions are shown; receipt is not refund authorization', () => {
  assert.deepEqual(returnActions(requested, admin), ['approve', 'reject', 'cancel']);
  assert.ok(!returnActions({ ...requested, status: 'approved' }, admin).includes('refund'));
  assert.ok(!returnActions({ ...requested, status: 'received' }, admin).includes('refund'));
  assert.ok(!returnActions({ ...inspected, inspection_passed: false }, admin).includes('refund'));
  for (const status of ['refunded', 'rejected', 'cancelled', 'refund_pending']) assert.deepEqual(returnActions({ ...inspected, status }, admin), []);
});

test('approval and rejection use the return decision API and rejection requires a note', async () => {
  const calls = [];
  const api = { decision: async (...args) => { calls.push(args); return { data: { status: 'approved' } }; } };
  await assert.rejects(runReturnAction(api, requested, admin, 'reject'), /rejection note/);
  await runReturnAction(api, requested, admin, 'approve', { note: ' Return instructions ' });
  await runReturnAction(api, requested, admin, 'reject', { note: 'Not eligible' });
  assert.deepEqual(calls, [['return-id', { decision: 'approve', note: 'Return instructions' }], ['return-id', { decision: 'reject', note: 'Not eligible' }]]);
});

test('inspection explicitly captures an outcome and note before online refund requests', async () => {
  const calls = [];
  const api = { inspection: async (...args) => calls.push(['inspection', ...args]), refund: async (...args) => calls.push(['refund', ...args]) };
  await assert.rejects(runReturnAction(api, { ...requested, status: 'received' }, admin, 'inspection', { passed: true }), /outcome and enter a note/);
  await runReturnAction(api, { ...requested, status: 'received' }, admin, 'inspection', { passed: true, note: 'Verified selected items' });
  await runReturnAction(api, inspected, admin, 'refund');
  await assert.rejects(runReturnAction(api, requested, admin, 'refund'), /not available/);
  assert.deepEqual(calls[1], ['refund', 'return-id', {}]);
});

test('COD uses attested repayment references; online refunds cannot be substituted', async () => {
  const calls = [];
  const api = { refund: async (...args) => { calls.push(args); return { data: { status: 'refund_pending', refund: { requires_approval: true } } }; } };
  await assert.rejects(runReturnAction(api, { ...inspected, payment_method: 'cod' }, admin, 'refund'), /actual COD repayment/);
  const result = await runReturnAction(api, { ...inspected, payment_method: 'cod' }, admin, 'refund', { manual_transfer_reference: ' BANK-123 ' });
  assert.equal(result.data.refund.requires_approval, true);
  assert.deepEqual(calls[0], ['return-id', { manual_transfer_reference: 'BANK-123' }]);
  await assert.rejects(runReturnAction(api, inspected, admin, 'refund', { manual_transfer_reference: 'BANK-123' }), /original payment/);
});

test('return tracking uses the attached AWB interface and requires shipping permission', async () => {
  const calls = [];
  const api = { tracking: async (...args) => calls.push(args), sync: async (id) => calls.push(id) };
  const row = { ...requested, status: 'approved' };
  const data = { tracking_number: ' REVERSE-123 ', courier_name: ' Courier ', provider: 'shiprocket' };
  await assert.rejects(runReturnAction(api, row, { permissions: ['orders.view', 'orders.update'] }, 'tracking', data), /not available/);
  await runReturnAction(api, row, admin, 'tracking', data);
  await runReturnAction(api, { ...row, status: 'return_shipped', tracking_number: 'REVERSE-123', tracking_provider: 'shiprocket' }, admin, 'sync');
  assert.deepEqual(calls, [['return-id', { tracking_number: 'REVERSE-123', courier_name: 'Courier', provider: 'shiprocket' }], 'return-id']);
});

test('late list/detail responses cannot overwrite newer filters and unmounted requests are cancelled', async () => {
  const resolvers = new Map();
  const results = [];
  const errors = [];
  const loader = createReturnLoader({ load: (key) => new Promise((resolve, reject) => resolvers.set(key, { resolve, reject })),
    onStart: () => {}, onResult: (data) => results.push(data), onError: (error) => errors.push(error) });
  const old = loader.run('old-filter');
  const fresh = loader.run('new-filter');
  resolvers.get('new-filter').resolve({ data: ['new-return'] });
  await fresh;
  resolvers.get('old-filter').resolve({ data: ['stale-return'] });
  await old;
  assert.deepEqual(results, [['new-return']]);
  const cancelled = loader.run('unmounted');
  loader.cancel();
  resolvers.get('unmounted').reject(new Error('late error'));
  await cancelled;
  assert.deepEqual(errors, []);
  const failed = loader.run('failure');
  resolvers.get('failure').reject(new Error('History unavailable'));
  await failed;
  assert.equal(errors[0].message, 'History unavailable');
});

test('approved returns prioritize reverse booking; partial booking resumes and disables manual forks', async () => {
  const row = { ...requested, status: 'approved' };
  const calls = [];
  const api = { createShipment: async (...args) => { calls.push(args); return { data: { ...row, status: 'return_shipped', tracking_number: 'REVERSE-AWB' } }; } };
  const actions = returnActions(row, admin);
  assert.ok(actions.indexOf('createShipment') < actions.indexOf('tracking'));
  await runReturnAction(api, row, admin, 'createShipment');
  for (const partial of [{ shipping_requested_at: '2026-10-05' }, { shiprocket_order_id: 'REVERSE-ID', shiprocket_shipment_id: 'REVERSE-SHIP' }]) {
    assert.ok(!returnActions({ ...row, ...partial }, admin).includes('tracking'));
    await runReturnAction(api, { ...row, ...partial }, admin, 'createShipment');
  }
  assert.deepEqual(calls, [['return-id'], ['return-id'], ['return-id']]);
});

test('booking requires approval and shipping grants and disappears after independent AWB attachment', async () => {
  const api = { createShipment: () => { throw new Error('must not be called'); } };
  for (const row of [requested, inspected, { ...requested, status: 'approved', tracking_number: 'OTHER-AWB' }, { ...requested, status: 'return_shipped', tracking_number: 'REVERSE-AWB' }]) {
    await assert.rejects(runReturnAction(api, row, admin, 'createShipment'), /not available/);
  }
  await assert.rejects(runReturnAction(api, { ...requested, status: 'approved' }, { permissions: ['orders.view', 'orders.update'] }, 'createShipment'), /not available/);
});

test('reverse simulator dispatches the return ID and cannot dispatch a forward shipment or RTO event', async () => {
  const calls = [];
  const api = { simulate: async (...args) => { calls.push(args); return { data: { return_status: 'received' } }; } };
  const row = { shipment_type: 'return', return_id: 'return-id', order_id: 'original-order', awb_code: 'REVERSE-AWB' };
  for (const step of RETURN_SHIPPING_EVENTS) await runReturnSimulatorEvent(api, row, step, 'Warehouse');
  assert.ok(calls.every(([id]) => id === 'return-id'));
  assert.deepEqual(calls.at(-1), ['return-id', { event: 'delivered', activity: 'RETURN DELIVERED', location: 'Warehouse' }]);
  assert.throws(() => runReturnSimulatorEvent(api, { order_id: 'original-order', awb_code: 'FORWARD-AWB' }, RETURN_SHIPPING_EVENTS[0]), /reverse shipment/);
  assert.throws(() => runReturnSimulatorEvent(api, row, { event: 'rto_delivered', status: 'RTO DELIVERED' }), /Outbound RTO/);
  assert.throws(() => runReturnSimulatorEvent(api, { ...row, awb_code: null }, RETURN_SHIPPING_EVENTS[0]), /return AWB/);
});

test('simulator loads return details independently of the outbound order count', async () => {
  const reverse = { shipment_type: 'return', return_id: 'return-id', order_id: 'original-order', awb_code: 'REVERSE-AWB',
    return_status: 'refunded', reason_label: 'Damaged product', items: [{ product_name: 'Purchased item', quantity: 2 }] };
  const result = await loadSimulatorShipments({
    loadForward: () => ({ data: { shipments: Array.from({ length: 17 }, (_, index) => ({ order_id: `order-${index}` })) } }),
    loadReturns: () => ({ data: { shipments: [reverse], provider: 'simulator' } }), canViewReturns: true,
  });
  assert.equal(result.forward.shipments.length, 17);
  assert.deepEqual(result.reverse.shipments, [reverse]);
  assert.equal(result.reverse.provider, 'simulator');
  assert.equal(result.forward.error, null);
  assert.equal(result.reverse.error, null);
});

test('one simulator endpoint failing cannot hide the other shipment type or masquerade as an empty list', async () => {
  for (const failed of ['forward', 'reverse']) {
    const failure = { response: { data: { detail: 'Endpoint unavailable' } } };
    const load = (type) => type === failed ? Promise.reject(failure) : { data: { shipments: [{ id: type }], provider: 'simulator' } };
    const result = await loadSimulatorShipments({ loadForward: () => load('forward'), loadReturns: () => load('reverse'), canViewReturns: true });
    assert.equal(result[failed].error, 'Endpoint unavailable');
    assert.deepEqual(result[failed].shipments, []);
    assert.equal(result[failed === 'forward' ? 'reverse' : 'forward'].shipments.length, 1);
  }
});

test('refreshed permissions load returns and stale permission-era responses cannot erase them', async () => {
  const pending = [];
  const results = [];
  let returnCalls = 0;
  const loader = createReturnLoader({
    load: async (allowed) => ({ data: await loadSimulatorShipments({
      loadForward: () => new Promise((resolve) => pending.push(resolve)),
      loadReturns: () => { returnCalls += 1; return { data: { shipments: [{ return_id: 'new-return', awb_code: 'REVERSE-AWB' }] } }; },
      canViewReturns: allowed,
    }) }), onStart: () => {}, onResult: (result) => results.push(result), onError: assert.fail,
  });
  const cached = loader.run(false);
  await Promise.resolve();
  const refreshed = loader.run(true);
  await Promise.resolve();
  pending[1]({ data: { shipments: [{ order_id: 'fresh-order' }] } });
  await refreshed;
  pending[0]({ data: { shipments: [{ order_id: 'cached-order' }] } });
  await cached;
  assert.equal(returnCalls, 1);
  assert.equal(results.length, 1);
  assert.equal(results[0].reverse.shipments[0].return_id, 'new-return');
  assert.equal(results[0].forward.shipments[0].order_id, 'fresh-order');
});

test('malformed return shipment responses are reported explicitly', async () => {
  const result = await loadSimulatorShipments({
    loadForward: () => ({ data: { shipments: [] } }), loadReturns: () => ({ data: { shipments: null } }), canViewReturns: true,
  });
  assert.match(result.reverse.error, /Invalid return shipment response/);
  assert.equal(result.forward.error, null);
});

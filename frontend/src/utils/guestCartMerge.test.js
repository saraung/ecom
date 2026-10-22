import test from 'node:test';
import assert from 'node:assert/strict';
import { createGuestCartMerger } from './guestCartMerge.js';

const saved = (items) => {
  const data = new Map([['cart', JSON.stringify(items)]]);
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
    read: () => JSON.parse(data.get('cart') || '[]'),
  };
};

test('partial failures retain only unacknowledged entries and retry their stable keys', async () => {
  const storage = saved([{ id: 'a', quantity: 2 }, { id: 'b', quantity: 3 }]);
  const calls = [];
  let fail = true;
  const merge = createGuestCartMerger({ storage, addItem: async (item) => {
    calls.push(item);
    if (item.variant_id === 'b' && fail) throw new Error('stock conflict');
  } });
  const first = await merge();
  assert.equal(first.failed.length, 1);
  assert.deepEqual(storage.read().map((item) => item.id), ['b']);
  fail = false;
  await merge();
  assert.equal(calls.length, 3);
  assert.equal(calls[1].merge_key, calls[2].merge_key);
  assert.equal(storage.getItem('cart'), null);
});

test('lost response retries the same idempotent request without double addition', async () => {
  const storage = saved([{ id: 'a', quantity: 2 }]);
  const receipts = new Set();
  let quantity = 0;
  let lostResponse = true;
  const merge = createGuestCartMerger({ storage, addItem: async (item) => {
    if (!receipts.has(item.merge_key)) {
      receipts.add(item.merge_key);
      quantity += item.quantity;
    }
    if (lostResponse) throw new Error('response lost');
  } });
  await merge();
  lostResponse = false;
  await merge();
  assert.equal(quantity, 2);
  assert.equal(storage.getItem('cart'), null);
});

test('duplicate entries add all quantities while variants of the same product remain distinct', async () => {
  const storage = saved([
    { id: 'product', variant: { id: 'v1' }, quantity: 1 },
    { id: 'product', variant_id: 'v1', quantity: 2 },
    { id: 'product', variant: { id: 'v2' }, quantity: 3 },
  ]);
  const totals = { v1: 5, v2: 0 };
  const merge = createGuestCartMerger({ storage, addItem: async (item) => {
    totals[item.variant_id] += item.quantity;
  } });
  await merge();
  assert.deepEqual(totals, { v1: 8, v2: 3 });
});

test('concurrent merge triggers share one flight', async () => {
  const storage = saved([{ id: 'a', quantity: 1 }]);
  let calls = 0;
  const merge = createGuestCartMerger({ storage, addItem: async () => { calls++; } });
  const first = merge();
  assert.equal(merge(), first);
  await first;
  assert.equal(calls, 1);
});

test('entries added while merging are preserved', async () => {
  const storage = saved([{ id: 'a', quantity: 1 }]);
  const merge = createGuestCartMerger({ storage, addItem: async () => {
    storage.setItem('cart', JSON.stringify([...storage.read(), { id: 'b', quantity: 2 }]));
  } });
  await merge();
  assert.deepEqual(storage.read(), [{ id: 'b', quantity: 2 }]);
});

test('extra quantity added to an in-flight entry survives with a new request identity', async () => {
  const storage = saved([{ id: 'a', quantity: 2 }]);
  let calls = 0;
  const requests = [];
  const merge = createGuestCartMerger({ storage, addItem: async (item) => {
    requests.push(item);
    if (calls++ === 0) {
      const items = storage.read();
      items[0].quantity += 3;
      storage.setItem('cart', JSON.stringify(items));
    }
  } });
  await merge();
  assert.equal(storage.read()[0].quantity, 3);
  await merge();
  assert.equal(requests[1].quantity, 3);
  assert.notEqual(requests[0].merge_key, requests[1].merge_key);
});

test('corrupt storage is preserved and no request is sent', async () => {
  const storage = saved([]);
  storage.setItem('cart', '{corrupt');
  const merge = createGuestCartMerger({ storage, addItem: async () => assert.fail('request sent') });
  await assert.rejects(merge());
  assert.equal(storage.getItem('cart'), '{corrupt');
});

test('invalid entries remain saved rather than silently disappearing', async () => {
  const storage = saved([{ name: 'No variant', quantity: 1 }]);
  const merge = createGuestCartMerger({ storage, addItem: async () => assert.fail('request sent') });
  assert.equal((await merge()).failed.length, 1);
  assert.equal(storage.read().length, 1);
});

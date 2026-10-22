import test from 'node:test';
import assert from 'node:assert/strict';
import { createReportLoader } from './reportLoader.js';

test('partial failure explicitly marks unavailable data and clears prior results on start', async () => {
  let published = { data: { sales: 'old' }, failures: [] };
  const load = createReportLoader({
    requests: [
      { key: 'sales', load: async () => { throw new Error('offline'); } },
      { key: 'orders', load: async () => ({ data: { count: 2 } }) },
    ],
    onStart: () => { published = null; },
    onResult: (result) => { published = result; },
  });
  const flight = load({ from_date: '2026-10-05' });
  assert.equal(published, null);
  await flight;
  assert.deepEqual(published, { data: { orders: { count: 2 } }, failures: ['sales'] });
});

test('an old filter response cannot overwrite the latest filter results', async () => {
  let finishOld;
  const old = new Promise((resolve) => { finishOld = resolve; });
  const results = [];
  const load = createReportLoader({
    requests: [{ key: 'sales', load: (params) => params.range === 'old' ? old : Promise.resolve({ data: 'new' }) }],
    onStart: () => {}, onResult: (result) => results.push(result),
  });
  const first = load({ range: 'old' });
  await load({ range: 'new' });
  finishOld({ data: 'old' });
  await first;
  assert.deepEqual(results, [{ data: { sales: 'new' }, failures: [] }]);
});

test('a synchronous request error is reported as unavailable', async () => {
  let result;
  await createReportLoader({
    requests: [{ key: 'revenue', load: () => { throw new Error('bad request'); } }],
    onStart: () => {}, onResult: (value) => { result = value; },
  })({});
  assert.deepEqual(result, { data: {}, failures: ['revenue'] });
});

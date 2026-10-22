import test from 'node:test';
import assert from 'node:assert/strict';
import { catalogParams, loadCatalogPage } from './catalog.js';

test('category links preserve UUID and request entire descendant catalog', () => {
  const id = '13e9175c-f2d8-45be-aa33-3dcc280f2820';
  const params = catalogParams({ category: id, sort: 'price-low', page: 2 });
  assert.equal(params.category_id, id);
  assert.equal(params.include_descendants, true);
  assert.equal(params.sort, 'price_asc');
  assert.equal(params.page, 2);
});

test('suggestions send bounded server search instead of filtering cached first page', async () => {
  let request;
  const api = { get: async (url, options) => {
    request = { url, options };
    return { data: { products: [{ slug: 'beyond-first-page' }], total: 1, total_pages: 1 } };
  } };
  const signal = new AbortController().signal;
  const page = await loadCatalogPage(api, { search: '  Beyond twenty  ', limit: 5 }, signal);
  assert.equal(request.options.params.search, 'Beyond twenty');
  assert.equal(request.options.params.limit, 5);
  assert.equal(request.options.signal, signal);
  assert.equal(page.products[0].slug, 'beyond-first-page');
});

test('blank query is omitted and malformed responses fail rather than appear empty', async () => {
  assert.equal(catalogParams({ search: '  ' }).search, undefined);
  await assert.rejects(loadCatalogPage({ get: async () => ({ data: [] }) }, {}), /Invalid catalog response/);
});

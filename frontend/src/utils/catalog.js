const sorts = { default: 'newest', 'price-low': 'price_asc', 'price-high': 'price_desc', name: 'name_asc' };

export function catalogParams({ search = '', category = 'all', sort = 'default', page = 1, limit = 20 } = {}) {
  const params = { page, limit, sort: sorts[sort] || sort, include_pagination: true };
  if (search.trim()) params.search = search.trim().slice(0, 100);
  if (category && category !== 'all') {
    params.category_id = category;
    params.include_descendants = true;
  }
  return params;
}

export async function loadCatalogPage(api, filters, signal) {
  const response = await api.get('/products/', { params: catalogParams(filters), signal });
  if (!Array.isArray(response.data?.products) || !Number.isInteger(response.data.total)) {
    throw new Error('Invalid catalog response');
  }
  return response.data;
}

import React, { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import ProductCard from '../../components/common/ProductCard';
import { ProductGridSkeleton } from '../../components/common/Skeleton';
import api from '../../api/axios';
import { categoryAPI } from '../../api/category';
import { loadCatalogPage } from '../../utils/catalog';

// Circular category thumbnail (Myntra-style). Falls back to the name
// initial on a neutral tile when no image is set — never blank space.
const CategoryThumb = ({ category, size = 'w-7 h-7 text-xs' }) => {
  const [failed, setFailed] = useState(false);
  if (category?.image_url && !failed) {
    return (
      <img
        src={category.image_url}
        alt=""
        aria-hidden="true"
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={`${size} rounded-full object-cover border border-border shrink-0`}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={`${size} rounded-full bg-muted text-muted-foreground flex items-center justify-center font-semibold shrink-0`}
    >
      {(category?.name || '?').charAt(0).toUpperCase()}
    </span>
  );
};

// Stable empty array: `data ?? []` would create a new identity on every
// render and defeat the memoised category tree.
const EMPTY_CATEGORIES = [];

const ProductList = () => {  const [searchParams] = useSearchParams();
  const [sortBy, setSortBy] = useState('default');
  const [selectedCategory, setSelectedCategory] = useState(searchParams.get('category') || 'all');
  const [page, setPage] = useState(1);

  const searchQuery = searchParams.get('search') || '';
  const categoryParam = searchParams.get('category');

  // Categories rarely change, so they are cached for ten minutes.
  const categoriesQuery = useQuery({
    queryKey: ['categories'],
    queryFn: () => categoryAPI.getCategories().then((res) => res.data),
    staleTime: 10 * 60 * 1000,
  });
  const categories = categoriesQuery.data ?? EMPTY_CATEGORIES;

  // One cache entry per filter combination. `keepPreviousData` keeps the
  // current grid on screen while a new page/filter loads (no layout jump),
  // and revisiting a filter the shopper already saw renders instantly.
  const productsQuery = useQuery({
    queryKey: ['catalog', { search: searchQuery, category: selectedCategory, sort: sortBy, page }],
    queryFn: ({ signal }) =>
      loadCatalogPage(
        api,
        { search: searchQuery, category: selectedCategory, sort: sortBy, page },
        signal
      ),
    placeholderData: keepPreviousData,
  });

  const filteredProducts = productsQuery.data?.products || [];
  const total = productsQuery.data?.total || 0;
  const totalPages = productsQuery.data?.total_pages || 0;
  // Skeleton only on the first load of this key; page changes keep old data.
  const loading = productsQuery.isLoading;
  const error = productsQuery.isError
    ? productsQuery.error?.response?.data?.detail || 'Failed to load products. Please try again.'
    : categoriesQuery.isError
      ? 'Failed to load categories. Please try again.'
      : '';

  // Build hierarchical tree for tabs
  const categoryTree = useMemo(() => {
    const buildTree = (parentId = null) => {
      return categories
        .filter(cat => cat.parent_id === parentId)
        .sort((a, b) => a.name.localeCompare(b.name))
        .map(cat => ({
          ...cat,
          children: buildTree(cat.id)
        }));
    };
    return buildTree();
  }, [categories]);

  // Get the full path (ancestors) from root to the selected category
  const selectedCategoryPath = useMemo(() => {
    if (selectedCategory === 'all') return [];

    const findPath = (nodes, targetId, path = []) => {
      for (const node of nodes) {
        const newPath = [...path, node];
        if (node.id === targetId) return newPath;
        if (node.children && node.children.length) {
          const found = findPath(node.children, targetId, newPath);
          if (found) return found;
        }
      }
      return null;
    };

    return findPath(categoryTree, selectedCategory) || [];
  }, [categoryTree, selectedCategory]);

  // A filter that shrinks the result set can leave `page` beyond the last
  // page; clamp to the backend's count instead of showing an empty grid.
  useEffect(() => {
    const lastPage = Math.max(1, productsQuery.data?.total_pages || 1);
    if (page > lastPage) setPage(lastPage);
  }, [productsQuery.data, page]);

  // Sync the selected category from the URL (`/products?category=<id>`),
  // e.g. when arriving from a search suggestion.
  useEffect(() => {
    setSelectedCategory(categoryParam || 'all');
  }, [categoryParam]);

  // Replacing a query resets pagination; React Query aborts the superseded
  // request automatically, so stale pages can no longer overwrite fresh ones.
  useEffect(() => {
    setPage(1);
  }, [searchQuery, sortBy, selectedCategory]);

  // Subtree product totals (direct product_count summed down the tree).
  const subtreeCount = (node) => {
    let total = Number(node.product_count) || 0;
    (node.children || []).forEach((child) => {
      total += subtreeCount(child);
    });
    return total;
  };

  // Selected node + its direct children (Baymard intermediary layer).
  const selectedNode = selectedCategoryPath.length > 0
    ? selectedCategoryPath[selectedCategoryPath.length - 1]
    : null;
  const selectedChildren = selectedNode?.children || [];
  // Tiles show the selected node's children; on a leaf, its siblings
  // instead — so sideways navigation never strands the shopper.
  const tileParentName = selectedChildren.length > 0
    ? selectedNode?.name
    : (selectedCategoryPath.length > 1
      ? selectedCategoryPath[selectedCategoryPath.length - 2]?.name
      : null);
  // Keep the selected category in the row so its image and title stay
  // visible; it is rendered in a selected state below instead of being
  // removed and leaving only its siblings.
  const siblingItems = selectedCategoryPath.length > 1
    ? (selectedCategoryPath[selectedCategoryPath.length - 2]?.children || [])
    : [];
  const tileItems = selectedChildren.length > 0 ? selectedChildren : siblingItems;

  // Clear all filters
  const clearFilters = () => {
    setSelectedCategory('all');
    setSortBy('default');
  };

  // Loading state
  if (loading) {
    return (
      <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        <div className="mb-4 sm:mb-6 md:mb-8">
          <div className="animate-pulse h-8 sm:h-9 md:h-10 w-48 sm:w-56 rounded-xl bg-muted" />
        </div>
        <ProductGridSkeleton count={8} />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center bg-card rounded-lg shadow-md p-6 sm:p-8 max-w-md mx-4">
          <div className="text-4xl sm:text-5xl mb-4">⚠️</div>
          <p className="text-destructive text-base sm:text-lg font-medium">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 bg-primary text-primary-foreground px-6 py-2 rounded-lg hover:bg-primary-hover transition text-sm sm:text-base"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between mb-4 sm:mb-6 md:mb-8 gap-3 sm:gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl md:text-3xl font-bold text-foreground">
            All Products
          </h1>
          {searchQuery && (
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Results for: <span className="font-medium text-muted-foreground">"{searchQuery}"</span>
              <span className="ml-1 text-primary font-medium">
                ({total} products)
              </span>
            </p>
          )}
          {selectedCategory !== 'all' && !searchQuery && (
            <p className="text-xs sm:text-sm text-muted-foreground mt-1">
              Category: <span className="font-medium text-muted-foreground">
                {categories.find(c => c.id === selectedCategory)?.name}
              </span>
              <span className="ml-1 text-primary font-medium">
                ({total} products)
              </span>
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* Sort Dropdown */}
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="px-3 sm:px-4 py-1.5 sm:py-2 text-sm border border-border rounded-lg focus:border-ring focus:ring-2 focus:ring-indigo-200 outline-none transition bg-card min-w-[120px] sm:min-w-[140px]"
            aria-label="Sort products"
          >
            <option value="default">Sort By</option>
            <option value="price-low">Price: Low to High</option>
            <option value="price-high">Price: High to Low</option>
            <option value="name">Name: A to Z</option>
          </select>
        </div>
      </div>

      {/* Horizontal Hierarchical Category Tabs */}
      <div className="mb-6 space-y-2">
        {/* Root row: "All" + top-level categories */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setSelectedCategory('all')}
            className={`px-3 py-1.5 text-sm rounded-full transition-colors whitespace-nowrap ${
              selectedCategory === 'all'
                ? 'bg-primary text-primary-foreground font-medium'
                : 'bg-muted text-muted-foreground hover:bg-muted/80'
            }`}
          >
            All
          </button>

          {categoryTree.map((category) => {
            const isSelected = selectedCategory === category.id;
            const isAncestor = selectedCategoryPath.some(p => p.id === category.id);
            return (
              <button
                key={category.id}
                onClick={() => setSelectedCategory(category.id)}
                className={`pl-1.5 pr-3.5 py-1.5 text-sm rounded-full transition-colors whitespace-nowrap inline-flex items-center gap-1.5 ${
                  isSelected
                    ? 'bg-primary text-primary-foreground font-medium'
                    : isAncestor
                    ? 'bg-primary/20 text-primary font-medium'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                <CategoryThumb category={category} />
                {category.name}
              </button>
            );
          })}
        </div>

        {/* Baymard intermediary layer: children of the selected category
            as image tiles (identifying imagery, above products); on a
            leaf, its siblings instead — replacing the old indented rows. */}
        {tileItems.length > 0 && (
          <div>
            {tileParentName && (
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                {selectedChildren.length > 0 ? `Shop ${tileParentName}` : `More in ${tileParentName}`}
              </p>
            )}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 pt-1">
            {tileItems.map((child) => {
              const isSelectedTile = child.id === selectedCategory;
              return (
                <button
                  key={child.id}
                  onClick={() => setSelectedCategory(child.id)}
                  aria-pressed={isSelectedTile}
                  className={`group flex items-center gap-3 p-3 rounded-xl border transition-colors text-left min-w-0 ${
                    isSelectedTile
                      ? 'border-primary bg-primary/10'
                      : 'border-border bg-card hover:bg-muted'
                  }`}
                >
                  <CategoryThumb category={child} size="w-12 h-12 text-base" />
                  <span className="min-w-0">
                    <span
                      className={`block font-medium text-sm truncate transition-colors ${
                        isSelectedTile ? 'text-primary' : 'text-foreground group-hover:text-primary'
                      }`}
                    >
                      {child.name}
                    </span>
                    <span className="block text-xs text-muted-foreground mt-0.5">
                      {subtreeCount(child)} product{subtreeCount(child) === 1 ? '' : 's'}
                    </span>
                  </span>
                </button>
              );
            })}
          </div>
          </div>
        )}
      </div>

      {/* Products Grid */}
      {filteredProducts.length === 0 ? (
        <div className="text-center py-8 sm:py-12 bg-card rounded-lg shadow-md">
          <div className="text-4xl sm:text-6xl mb-4">🔍</div>
          <p className="text-muted-foreground text-base sm:text-lg font-medium">No products found</p>
          <p className="text-muted-foreground text-sm mt-2">Try adjusting your filters or search criteria</p>
          {(selectedCategory !== 'all' || sortBy !== 'default') && (
            <button
              onClick={clearFilters}
              className="mt-4 inline-block bg-primary text-primary-foreground px-6 py-2 rounded-lg hover:bg-primary-hover transition text-sm sm:text-base"
            >
              Clear All Filters
            </button>
          )}
        </div>
      ) : (
        <>
          {/* Products count */}
          <div className="mb-4 text-sm text-muted-foreground">
            Showing <span className="font-medium text-muted-foreground">{filteredProducts.length}</span> of {total} products
          </div>

          <div className="grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-4 md:gap-6">
            {filteredProducts.map((product) => (
              <ProductCard key={product.id} product={product} />
            ))}
          </div>
          {totalPages > 1 && (
            <nav aria-label="Product pages" className="flex items-center justify-center gap-4 mt-6">
              <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="px-4 py-2 rounded bg-muted disabled:opacity-40">Previous</button>
              <span>Page {page} of {totalPages}</span>
              <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} className="px-4 py-2 rounded bg-muted disabled:opacity-40">Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
};

export default ProductList;

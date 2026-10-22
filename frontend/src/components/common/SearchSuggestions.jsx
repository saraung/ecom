import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search, Folder, Package } from 'lucide-react';
import api from '../../api/axios';
import { categoryAPI } from '../../api/category';
import { formatPrice } from '../../utils/format';
import { loadCatalogPage } from '../../utils/catalog';

const PLACEHOLDER_IMG =
  'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"%3E%3Crect width="300" height="300" fill="%23f4f4f5"/%3E%3Ctext x="50%25" y="50%25" font-family="Arial" font-size="16" font-weight="bold" fill="%23a1a1aa" text-anchor="middle" dy=".3em"%3EProduct Image%3C/text%3E%3C/svg%3E';

const highlight = (text, query) => {
  const q = query.trim();
  if (!q) return text;
  const idx = text.toLowerCase().indexOf(q.toLowerCase());
  if (idx === -1) return text;
  return (
    <>
      {text.slice(0, idx)}
      <span className="text-primary font-bold">{text.slice(idx, idx + q.length)}</span>
      {text.slice(idx + q.length)}
    </>
  );
};

const SearchSuggestions = ({ query, inputRef, onSelectProduct, onSelectCategory, onSearch }) => {
  const [catalog, setCatalog] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const listRef = useRef(null);

  const show = query.trim().length > 0;

  // Debounced server search includes products beyond the first catalog page.
  useEffect(() => {
    if (!show) return;
    let cancelled = false;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    const timer = setTimeout(() => {
      Promise.all([loadCatalogPage(api, { search: query, limit: 5 }, controller.signal), categoryAPI.getCategories()])
        .then(([data, categories]) => {
          if (!cancelled) setCatalog({ query: query.trim(), products: data.products, categories: categories.data });
        })
        .catch(() => { if (!cancelled) setError('Search is temporarily unavailable.'); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [show, query]);

  const results = useMemo(() => {
    if (!catalog || !show || catalog.query !== query.trim()) return { products: [], categories: [] };
    const q = query.trim().toLowerCase();
    const products = catalog.products;
    const categories = catalog.categories
      .filter((c) => c.name.toLowerCase().includes(q))
      .slice(0, 3);
    return { products, categories };
  }, [catalog, query, show]);

  const count = results.products.length + results.categories.length;
  const hasResults = count > 0;

  useEffect(() => setActiveIndex(-1), [query]);

  // Keep the highlighted row visible while scrolling with the arrow keys.
  useEffect(() => {
    const el = listRef.current?.children?.[activeIndex];
    if (el && el.scrollIntoView) el.scrollIntoView({ block: 'nearest' });
  }, [activeIndex]);

  const pickActive = (index) => {
    if (index < 0 || index >= count) return;
    if (index < results.products.length) {
      onSelectProduct(results.products[index]);
    } else {
      onSelectCategory(results.categories[index - results.products.length]);
    }
  };

  // Arrow-key navigation + Enter/Escape, wired to the input that opened the panel.
  useEffect(() => {
    const inputEl = inputRef?.current;
    if (!inputEl || !show || count === 0) return;
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => (i + 1) % count);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => (i - 1 + count) % count);
      } else if (e.key === 'Enter') {
        if (activeIndex >= 0) {
          e.preventDefault();
          pickActive(activeIndex);
        }
      } else if (e.key === 'Escape') {
        setActiveIndex(-1);
      }
    };
    inputEl.addEventListener('keydown', handleKeyDown);
    return () => inputEl.removeEventListener('keydown', handleKeyDown);
  }, [show, count, activeIndex, results, inputRef, pickActive]);

  if (!show) return null;

  return (
    <div className="mt-2 rounded-2xl bg-card border border-border shadow-lg overflow-hidden">
      <div ref={listRef} className="max-h-80 overflow-y-auto custom-scrollbar py-1">
        {loading && (
          <div className="px-4 py-3 text-xs font-medium text-muted-foreground">
            Searching products…
          </div>
        )}

        {error && <div role="alert" className="px-4 py-3 text-xs text-destructive">{error}</div>}
        {!loading && !error && catalog && !hasResults && (
          <div className="px-4 py-3 text-xs font-medium text-muted-foreground">
            No products or categories match "{query.trim()}".
          </div>
        )}

        {results.products.length > 0 && (
          <>
            <p className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Products
            </p>
            {results.products.map((product, idx) => (
              <button
                key={`p-${product.id}`}
                type="button"
                onMouseEnter={() => setActiveIndex(idx)}
                onClick={() => onSelectProduct(product)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${activeIndex === idx ? 'bg-primary-soft' : 'hover:bg-primary-soft/60'}`}
              >
                <img
                  src={product.images?.[0]?.url || PLACEHOLDER_IMG}
                  alt=""
                  className="w-10 h-10 shrink-0 rounded-xl object-cover bg-muted"
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold text-foreground truncate">
                    {highlight(product.name, query)}
                  </p>
                  <p className="text-xs font-medium text-muted-foreground">
                    {formatPrice(product.price)}
                  </p>
                </div>
                <Package size={14} className="shrink-0 text-muted-foreground" strokeWidth={2} />
              </button>
            ))}
          </>
        )}

        {results.categories.length > 0 && (
          <>
            <p className="px-4 pt-2 pb-1 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
              Categories
            </p>
            {results.categories.map((category, idx) => {
              const index = results.products.length + idx;
              return (
                <button
                  key={`c-${category.id}`}
                  type="button"
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => onSelectCategory(category)}
                  className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${activeIndex === index ? 'bg-primary-soft' : 'hover:bg-primary-soft/60'}`}
                >
                  <span className="w-10 h-10 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center">
                    <Folder size={16} strokeWidth={2} />
                  </span>
                  <span className="min-w-0 flex-1 text-sm font-semibold text-foreground truncate">
                    {highlight(category.name, query)}
                  </span>
                  <span className="shrink-0 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                    Category
                  </span>
                </button>
              );
            })}
          </>
        )}
      </div>

      <button
        type="submit"
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => onSearch()}
        className="w-full flex items-center gap-2 px-4 py-2.5 border-t border-border bg-primary-soft/30 hover:bg-primary-soft transition-colors text-left"
      >
        <Search size={14} className="shrink-0 text-primary" strokeWidth={2.5} />
        <span className="text-xs font-bold text-foreground truncate">
          Search for "{query.trim()}"
        </span>
        <span className="ml-auto shrink-0 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
          Enter ↵
        </span>
      </button>
    </div>
  );
};

export default SearchSuggestions;

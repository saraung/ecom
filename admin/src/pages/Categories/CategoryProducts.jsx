// src/pages/Categories/CategoryProducts.jsx
import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Plus, Package, Search, X, Check, Trash2, Image as ImageIcon } from 'lucide-react';
import { getCategoryById } from '../../api/categories';
import { getAdminProducts, updateProduct } from '../../api/products';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatPrice } from '../../utils/format';

const CategoryProducts = () => {
  const { categoryId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  // Adding/removing a product from a category goes through updateProduct, so
  // the gate mirrors that endpoint's require_perm("products.update").
  const canAssign = canDo(user, 'products.update');
  const [category, setCategory] = useState(null);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [allProducts, setAllProducts] = useState([]);
  const [selectedProducts, setSelectedProducts] = useState(new Set());
  const [searchTerm, setSearchTerm] = useState('');
  const [addingProducts, setAddingProducts] = useState(false);
  const [showSuccessMessage, setShowSuccessMessage] = useState(false);
  const [confirmState, setConfirmState] = useState(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all'); // all | active | inactive

  useEffect(() => {
    fetchCategoryAndProducts();
  }, [categoryId]);

  const fetchCategoryAndProducts = async () => {
    try {
      setLoading(true);
      
      const categoryResponse = await getCategoryById(categoryId);
      setCategory(categoryResponse.data);

      // Admin endpoint — includes inactive products (public /products hides them)
      const productsResponse = await getAdminProducts({ category_id: categoryId, limit: 100 });
      const body = productsResponse.data;
      setProducts(Array.isArray(body) ? body : (body?.products || []));
      
    } catch {
      toast.error('Failed to load category products');
    } finally {
      setLoading(false);
    }
  };

  const fetchAllProducts = async () => {
    try {
      const response = await getAdminProducts({ limit: 100 });
      const body = response.data;
      setAllProducts(Array.isArray(body) ? body : (body?.products || []));
    } catch {
      toast.error('Failed to load products');
    }
  };

  const handleOpenAddPanel = async () => {
    setShowAddPanel(true);
    setSelectedProducts(new Set());
    setSearchTerm('');
    await fetchAllProducts();
  };

  const handleAddProducts = async () => {
    if (selectedProducts.size === 0) {
      toast.error('Please select products to add');
      return;
    }

    try {
      setAddingProducts(true);

      // Assign in parallel; report partial success instead of failing
      // the whole batch on one bad row (bulk-action pattern).
      const ids = [...selectedProducts];
      const results = await Promise.allSettled(
        ids.map((productId) => updateProduct(productId, { category_id: categoryId }))
      );
      const ok = results.filter((r) => r.status === 'fulfilled').length;
      const failed = results.length - ok;

      if (ok > 0) {
        toast.success(
          failed > 0
            ? `Added ${ok} of ${results.length} products to ${category.name} (${failed} failed)`
            : `Added ${ok} products to ${category.name}`
        );
      } else {
        toast.error('Failed to add products');
      }
      setShowAddPanel(false);
      setSelectedProducts(new Set());
      
      // Show success message briefly
      setShowSuccessMessage(true);
      setTimeout(() => setShowSuccessMessage(false), 3000);
      
      // Refresh products in category
      await fetchCategoryAndProducts();
    } catch {
      toast.error('Failed to add products');
    } finally {
      setAddingProducts(false);
    }
  };

  const handleRemoveProduct = (productId) => {
    setConfirmState({ kind: 'remove', target: productId });
  };

  const runConfirmed = async () => {
    const s = confirmState;
    if (!s) return;
    try {
      setRemoveBusy(true);
      await updateProduct(s.target, { category_id: null });
      toast.success('Product removed from category');
      fetchCategoryAndProducts();
    } catch {
      toast.error('Failed to remove product');
    } finally {
      setRemoveBusy(false);
      setConfirmState(null);
    }
  };

  const toggleProductSelection = (productId) => {
    const newSelected = new Set(selectedProducts);
    if (newSelected.has(productId)) {
      newSelected.delete(productId);
    } else {
      newSelected.add(productId);
    }
    setSelectedProducts(newSelected);
  };

  // 👇 First product image (same pattern as ProductList.jsx)
  const getProductImage = (product) => {
    if (product.images && Array.isArray(product.images) && product.images.length > 0) {
      const image = product.images[0];
      if (image && image.url) {
        return image.url;
      }
    }
    return null;
  };

  // Filter products based on search term
  const filteredAllProducts = useMemo(() => {
    if (!searchTerm.trim()) return allProducts;
    
    return allProducts.filter(product => 
      product.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.slug?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      product.description?.toLowerCase().includes(searchTerm.toLowerCase())
    );
  }, [allProducts, searchTerm]);

  // Separate products: already in category vs available
  const productsInCategory = useMemo(() => {
    const categoryProductIds = new Set(products.map(p => p.id));
    return filteredAllProducts.filter(p => categoryProductIds.has(p.id));
  }, [filteredAllProducts, products]);

  // In-category grid respects the status filter (inactive included now).
  const visibleProducts = useMemo(() => {
    if (statusFilter === 'active') return products.filter((p) => p.is_active);
    if (statusFilter === 'inactive') return products.filter((p) => !p.is_active);
    return products;
  }, [products, statusFilter]);

  const productsNotInCategory = useMemo(() => {
    const categoryProductIds = new Set(products.map(p => p.id));
    return filteredAllProducts.filter(p => !categoryProductIds.has(p.id));
  }, [filteredAllProducts, products]);

  if (loading) {
    return <PageSkeleton type="category-products" />;
  }

  return (
    // No max-width wrapper here (unlike ProductDetail's max-w-6xl): list/detail
    // tabs all render full-width (e.g. CategoryList's plain <div>) so the
    // header and grid line up with the sidebar spacing of every other tab.
    // pb-8 keeps the bottom margin so the grid never touches <main>'s padding.
    <div className="pb-8">
      {/* Success Message */}
      {showSuccessMessage && (
        <div className="mb-4 p-4 bg-success/10 border border-success/30 rounded-lg flex items-center gap-2 text-success">
          <Check size={20} />
          <span>Products added successfully!</span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4 mb-6">
        <div className="flex items-center gap-3 sm:gap-4 min-w-0">
          <button
            onClick={() => navigate('/categories')}
            className="p-2 hover:bg-muted rounded-lg transition shrink-0"
            aria-label="Back to categories"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">
              {category?.name || 'Category Products'}
            </h1>
            <p className="text-sm text-muted-foreground">
              {products.length} products in this category
            </p>
          </div>
        </div>

        {canAssign && (
          <button
            onClick={handleOpenAddPanel}
            className="bg-primary text-primary-foreground px-4 py-2.5 sm:py-2 rounded-lg hover:bg-primary-hover transition flex items-center justify-center gap-2 w-full sm:w-auto"
          >
            <Plus size={20} />
            Add Products
          </button>
        )}
      </div>

      {/* Main Content Area with Flex Layout */}
      <div className="flex gap-6">
        {/* Products Grid - Takes remaining space */}
        <div className={`flex-1 transition-all min-w-0 ${showAddPanel ? 'opacity-50 pointer-events-none' : ''}`}>
          <div className="flex items-center justify-between gap-3 mb-3">
            <p className="text-sm text-muted-foreground">
              Showing {visibleProducts.length} of {products.length}
            </p>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="border border-input rounded-lg px-3 py-1.5 text-sm bg-card text-foreground"
              aria-label="Filter by status"
            >
              <option value="all">All statuses</option>
              <option value="active">Active only</option>
              <option value="inactive">Inactive only</option>
            </select>
          </div>
          {visibleProducts.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {visibleProducts.map(product => {
                const imageUrl = getProductImage(product);
                return (
                <div
                  key={product.id}
                  onClick={() => navigate(`/products/${product.slug}`)}
                  className="bg-card rounded-lg shadow-sm overflow-hidden hover:shadow-md transition group cursor-pointer relative"
                >
                  <div className="aspect-square bg-muted overflow-hidden">
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={product.name}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center">
                        <ImageIcon size={20} className="text-muted-foreground" />
                      </div>
                    )}
                  </div>
                  {canAssign && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleRemoveProduct(product.id);
                      }}
                      className="absolute top-1.5 right-1.5 p-1.5 bg-card/90 text-destructive hover:bg-destructive hover:text-white rounded-full shadow transition"
                      title="Remove from category"
                    >
                      <Trash2 size={12} />
                    </button>
                  )}
                  <div className="p-2">
                    <h3
                      className="text-xs font-medium text-foreground truncate group-hover:text-primary-hover transition"
                      title={product.name}
                    >
                      {product.name}
                    </h3>
                    <div className="flex items-center justify-between gap-1 mt-0.5">
                      <p className="text-xs text-muted-foreground">{formatPrice(product.price)}</p>
                      {!product.is_active && (
                        <span className="badge badge-danger text-[10px]">Inactive</span>
                      )}
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
          ) : (
            <div className="bg-card rounded-lg shadow-sm p-12 text-center">
              <Package className="mx-auto text-muted-foreground mb-4" size={48} />
              <p className="text-muted-foreground">No products in this category yet.</p>
              {canAssign && (
                <button
                  onClick={handleOpenAddPanel}
                  className="mt-4 text-primary hover:text-primary-hover"
                >
                  Add your first product →
                </button>
              )}
            </div>
          )}
        </div>

        {/* Add Products Side Panel */}
        {showAddPanel && (
          <div className="w-full md:w-96 flex-shrink-0 bg-card rounded-xl shadow-xl border border-border flex flex-col max-h-[calc(100vh-200px)]">
            {/* Panel Header */}
            <div className="p-4 border-b flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-foreground">Add Products</h2>
                <p className="text-sm text-muted-foreground">to {category?.name}</p>
              </div>
              <button
                onClick={() => setShowAddPanel(false)}
                className="p-2 hover:bg-muted rounded-lg transition"
              >
                <X size={20} />
              </button>
            </div>

            {/* Search Bar */}
            <div className="p-4 border-b">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
                <input
                  type="text"
                  placeholder="Search products..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
            </div>

            {/* Products List */}
            <div className="flex-1 overflow-y-auto p-4">
              {filteredAllProducts.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  No products found
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Products NOT in category */}
                  {productsNotInCategory.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                        Available Products
                      </h3>
                      <div className="space-y-2">
                        {productsNotInCategory.map(product => (
                          <label 
                            key={product.id} 
                            className="flex items-center gap-3 p-3 bg-muted hover:bg-primary-soft rounded-lg cursor-pointer transition"
                          >
                            <input
                              type="checkbox"
                              checked={selectedProducts.has(product.id)}
                              onChange={() => toggleProductSelection(product.id)}
                              className="rounded border-input text-primary focus:ring-primary"
                            />
                            <div className="flex-1 min-w-0">
                              <span className="font-medium text-sm block truncate">{product.name}</span>
                              <span className="text-xs text-muted-foreground">{formatPrice(product.price)}</span>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Products already in category */}
                  {productsInCategory.length > 0 && (
                    <div>
                      <h3 className="text-xs font-semibold text-muted-foreground uppercase mb-2">
                        Already in Category
                      </h3>
                      <div className="space-y-2">
                        {productsInCategory.map(product => (
                          <div 
                            key={product.id} 
                            className="flex items-center gap-3 p-3 bg-success/10 rounded-lg opacity-60"
                          >
                            <Check size={16} className="text-success" />
                            <div className="flex-1 min-w-0">
                              <span className="font-medium text-sm block truncate">{product.name}</span>
                              <span className="text-xs text-muted-foreground">{formatPrice(product.price)}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Panel Footer */}
            <div className="p-4 border-t bg-muted">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-muted-foreground">
                  {selectedProducts.size} selected
                </span>
                {selectedProducts.size > 0 && (
                  <button
                    onClick={() => setSelectedProducts(new Set())}
                    className="text-sm text-muted-foreground hover:text-muted-foreground"
                  >
                    Clear
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setShowAddPanel(false)}
                  className="flex-1 px-4 py-2 text-muted-foreground bg-card border border-input rounded-lg hover:bg-muted transition"
                >
                  Cancel
                </button>
                <button
                  onClick={handleAddProducts}
                  disabled={selectedProducts.size === 0 || addingProducts}
                  className="flex-1 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {addingProducts ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Adding...
                    </>
                  ) : (
                    <>
                      <Plus size={16} />
                      Add {selectedProducts.size > 0 ? selectedProducts.size : ''}
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Mobile Overlay for Add Panel */}
      {showAddPanel && (
        <div 
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={() => setShowAddPanel(false)}
        />
      )}

      {/* Mobile Add Panel (slides from bottom) */}
      {showAddPanel && (
        <div className="fixed bottom-0 left-0 right-0 z-50 md:hidden bg-card rounded-t-2xl shadow-2xl max-h-[80vh] flex flex-col">
          <div className="p-4 border-b flex items-center justify-between">
            <h2 className="text-lg font-bold">Add Products to {category?.name}</h2>
            <button
              onClick={() => setShowAddPanel(false)}
              className="p-2 hover:bg-muted rounded-lg"
            >
              <X size={20} />
            </button>
          </div>
          
          <div className="p-4 border-b">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
              <input
                type="text"
                placeholder="Search products..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto p-4">
            {/* Same product list as desktop */}
            {filteredAllProducts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">No products found</div>
            ) : (
              <div className="space-y-2">
                {productsNotInCategory.map(product => (
                  <label key={product.id} className="flex items-center gap-3 p-3 bg-muted rounded-lg cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedProducts.has(product.id)}
                      onChange={() => toggleProductSelection(product.id)}
                      className="rounded border-input"
                    />
                    <div className="flex-1">
                      <span className="font-medium">{product.name}</span>
                      <span className="text-sm text-muted-foreground ml-2">{formatPrice(product.price)}</span>
                    </div>
                  </label>
                ))}
              </div>
            )}
          </div>
          
          <div className="p-4 border-t">
            <button
              onClick={handleAddProducts}
              disabled={selectedProducts.size === 0 || addingProducts}
              className="w-full bg-primary text-primary-foreground px-4 py-3 rounded-lg hover:bg-primary-hover transition disabled:opacity-50"
            >
              Add {selectedProducts.size} Products
            </button>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        busy={removeBusy}
        title="Remove product"
        message="Remove this product from the category?"
        confirmLabel="Remove"
        tone="primary"
        onConfirm={runConfirmed}
        onClose={() => { if (!removeBusy) setConfirmState(null); }}
      />
    </div>
  );
};

export default CategoryProducts;
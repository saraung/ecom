// src/pages/Products/ProductList.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Edit, Trash2, Image as ImageIcon, Eye } from 'lucide-react';
import { getAdminProducts, bulkDeleteProducts, bulkUpdateProductStatus } from '../../api/products';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions'; // 👈 ADDED
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatPrice as sharedFormatPrice } from '../../utils/format';

const ProductList = () => {
  const navigate = useNavigate();
  const { user } = useAuth(); // 👈 ADDED: session carries role + permissions
  // Mirrors the backend gates: products.create for new, products.update for
  // edit/bulk status, products.delete for removal — not a role-string check.
  const canCreate = canDo(user, 'products.create');
  const canUpdate = canDo(user, 'products.update');
  const canDelete = canDo(user, 'products.delete');
  const [allProducts, setAllProducts] = useState([]);
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all'); // all | active | inactive
  const [selectedIds, setSelectedIds] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalProducts, setTotalProducts] = useState(0);
  const itemsPerPage = 10;
  const [confirmState, setConfirmState] = useState(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  useEffect(() => {
    fetchProducts();
  }, []);

  useEffect(() => {
    let filtered = allProducts;
    if (statusFilter === 'active') {
      filtered = filtered.filter((p) => p.is_active);
    } else if (statusFilter === 'inactive') {
      filtered = filtered.filter((p) => !p.is_active);
    }
    if (search.trim() !== '') {
      const q = search.toLowerCase();
      filtered = filtered.filter(product =>
        product.name.toLowerCase().includes(q) ||
        product.slug.toLowerCase().includes(q)
      );
    }
    setProducts(filtered);
    setTotalProducts(filtered.length);
    setCurrentPage(1);
  }, [search, statusFilter, allProducts]);

  const fetchProducts = async () => {
    try {
      setLoading(true);
      // Admin endpoint — includes inactive products (public /products hides them)
      const response = await getAdminProducts({ limit: 100 });


      // Admin shape: { products: [...] } — fall back to raw list for safety
      const body = response.data;
      const productData = Array.isArray(body) ? body : (body?.products || []);
      
      productData.forEach(p => {
        if (p.images && p.images.length > 0) {
        }
      });
      
      setAllProducts(productData);
      setProducts(productData);
      setTotalProducts(productData.length);
      setTotalPages(Math.ceil(productData.length / itemsPerPage));
    } catch {
      toast.error('Failed to load products');
      setAllProducts([]);
      setProducts([]);
    } finally {
      setLoading(false);
    }
  };

  const getCurrentPageItems = () => {
    const start = (currentPage - 1) * itemsPerPage;
    const end = start + itemsPerPage;
    return products.slice(start, end);
  };

  const handleDelete = (product) => {
    // 👈 Only products.delete can delete (hard delete — the row is gone;
    // deactivation lives under Activate/Deactivate via products.update)
    if (!canDelete) {
      toast.error('You do not have permission to delete products');
      return;
    }
    setConfirmState({ kind: 'delete', target: product });
  };

  const runConfirmed = async () => {
    const s = confirmState;
    if (!s) return;
    try {
      setDeleteBusy(true);
      await bulkDeleteProducts([s.target.id]);
      toast.success('Product permanently deleted');
      fetchProducts();
    } catch (err) {
      // 409 surfaces the guard reason, e.g. 'Cannot delete "X": has order
      // history. Deactivate it instead.' — show it, don't genericize.
      const detail = err.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Failed to delete product');
    } finally {
      setDeleteBusy(false);
      setConfirmState(null);
    }
  };

  const handleBulkStatus = async (isActive) => {
    // 👈 Only products.update can bulk update
    if (!canUpdate) {
      toast.error('You do not have permission to perform bulk actions');
      return;
    }
    
    if (selectedIds.length === 0) {
      toast.error('Please select products');
      return;
    }

    try {
      await bulkUpdateProductStatus(selectedIds, isActive);
      toast.success(`Products ${isActive ? 'activated' : 'deactivated'} successfully`);
      setSelectedIds([]);
      fetchProducts();
    } catch {
      toast.error('Failed to update products');
    }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  const toggleSelectAll = () => {
    const currentItems = getCurrentPageItems();
    const currentIds = currentItems.map(p => p.id);
    const allSelected = currentIds.every(id => selectedIds.includes(id));
    
    if (allSelected) {
      setSelectedIds(prev => prev.filter(id => !currentIds.includes(id)));
    } else {
      const newIds = [...new Set([...selectedIds, ...currentIds])];
      setSelectedIds(newIds);
    }
  };

  const formatPrice = (price) => sharedFormatPrice(price, { decimals: 0 });

  const getProductImage = (product) => {
    if (product.images && Array.isArray(product.images) && product.images.length > 0) {
      const image = product.images[0];
      if (image && image.url) {
        return image.url;
      }
    }
    return null;
  };

  const getVariantDisplay = (product) => {
    const count = product.variants?.length || 0;
    if (count === 0) return '0';
    return count;
  };

  const totalPagesCount = Math.ceil(products.length / itemsPerPage);
  const currentItems = getCurrentPageItems();

  if (loading) {
    return <PageSkeleton type="products" />;
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Products</h1>
          <p className="text-sm text-muted-foreground mt-1">{totalProducts} products found</p>
        </div>
        {/* 👇 Add Product button - products.create */}
        {canCreate && (
          <button
            onClick={() => navigate('/products/new')}
            className="btn-primary flex items-center justify-center gap-2 w-full sm:w-auto py-2.5 sm:py-2"
          >
            <Plus size={20} />
            Add Product
          </button>
        )}
      </div>

      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div className="relative w-full sm:flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
          <input
            type="text"
            placeholder="Search products..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="border border-input rounded-lg px-3 py-2 text-sm bg-card text-foreground"
          aria-label="Filter by status"
        >
          <option value="all">All statuses</option>
          <option value="active">Active only</option>
          <option value="inactive">Inactive only</option>
        </select>
        {/* 👇 Bulk actions - products.update */}
        {selectedIds.length > 0 && canUpdate && (
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => handleBulkStatus(true)}
              className="btn-success text-sm"
            >
              Activate ({selectedIds.length})
            </button>
            <button
              onClick={() => handleBulkStatus(false)}
              className="btn-danger text-sm"
            >
              Deactivate ({selectedIds.length})
            </button>
          </div>
        )}
      </div>

      <div className="bg-card rounded-xl shadow-sm overflow-hidden">
        {/* Desktop Table View */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={currentItems.length > 0 && currentItems.every(p => selectedIds.includes(p.id))}
                    onChange={toggleSelectAll}
                    className="rounded border-input"
                  />
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Product</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Price</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Variants</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {currentItems.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-8 text-center text-muted-foreground">
                    No products found. Add your first product!
                  </td>
                </tr>
              ) : (
                currentItems.map((product) => {
                  const imageUrl = getProductImage(product);
                  return (
                    <tr key={product.id} className="hover:bg-muted transition-colors">
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(product.id)}
                          onChange={() => toggleSelect(product.id)}
                          className="rounded border-input"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {imageUrl ? (
                            <img
                              src={imageUrl}
                              alt={product.name}
                              className="w-10 h-10 object-cover rounded border"
                              onError={(e) => {
                                e.target.src = 'https://via.placeholder.com/40?text=No+Image';
                              }}
                            />
                          ) : (
                            <div className="w-10 h-10 bg-muted rounded flex items-center justify-center border">
                              <ImageIcon size={16} className="text-muted-foreground" />
                            </div>
                          )}
                          <div>
                            <div className="font-medium text-foreground">{product.name}</div>
                            <div className="text-sm text-muted-foreground">{product.slug}</div>
                            {product.images && product.images.length > 0 && (
                              <div className="text-xs text-muted-foreground">{product.images.length} images</div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 font-medium">
                        {formatPrice(product.price)}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`badge ${product.is_active ? 'badge-success' : 'badge-danger'}`}>
                          {product.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {getVariantDisplay(product)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => navigate(`/products/${product.slug}`)}
                            className="p-1 text-muted-foreground hover:bg-muted rounded transition-colors"
                            title="View Product"
                          >
                            <Eye size={18} />
                          </button>
                          {canUpdate && (
                            <button
                              onClick={() => navigate(`/products/${product.slug}/edit`)}
                              className="p-1 text-primary hover:bg-primary-soft rounded transition-colors"
                              title="Edit Product"
                            >
                              <Edit size={18} />
                            </button>
                          )}
                          {canDelete && (
                            <button
                              onClick={() => handleDelete(product)}
                              className="p-1 text-destructive hover:bg-destructive/10 rounded transition-colors"
                              title="Delete Product"
                            >
                              <Trash2 size={18} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Mobile Card View */}
        <div className="md:hidden divide-y divide-border">
          {currentItems.length === 0 ? (
            <div className="px-4 py-8 text-center text-muted-foreground">
              No products found. Add your first product!
            </div>
          ) : (
            currentItems.map((product) => {
              const imageUrl = getProductImage(product);
              return (
                <div key={product.id} className="p-4 space-y-3">
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(product.id)}
                      onChange={() => toggleSelect(product.id)}
                      className="rounded border-input mt-1"
                    />
                    {imageUrl ? (
                      <img
                        src={imageUrl}
                        alt={product.name}
                        className="w-12 h-12 object-cover rounded border shrink-0"
                        onError={(e) => {
                          e.target.src = 'https://via.placeholder.com/48?text=No+Image';
                        }}
                      />
                    ) : (
                      <div className="w-12 h-12 bg-muted rounded flex items-center justify-center border shrink-0">
                        <ImageIcon size={16} className="text-muted-foreground" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-foreground truncate">{product.name}</div>
                      <div className="text-sm text-muted-foreground truncate">{product.slug}</div>
                      {product.images && product.images.length > 0 && (
                        <div className="text-xs text-muted-foreground">{product.images.length} images</div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <span className="font-medium">{formatPrice(product.price)}</span>
                      <span className={`badge ${product.is_active ? 'badge-success' : 'badge-danger'}`}>
                        {product.is_active ? 'Active' : 'Inactive'}
                      </span>
                      <span className="text-sm text-muted-foreground">
                        Variants: {getVariantDisplay(product)}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => navigate(`/products/${product.slug}`)}
                        className="p-1.5 text-muted-foreground hover:bg-muted rounded transition-colors"
                        title="View Product"
                      >
                        <Eye size={18} />
                      </button>
                      {canUpdate && (
                        <button
                          onClick={() => navigate(`/products/${product.slug}/edit`)}
                          className="p-1.5 text-primary hover:bg-primary-soft rounded transition-colors"
                          title="Edit Product"
                        >
                          <Edit size={18} />
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(product)}
                          className="p-1.5 text-destructive hover:bg-destructive/10 rounded transition-colors"
                          title="Delete Product"
                        >
                          <Trash2 size={18} />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {products.length > 0 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, products.length)} of {products.length} products
            </div>
            <div className="flex gap-2">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(p => p - 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-muted-foreground">
                Page {currentPage} of {totalPagesCount}
              </span>
              <button
                disabled={currentPage === totalPagesCount}
                onClick={() => setCurrentPage(p => p + 1)}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      <ConfirmDialog
        open={!!confirmState}
        busy={deleteBusy}
        title="Delete product"
        message={confirmState?.target ? `Permanently delete "${confirmState.target.name}"? Images, variants, reviews and wishlist entries are removed and cannot be undone.` : ''}
        confirmLabel="Delete permanently"
        tone="danger"
        onConfirm={runConfirmed}
        onClose={() => { if (!deleteBusy) setConfirmState(null); }}
      />
    </div>
  );
};

export default ProductList;
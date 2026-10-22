// src/pages/Products/ProductDetail.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { 
  ArrowLeft, 
  Edit, 
  Package, 
  Tag, 
  Layers, 
  Image as ImageIcon,
  CheckCircle,
  XCircle,
  Clock,
  Calendar
} from 'lucide-react';
import { getAdminProductBySlug } from '../../api/products';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions'; // 👈 ADDED
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { formatPrice, formatDate } from '../../utils/format';

const ProductDetail = () => {
  const navigate = useNavigate();
  const { slug } = useParams();
  const { user } = useAuth(); // 👈 ADDED: session carries role + permissions
  // Every edit entry point on this page just routes to /products/:slug/edit,
  // whose backend requires products.update.
  const canEdit = canDo(user, 'products.update');
  const [loading, setLoading] = useState(true);
  const [product, setProduct] = useState(null);

  useEffect(() => {
    if (slug) {
      fetchProduct();
    }
  }, [slug]);

  const fetchProduct = async () => {
    try {
      setLoading(true);
      const response = await getAdminProductBySlug(slug);
      setProduct(response.data);
    } catch {
      toast.error('Failed to load product');
      navigate('/products');
    } finally {
      setLoading(false);
    }
  };



  // Get category name safely
  const getCategoryName = () => {
    if (!product) return 'Uncategorized';
    if (product.category && typeof product.category === 'object') {
      return product.category.name || 'Uncategorized';
    }
    if (product.category_id) {
      return 'Category ID: ' + product.category_id.substring(0, 8) + '...';
    }
    return 'Uncategorized';
  };

  // Get total stock from variants
  const getTotalStock = () => {
    if (!product.variants || product.variants.length === 0) return 0;
    return product.variants.reduce((sum, v) => sum + (parseInt(v.stock) || 0), 0);
  };

  if (loading) {
    return <PageSkeleton type="product-detail" />;
  }

  if (!product) {
    return (
      <div className="text-center py-12">
        <Package size={48} className="mx-auto text-muted-foreground mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Product not found</h2>
        <button
          onClick={() => navigate('/products')}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Products
        </button>
      </div>
    );
  }

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={() => navigate('/products')}
            className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
            aria-label="Back to products"
          >
            <ArrowLeft size={20} />
          </button>
          <div className="min-w-0">
            <h1 className="text-lg sm:text-xl font-bold text-foreground break-words">{product.name}</h1>
            <p className="text-sm text-muted-foreground break-all">Slug: {product.slug}</p>
          </div>
        </div>
        {/* 👇 Edit button - products.update */}
        {canEdit && (
          <button
            onClick={() => navigate(`/products/${product.slug}/edit`)}
            className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors w-full sm:w-auto"
          >
            <Edit size={18} />
            Edit Product
          </button>
        )}
      </div>

      {/* Main Content - full-bleed 5-col: info (3) + gallery/ops rail (2) */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Left Column - Product Info */}
        <div className="lg:col-span-3 space-y-4">
          {/* Basic Info */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
            <h2 className="text-base font-semibold text-foreground mb-3">Product Information</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <p className="text-sm text-muted-foreground">Name</p>
                <p className="font-medium text-foreground">{product.name || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Slug</p>
                <p className="font-medium text-foreground">{product.slug || 'N/A'}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Category</p>
                <p className="font-medium text-foreground">{getCategoryName()}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                  product.is_active ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive'
                }`}>
                  {product.is_active ? (
                    <><CheckCircle size={12} /> Active</>
                  ) : (
                    <><XCircle size={12} /> Inactive</>
                  )}
                </span>
              </div>
            </div>
            
            {/* Description */}
            {product.description && (
              <div className="mt-3 pt-3 border-t border-border">
                <p className="text-sm text-muted-foreground">Description</p>
                <p className="text-muted-foreground mt-1 whitespace-pre-wrap">{product.description}</p>
              </div>
            )}
            
            {/* Created At */}
            {(product.created_at || product.updated_at) && (
              <div className="mt-3 pt-3 border-t border-border grid grid-cols-1 sm:grid-cols-2 gap-3">
                {product.created_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Created</p>
                    <p className="text-sm text-muted-foreground flex items-center gap-1">
                      <Calendar size={14} />
                      {formatDate(product.created_at)}
                    </p>
                  </div>
                )}
                {product.updated_at && product.updated_at !== product.created_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Last Updated</p>
                    <p className="text-sm text-muted-foreground flex items-center gap-1">
                      <Clock size={14} />
                      {formatDate(product.updated_at)}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Pricing */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
            <h2 className="text-base font-semibold text-foreground mb-3">Pricing</h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-sm text-muted-foreground">Price</p>
                <p className="text-xl font-bold text-foreground">{formatPrice(product.price)}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Compare at Price</p>
                {product.compare_at_price ? (
                  <>
                    <p className="text-lg font-medium text-muted-foreground line-through">
                      {formatPrice(product.compare_at_price)}
                    </p>
                    <p className="text-sm text-success">
                      Save {formatPrice(product.compare_at_price - product.price)}
                    </p>
                  </>
                ) : (
                  <p className="text-muted-foreground">Not set</p>
                )}
              </div>
            </div>
          </div>

          {/* Variants */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
            <h2 className="text-base font-semibold text-foreground mb-3">
              Variants ({product.variants?.length || 0})
            </h2>
            {product.variants && product.variants.length > 0 ? (
              <div className="space-y-3 xl:space-y-0 xl:grid xl:grid-cols-2 xl:gap-3">
                {product.variants.map((variant) => (
                  <div key={variant.id} className="flex flex-wrap items-center justify-between gap-2 p-3 bg-muted rounded-lg border border-border hover:bg-muted transition-colors">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Tag size={16} className="text-muted-foreground" />
                        <span className="font-medium text-foreground">{variant.sku}</span>
                      </div>
                      <div className="text-sm text-muted-foreground mt-1 flex flex-wrap gap-2">
                        {variant.attributes && Object.entries(variant.attributes).map(([key, value]) => (
                          <span key={key} className="bg-muted px-2 py-0.5 rounded">
                            <span className="font-medium">{key}:</span> {value}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="text-right flex-shrink-0 ml-4">
                      <div className="font-semibold text-foreground">
                        {variant.price_override ? formatPrice(variant.price_override) : formatPrice(product.price)}
                      </div>
                      <div className="text-sm text-muted-foreground">Stock: {variant.stock || 0}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-muted-foreground">
                <Layers size={32} className="mx-auto text-muted-foreground mb-2" />
                <p>No variants for this product</p>
                {canEdit && (
                  <button
                    onClick={() => navigate(`/products/${product.slug}/edit`)}
                    className="mt-2 text-sm text-primary hover:text-primary-hover"
                  >
                    Add variants in edit mode
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Right Column - Images & Stats */}
        <div className="lg:col-span-2 space-y-4">
          {/* Images */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
            <h2 className="text-base font-semibold text-foreground mb-3">
              Images ({product.images?.length || 0})
            </h2>
            {product.images && product.images.length > 0 ? (
              <div className="grid grid-cols-3 xl:grid-cols-4 gap-2">
                {product.images.map((image, index) => (
                  <div key={image.id || index} className="relative aspect-square group">
                    <img
                      src={image.url}
                      alt={image.alt_text || product.name}
                      className="w-full h-full object-cover rounded-lg border border-border group-hover:border-primary transition-colors"
                      onError={(e) => {
                        e.target.src = 'https://via.placeholder.com/150?text=No+Image';
                      }}
                    />
                    {image.alt_text && (
                      <div className="absolute bottom-1 left-1 right-1 bg-black/60 text-white text-xs px-2 py-1 rounded truncate opacity-0 group-hover:opacity-100 transition-opacity">
                        {image.alt_text}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-muted-foreground">
                <ImageIcon size={32} className="mx-auto text-muted-foreground mb-2" />
                <p>No images</p>
                {canEdit && (
                  <button
                    onClick={() => navigate(`/products/${product.slug}/edit`)}
                    className="mt-2 text-sm text-primary hover:text-primary-hover"
                  >
                    Add images in edit mode
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Quick Stats */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
            <h2 className="text-base font-semibold text-foreground mb-3">Quick Stats</h2>
            <div className="space-y-3">
              <div className="flex items-center justify-between p-2 bg-muted rounded-lg">
                <span className="text-sm text-muted-foreground">Total Variants</span>
                <span className="font-semibold text-foreground">{product.variants?.length || 0}</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-muted rounded-lg">
                <span className="text-sm text-muted-foreground">Total Images</span>
                <span className="font-semibold text-foreground">{product.images?.length || 0}</span>
              </div>
              <div className="flex items-center justify-between p-2 bg-muted rounded-lg">
                <span className="text-sm text-muted-foreground">Total Stock</span>
                <span className="font-semibold text-foreground">{getTotalStock()}</span>
              </div>
              <div className="p-2 bg-muted rounded-lg">
                <span className="text-sm text-muted-foreground">SKUs</span>
                {product.variants && product.variants.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {product.variants.map((variant) => (
                      <span
                        key={variant.id}
                        className="inline-block max-w-full px-2 py-0.5 bg-card border border-border rounded-md text-xs font-medium text-foreground truncate"
                      >
                        {variant.sku}
                      </span>
                    ))}
                  </div>
                ) : (
                  <span className="font-semibold text-foreground">N/A</span>
                )}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-5">
            <h2 className="text-base font-semibold text-foreground mb-3">Actions</h2>
            <div className="space-y-2">
              <button
                onClick={() => navigate('/products')}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors"
              >
                <ArrowLeft size={18} />
                Back to Products
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ProductDetail;
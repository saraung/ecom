// src/pages/Products/ProductForm.jsx - With Reorder Functionality

import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { 
  ArrowLeft, 
  Plus, 
  Trash2, 
  Upload, 
  Image as ImageIcon, 
  Save, 
  RefreshCw, 
  X,
  ChevronDown,
  Edit2,
  GripVertical,
  ArrowUp,
  ArrowDown
} from 'lucide-react';
import {
  getAdminProductBySlug,
  createProduct,
  updateProduct,
  createVariant,
  updateVariant,
  deleteVariant,
  addProductImage,
  uploadProductImage,
  deleteProductImage,
  reorderProductImages // ✅ NEW IMPORT
} from '../../api/products';
import { getCategories } from '../../api/categories';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { formatPrice } from '../../utils/format';

const ProductForm = () => {
  const navigate = useNavigate();
  const { slug } = useParams();
  const isEdit = !!slug;
  const descriptionRef = useRef(null);

  const autoResizeTextarea = () => {
    const el = descriptionRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  };

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [productId, setProductId] = useState(null);
  const [isProductSaved, setIsProductSaved] = useState(false);
  
  // Categories
  const [categories, setCategories] = useState([]);
  const [loadingCategories, setLoadingCategories] = useState(false);
  
  // Product basic info
  const [product, setProduct] = useState({
    name: '',
    slug: '',
    description: '',
    price: '',
    compare_at_price: '',
    category_id: null,
    is_active: true,
  });
  
  // Variants
  const [variants, setVariants] = useState([]);
  const [newVariant, setNewVariant] = useState({
    sku: '',
    attributes: {},
    price_override: '',
    stock: 0,
  });
  const [attributeKey, setAttributeKey] = useState('');
  const [attributeValue, setAttributeValue] = useState('');
  
  // Images
  const [images, setImages] = useState([]);
  const [imageUrl, setImageUrl] = useState('');
  const [imageAltText, setImageAltText] = useState('');
  const [uploadingImage, setUploadingImage] = useState(false);

  // Image Reorder Modal State
  const [isReorderModalOpen, setIsReorderModalOpen] = useState(false);
  const [reorderImages, setReorderImages] = useState([]);
  const [isReordering, setIsReordering] = useState(false);

  // Edit Variant Modal State
  const [editingVariant, setEditingVariant] = useState(null);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [confirmState, setConfirmState] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [editVariantData, setEditVariantData] = useState({
    sku: '',
    attributes: {},
    price_override: '',
    stock: 0,
  });
  const [editAttributeKey, setEditAttributeKey] = useState('');
  const [editAttributeValue, setEditAttributeValue] = useState('');

  // Load data on mount
  useEffect(() => {
    const loadData = async () => {
      await fetchCategories();
      if (isEdit) {
        await fetchProduct();
      }
    };
    loadData();
  }, [slug]);

  // Keep description textarea height in sync with its content
  useEffect(() => {
    autoResizeTextarea();
  }, [product.description]);

  // Fetch categories
  const fetchCategories = async () => {
    try {
      setLoadingCategories(true);
      const response = await getCategories({ is_active: true });
      
      let categoriesData = [];
      if (Array.isArray(response.data)) {
        categoriesData = response.data;
      } else if (response.data?.items) {
        categoriesData = response.data.items;
      } else if (response.data?.data) {
        categoriesData = response.data.data;
      } else if (response.data?.categories) {
        categoriesData = response.data.categories;
      }
      
      setCategories(categoriesData);
      return categoriesData;
    } catch {
      return [];
    } finally {
      setLoadingCategories(false);
    }
  };

  // Fetch product
  const fetchProduct = async () => {
    try {
      setLoading(true);
      const response = await getAdminProductBySlug(slug);
      const data = response.data;
      
      
      setProductId(data.id);
      setProduct({
        name: data.name,
        slug: data.slug,
        description: data.description || '',
        price: data.price,
        compare_at_price: data.compare_at_price || '',
        category_id: data.category_id || null,
        is_active: data.is_active !== undefined ? data.is_active : true,
      });
      setVariants(data.variants || []);
      setImages(data.images || []);
      setIsProductSaved(true);
    } catch {
      toast.error('Failed to load product');
      setTimeout(() => navigate('/products'), 2000);
    } finally {
      setLoading(false);
    }
  };

  // ========== PRODUCT CRUD ==========
  const handleCreateProduct = async () => {
    if (!product.name || !product.slug || !product.price) {
      toast.error('Please fill in all required fields');
      return;
    }

    try {
      setSaving(true);
      const data = {
        ...product,
        price: parseFloat(product.price),
        compare_at_price: product.compare_at_price ? parseFloat(product.compare_at_price) : null,
        category_id: product.category_id || null,
        is_active: product.is_active,
      };


      const response = await createProduct(data);
      setProductId(response.data.id);
      setIsProductSaved(true);
      toast.success('Product created! Now you can add variants and images.');
      
      navigate(`/products/${response.data.slug}/edit`, { replace: true });
      
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to create product');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateProduct = async () => {
    if (!product.name || !product.slug || !product.price) {
      toast.error('Please fill in all required fields');
      return;
    }

    try {
      setSaving(true);
      const data = {
        ...product,
        price: parseFloat(product.price),
        compare_at_price: product.compare_at_price ? parseFloat(product.compare_at_price) : null,
        category_id: product.category_id || null,
        is_active: product.is_active,
      };


      await updateProduct(productId, data);
      toast.success('Product updated successfully');
      
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update product');
    } finally {
      setSaving(false);
    }
  };

  // ========== VARIANT CRUD ==========
  const handleAddVariant = async () => {
    if (!newVariant.sku || Object.keys(newVariant.attributes).length === 0) {
      toast.error('Please fill SKU and at least one attribute');
      return;
    }

    if (!productId) {
      toast.error('Please save the product first');
      return;
    }

    try {
      const response = await createVariant(productId, {
        sku: newVariant.sku,
        attributes: newVariant.attributes,
        price_override: newVariant.price_override ? parseFloat(newVariant.price_override) : null,
        stock: parseInt(newVariant.stock) || 0,
      });
      
      setVariants([...variants, response.data]);
      toast.success('Variant added successfully');
      
      setNewVariant({ sku: '', attributes: {}, price_override: '', stock: 0 });
      setAttributeKey('');
      setAttributeValue('');
      
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add variant');
    }
  };

  const handleEditVariant = (variant) => {
    setEditingVariant(variant);
    setEditVariantData({
      sku: variant.sku,
      attributes: variant.attributes || {},
      price_override: variant.price_override || '',
      stock: variant.stock || 0,
    });
    setIsEditModalOpen(true);
  };

  const handleSaveVariantEdit = async () => {
    if (!editVariantData.sku || Object.keys(editVariantData.attributes).length === 0) {
      toast.error('Please fill SKU and at least one attribute');
      return;
    }

    try {
      const data = {
        sku: editVariantData.sku,
        attributes: editVariantData.attributes,
        price_override: editVariantData.price_override ? parseFloat(editVariantData.price_override) : null,
        stock: parseInt(editVariantData.stock) || 0,
      };

      const response = await updateVariant(productId, editingVariant.id, data);
      
      const updatedVariants = variants.map(v => 
        v.id === editingVariant.id ? response.data : v
      );
      setVariants(updatedVariants);
      
      toast.success('Variant updated successfully');
      setIsEditModalOpen(false);
      setEditingVariant(null);
      
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update variant');
    }
  };

  const handleDeleteVariant = (variantId) => {
    setConfirmState({ kind: 'variant', target: variantId });
  };

  const handleDeleteImage = (imageId) => {
    setConfirmState({ kind: 'image', target: imageId });
  };

  const runConfirmed = async () => {
    const s = confirmState;
    if (!s) return;
    if (s.kind === 'variant') {
      try {
        setConfirmBusy(true);
        await deleteVariant(productId, s.target);
        setVariants((prev) => prev.filter((v) => v.id !== s.target));
        toast.success('Variant deleted');
      } catch {
        toast.error('Failed to delete variant');
      } finally {
        setConfirmBusy(false);
        setConfirmState(null);
      }
    } else {
      try {
        setConfirmBusy(true);
        await deleteProductImage(productId, s.target);
        setImages((prev) => prev.filter((img) => img.id !== s.target));
        toast.success('Image deleted');
      } catch {
        toast.error('Failed to delete image');
      } finally {
        setConfirmBusy(false);
        setConfirmState(null);
      }
    }
  };

  // Edit Variant - Add Attribute
  const addEditAttribute = () => {
    if (!editAttributeKey || !editAttributeValue) return;
    setEditVariantData({
      ...editVariantData,
      attributes: { ...editVariantData.attributes, [editAttributeKey]: editAttributeValue },
    });
    setEditAttributeKey('');
    setEditAttributeValue('');
  };

  // Edit Variant - Remove Attribute
  const removeEditAttribute = (key) => {
    const newAttributes = { ...editVariantData.attributes };
    delete newAttributes[key];
    setEditVariantData({ ...editVariantData, attributes: newAttributes });
  };

  // ========== UI HELPERS ==========
  const addAttribute = () => {
    if (!attributeKey || !attributeValue) return;
    setNewVariant({
      ...newVariant,
      attributes: { ...newVariant.attributes, [attributeKey]: attributeValue },
    });
    setAttributeKey('');
    setAttributeValue('');
  };

  const removeAttribute = (key) => {
    const newAttributes = { ...newVariant.attributes };
    delete newAttributes[key];
    setNewVariant({ ...newVariant, attributes: newAttributes });
  };

  // ========== IMAGE CRUD ==========
  const handleAddImage = async () => {
    if (!imageUrl) {
      toast.error('Please enter an image URL');
      return;
    }

    if (!productId) {
      toast.error('Please save the product first');
      return;
    }

    try {
      const response = await addProductImage(productId, {
        url: imageUrl,
        alt_text: imageAltText || null,
        sort_order: images.length,
      });
      
      setImages([...images, response.data]);
      toast.success('Image added successfully');
      setImageUrl('');
      setImageAltText('');
      
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to add image');
    }
  };

  const handleUploadImage = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !productId) return;
    try {
      setUploadingImage(true);
      const response = await uploadProductImage(productId, file, imageAltText);
      setImages((previous) => [...previous, response.data]);
      setImageAltText('');
      toast.success('Image uploaded to Cloudinary');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to upload image');
    } finally {
      setUploadingImage(false);
    }
  };

  // ========== IMAGE REORDER ========== ✅ NEW
  const handleOpenReorderModal = () => {
    setReorderImages([...images]);
    setIsReorderModalOpen(true);
  };

  const handleReorderImageUp = (index) => {
    if (index === 0) return;
    const newImages = [...reorderImages];
    [newImages[index], newImages[index - 1]] = [newImages[index - 1], newImages[index]];
    setReorderImages(newImages);
  };

  const handleReorderImageDown = (index) => {
    if (index === reorderImages.length - 1) return;
    const newImages = [...reorderImages];
    [newImages[index], newImages[index + 1]] = [newImages[index + 1], newImages[index]];
    setReorderImages(newImages);
  };

  const handleReorderImageDrag = (fromIndex, toIndex) => {
    if (fromIndex === toIndex) return;
    const newImages = [...reorderImages];
    const [movedItem] = newImages.splice(fromIndex, 1);
    newImages.splice(toIndex, 0, movedItem);
    setReorderImages(newImages);
  };

  const handleSaveReorder = async () => {
    if (reorderImages.length < 2) {
      toast.info('Need at least 2 images to reorder');
      setIsReorderModalOpen(false);
      return;
    }

    setIsReordering(true);
    try {
      const imageIds = reorderImages.map(img => img.id);
      await reorderProductImages(productId, imageIds);
      
      // Update the images state with the new order
      setImages(reorderImages);
      toast.success('Images reordered successfully');
      setIsReorderModalOpen(false);
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to reorder images');
    } finally {
      setIsReordering(false);
    }
  };

  if (loading) {
    return <PageSkeleton type="product-form" title={isEdit ? "Edit Product" : "Create New Product"} mode={isEdit ? "edit" : "create"} />;
  }

  return (
    // Full-width (no max-w-* mx-auto wrapper) so the form fills the available
    // space and lines up with the other admin tabs under AdminLayout.
    <div className="pb-8">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-4">
        <button
          onClick={() => navigate('/products')}
          className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
          aria-label="Back to products"
        >
          <ArrowLeft size={20} />
        </button>
        <h1 className="text-lg sm:text-xl font-bold text-foreground break-words min-w-0 flex-1 basis-40">
          {isEdit ? `Edit Product: ${product.name}` : 'Create New Product'}
        </h1>
        {isProductSaved && (
          <span className="text-xs sm:text-sm text-success bg-success/10 px-3 py-1 rounded-full shrink-0">
            ✓ Product Saved
          </span>
        )}
      </div>

      <div className={`grid grid-cols-1 gap-4 ${isProductSaved ? 'lg:grid-cols-3' : ''}`}>
        {/* ========== LEFT COLUMN - PRODUCT INFO ========== */}
        <div className={`flex flex-col gap-4 ${isProductSaved ? '' : 'lg:col-span-3'}`}>
        {/* ========== PRODUCT INFO ========== */}
        <div className="bg-card rounded-xl shadow-sm p-4 sm:p-5 border border-border flex-1">
          <h2 className="text-base font-semibold text-foreground mb-3">Product Information</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Name <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={product.name}
                onChange={(e) => setProduct({ ...product, name: e.target.value })}
                className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Slug <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={product.slug}
                onChange={(e) => setProduct({ ...product, slug: e.target.value.toLowerCase().replace(/\s/g, '-') })}
                className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                required
              />
            </div>
          </div>

          <div className="mt-3">
            <label className="block text-sm font-medium text-muted-foreground mb-1">Category</label>
            <div className="relative">
              <select
                value={product.category_id || ''}
                onChange={(e) => {
                  const value = e.target.value;
                  setProduct({ ...product, category_id: value || null });
                }}
                className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent appearance-none"
              >
                <option value="">No Category</option>
                {categories.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground pointer-events-none" size={18} />
            </div>
          </div>

          <div className="mt-3">
            <label className="block text-sm font-medium text-muted-foreground mb-1">Description</label>
            <textarea
              ref={descriptionRef}
              rows="3"
              value={product.description}
              onChange={(e) => {
                setProduct({ ...product, description: e.target.value });
                autoResizeTextarea();
              }}
              className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent resize-none overflow-hidden"
              placeholder="Product description"
            />
          </div>

          {/* Pricing */}
          <div className="mt-3 pt-3 border-t border-border">
            <p className="text-sm font-medium text-muted-foreground mb-2">Pricing</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  Price <span className="text-destructive">*</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={product.price}
                  onChange={(e) => setProduct({ ...product, price: e.target.value })}
                  className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                  placeholder="0.00"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">Compare at Price</label>
                <input
                  type="number"
                  step="0.01"
                  value={product.compare_at_price}
                  onChange={(e) => setProduct({ ...product, compare_at_price: e.target.value })}
                  className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                  placeholder="0.00"
                />
              </div>
            </div>
          </div>

          {/* Status */}
          <div className="mt-3 pt-3 border-t border-border flex items-center gap-4">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={product.is_active === true}
                onChange={(e) => {
                  setProduct({ ...product, is_active: e.target.checked });
                }}
                className="w-4 h-4 text-primary rounded border-input focus:ring-primary"
              />
              <span className="text-sm text-muted-foreground">
                {product.is_active ? 'Active' : 'Inactive'}
              </span>
            </label>
            <span className={`text-xs px-2 py-1 rounded-full ${product.is_active ? 'bg-success/15 text-success' : 'bg-destructive/15 text-destructive'}`}>
              {product.is_active ? 'Published' : 'Draft'}
            </span>
          </div>
        </div>

        {/* ========== CREATE/UPDATE BUTTON ========== */}
        {/* Actions — full-width card with compact right-aligned buttons (same
            pattern as the Coupon/Category forms) so the button doesn't stretch. */}
        <div className="bg-card rounded-xl shadow-sm p-3 border border-border flex flex-wrap items-center gap-x-4 gap-y-2 justify-end">
          {!isProductSaved ? (
            <p className="text-sm text-muted-foreground mr-auto">
              After creating, you'll be able to add variants and images
            </p>
          ) : (
            <p className="text-sm text-muted-foreground mr-auto">
              Update basic product information
            </p>
          )}
          <button
            type="button"
            onClick={isProductSaved ? handleUpdateProduct : handleCreateProduct}
            disabled={saving}
            className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium"
          >
            {saving ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                {isProductSaved ? 'Updating Product...' : 'Creating Product...'}
              </>
            ) : (
              <>
                <Save size={16} />
                {isProductSaved ? 'Update Product' : 'Create Product'}
              </>
            )}
          </button>
        </div>

        {/* Close LEFT COLUMN */}
        </div>

        {/* ========== MIDDLE COLUMN - VARIANTS ========== */}
        {isProductSaved && (
          <div className="flex flex-col gap-4">
          <div className="bg-card rounded-xl shadow-sm p-4 sm:p-5 border border-border flex-1 flex flex-col">
            <h2 className="text-base font-semibold text-foreground mb-3">
              Variants ({variants.length})
            </h2>
            
            <div className="border rounded-lg p-3 mb-3 bg-muted">
              <div className="grid grid-cols-1 gap-3">
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    SKU <span className="text-destructive">*</span>
                  </label>
                  <input
                    type="text"
                    value={newVariant.sku}
                    onChange={(e) => setNewVariant({ ...newVariant, sku: e.target.value.toUpperCase() })}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="TSHIRT-BLK-M"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Price Override</label>
                  <input
                    type="number"
                    step="0.01"
                    value={newVariant.price_override}
                    onChange={(e) => setNewVariant({ ...newVariant, price_override: e.target.value })}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Leave empty"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Stock</label>
                  <input
                    type="number"
                    value={newVariant.stock}
                    onChange={(e) => setNewVariant({ ...newVariant, stock: e.target.value })}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="0"
                  />
                </div>
              </div>
              
              <div className="mt-3">
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  Attributes <span className="text-destructive">*</span>
                </label>
                <div className="flex flex-col sm:flex-row gap-2 mb-2">
                  <input
                    type="text"
                    value={attributeKey}
                    onChange={(e) => setAttributeKey(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Key (e.g., size)"
                  />
                  <input
                    type="text"
                    value={attributeValue}
                    onChange={(e) => setAttributeValue(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Value (e.g., M)"
                  />
                  <button 
                    type="button" 
                    onClick={addAttribute} 
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors whitespace-nowrap"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(newVariant.attributes).map(([key, value]) => (
                    <span key={key} className="bg-primary-soft text-primary-soft-foreground px-3 py-1 rounded-full text-sm flex items-center gap-2 max-w-[200px]">
                      <span className="truncate">{key}: {value}</span>
                      <button 
                        type="button" 
                        onClick={() => removeAttribute(key)} 
                        className="text-primary hover:text-primary-hover shrink-0"
                      >
                        <X size={14} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
              
              <button 
                type="button" 
                onClick={handleAddVariant} 
                className="mt-3 w-full bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary-hover transition-colors flex items-center justify-center gap-2"
              >
                <Plus size={16} /> Add Variant
              </button>
            </div>

            {variants.length > 0 && (
              <div className="space-y-2 flex-1 overflow-y-auto min-h-24 mt-2">
                {variants.map((variant) => {
                  const stock = Number(variant.stock ?? 0);
                  const stockBadge = stock <= 0
                    ? 'badge-danger'
                    : stock <= 5
                      ? 'badge-warning'
                      : 'badge-success';
                  const stockLabel = stock <= 0 ? 'Out of stock' : `${stock} in stock`;
                  return (
                  <div key={variant.id} className="flex flex-wrap items-center justify-between gap-3 bg-muted p-3 rounded-lg border border-border">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground">{variant.sku}</span>
                        <span className={`badge ${stockBadge}`} title={`Current stock: ${stock}`}>
                          {stockLabel}
                        </span>
                      </div>
                      <div className="text-sm text-muted-foreground truncate max-w-[300px]">
                        {Object.entries(variant.attributes).map(([k, v]) => `${k}: ${v}`).join(', ')}
                        {variant.price_override && ` • ${formatPrice(variant.price_override)}`}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleEditVariant(variant)}
                        className="text-primary hover:text-primary-hover transition-colors p-1"
                        title="Edit variant"
                      >
                        <Edit2 size={18} />
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteVariant(variant.id)}
                        className="text-destructive hover:text-destructive transition-colors p-1"
                        title="Delete variant"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                  );
                })}
              </div>
            )}
          </div>
          </div>
        )}

        {/* ========== RIGHT COLUMN - IMAGES ========== */}
        {isProductSaved && (
          <div className="flex flex-col gap-4">
          <div className="bg-card rounded-xl shadow-sm p-4 sm:p-5 border border-border flex-1 flex flex-col">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <h2 className="text-base font-semibold text-foreground">
                Images ({images.length})
              </h2>
              {images.length > 1 && (
                <button
                  type="button"
                  onClick={handleOpenReorderModal}
                  className="text-primary hover:text-primary-hover text-sm font-medium flex items-center gap-1 transition-colors"
                >
                  <GripVertical size={16} />
                  Reorder Images
                </button>
              )}
            </div>
            
            {/* Add Image Form */}
            <div className="border rounded-lg p-3 mb-3 bg-muted">
              <div className="grid grid-cols-1 gap-3">
                 <div>
                   <label className="block text-sm font-medium text-muted-foreground mb-1">
                     Image URL
                  </label>
                  <input
                    type="url"
                    value={imageUrl}
                    onChange={(e) => setImageUrl(e.target.value)}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="https://example.com/image.jpg"
                   />
                 </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">
                    Alt Text <span className="text-muted-foreground text-xs">(optional)</span>
                  </label>
                  <input
                    type="text"
                    value={imageAltText}
                    onChange={(e) => setImageAltText(e.target.value)}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Product description for accessibility"
                  />
                </div>
              </div>
              
               <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
               <button
                 type="button" 
                 onClick={handleAddImage} 
                 className="w-full bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary-hover transition-colors flex items-center justify-center gap-2"
               >
                 <Plus size={18} /> Add from URL
               </button>
               <label className="w-full bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary-hover transition-colors flex items-center justify-center gap-2 cursor-pointer">
                  <Upload size={18} /> {uploadingImage ? 'Uploading…' : 'Upload'}
                 <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="sr-only" disabled={uploadingImage} onChange={handleUploadImage} />
               </label>
               </div>
            </div>
            
            {/* Image Grid */}
            {images.length === 0 ? (
              <div className="flex-1 text-center py-8 text-muted-foreground border-2 border-dashed rounded-lg flex flex-col items-center justify-center">
                <ImageIcon size={32} className="mx-auto text-muted-foreground mb-2" />
                <p>No images added yet</p>
                <p className="text-sm">Upload a photo or add an image URL above</p>
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3 content-start flex-1">
                {images.map((image, index) => (
                  <div key={image.id} className="relative group">
                    <img
                      src={image.url}
                      alt={image.alt_text || `Product image ${index + 1}`}
                      className="w-full h-32 object-cover rounded-lg border border-border"
                      onError={(e) => {
                        e.target.src = 'https://via.placeholder.com/150?text=Invalid+URL';
                      }}
                    />
                    {/* Alt Text Overlay */}
                    <div className="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-[10px] p-1 truncate opacity-0 group-hover:opacity-100 transition-opacity">
                      {image.alt_text || 'No alt text'}
                    </div>
                    {/* Sort Order Badge */}
                    <div className="absolute top-2 left-2 bg-primary text-primary-foreground text-[10px] font-bold px-2 py-0.5 rounded-full">
                      #{image.sort_order !== undefined ? image.sort_order : index}
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteImage(image.id)}
                      className="absolute top-2 right-2 bg-destructive text-white p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-destructive/90"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
          </div>
        )}

        {/* ========== CANCEL BUTTON ========== */}
        <div className="flex justify-end lg:col-span-3">
          <button
            type="button"
            onClick={() => navigate('/products')}
            className="px-4 py-1.5 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium"
          >
            Cancel
          </button>
        </div>
      </div>

      {/* ========== REORDER IMAGES MODAL ========== */}
      {isReorderModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-4 sm:p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-foreground">Reorder Images</h2>
              <button
                onClick={() => {
                  setIsReorderModalOpen(false);
                  setReorderImages([]);
                }}
                className="text-muted-foreground hover:text-muted-foreground transition"
              >
                <X size={24} />
              </button>
            </div>

            <p className="text-sm text-muted-foreground mb-4">
              Drag or use the arrow buttons to reorder images. The first image will be displayed as the main product image.
            </p>

            <div className="space-y-2 max-h-[50vh] overflow-y-auto">
              {reorderImages.map((image, index) => (
                <div
                  key={image.id}
                  className="flex flex-wrap items-center gap-3 p-3 bg-muted rounded-lg border border-border hover:border-primary/50 transition"
                >
                  {/* Drag Handle */}
                  <div className="cursor-move text-muted-foreground hover:text-muted-foreground">
                    <GripVertical size={20} />
                  </div>
                  
                  {/* Thumbnail */}
                  <img
                    src={image.url}
                    alt={image.alt_text || `Image ${index + 1}`}
                    className="w-16 h-16 object-cover rounded-lg border border-border"
                    onError={(e) => {
                      e.target.src = 'https://via.placeholder.com/64?text=Error';
                    }}
                  />
                  
                  {/* Image Info */}
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">
                      {image.alt_text || `Image ${index + 1}`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Position: #{index + 1}
                    </p>
                  </div>

                  {/* Move Buttons */}
                  <div className="flex flex-col gap-1">
                    <button
                      type="button"
                      onClick={() => handleReorderImageUp(index)}
                      disabled={index === 0}
                      className="p-1 text-muted-foreground hover:text-primary-hover transition disabled:opacity-30 disabled:cursor-not-allowed"
                      title="Move up"
                    >
                      <ArrowUp size={18} />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleReorderImageDown(index)}
                      disabled={index === reorderImages.length - 1}
                      className="p-1 text-muted-foreground hover:text-primary-hover transition disabled:opacity-30 disabled:cursor-not-allowed"
                      title="Move down"
                    >
                      <ArrowDown size={18} />
                    </button>
                  </div>
                </div>
              ))}
            </div>

            {/* Buttons */}
            <div className="flex flex-col sm:flex-row gap-3 mt-6 pt-4 border-t border-border">
              <button
                type="button"
                onClick={handleSaveReorder}
                disabled={isReordering}
                className="flex-1 bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {isReordering ? (
                  <>
                    <RefreshCw size={18} className="animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save size={18} />
                    Save Order
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsReorderModalOpen(false);
                  setReorderImages([]);
                }}
                className="flex-1 border border-input text-muted-foreground px-4 py-2 rounded-lg hover:bg-muted transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========== EDIT VARIANT MODAL ========== */}
      {isEditModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-card rounded-xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-4 sm:p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-foreground">Edit Variant</h2>
              <button
                onClick={() => {
                  setIsEditModalOpen(false);
                  setEditingVariant(null);
                }}
                className="text-muted-foreground hover:text-muted-foreground transition"
              >
                <X size={24} />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  SKU <span className="text-destructive">*</span>
                </label>
                <input
                  type="text"
                  value={editVariantData.sku}
                  onChange={(e) => setEditVariantData({ ...editVariantData, sku: e.target.value.toUpperCase() })}
                  className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Price Override</label>
                  <input
                    type="number"
                    step="0.01"
                    value={editVariantData.price_override}
                    onChange={(e) => setEditVariantData({ ...editVariantData, price_override: e.target.value })}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Leave empty"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Stock</label>
                  <input
                    type="number"
                    value={editVariantData.stock}
                    onChange={(e) => setEditVariantData({ ...editVariantData, stock: e.target.value })}
                    className="w-full px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="0"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">
                  Attributes <span className="text-destructive">*</span>
                </label>
                <div className="flex flex-col sm:flex-row gap-2 mb-2">
                  <input
                    type="text"
                    value={editAttributeKey}
                    onChange={(e) => setEditAttributeKey(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Key (e.g., size)"
                  />
                  <input
                    type="text"
                    value={editAttributeValue}
                    onChange={(e) => setEditAttributeValue(e.target.value)}
                    className="flex-1 min-w-0 px-3 py-1.5 text-sm border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="Value (e.g., M)"
                  />
                  <button 
                    type="button" 
                    onClick={addEditAttribute} 
                    className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors whitespace-nowrap"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(editVariantData.attributes).map(([key, value]) => (
                    <span key={key} className="bg-primary-soft text-primary-soft-foreground px-3 py-1 rounded-full text-sm flex items-center gap-2 max-w-[200px]">
                      <span className="truncate">{key}: {value}</span>
                      <button 
                        type="button" 
                        onClick={() => removeEditAttribute(key)} 
                        className="text-primary hover:text-primary-hover shrink-0"
                      >
                        <X size={14} />
                      </button>
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex flex-col sm:flex-row gap-3 mt-6 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={handleSaveVariantEdit}
                  className="flex-1 bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:bg-primary-hover transition-colors"
                >
                  Save Changes
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setIsEditModalOpen(false);
                    setEditingVariant(null);
                  }}
                  className="flex-1 border border-input text-muted-foreground px-4 py-2 rounded-lg hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmState}
        busy={confirmBusy}
        title={!confirmState ? '' : confirmState.kind === 'variant' ? 'Remove variant' : 'Remove image'}
        message={!confirmState ? '' : confirmState.kind === 'variant' ? 'Remove this variant?' : 'Remove this image?'}
        confirmLabel="Delete"
        tone="danger"
        onConfirm={runConfirmed}
        onClose={() => { if (!confirmBusy) setConfirmState(null); }}
      />
    </div>
  );
};

export default ProductForm;

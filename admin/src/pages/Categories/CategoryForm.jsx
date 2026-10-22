// src/pages/Categories/CategoryForm.jsx
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Save, RefreshCw, ChevronDown, Shield, Upload } from 'lucide-react';
import { createCategory, updateCategory, getCategoryById, getCategories, uploadCategoryImage } from '../../api/categories';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions'; // 👈 ADDED
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';

const CategoryForm = () => {
  const navigate = useNavigate();
  const { id } = useParams();
  const { user } = useAuth(); // 👈 ADDED: session carries role + permissions
  const isEdit = !!id;
  // Permission check — matches the backend require_perm("categories.manage").
  // Evaluated here but RETURNED from below, after every hook: an early return
  // above the useState/useEffect calls throws "Rendered fewer hooks than
  // expected" the moment /auth/me resolves and flips this to true.
  const allowed = canDo(user, 'categories.manage');

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingCategories, setLoadingCategories] = useState(false);
  const [categories, setCategories] = useState([]);
  const [formData, setFormData] = useState({
    name: '',
    slug: '',
    parent_id: null,
    image_url: '',
    is_active: true,
    sort_order: 0,
  });
  const [uploadingImage, setUploadingImage] = useState(false);
  const fileInputRef = useRef(null);

  // Load categories for parent dropdown
  useEffect(() => {
    fetchAllCategories();
  }, []);

  // Load category data if editing
  useEffect(() => {
    if (isEdit) {
      fetchCategory();
    }
  }, [id]);

  const fetchAllCategories = async () => {
    try {
      setLoadingCategories(true);
      const response = await getCategories();
      
      let categoriesData = [];
      if (Array.isArray(response.data)) {
        categoriesData = response.data;
      } else if (response.data?.items) {
        categoriesData = response.data.items;
      } else if (response.data?.data) {
        categoriesData = response.data.data;
      }
      
      if (isEdit && id) {
        categoriesData = categoriesData.filter(cat => cat.id !== id);
      }
      
      setCategories(categoriesData);
    } catch {
    } finally {
      setLoadingCategories(false);
    }
  };

  const fetchCategory = async () => {
    try {
      setLoading(true);
      const response = await getCategoryById(id);
      const data = response.data;
      setFormData({
        name: data.name || '',
        slug: data.slug || '',
        parent_id: data.parent_id || null,
        image_url: data.image_url || '',
        is_active: data.is_active !== false,
        sort_order: data.sort_order ?? 0,
      });
    } catch {
      toast.error('Failed to load category');
      navigate('/categories');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!formData.name || !formData.slug) {
      toast.error('Please fill in all required fields');
      return;
    }

    try {
      setSaving(true);
      
      const data = {
        name: formData.name,
        slug: formData.slug.toLowerCase().replace(/\s/g, '-'),
        image_url: formData.image_url.trim() || null,
        is_active: !!formData.is_active,
        sort_order: Number.isFinite(Number(formData.sort_order)) ? Number(formData.sort_order) : 0,
      };

      if (formData.parent_id) {
        data.parent_id = formData.parent_id;
      }


      if (isEdit) {
        await updateCategory(id, data);
        toast.success('Category updated successfully');
      } else {
        await createCategory(data);
        toast.success('Category created successfully');
      }
      
      navigate('/categories');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to save category');
    } finally {
      setSaving(false);
    }
  };

  const handleNameChange = (e) => {
    const name = e.target.value;
    setFormData({
      ...formData,
      name,
      slug: name.toLowerCase().replace(/\s/g, '-')
    });
  };

  // Upload a thumbnail to Cloudinary (com/categories/{id}) — edit mode
  // only, since the folder is per-category. Falls back to pasting a URL.
  const handleImageUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!isEdit || !id) {
      toast.error('Save the category first, then upload an image');
      return;
    }
    try {
      setUploadingImage(true);
      const response = await uploadCategoryImage(id, file);
      const url = response.data?.image_url;
      if (!url) throw new Error('No URL returned');
      setFormData((prev) => ({ ...prev, image_url: url }));
      toast.success('Thumbnail uploaded to Cloudinary');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to upload image');
    } finally {
      setUploadingImage(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // Access check AFTER every hook and handler — Rules of Hooks (same order
  // Reports.jsx uses), so `allowed` flipping between renders can never change
  // the number of hooks React sees.
  if (!allowed) {
    return (
      <div className="text-center py-12">
        <Shield size={48} className="mx-auto text-destructive mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Access Denied</h2>
        <p className="text-muted-foreground mt-2">You don't have permission to manage categories.</p>
        <button
          onClick={() => navigate('/')}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Dashboard
        </button>
      </div>
    );
  }

  if (loading) {
    return <PageSkeleton type="category-form" title={isEdit ? "Edit Category" : "Create New Category"} />;
  }

  return (
    // Full-width (no max-w-* mx-auto wrapper) so the form fills the available
    // space and lines up with the other admin tabs under AdminLayout.
    // pb-8 keeps a clean bottom gap against <main>'s padding.
    <div className="pb-8">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-3">
        <button
          onClick={() => navigate('/categories')}
          className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
          aria-label="Back to categories"
        >
          <ArrowLeft size={18} />
        </button>
        <h1 className="text-lg font-bold text-foreground break-words min-w-0">
          {isEdit ? 'Edit Category' : 'Create New Category'}
        </h1>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className="bg-card rounded-xl shadow-sm p-4 sm:p-5 border border-border">
          {/* Name + Slug sit side-by-side on wide screens so the form uses the
              full width instead of leaving long empty input rows. */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Name */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Name <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={handleNameChange}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="Shoes"
                required
              />
            </div>
            
            {/* Slug */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Slug <span className="text-destructive">*</span>
              </label>
              <input
                type="text"
                value={formData.slug}
                onChange={(e) => setFormData({ ...formData, slug: e.target.value.toLowerCase().replace(/\s/g, '-') })}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="shoes"
                required
              />
              <p className="text-xs text-muted-foreground mt-1">
                Auto-generated from name: <span className="text-primary">{formData.slug || 'category-slug'}</span>
              </p>
            </div>

            {/* Parent Category */}
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Parent Category
              </label>              <div className="relative">
                <select
                  value={formData.parent_id || ''}
                  onChange={(e) => {
                    const value = e.target.value;
                    setFormData({ ...formData, parent_id: value || null });
                  }}
                  className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent appearance-none"
                >
                  <option value="">No Parent (Top Level)</option>
                  {loadingCategories ? (
                    <option value="" disabled>Loading categories...</option>
                  ) : (
                    categories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.name}
                      </option>
                    ))
                  )}
                </select>
                <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground pointer-events-none" size={18} />
              </div>
              {formData.parent_id && (
                <p className="text-xs text-primary mt-1">
                  Will be nested under: {categories.find(c => c.id === formData.parent_id)?.name || 'Unknown'}
                </p>
              )}
              {!loadingCategories && categories.length === 0 && (
                <p className="text-xs text-muted-foreground mt-1">
                  No categories available to be parent. Create top-level categories first.
                </p>
              )}
            </div>

            {/* Image URL */}
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Image URL
              </label>
              <div className="flex items-center gap-3">
                {formData.image_url ? (
                  <img
                    src={formData.image_url}
                    alt={formData.name || 'Category thumbnail'}
                    loading="lazy"
                    referrerPolicy="no-referrer"
                    onError={(e) => {
                      e.currentTarget.style.display = 'none';
                    }}
                    className="w-12 h-12 object-cover rounded-lg border border-border shrink-0"
                  />
                ) : null}
                <input
                  type="url"
                  value={formData.image_url}
                  onChange={(e) => setFormData({ ...formData, image_url: e.target.value })}
                  className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                  placeholder="https://…"
                />
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  onChange={handleImageUpload}
                  className="hidden"
                  aria-label="Upload thumbnail"
                />
                <button
                  type="button"
                  disabled={uploadingImage || !isEdit}
                  onClick={() => fileInputRef.current?.click()}
                  title={isEdit ? 'Upload to Cloudinary (com/categories)' : 'Save the category first, then upload'}
                  className="shrink-0 px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium disabled:opacity-50 flex items-center gap-2"
                >
                  {uploadingImage ? (
                    <RefreshCw size={16} className="animate-spin" />
                  ) : (
                    <Upload size={16} />
                  )}
                  {uploadingImage ? 'Uploading…' : 'Upload'}
                </button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Paste any image URL, or upload one to Cloudinary{isEdit ? '' : ' (after saving)'}.
                Thumbnail shown in the category tree.
              </p>
            </div>

            {/* Sort Order */}
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">
                Sort Order
              </label>
              <input
                type="number"
                step="1"
                value={formData.sort_order}
                onChange={(e) => setFormData({ ...formData, sort_order: e.target.value })}
                className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="0"
              />
              <p className="text-xs text-muted-foreground mt-1">
                Lower shows first among siblings.
              </p>
            </div>

            {/* Visible */}
            <div className="flex items-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer text-sm font-medium text-muted-foreground">
                <input
                  type="checkbox"
                  checked={!!formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="rounded border-input"
                />
                Visible on storefront
              </label>
            </div>
          </div>
        </div>

        {/* Actions — full-width card with compact right-aligned buttons,
            same pattern as the Coupon form so wide screens stay tidy. */}
        <div className="bg-card rounded-xl shadow-sm border border-border p-3 flex flex-wrap items-center gap-x-4 gap-y-2 justify-end">
          <button
            type="button"
            onClick={() => navigate('/categories')}
            className="px-4 py-1.5 border border-input rounded-lg hover:bg-muted transition-colors text-sm font-medium"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="bg-primary text-primary-foreground px-4 py-1.5 rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 text-sm font-medium"
          >
            {saving ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save size={16} />
                {isEdit ? 'Update Category' : 'Create Category'}
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};

export default CategoryForm;
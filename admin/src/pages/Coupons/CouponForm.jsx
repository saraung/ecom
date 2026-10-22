// src/pages/Coupons/CouponForm.jsx
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { 
  ArrowLeft, 
  Save, 
  RefreshCw, 
  Calendar, 
  Percent, 
  Tag,
  Users,
  Sparkles,
  Shield,
  Zap
} from 'lucide-react';
import { getCouponById, createCoupon, updateCoupon } from '../../api/coupons';
import { getCategories } from '../../api/categories';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions'; // 👈 ADDED
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { currencySymbol } from '../../utils/format';

const CouponForm = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams();
  const { user } = useAuth();
  const isEdit = !!id;
  // Permission check — matches the backend require_perm("coupons.manage").
  // Evaluated here but RETURNED from below, after every hook: an early return
  // above the useRef/useState/useEffect calls throws "Rendered fewer hooks than
  // expected" the moment /auth/me resolves and flips this to true.
  const allowed = canDo(user, 'coupons.manage');

  const toastShown = useRef(false);
  const generatedCode = location.state?.generatedCode || '';

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    code: generatedCode || '',
    coupon_type: 'manual',
    discount_type: 'percentage',
    value: '',
    trigger_type: 'none',
    trigger_min_cart_value: '',
    trigger_min_item_count: '',
    trigger_category_id: '',
    trigger_category_spend: '',
    min_order_value: '',
    max_uses: '',
    max_uses_per_user: 1,
    valid_from: new Date().toISOString().split('T')[0],
    valid_until: '',
    is_active: true,
    internal_only: false
  });
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    if (isEdit) {
      fetchCoupon();
    }
  }, [id]);

  useEffect(() => {
    if (generatedCode && !isEdit && !toastShown.current) {
      toastShown.current = true;
      toast.success(`✨ Code "${generatedCode}" generated! Fill in the details below.`, {
        duration: 4000,
      });
    }
  }, [generatedCode, isEdit]);

  // Load categories for the "category spend" trigger dropdown
  useEffect(() => {
    if (formData.coupon_type === 'automatic' && categories.length === 0) {
      getCategories({ limit: 100 })
        .then((res) => {
          const list = Array.isArray(res.data) ? res.data : (res.data?.items || []);
          setCategories(list);
        })
        .catch(() => toast.error('Failed to load categories'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [formData.coupon_type]);

  const fetchCoupon = async () => {
    try {
      setLoading(true);
      const response = await getCouponById(id);
      const data = response.data;
      setFormData({
        code: data.code || '',
        coupon_type: data.coupon_type || 'manual',
        discount_type: data.discount_type || 'percentage',
        value: data.value || '',
        trigger_type: data.trigger_type || 'none',
        trigger_min_cart_value: data.trigger_min_cart_value != null ? String(data.trigger_min_cart_value) : '',
        trigger_min_item_count: data.trigger_min_item_count != null ? String(data.trigger_min_item_count) : '',
        trigger_category_id: data.trigger_category_id || '',
        trigger_category_spend: data.trigger_category_spend != null ? String(data.trigger_category_spend) : '',
        min_order_value: data.min_order_value || '',
        max_uses: data.max_uses || '',
        max_uses_per_user: data.max_uses_per_user || 1,
        valid_from: data.valid_from ? data.valid_from.split('T')[0] : new Date().toISOString().split('T')[0],
        valid_until: data.valid_until ? data.valid_until.split('T')[0] : '',
        is_active: data.is_active !== undefined ? data.is_active : true,
        internal_only: !!data.internal_only
      });
    } catch {
      toast.error('Failed to load coupon');
      navigate('/coupons');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const isAutomatic = formData.coupon_type === 'automatic';

    if (!isAutomatic && !formData.code) {
      toast.error('Please enter a coupon code');
      return;
    }
    if (!formData.value) {
      toast.error('Please fill in all required fields');
      return;
    }
    if (isAutomatic) {
      if (formData.trigger_type === 'none') {
        toast.error('Choose a trigger condition for the automatic coupon');
        return;
      }
      if (formData.trigger_type === 'min_cart_value' && !formData.trigger_min_cart_value) {
        toast.error('Enter the minimum cart value trigger');
        return;
      }
      if (formData.trigger_type === 'min_item_count' && !formData.trigger_min_item_count) {
        toast.error('Enter the minimum item count trigger');
        return;
      }
      if (formData.trigger_type === 'category_spend' && (!formData.trigger_category_id || !formData.trigger_category_spend)) {
        toast.error('Pick a category and enter the minimum spend trigger');
        return;
      }
    }

    if (formData.valid_until && formData.valid_from) {
      const from = new Date(formData.valid_from);
      const until = new Date(formData.valid_until);
      if (until < from) {
        toast.error('Valid Until date cannot be before Valid From date');
        return;
      }
    }

    const data = {
      coupon_type: formData.coupon_type,
      discount_type: formData.discount_type,
      value: parseFloat(formData.value),
      trigger_type: isAutomatic ? formData.trigger_type : 'none',
      trigger_min_cart_value: isAutomatic && formData.trigger_type === 'min_cart_value' ? parseFloat(formData.trigger_min_cart_value) : null,
      trigger_min_item_count: isAutomatic && formData.trigger_type === 'min_item_count' ? parseInt(formData.trigger_min_item_count) : null,
      trigger_category_id: isAutomatic && formData.trigger_type === 'category_spend' ? formData.trigger_category_id : null,
      trigger_category_spend: isAutomatic && formData.trigger_type === 'category_spend' ? parseFloat(formData.trigger_category_spend) : null,
      min_order_value: formData.min_order_value ? parseFloat(formData.min_order_value) : null,
      max_uses: formData.max_uses ? parseInt(formData.max_uses) : null,
      max_uses_per_user: parseInt(formData.max_uses_per_user) || 1,
      valid_from: formData.valid_from ? new Date(formData.valid_from).toISOString() : new Date().toISOString(),
      valid_until: formData.valid_until ? new Date(formData.valid_until).toISOString() : null,
      is_active: formData.is_active,
      internal_only: !!formData.internal_only
    };
    // Automatic coupon codes are generated server-side — never send one.
    if (!isAutomatic) {
      data.code = formData.code.toUpperCase();
    }

    try {
      setSaving(true);
      
      if (isEdit) {
        await updateCoupon(id, data);
        toast.success('✅ Coupon updated successfully');
      } else {
        await createCoupon(data);
        toast.success('✅ Coupon created successfully');
      }
      
      navigate('/coupons');
    } catch (error) {
      const detail = error.response?.data?.detail;
      const message = Array.isArray(detail)
        ? detail.map((d) => d.msg).join(', ')
        : (detail || 'Failed to save coupon');
      toast.error(message);
    } finally {
      setSaving(false);
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
        <p className="text-muted-foreground mt-2">You don't have permission to manage coupons.</p>
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
    return <PageSkeleton type="coupon-form" title={isEdit ? "Edit Coupon" : "Create New Coupon"} submitLabel={isEdit ? "Update Coupon" : "Create Coupon"} mode={isEdit ? "edit" : "create"} />;
  }

  return (
    // Full-width (no max-w-* mx-auto wrapper) so the coupon form fills the
    // available space and lines up with the other admin tabs under AdminLayout.
    // pb-8 keeps a clean bottom gap against <main>'s padding.
    <div className="pb-8">
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 mb-3">
        <button
          onClick={() => navigate('/coupons')}
          className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
          aria-label="Back to coupons"
        >
          <ArrowLeft size={18} />
        </button>
        <h1 className="text-lg font-bold text-foreground break-words min-w-0 flex-1 basis-40">
          {isEdit ? 'Edit Coupon' : 'Create New Coupon'}
        </h1>
        {generatedCode && !isEdit && (
          <span className="text-xs text-purple-500 bg-purple-500/10 px-3 py-1 rounded-full flex items-center gap-1 shrink-0 break-all">
            <Sparkles size={14} className="shrink-0" />
            Generated: {generatedCode}
          </span>
        )}
      </div>

      <form onSubmit={handleSubmit} className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Basic Information */}
        <div className="bg-card rounded-xl shadow-sm p-3 border border-border">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Basic Information</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Coupon Type
              </label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, coupon_type: 'manual', trigger_type: 'none' })}
                  className={`flex items-start gap-2 p-3 rounded-xl border text-left transition-colors ${
                    formData.coupon_type === 'manual'
                      ? 'border-primary bg-primary-soft'
                      : 'border-input hover:bg-muted'
                  }`}
                >
                  <Tag size={16} className="mt-0.5 text-primary" />
                  <span>
                    <span className="block text-sm font-semibold text-foreground">Manual code</span>
                    <span className="block text-xs text-muted-foreground">Customer types the code at checkout</span>
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setFormData({ ...formData, coupon_type: 'automatic' })}
                  className={`flex items-start gap-2 p-3 rounded-xl border text-left transition-colors ${
                    formData.coupon_type === 'automatic'
                      ? 'border-primary bg-primary-soft'
                      : 'border-input hover:bg-muted'
                  }`}
                >
                  <Zap size={16} className="mt-0.5 text-primary" />
                  <span>
                    <span className="block text-sm font-semibold text-foreground">Automatic</span>
                    <span className="block text-xs text-muted-foreground">No code needed — applies itself at checkout</span>
                  </span>
                </button>
              </div>
            </div>
            {formData.coupon_type === 'manual' ? (
              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Coupon Code <span className="text-destructive">*</span>
                </label>
                <div className="relative">
                  <Tag className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={16} />
                  <input
                    type="text"
                    value={formData.code}
                    onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                    className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent uppercase"
                    placeholder="SUMMER20"
                    required
                    disabled={isEdit}
                  />
                </div>
                {isEdit && (
                  <p className="text-xs text-muted-foreground mt-1">Coupon code cannot be changed after creation</p>
                )}
                {generatedCode && !isEdit && (
                  <p className="text-xs text-purple-500 mt-1 flex items-center gap-1">
                    <Sparkles size={12} />
                    Auto-generated code
                  </p>
                )}
              </div>
            ) : (
              <div className="md:col-span-2 flex items-start gap-2 p-3 rounded-lg bg-primary-soft border border-primary/20">
                <Zap size={16} className="mt-0.5 text-primary shrink-0" />
                <p className="text-xs text-muted-foreground">
                  No code needed — a unique internal code (AUTO-XXXXXX) is generated automatically when you save. The backend applies this coupon by itself.
                </p>
              </div>
            )}
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Discount Type <span className="text-destructive">*</span>
              </label>
              <select
                value={formData.discount_type}
                onChange={(e) => setFormData({ ...formData, discount_type: e.target.value })}
                className="w-full px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="percentage">Percentage (%)</option>
                <option value="fixed">Fixed Amount ({currencySymbol()})</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Discount Value <span className="text-destructive">*</span>
              </label>
              <div className="relative">
                {formData.discount_type === 'percentage' ? (
                  <Percent className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={16} />
                ) : (
                  <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground text-sm font-semibold" aria-hidden="true">{currencySymbol()}</span>
                )}
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={formData.value}
                  onChange={(e) => setFormData({ ...formData, value: e.target.value })}
                  className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                  placeholder={formData.discount_type === 'percentage' ? '20' : '100'}
                  required
                />
              </div>
            </div>
          </div>
        </div>

        {/* Restrictions */}
        <div className="bg-card rounded-xl shadow-sm p-3 border border-border">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Restrictions</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Minimum Order Value
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={formData.min_order_value}
                onChange={(e) => setFormData({ ...formData, min_order_value: e.target.value })}
                className="w-full px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="e.g., 500"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Maximum Uses (Total)
              </label>
              <input
                type="number"
                min="1"
                value={formData.max_uses}
                onChange={(e) => setFormData({ ...formData, max_uses: e.target.value })}
                className="w-full px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                placeholder="e.g., 100"
              />
              {!formData.max_uses && (
                <p className="text-xs text-warning mt-1">No cap — flagged as risky hygiene (unlimited uses).</p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Valid From
              </label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={16} />
                <input
                  type="date"
                  value={formData.valid_from}
                  onChange={(e) => setFormData({ ...formData, valid_from: e.target.value })}
                  className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Valid Until
              </label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={16} />
                <input
                  type="date"
                  value={formData.valid_until}
                  onChange={(e) => setFormData({ ...formData, valid_until: e.target.value })}
                  className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                />
              </div>
              {!formData.valid_until && (
                <p className="text-xs text-warning mt-1">No expiry — flagged as risky hygiene.</p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-muted-foreground mb-1">
                Max Uses Per User
              </label>
              <div className="relative">
                <Users className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={16} />
                <input
                  type="number"
                  min="1"
                  value={formData.max_uses_per_user}
                  onChange={(e) => setFormData({ ...formData, max_uses_per_user: e.target.value })}
                  className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                  placeholder="1"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Trigger Condition (automatic coupons only) */}
        {formData.coupon_type === 'automatic' && (
          <div className="lg:col-span-2 bg-card rounded-xl shadow-sm p-3 border border-border">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">Trigger Condition</h2>
            <p className="text-xs text-muted-foreground mb-2">
              The backend applies this coupon by itself whenever the condition below is met, and always re-checks eligibility server-side before checkout.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-muted-foreground mb-1">
                  Applies automatically when <span className="text-destructive">*</span>
                </label>
                <select
                  value={formData.trigger_type}
                  onChange={(e) => setFormData({
                    ...formData,
                    trigger_type: e.target.value,
                    trigger_min_cart_value: '',
                    trigger_min_item_count: '',
                    trigger_category_id: '',
                    trigger_category_spend: ''
                  })}
                  className="w-full px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                >
                  <option value="min_cart_value">Cart value reaches a minimum amount</option>
                  <option value="min_item_count">Cart has a minimum number of items</option>
                  <option value="category_spend">Customer spends a minimum on a specific category</option>
                  <option value="first_order">It is the customer's first order</option>
                </select>
              </div>

              {formData.trigger_type === 'min_cart_value' && (
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Minimum cart value ({currencySymbol()}) <span className="text-destructive">*</span>
                  </label>
                  <div className="relative">
                    <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground text-sm font-semibold" aria-hidden="true">{currencySymbol()}</span>
                    <input
                      type="number"
                      min="1"
                      step="0.01"
                      value={formData.trigger_min_cart_value}
                      onChange={(e) => setFormData({ ...formData, trigger_min_cart_value: e.target.value })}
                      className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                      placeholder="e.g., 2000"
                      required
                    />
                  </div>
                </div>
              )}

              {formData.trigger_type === 'min_item_count' && (
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">
                    Minimum item count <span className="text-destructive">*</span>
                  </label>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={formData.trigger_min_item_count}
                    onChange={(e) => setFormData({ ...formData, trigger_min_item_count: e.target.value })}
                    className="w-full px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                    placeholder="e.g., 3"
                    required
                  />
                </div>
              )}

              {formData.trigger_type === 'category_spend' && (
                <>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Category <span className="text-destructive">*</span>
                    </label>
                    <select
                      value={formData.trigger_category_id}
                      onChange={(e) => setFormData({ ...formData, trigger_category_id: e.target.value })}
                      className="w-full px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                      required
                    >
                      <option value="">Select a category…</option>
                      {categories.map((c) => (
                        <option key={c.id} value={c.id}>{c.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted-foreground mb-1">
                      Minimum spend in category ({currencySymbol()}) <span className="text-destructive">*</span>
                    </label>
                    <div className="relative">
                      <span className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground text-sm font-semibold" aria-hidden="true">{currencySymbol()}</span>
                      <input
                        type="number"
                        min="1"
                        step="0.01"
                        value={formData.trigger_category_spend}
                        onChange={(e) => setFormData({ ...formData, trigger_category_spend: e.target.value })}
                        className="w-full pl-9 pr-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="e.g., 5000"
                        required
                      />
                    </div>
                  </div>
                </>
              )}

              {formData.trigger_type === 'first_order' && (
                <div className="md:col-span-2 text-xs text-muted-foreground bg-primary-soft border border-primary/20 rounded-lg p-3">
                  Applies only to customers who have never placed a valid order (cancelled and refunded orders do not count).
                </div>
              )}
            </div>
          </div>
        )}

        {/* Status + Actions */}
        <div className="lg:col-span-2 bg-card rounded-xl shadow-sm border border-border p-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.is_active}
              onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
              className="w-4 h-4 text-primary rounded border-input focus:ring-primary"
            />
            <span className="text-xs font-medium text-foreground">Active</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer" title="Staff/test codes rejected at checkout validation">
            <input
              type="checkbox"
              checked={!!formData.internal_only}
              onChange={(e) => setFormData({ ...formData, internal_only: e.target.checked })}
              className="w-4 h-4 text-primary rounded border-input focus:ring-primary"
            />
            <span className="text-xs font-medium text-foreground">Internal only</span>
          </label>
          <span className="text-xs text-muted-foreground">
            {formData.is_active ? 'Coupon is available for use' : 'Coupon is disabled'}
            {formData.internal_only ? ' · staff/test code — never valid on public orders' : ''}
          </span>
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => navigate('/coupons')}
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
                  {isEdit ? 'Update Coupon' : 'Create Coupon'}
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

export default CouponForm;
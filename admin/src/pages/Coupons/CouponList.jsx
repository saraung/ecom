// src/pages/Coupons/CouponList.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Plus, 
  Search, 
  Edit, 
  Trash2, 
  Percent, 
  Copy, 
  Calendar,
  Tag,
  RefreshCw,
  Users,
  Sparkles,
  Zap
} from 'lucide-react';
import { getCoupons, deleteCoupon, generateCoupon, getRiskyCoupons } from '../../api/coupons';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions'; // 👈 ADDED
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import { currencySymbol, formatPrice, formatDate } from '../../utils/format';

// Trigger summary shown under the "Automatic" badge in the coupons table
const getTriggerLabel = (coupon) => {
  switch (coupon.trigger_type) {
    case 'min_cart_value':
      return `Cart ≥ ${formatPrice(coupon.trigger_min_cart_value)}`;
    case 'min_item_count':
      return `${coupon.trigger_min_item_count}+ items`;
    case 'category_spend':
      return `${formatPrice(coupon.trigger_category_spend)} in category`;
    case 'first_order':
      return 'First order';
    default:
      return '';
  }
};

const CouponList = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  // Every coupon mutation on this page maps to one backend permission:
  // create / generate / edit / delete all require coupons.manage.
  const canManage = canDo(user, 'coupons.manage');
  const [loading, setLoading] = useState(true);
  const [coupons, setCoupons] = useState([]);
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [totalCoupons, setTotalCoupons] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [risky, setRisky] = useState({ count: 0, coupons: [] });
  const [confirmState, setConfirmState] = useState(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const itemsPerPage = 10;

  useEffect(() => {
    fetchCoupons();
    getRiskyCoupons().then((r) => setRisky(r.data || { count: 0, coupons: [] })).catch(() => {});
  }, [currentPage]);

  const fetchCoupons = async () => {
    try {
      setLoading(true);
      const params = {
        page: currentPage,
        limit: itemsPerPage,
        search: search || undefined
      };
      
      const response = await getCoupons(params);
      
      let couponsData = [];
      let total = 0;
      
      if (Array.isArray(response.data)) {
        couponsData = response.data;
        total = response.data.length;
      } else if (response.data?.items) {
        couponsData = response.data.items;
        total = response.data.total || couponsData.length;
      } else if (response.data?.data) {
        couponsData = response.data.data;
        total = response.data.total || couponsData.length;
      }
      
      setCoupons(couponsData);
      setTotalCoupons(total);
      setTotalPages(Math.ceil(total / itemsPerPage) || 1);
    } catch {
      toast.error('Failed to load coupons');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = (id, code) => {
    // 👈 Only coupons.manage can delete
    if (!canManage) {
      toast.error('You do not have permission to delete coupons');
      return;
    }

    setConfirmState({
      id,
      title: 'Delete Coupon',
      message: `Are you sure you want to delete coupon "${code}"?`,
    });
  };

  const runConfirmed = async () => {
    if (!confirmState) return;
    try {
      setConfirmBusy(true);
      await deleteCoupon(confirmState.id);
      toast.success('Coupon deleted successfully');
      fetchCoupons();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to delete coupon');
    } finally {
      setConfirmBusy(false);
      setConfirmState(null);
    }
  };

  const handleGenerate = async () => {
    // 👈 Only coupons.manage can generate
    if (!canManage) {
      toast.error('You do not have permission to generate coupons');
      return;
    }
    
    try {
      setGenerating(true);
      const response = await generateCoupon();
      const generatedCode = response.data.code;
      
      navigate('/coupons/new', { 
        state: { generatedCode } 
      });
    } catch {
      toast.error('Failed to generate coupon code');
    } finally {
      setGenerating(false);
    }
  };

  const handleCopyCode = (code) => {
    navigator.clipboard.writeText(code);
    toast.success('Coupon code copied!', { duration: 2000 });
  };

  const getDiscountDisplay = (coupon) => {
    if (coupon.discount_type === 'percentage') {
      return `${coupon.value}%`;
    } else {
      return `${formatPrice(coupon.value)}`;
    }
  };

  const getStatusBadge = (coupon) => {
    const now = new Date();
    const validFrom = new Date(coupon.valid_from);
    const validUntil = coupon.valid_until ? new Date(coupon.valid_until) : null;
    
    if (!coupon.is_active) {
      return { label: 'Inactive', color: 'bg-muted text-foreground' };
    }
    if (coupon.valid_until && validUntil < now) {
      return { label: 'Expired', color: 'bg-destructive/15 text-destructive' };
    }
    if (coupon.valid_from && validFrom > now) {
      return { label: 'Scheduled', color: 'bg-warning/20 text-warning' };
    }
    return { label: 'Active', color: 'bg-success/15 text-success' };
  };

  const filteredCoupons = coupons.filter(coupon =>
    coupon.code?.toLowerCase().includes(search.toLowerCase())
  );

  if (loading) {
    return <PageSkeleton type="coupons" />;
  }

  return (
    <div>
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Coupons</h1>
          <p className="text-sm text-muted-foreground mt-1">{totalCoupons} coupons found</p>
        </div>
        <div className="flex flex-col sm:flex-row w-full sm:w-auto gap-2">
          {/* 👇 coupons.manage can generate */}
          {canManage && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50"
            >
              {generating ? (
                <>
                  <RefreshCw size={18} className="animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles size={18} />
                  Generate Code
                </>
              )}
            </button>
          )}
          {/* 👇 coupons.manage can create */}
          {canManage && (
            <button
              onClick={() => navigate('/coupons/new')}
              className="btn-primary flex items-center justify-center gap-2 py-2.5 sm:py-2"
            >
              <Plus size={20} />
              Create Coupon
            </button>
          )}
        </div>
      </div>

      <div className="relative w-full max-w-md mb-4">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
        <input
          type="text"
          placeholder="Search coupons by code..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && fetchCoupons()}
          className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
        />
      </div>
      {risky.count > 0 && (
        <div className="mb-4 text-xs bg-warning/10 border border-warning/30 text-warning rounded-lg p-3">
          Hygiene: {risky.count} live coupon{ risky.count === 1 ? '' : 's'} missing expiry/caps or granting 100% off —{' '}
          {risky.coupons.slice(0, 5).map((c) => `${c.code} (${c.reasons.join(', ')})`).join(' · ')}
          {risky.count > 5 ? ' …' : ''}
        </div>
      )}

      <div className="bg-card rounded-xl shadow-sm overflow-hidden border border-border">
        {/* Desktop table */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full min-w-[880px]">
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Type</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Code</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Discount</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Min Order</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Valid From</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Valid Until</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Uses</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredCoupons.length === 0 ? (
                <tr>
                  <td colSpan="9" className="px-4 py-8 text-center text-muted-foreground">
                    No coupons found. Create your first coupon!
                  </td>
                </tr>
              ) : (
                filteredCoupons.map((coupon) => {
                  const status = getStatusBadge(coupon);
                  return (
                    <tr key={coupon.id} className="hover:bg-muted transition-colors">
                      <td className="px-4 py-3">
                        {coupon.coupon_type === 'automatic' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-purple-500/15 text-purple-600">
                            <Zap size={12} />
                            Automatic
                          </span>
                        ) : (
                          <span className="px-2 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground">
                            Manual
                          </span>
                        )}
                        {coupon.coupon_type === 'automatic' && getTriggerLabel(coupon) && (
                          <div className="text-xs text-muted-foreground mt-1">{getTriggerLabel(coupon)}</div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="font-mono font-bold text-primary bg-primary-soft px-3 py-1 rounded-lg">
                            {coupon.code}
                          </span>
                          <button
                            onClick={() => handleCopyCode(coupon.code)}
                            className="text-muted-foreground hover:text-muted-foreground transition-colors"
                            title="Copy code"
                          >
                            <Copy size={16} />
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          {coupon.discount_type === 'percentage' ? (
                            <Percent size={16} className="text-success" />
                          ) : (
                            <span className="text-success text-base font-semibold leading-none" aria-hidden="true">{currencySymbol()}</span>
                          )}
                          <span className="font-semibold text-success">
                            {getDiscountDisplay(coupon)}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {coupon.min_order_value ? `${formatPrice(coupon.min_order_value)}` : '—'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(coupon.valid_from)}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {coupon.valid_until ? formatDate(coupon.valid_until) : 'Never'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm">
                          <span className="font-medium">{coupon.times_used || 0}</span>
                          {coupon.max_uses && (
                            <span className="text-muted-foreground"> / {coupon.max_uses}</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${status.color}`}>
                          {status.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {/* 👇 coupons.manage can edit */}
                          {canManage && (
                            <button
                              onClick={() => navigate(`/coupons/${coupon.id}/edit`)}
                              className="p-1 text-primary hover:bg-primary-soft rounded transition-colors"
                              title="Edit Coupon"
                            >
                              <Edit size={18} />
                            </button>
                          )}
                          {/* 👇 coupons.manage can delete */}
                          {canManage && (
                            <button
                              onClick={() => handleDelete(coupon.id, coupon.code)}
                              className="p-1 text-destructive hover:bg-destructive/10 rounded transition-colors"
                              title="Delete Coupon"
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

        {/* Mobile cards */}
        <div className="md:hidden divide-y divide-border">
          {filteredCoupons.length === 0 ? (
            <div className="px-4 py-8 text-center text-muted-foreground">
              No coupons found. Create your first coupon!
            </div>
          ) : (
            filteredCoupons.map((coupon) => {
              const status = getStatusBadge(coupon);
              return (
                <div key={coupon.id} className="p-4 space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-mono font-bold text-primary bg-primary-soft px-2.5 py-1 rounded-lg text-sm truncate">
                        {coupon.code}
                      </span>
                      <button
                        onClick={() => handleCopyCode(coupon.code)}
                        className="p-1.5 text-muted-foreground hover:text-foreground shrink-0"
                        title="Copy code"
                        aria-label={`Copy ${coupon.code}`}
                      >
                        <Copy size={15} />
                      </button>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium shrink-0 ${status.color}`}>
                      {status.label}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    {coupon.coupon_type === 'automatic' ? (
                      <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-purple-500/15 text-purple-600">
                        <Zap size={12} />
                        Automatic
                      </span>
                    ) : (
                      <span className="px-2 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground">
                        Manual
                      </span>
                    )}
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-success">
                      {coupon.discount_type === 'percentage' ? (
                        <Percent size={14} />
                      ) : (
                        <span className="text-sm font-semibold leading-none" aria-hidden="true">{currencySymbol()}</span>
                      )}
                      {getDiscountDisplay(coupon)}
                    </span>
                    {coupon.coupon_type === 'automatic' && getTriggerLabel(coupon) && (
                      <span className="text-xs text-muted-foreground">{getTriggerLabel(coupon)}</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{coupon.min_order_value ? `Min ${formatPrice(coupon.min_order_value)}` : 'No min order'}</span>
                    <span>
                      {coupon.times_used || 0}
                      {coupon.max_uses ? ` / ${coupon.max_uses}` : ''} used
                    </span>
                    <span>{coupon.valid_until ? formatDate(coupon.valid_until) : 'No expiry'}</span>
                  </div>
                  {canManage && (
                    <div className="flex gap-2 pt-1">
                      <button
                        onClick={() => navigate(`/coupons/${coupon.id}/edit`)}
                        className="flex-1 px-3 py-2.5 border border-input rounded-lg text-sm flex items-center justify-center gap-1 hover:bg-muted"
                      >
                        <Edit size={14} />
                        Edit
                      </button>
                      <button
                        onClick={() => handleDelete(coupon.id, coupon.code)}
                        className="flex-1 px-3 py-2.5 border border-input rounded-lg text-sm flex items-center justify-center gap-1 text-destructive hover:bg-destructive/10"
                      >
                        <Trash2 size={14} />
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, totalCoupons)} of {totalCoupons} coupons
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
                Page {currentPage} of {totalPages}
              </span>
              <button
                disabled={currentPage === totalPages}
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
        title={confirmState?.title || 'Delete Coupon'}
        message={confirmState?.message}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        tone="danger"
        busy={confirmBusy}
        onClose={() => { if (!confirmBusy) setConfirmState(null); }}
        onConfirm={runConfirmed}
      />
    </div>
  );
};

export default CouponList;
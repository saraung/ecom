// src/pages/Dashboard/Dashboard.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Package, 
  ShoppingBag, 
  Users, 
  Clock,
  DollarSign,
  CheckCircle,
  XCircle,
  Truck,
  RefreshCw,
  ChevronRight,
  Eye,
  BarChart3,
  PieChart,
  TrendingUp,
  Tags
} from 'lucide-react';
import { getDashboardStats, getTopProducts } from '../../api/analytics';
import { getCategories } from '../../api/categories';
import { getProducts } from '../../api/products';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import StatCard from '../../components/cards/StatCard';
import InfoCard from '../../components/cards/InfoCard';
import RevenueChart from '../../components/charts/RevenueChart';
import TopProductsChart from '../../components/charts/TopProductsChart';
import OrderStatusChart from '../../components/charts/OrderStatusChart';
import SalesByCategoryChart from '../../components/charts/SalesByCategoryChart';
import SalesTrendChart from '../../components/charts/SalesTrendChart';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { formatDate, formatNumber, formatPrice, formatShort } from '../../utils/format';

// Compact on small screens, full precision on desktop — both from the
// deployment locale (lakh/crore under en-IN, K/M under en-US/…).
const useResponsivePrice = () => {
  const [isMobile, setIsMobile] = useState(window.innerWidth < 640);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 640);
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  return (price) => (isMobile ? formatShort(price) : formatPrice(price));
};

const Dashboard = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  // Each dashboard card/shortcut is keyed off the permission its destination
  // needs (users.view, orders.view, products.create, categories.view) rather
  // than the single legacy `role` string, so stacked roles can't hide them.
  const canViewUsers = canDo(user, 'users.view', 'admin');
  const canViewOrders = canDo(user, 'orders.view', 'manager');
  const canCreateProducts = canDo(user, 'products.create', 'staff');
  const canViewCategories = canDo(user, 'categories.view', 'manager');
  const [loading, setLoading] = useState(true);
  const formatPrice = useResponsivePrice();
  const [dashboardData, setDashboardData] = useState({
    users: {
      total_users: 0,
      active_users: 0,
      inactive_users: 0,
      admin_users: 0,
      staff_users: 0,
      manager_users: 0,
      customer_users: 0
    },
    orders: {
      total: 0,
      pending: 0,
      confirmed: 0,
      shipped: 0,
      delivered: 0,
      cancelled: 0,
      refunded: 0
    },
    revenue: {
      today: { orders: 0, revenue: 0 },
      this_week: { orders: 0, revenue: 0 },
      this_month: { orders: 0, revenue: 0 },
      total: { orders: 0, revenue: 0, pending_orders: 0, total_products: 0 },
      top_products: []
    },
    total_products: 0,
    recent_orders: [],
    sales_trend: [],
    // Top 4 root categories + "Others" bucket (30d). Preferred source is the
    // backend key; the client-side fallback below fills it in until the
    // backend ships it.
    sales_by_category: []
  });

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const toISODate = (d) => d.toISOString().split('T')[0];

  // Walk a category up to its root via parent_id (cycle-safe). Children
  // credit their top-level parent so the chart never exceeds 5 rows.
  const resolveRootCategory = (categoryId, categoryMap) => {
    let current = categoryMap[categoryId];
    if (!current) return null;
    const seen = new Set();
    while (current?.parent_id && categoryMap[current.parent_id] && !seen.has(current.id)) {
      seen.add(current.id);
      current = categoryMap[current.parent_id];
    }
    return current;
  };

  // INTERIM fallback: derives last-30d sales-by-category client-side from
  // APIs that already exist (top-products + catalog + category tree).
  // Skipped entirely once GET /admin/dashboard ships `sales_by_category`.
  // Products that can't be mapped to a category fold into "Others".
  const deriveSalesByCategory = async () => {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - 30);

    const [topRes, catRes, prodRes] = await Promise.allSettled([
      getTopProducts({ limit: 100, from_date: toISODate(from), to_date: toISODate(to) }),
      getCategories(),
      getProducts(),
    ]);

    if (topRes.status !== 'fulfilled') return [];
    const topItems = Array.isArray(topRes.value?.data) ? topRes.value.data : [];
    if (topItems.length === 0) return [];

    // Category map (handles array or paginated {items/data} shapes).
    const rawCats =
      catRes.status === 'fulfilled'
        ? (Array.isArray(catRes.value?.data)
            ? catRes.value.data
            : catRes.value?.data?.items || catRes.value?.data?.data || [])
        : [];
    const categoryMap = {};
    rawCats.forEach((c) => {
      if (c?.id) categoryMap[c.id] = c;
    });

    // product_id → category_id map (handles array or paginated shapes).
    const rawProds =
      prodRes.status === 'fulfilled'
        ? (Array.isArray(prodRes.value?.data)
            ? prodRes.value.data
            : prodRes.value?.data?.items || prodRes.value?.data?.data || [])
        : [];
    const productCategoryMap = {};
    rawProds.forEach((p) => {
      if (!p?.id) return;
      const cid =
        p.category_id ||
        (p.category && typeof p.category === 'object' ? p.category.id : null) ||
        null;
      if (cid) productCategoryMap[p.id] = cid;
    });

    // Aggregate product revenue/qty into root categories.
    const byRoot = {};
    let othersRevenue = 0;
    let othersQty = 0;
    topItems.forEach((item) => {
      const revenue = Number(item?.total_revenue) || 0;
      const qty = Number(item?.total_quantity_sold) || 0;
      const root = resolveRootCategory(productCategoryMap[item?.product_id], categoryMap);
      if (!root) {
        othersRevenue += revenue;
        othersQty += qty;
        return;
      }
      if (!byRoot[root.id]) {
        byRoot[root.id] = { category_id: root.id, category_name: root.name, revenue: 0, quantity_sold: 0 };
      }
      byRoot[root.id].revenue += revenue;
      byRoot[root.id].quantity_sold += qty;
    });

    const ranked = Object.values(byRoot).sort((a, b) => b.revenue - a.revenue);
    const top4 = ranked.slice(0, 4);
    const rest = ranked.slice(4);
    const restRevenue = rest.reduce((s, r) => s + r.revenue, 0) + othersRevenue;
    const restQty = rest.reduce((s, r) => s + r.quantity_sold, 0) + othersQty;
    if (restRevenue > 0 || restQty > 0) {
      top4.push({ category_id: null, category_name: 'Others', revenue: restRevenue, quantity_sold: restQty });
    }
    return top4;
  };

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const response = await getDashboardStats();
      const base = response.data || {};
      let salesByCategory = base.sales_by_category || [];
      if (salesByCategory.length === 0) {
        try {
          salesByCategory = await deriveSalesByCategory();
        } catch {
          salesByCategory = [];
        }
      }
      setDashboardData({ ...base, sales_by_category: salesByCategory });
    } catch {
      toast.error('Failed to load dashboard');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const config = {
      pending: { icon: Clock, color: 'bg-warning/20 text-warning' },
      confirmed: { icon: CheckCircle, color: 'bg-primary-soft text-primary-soft-foreground' },
      shipped: { icon: Truck, color: 'bg-purple-500/15 text-purple-600 dark:text-purple-300' },
      delivered: { icon: CheckCircle, color: 'bg-success/15 text-success' },
      cancelled: { icon: XCircle, color: 'bg-destructive/15 text-destructive' },
      refunded: { icon: RefreshCw, color: 'bg-muted text-foreground' }
    };
    const { icon: Icon, color } = config[status] || config.pending;
    return { Icon, color };
  };

  if (loading) {
    return <PageSkeleton type="dashboard" />;
  }

  // Prefer the ranked top-products widget; fall back to the period chart only
  // when nothing sold in the last 30 days.
  const topProducts = dashboardData.revenue?.top_products || [];
  const hasTopProducts = topProducts.length > 0;

  // Top 4 root categories + "Others" (30d). Never exceeds 5 rows by
  // construction (backend key or the client-side fallback above).
  const salesByCategory = dashboardData.sales_by_category || [];

  const handleCategorySelect = (category) => {
    if (category?.category_id) {
      navigate(`/categories/${category.category_id}/products`);
    }
  };

  return (
    <div className="space-y-4 sm:space-y-6 px-2 sm:px-0">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-foreground">Dashboard</h1>
          <p className="text-xs sm:text-sm text-muted-foreground mt-1">
            Welcome back! Here's what's happening with your store.
          </p>
        </div>
        <button
          onClick={fetchDashboardData}
          className="self-start sm:self-auto p-2 hover:bg-muted rounded-lg transition"
          title="Refresh data"
        >
          <RefreshCw size={16} className="text-muted-foreground" />
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-4">
        <StatCard
          title="Revenue"
          value={formatPrice(dashboardData.revenue.total.revenue || 0)}
          icon={DollarSign}
          color="green"
          subtitle={`Today: ${formatPrice(dashboardData.revenue.today.revenue || 0)}`}
          onClick={() => navigate('/reports')}
        />
        <StatCard
          title="Orders"
          value={formatNumber(dashboardData.orders.total || 0)}
          icon={ShoppingBag}
          color="blue"
          subtitle={`${dashboardData.orders.pending || 0} pending`}
          onClick={() => navigate('/orders')}
        />
        <StatCard
          title="Products"
          value={formatNumber(dashboardData.total_products || 0)}
          icon={Package}
          color="purple"
          subtitle="In store"
          onClick={() => navigate('/products')}
        />
        <StatCard
          title="Users"
          value={formatNumber(dashboardData.users.total_users || 0)}
          icon={Users}
          color="orange"
          subtitle={`${dashboardData.users.active_users || 0} active`}
          onClick={canViewUsers ? () => navigate('/users') : undefined}
        />
      </div>

      {/* Revenue Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <InfoCard 
          title="Top Products by Revenue (30d)" 
          icon={BarChart3}
          action={
            <button 
              onClick={() => navigate('/reports?tab=products')}
              className="text-xs sm:text-sm text-primary hover:text-primary-hover font-medium flex items-center gap-1"
            >
              <span className="hidden sm:inline">Details</span> 
              <ChevronRight size={16} />
            </button>
          }
        >
          {hasTopProducts ? (
            <TopProductsChart products={topProducts} max={4} />
          ) : (
            <RevenueChart data={dashboardData.revenue} />
          )}
        </InfoCard>

        <InfoCard title="Sales Trend" icon={TrendingUp}>
          <SalesTrendChart data={dashboardData.sales_trend} />
        </InfoCard>
      </div>

      {/* Order Status & Sales by Category */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <InfoCard title="Order Distribution" icon={PieChart}>
          <OrderStatusChart orders={dashboardData.orders} />
        </InfoCard>

        <InfoCard
          title="Sales by Category (30d)"
          icon={Tags}
          action={
            <button
              onClick={() => navigate('/categories')}
              className="text-xs sm:text-sm text-primary hover:text-primary-hover font-medium flex items-center gap-1"
            >
              <span className="hidden sm:inline">Details</span>
              <ChevronRight size={16} />
            </button>
          }
        >
          <SalesByCategoryChart data={salesByCategory} max={5} onSelect={handleCategorySelect} />
        </InfoCard>
      </div>

      {/* Recent Orders - orders.view */}
      {canViewOrders && (
        <InfoCard 
          title="Recent Orders" 
          icon={ShoppingBag}
          action={
            <button 
              onClick={() => navigate('/orders')}
              className="text-xs sm:text-sm text-primary hover:text-primary-hover font-medium flex items-center gap-1"
            >
              <span className="hidden sm:inline">View All</span> 
              <ChevronRight size={16} />
            </button>
          }
        >
          {dashboardData.recent_orders && dashboardData.recent_orders.length > 0 ? (
            <>
              {/* Mobile: Card view */}
              <div className="sm:hidden space-y-3">
                {dashboardData.recent_orders.slice(0, 5).map((order) => {
                  const { Icon, color } = getStatusBadge(order.status);
                  return (
                    <div 
                      key={order.id}
                      className="p-4 bg-muted rounded-lg cursor-pointer hover:bg-muted transition"
                      onClick={() => navigate(`/orders/${order.id}`)}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <div className="font-medium text-foreground">#{order.order_number}</div>
                          <div className="text-xs text-muted-foreground">
                            {formatDate(order.placed_at, {
                              day: '2-digit',
                              month: 'short',
                              year: 'numeric'
                            })}
                          </div>
                        </div>
                        <span className={`px-2 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1 ${color}`}>
                          <Icon size={12} />
                          {order.status}
                        </span>
                      </div>
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-semibold text-foreground">
                          {formatPrice(parseFloat(order.grand_total))}
                        </span>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            navigate(`/orders/${order.id}`);
                          }}
                          className="text-primary hover:text-primary-hover"
                        >
                          <Eye size={16} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Desktop: Table view */}
              <div className="hidden sm:block overflow-x-auto">
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-muted">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        Order #
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        Date
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        Total
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        Action
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-card divide-y divide-border">
                    {dashboardData.recent_orders.slice(0, 5).map((order) => {
                      const { Icon, color } = getStatusBadge(order.status);
                      return (
                        <tr 
                          key={order.id}
                          className="hover:bg-muted cursor-pointer"
                          onClick={() => navigate(`/orders/${order.id}`)}
                        >
                          <td className="px-4 py-3 text-sm font-medium text-foreground">
                            #{order.order_number}
                          </td>
                          <td className="px-4 py-3 text-sm text-muted-foreground">
                            {formatDate(order.placed_at, {
                              day: '2-digit',
                              month: 'short',
                              year: 'numeric'
                            })}
                          </td>
                          <td className="px-4 py-3">
                            <span className={`px-2 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1 ${color}`}>
                              <Icon size={12} />
                              {order.status}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-sm font-semibold text-foreground text-right">
                            {formatPrice(parseFloat(order.grand_total))}
                          </td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/orders/${order.id}`);
                              }}
                              className="text-primary hover:text-primary-hover"
                            >
                              <Eye size={16} />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <ShoppingBag size={32} className="mx-auto text-muted-foreground mb-2" />
              <p>No recent orders</p>
            </div>
          )}
        </InfoCard>
      )}

      {/* Quick Actions */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 sm:gap-4">
        {/* Add Product - products.create */}
        {canCreateProducts && (
          <button
            onClick={() => navigate('/products/new')}
            className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-3 sm:p-4 bg-primary-soft text-primary rounded-xl hover:bg-primary-hover/20 transition-colors"
          >
            <Package size={18} />
            <span className="text-xs sm:text-sm font-medium">Add Product</span>
          </button>
        )}
        
        {/* Shortcuts are each gated by the permission their destination page
            needs, so staff who can open /orders still see that shortcut. */}
        {canViewCategories && (
          <button
            onClick={() => navigate('/categories')}
            className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-3 sm:p-4 bg-purple-500/10 text-purple-600 dark:text-purple-300 rounded-xl hover:bg-purple-500/20 transition-colors"
          >
            <Package size={18} />
            <span className="text-xs sm:text-sm font-medium">Categories</span>
          </button>
        )}

        {canViewOrders && (
          <button
            onClick={() => navigate('/orders')}
            className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-3 sm:p-4 bg-success/10 text-success rounded-xl hover:bg-success/20 transition-colors"
          >
            <ShoppingBag size={18} />
            <span className="text-xs sm:text-sm font-medium">Orders</span>
          </button>
        )}

        {canViewOrders && (
          <button
            onClick={() => navigate('/orders?status=pending')}
            className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-3 sm:p-4 bg-warning/10 text-warning rounded-xl hover:bg-warning/20 transition-colors"
          >
            <Clock size={18} />
            <span className="text-xs sm:text-sm font-medium">
              Pending ({dashboardData.orders.pending || 0})
            </span>
          </button>
        )}
        
        {canViewUsers && (
          <button
            onClick={() => navigate('/users')}
            className="flex flex-col sm:flex-row items-center justify-center gap-1 sm:gap-2 p-3 sm:p-4 bg-orange-500/10 text-orange-600 dark:text-orange-300 rounded-xl hover:bg-orange-500/20 transition-colors"
          >
            <Users size={18} />
            <span className="text-xs sm:text-sm font-medium">Users</span>
          </button>
        )}
      </div>
    </div>
  );
};

export default Dashboard;
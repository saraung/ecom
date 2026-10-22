// src/pages/Reports/Reports.jsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Download, 
  Calendar, 
  TrendingUp, 
  ShoppingBag, 
  Users,
  Package,
  DollarSign,
  RefreshCw,
  Shield,
  Filter,
  X,
  Image as ImageIcon
} from 'lucide-react';
import jsPDF from 'jspdf';
import autoTable, { __createTable, __drawTable } from 'jspdf-autotable';
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { 
  getSalesReport, 
  getTopProducts, 
  getOrderStatistics,
  getRevenueReport,
  getCustomerSummary,
  getDashboardStats
} from '../../api/analytics';
import { getProductImages } from '../../api/products';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import OrderStatusChart from '../../components/charts/OrderStatusChart';
import { formatDate, formatPrice as sharedFormatPrice, formatNumber, formatShort } from '../../utils/format';
import { getRegion } from '../../utils/region';
import { createReportLoader } from '../../utils/reportLoader';

const Reports = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  // Matches the backend's require_perm("reports.view"). Kept out of the gate
  // below rather than a role-string check so stacked roles can't lock us out.
  const allowed = canDo(user, 'reports.view');
  // NOTE: hooks below must stay unconditional (Rules of Hooks). The
  // access-denied screen is returned only AFTER all hooks run.

  const [loading, setLoading] = useState(true);
  const [dateRange, setDateRange] = useState({
    from_date: new Date(new Date().setDate(new Date().getDate() - 30)).toISOString().split('T')[0],
    to_date: new Date().toISOString().split('T')[0]
  });
  const [groupBy, setGroupBy] = useState('day');
  const [dashboardData, setDashboardData] = useState(null);
  const [salesData, setSalesData] = useState(null);
  const [topProducts, setTopProducts] = useState([]);
  const [orderStats, setOrderStats] = useState(null);
  const [revenueData, setRevenueData] = useState(null);
  const [customerSummary, setCustomerSummary] = useState(null);
  // Prior equal-length period sales summary for ▲/▼ deltas (best-effort;
  // a failed fetch just hides deltas, never blocks the report).
  const [prevSummary, setPrevSummary] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [showFilters, setShowFilters] = useState(true);
  // 👇 Product images for the Top Selling Products report
  const [productImages, setProductImages] = useState({});
  const [failedImages, setFailedImages] = useState(() => new Set());
  const [reportErrors, setReportErrors] = useState([]);
  const [loadReports] = useState(() => createReportLoader({
    requests: [
      { key: 'dashboard', load: () => getDashboardStats() },
      { key: 'sales', load: getSalesReport },
      { key: 'products', load: (params) => getTopProducts({ ...params, limit: 10 }) },
      { key: 'orders', load: getOrderStatistics },
      { key: 'revenue', load: getRevenueReport },
      { key: 'customers', load: getCustomerSummary },
    ],
    onStart: () => {
      setLoading(true);
      setReportErrors([]);
      setDashboardData(null);
      setSalesData(null);
      setTopProducts([]);
      setOrderStats(null);
      setRevenueData(null);
      setCustomerSummary(null);
    },
    onResult: ({ data, failures }) => {
      setDashboardData(data.dashboard ?? null);
      setSalesData(data.sales ?? null);
      setTopProducts(data.products ?? []);
      setOrderStats(data.orders ?? null);
      setRevenueData(data.revenue ?? null);
      setCustomerSummary(data.customers ?? null);
      setReportErrors(failures);
      setLoading(false);
      if (failures.length) toast.error(`Could not load: ${failures.join(', ')}. Please retry.`);
    },
  }));
  const fetchAllReports = useCallback(() => loadReports({ ...dateRange, group_by: groupBy }),
    [loadReports, dateRange, groupBy]);

  // Quick date range presets
  const datePresets = [
    { label: 'Today', days: 0 },
    { label: 'Last 7 Days', days: 7 },
    { label: 'Last 30 Days', days: 30 },
    { label: 'Last 90 Days', days: 90 },
    { label: 'This Year', days: 365 },
  ];

  // Active preset: exact match of the current range against each
  // preset's implied range (same UTC derivation as handleDatePreset).
  // Custom ranges match nothing — honestly signalling a custom scope.
  const activePreset = (() => {
    const fmt = (d) => d.toISOString().split('T')[0];
    const today = fmt(new Date());
    for (const preset of datePresets) {
      const from = new Date();
      from.setDate(from.getDate() - preset.days);
      if (fmt(from) === dateRange.from_date && today === dateRange.to_date) {
        return preset.label;
      }
    }
    return null;
  })();

  // Resolve the image URL for a top-selling product. Prefers an image field
  // returned by the analytics endpoint, then falls back to images fetched
  // separately from the product images API.
  const getTopProductImage = (product) => {
    if (!product) return null;
    const direct =
      product.product_image ||
      product.image_url ||
      product.image ||
      product.thumbnail ||
      product.primary_image;
    if (direct) return direct;
    if (Array.isArray(product.images) && product.images.length > 0) {
      return product.images[0]?.url || product.images[0]?.image || null;
    }
    return productImages[product.product_id] || null;
  };

  const handleImageError = (key) => {
    setFailedImages((prev) => {
      const next = new Set(prev);
      next.add(String(key));
      return next;
    });
  };

  // Fetch images for top products when the analytics payload doesn't
  // already include an image URL (limit: 10 products, runs per date range).
  useEffect(() => {
    if (!Array.isArray(topProducts) || topProducts.length === 0) return;

    const missing = topProducts.filter(
      (product) => product?.product_id != null && !getTopProductImage(product)
    );
    if (missing.length === 0) return;

    let cancelled = false;

    const fetchMissingImages = async () => {
      const results = await Promise.allSettled(
        missing.map(async (product) => {
          const response = await getProductImages(product.product_id);
          const data = response?.data;
          const list = Array.isArray(data)
            ? data
            : data?.results || data?.images || [];
          const first = list.find((img) => img?.url || img?.image);
          return { id: product.product_id, url: first?.url || first?.image || null };
        })
      );

      if (cancelled) return;

      setProductImages((prev) => {
        const next = { ...prev };
        results.forEach((result) => {
          if (result.status === 'fulfilled' && result.value?.url) {
            next[result.value.id] = result.value.url;
          }
        });
        return next;
      });
    };

    fetchMissingImages();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topProducts]);

  useEffect(() => {
    if (!allowed) return;
    fetchAllReports();
  }, [allowed, fetchAllReports]);

  // Prior-period comparison: same range length, immediately before `from`.
  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    const dayMs = 86400000;
    const from = new Date(`${dateRange.from_date}T00:00:00`);
    const to = new Date(`${dateRange.to_date}T00:00:00`);
    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime()) || to < from) {
      setPrevSummary(null);
      return;
    }
    const days = Math.max(1, Math.round((to - from) / dayMs) + 1);
    const prevTo = new Date(from);
    prevTo.setDate(prevTo.getDate() - 1);
    const prevFrom = new Date(prevTo);
    prevFrom.setDate(prevFrom.getDate() - (days - 1));
    const fmt = (d) => d.toISOString().split('T')[0];
    getSalesReport({ from_date: fmt(prevFrom), to_date: fmt(prevTo) })
      .then((res) => {
        if (!cancelled) setPrevSummary(res.data?.summary || null);
      })
      .catch(() => {
        if (!cancelled) setPrevSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [allowed, dateRange]);

  const formatPrice = (price) => sharedFormatPrice(price, { decimals: 0 });

  // ASCII-safe money/counts for file exports (PDF + CSV): jsPDF's
  // built-in font has no rupee glyph (U+20B9), so Intl currency symbols
  // render as garbage — use the ASCII code (INR/USD/EUR) with locale
  // grouping instead. CSV reuses these (fields are always quoted).
  const pdfPrice = (value) => {
    const pdfRegion = getRegion();
    const amount = Number(value || 0);
    try {
      const grouped = new Intl.NumberFormat(pdfRegion.locale, {
        maximumFractionDigits: 0,
      }).format(amount);
      return `${pdfRegion.currency} ${grouped}`;
    } catch {
      return `${pdfRegion.currency} ${Math.round(amount)}`;
    }
  };
  const pdfCount = (value) => {
    try {
      return new Intl.NumberFormat(getRegion().locale).format(Number(value || 0));
    } catch {
      return String(Number(value || 0));
    }
  };
  const deltaText = (cur, prev) => {
    const d = periodDelta(cur, prev);
    if (d === null) return 'n/a';
    return `${d >= 0 ? '+' : ''}${d.toFixed(1)}% vs prior period`;
  };

  const handleExport = (type) => {
    const required = type === 'overview' ? ['sales', 'revenue', 'dashboard'] : [type];
    if (loading || required.some((key) => reportErrors.includes(key))) {
      toast.error('This report is unavailable. Retry before exporting.');
      return;
    }
    const doc = new jsPDF();
    const dateStr = `${dateRange.from_date} to ${dateRange.to_date}`;
    const nowStamp = (() => {
      const d = new Date();
      const p = (n) => String(n).padStart(2, '0');
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
    })();
    const fileName = `report-${type}-${new Date().toISOString().slice(0, 10)}.pdf`;
    const footer = () => {
      const pages = doc.getNumberOfPages();
      for (let i = 1; i <= pages; i++) {
        doc.setPage(i);
        doc.setFontSize(8);
        doc.setTextColor(128);
        doc.text(
          `E-shop Admin - Generated ${nowStamp} - Page ${i} of ${pages}`,
          14,
          doc.internal.pageSize.height - 10
        );
        doc.setTextColor(0);
      }
    };

    doc.setFontSize(18);
    doc.text(`E-shop - ${type.charAt(0).toUpperCase() + type.slice(1)} Report`, 14, 22);
    doc.setFontSize(10);
    doc.setTextColor(128);
    doc.text(`Date Range: ${dateStr}`, 14, 30);
    if (type === 'overview' && dashboardData?.revenue?.total?.revenue != null) {
      doc.text(`Lifetime Revenue: ${pdfPrice(dashboardData.revenue.total.revenue)}`, 14, 35);
    }
    doc.setTextColor(0);

    if (type === 'overview') {
      const rows = [
        ['Total Revenue (Filtered)', pdfPrice(filteredRevenue), deltaText(filteredRevenue, prevSummary?.total_sales)],
        ['Total Orders (Filtered)', pdfCount(filteredOrders), deltaText(filteredOrders, prevSummary?.order_count)],
        ['Average Order Value', pdfPrice(filteredAvgOrder), deltaText(filteredAvgOrder, prevSummary?.average_order_value)],
      ];

      const table1 = __createTable(doc, {
        startY: 40,
        head: [['Metric', 'Value', 'Change']],
        body: rows,
        theme: 'grid',
        headStyles: { fillColor: [0, 0, 0] },
        styles: { fontSize: 10 },
      });
      __drawTable(doc, table1);

      if (revenueData?.period_data?.length > 0) {
        const y = table1.finalY + 10;
        doc.setFontSize(14);
        doc.text('Revenue Breakdown', 14, y);

        autoTable(doc, {
          startY: y + 6,
           head: [['Period', 'Revenue', 'Discounts (included)', 'Tax', 'Shipping', 'Refunds', 'Net Revenue']],
          body: revenueData.period_data.map(p => [
            p.period,
            pdfPrice(p.revenue),
            pdfPrice(p.discounts),
            pdfPrice(p.tax),
            pdfPrice(p.shipping),
            pdfPrice(p.refunds || 0),
            pdfPrice(p.net_revenue),
          ]),
          theme: 'grid',
          headStyles: { fillColor: [0, 0, 0] },
          styles: { fontSize: 9 },
        });
      }
    } else if (type === 'products') {
      if (topProducts.length === 0) {
        doc.text('No product data available.', 14, 40);
      } else {
        autoTable(doc, {
          startY: 36,
          head: [['#', 'Product', 'Qty Sold', 'Revenue', 'Avg Price']],
          body: topProducts.map((p, i) => [
            i + 1,
            p.product_name,
            p.total_quantity_sold,
            pdfPrice(p.total_revenue),
            pdfPrice(p.average_price),
          ]),
          theme: 'grid',
          headStyles: { fillColor: [0, 0, 0] },
          styles: { fontSize: 9 },
        });
      }
    } else if (type === 'orders') {
      if (!orderStats) {
        doc.text('No order data available.', 14, 40);
      } else {
        doc.text(`Total Orders: ${orderStats.total_orders}`, 14, 40);

        autoTable(doc, {
          startY: 46,
          head: [['Status', 'Count', 'Revenue']],
          body: (orderStats.by_status || []).map(s => [
            s.status.charAt(0).toUpperCase() + s.status.slice(1),
            s.count,
            pdfPrice(s.revenue),
          ]),
          theme: 'grid',
          headStyles: { fillColor: [0, 0, 0] },
          styles: { fontSize: 10 },
        });
      }
    } else if (type === 'customers') {
      if (!customerSummary) {
        doc.text('No customer data available.', 14, 40);
      } else {
        autoTable(doc, {
          startY: 36,
          head: [['Metric', 'Value']],
          body: [
            ['Total Customers', customerSummary.total_customers],
            ['Active Customers', customerSummary.active_customers],
            ['New Customers', customerSummary.new_customers],
            ['Repeat Customers', customerSummary.repeat_customers],
            ['Retention Rate', `${customerSummary.customer_retention_rate}%`],
          ],
          theme: 'grid',
          headStyles: { fillColor: [0, 0, 0] },
          styles: { fontSize: 10 },
        });
      }
    }

    footer();
    doc.save(fileName);
    toast.success(`${type.charAt(0).toUpperCase() + type.slice(1)} report exported as PDF`);
  };

  // CSV export for the active tab (ASCII-safe via pdfPrice/pdfCount).
  const handleExportCSV = () => {
    if (loading) {
      toast.error('Reports are still loading. Please wait.');
      return;
    }
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const stamp = new Date().toISOString().slice(0, 10);
    let rows = [];
    if (activeTab === 'overview') {
      rows = [
        ['Metric', 'Value', 'Change'],
        ['Total Revenue (Filtered)', pdfPrice(filteredRevenue), deltaText(filteredRevenue, prevSummary?.total_sales)],
        ['Total Orders (Filtered)', pdfCount(filteredOrders), deltaText(filteredOrders, prevSummary?.order_count)],
        ['Average Order Value', pdfPrice(filteredAvgOrder), deltaText(filteredAvgOrder, prevSummary?.average_order_value)],
        [],
        ['Period', 'Revenue', 'Discounts', 'Tax', 'Shipping', 'Refunds', 'Net Revenue'],
        ...(revenueData?.period_data || []).map((p) => [
          p.period, pdfPrice(p.revenue), pdfPrice(p.discounts), pdfPrice(p.tax),
          pdfPrice(p.shipping), pdfPrice(p.refunds || 0), pdfPrice(p.net_revenue),
        ]),
      ];
    } else if (activeTab === 'products') {
      if (reportErrors.includes('products') || topProducts.length === 0) {
        toast.error('No product data to export for this range.');
        return;
      }
      rows = [
        ['#', 'Product', 'Slug', 'Qty Sold', 'Revenue', 'Avg Price'],
        ...topProducts.map((p, i) => [
          i + 1, p.product_name, p.product_slug || '', p.total_quantity_sold,
          pdfPrice(p.total_revenue), pdfPrice(p.average_price),
        ]),
      ];
    } else if (activeTab === 'orders') {
      if (!orderStats) {
        toast.error('No order data to export for this range.');
        return;
      }
      rows = [
        ['Status', 'Count', 'Revenue'],
        ...(orderStats.by_status || []).map((s) => [s.status, s.count, pdfPrice(s.revenue)]),
      ];
    } else {
      if (!customerSummary) {
        toast.error('No customer data to export for this range.');
        return;
      }
      rows = [
        ['Metric', 'Value'],
        ['Total Customers', customerSummary.total_customers],
        ['Active Customers', customerSummary.active_customers],
        ['New Customers', customerSummary.new_customers],
        ['Repeat Customers', customerSummary.repeat_customers],
        ['Retention Rate', `${customerSummary.customer_retention_rate}%`],
      ];
    }
    const blob = new Blob([rows.map((r) => r.map(esc).join(',')).join('\n')], {
      type: 'text/csv;charset=utf-8',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report-${activeTab}-${stamp}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success(`${activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} report exported as CSV`);
  };

  const handleDatePreset = (days) => {
    const to = new Date();
    const from = new Date();
    from.setDate(from.getDate() - days);
    
    setDateRange({
      from_date: from.toISOString().split('T')[0],
      to_date: to.toISOString().split('T')[0]
    });
  };

  const getStatusColor = (status) => {
    const colors = {
      pending: 'bg-warning/20 text-warning',
      confirmed: 'bg-primary-soft text-primary-soft-foreground',
      shipped: 'bg-purple-500/15 text-purple-600 dark:text-purple-300',
      out_for_delivery: 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-300',
      delivered: 'bg-success/15 text-success',
      cancelled: 'bg-destructive/15 text-destructive',
      rto: 'bg-orange-500/15 text-orange-600 dark:text-orange-300',
      refunded: 'bg-muted text-foreground'
    };
    return colors[status] || 'bg-muted text-foreground';
  };

  // Calculate date-filtered totals for overview
  const filteredRevenue = salesData?.summary?.total_sales || 0;
  const filteredOrders = salesData?.summary?.order_count || 0;
  const filteredAvgOrder = salesData?.summary?.average_order_value || 0;

  // Prior-period % delta (null = hide: no baseline or zero baseline).
  const periodDelta = (cur, prev) => {
    if (prev == null || prev === 0) return null;
    const pct = ((cur - prev) / Math.abs(prev)) * 100;
    return Number.isFinite(pct) ? pct : null;
  };

  const DeltaLine = ({ cur, prev }) => {
    const d = periodDelta(cur, prev);
    if (d === null) return null;
    const up = d >= 0;
    return (
      <p className={`text-xs mt-1 font-medium ${up ? 'text-success' : 'text-destructive'}`}>
        {up ? '▲' : '▼'} {Math.abs(d).toFixed(1)}% vs prior period
      </p>
    );
  };

  // Revenue trend series for the AreaChart (grouped by day/week/month).
  const revenueTrend = (revenueData?.period_data || []).map((p) => ({
    period: p.period,
    Revenue: Number(p.revenue) || 0,
    Net: Number(p.net_revenue) || 0,
  }));

  // Order-status counts shaped for the shared donut chart.
  const orderStatusCounts = {};
  (orderStats?.by_status || []).forEach((s) => {
    if (s?.status) orderStatusCounts[s.status] = s.count || 0;
  });

  // Empty-state copy: genuine empty (store never sold) vs filtered empty
  // (this range has nothing — widen the dates). Lifetime revenue is the
  // signal; a failed load is handled separately by reportErrors.
  const lifetimeRevenue = Number(dashboardData?.revenue?.total?.revenue || 0);
  const emptyCopy = lifetimeRevenue > 0
    ? 'No sales in this range — try widening the dates.'
    : 'No sales yet — data appears here after the first order.';

  // Access check — AFTER all hooks (Rules of Hooks): users without
  // reports.view see this instead of the reports.
  if (!allowed) {
    return (
      <div className="text-center py-12">
        <Shield size={48} className="mx-auto text-destructive mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Access Denied</h2>
        <p className="text-muted-foreground mt-2">You don't have permission to view reports.</p>
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
    return <PageSkeleton type="reports" />;
  }

  return (
    <div className="space-y-6">
      {reportErrors.length > 0 && (
        <div role="alert" className="rounded-lg border border-destructive p-4 text-destructive">
          Reports unavailable: {reportErrors.join(', ')}. Use Refresh to retry. Failed data is not shown or exported.
        </div>
      )}
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Reports & Analytics</h1>
          <p className="text-sm text-muted-foreground mt-1 break-words">
            Showing data from {formatDate(dateRange.from_date, { day: '2-digit', month: 'short' })} to {formatDate(dateRange.to_date, { day: '2-digit', month: 'short', year: 'numeric' })}
            {dashboardData?.revenue?.total?.revenue != null && (
              <> · Lifetime revenue {formatPrice(dashboardData.revenue.total.revenue)}</>
            )}
          </p>
        </div>
        <div className="flex flex-col sm:flex-row w-full sm:w-auto gap-2 sm:gap-3">
          <button
            onClick={() => handleExport(activeTab)}
            disabled={reportErrors.some((key) => activeTab === 'overview'
              ? ['sales', 'revenue', 'dashboard'].includes(key) : key === activeTab)}
            className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors disabled:opacity-50"
          >
            <Download size={18} />
            PDF
          </button>
          <button
            onClick={handleExportCSV}
            className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors"
          >
            <Download size={18} />
            CSV
          </button>
          <button
            onClick={fetchAllReports}
            className="flex items-center justify-center gap-2 px-4 py-2.5 sm:py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors"
          >
            <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </div>

      {/* Date Range Filter */}
      <div className="bg-card rounded-xl shadow-sm border border-border p-4">
        <div className="flex flex-col gap-4">
          {/* Quick Presets */}
          <div className="flex flex-wrap gap-2">
            {datePresets.map(preset => {
              const isActive = activePreset === preset.label;
              return (
                <button
                  key={preset.label}
                  onClick={() => handleDatePreset(preset.days)}
                  aria-pressed={isActive}
                  className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary-soft text-primary'
                      : 'bg-muted text-muted-foreground hover:bg-muted transition-colors'
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>
          
          {/* Custom Date Range */}
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Calendar size={18} className="text-muted-foreground" />
              <label className="text-sm font-medium text-muted-foreground">From:</label>
              <input
                type="date"
                value={dateRange.from_date}
                onChange={(e) => setDateRange({ ...dateRange, from_date: e.target.value })}
                className="px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-muted-foreground">To:</label>
              <input
                type="date"
                value={dateRange.to_date}
                onChange={(e) => setDateRange({ ...dateRange, to_date: e.target.value })}
                className="px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-muted-foreground">Group By:</label>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value)}
                className="px-3 py-1.5 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
              >
                <option value="day">Day</option>
                <option value="week">Week</option>
                <option value="month">Month</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-border overflow-x-auto">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
            activeTab === 'overview' 
              ? 'border-primary text-primary' 
              : 'border-transparent text-muted-foreground hover:text-muted-foreground'
          }`}
        >
          Overview
        </button>
        <button
          onClick={() => setActiveTab('products')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
            activeTab === 'products' 
              ? 'border-primary text-primary' 
              : 'border-transparent text-muted-foreground hover:text-muted-foreground'
          }`}
        >
          Products
        </button>
        <button
          onClick={() => setActiveTab('orders')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
            activeTab === 'orders' 
              ? 'border-primary text-primary' 
              : 'border-transparent text-muted-foreground hover:text-muted-foreground'
          }`}
        >
          Orders
        </button>
        <button
          onClick={() => setActiveTab('customers')}
          className={`px-4 py-2 text-sm font-medium border-b-2 whitespace-nowrap transition-colors ${
            activeTab === 'customers' 
              ? 'border-primary text-primary' 
              : 'border-transparent text-muted-foreground hover:text-muted-foreground'
          }`}
        >
          Customers
        </button>
      </div>

      {/* Overview Tab - Now shows DATE FILTERED data */}
      {activeTab === 'overview' && salesData && (
        <>
          {/* Revenue Summary Cards - Date Filtered, with prior-period deltas */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="bg-card rounded-xl shadow-sm border border-border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Revenue (Filtered)</p>
                  <p className="text-2xl font-bold text-foreground">
                    {formatPrice(filteredRevenue)}
                  </p>
                  <DeltaLine cur={filteredRevenue} prev={prevSummary?.total_sales} />
                  <p className="text-xs text-muted-foreground mt-1">
                    {dateRange.from_date} to {dateRange.to_date}
                  </p>
                </div>
                <div className="bg-success/10 p-3 rounded-lg">
                  <DollarSign size={24} className="text-success" />
                </div>
              </div>
            </div>
            <div className="bg-card rounded-xl shadow-sm border border-border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Total Orders (Filtered)</p>
                  <p className="text-2xl font-bold text-foreground">
                    {formatNumber(filteredOrders)}
                  </p>
                  <DeltaLine cur={filteredOrders} prev={prevSummary?.order_count} />
                </div>
                <div className="bg-orange-500/10 p-3 rounded-lg">
                  <ShoppingBag size={24} className="text-orange-500" />
                </div>
              </div>
            </div>
            <div className="bg-card rounded-xl shadow-sm border border-border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-sm text-muted-foreground">Average Order Value</p>
                  <p className="text-2xl font-bold text-foreground">
                    {formatPrice(filteredAvgOrder)}
                  </p>
                  <DeltaLine cur={filteredAvgOrder} prev={prevSummary?.average_order_value} />
                </div>
                <div className="bg-primary-soft p-3 rounded-lg">
                  <TrendingUp size={24} className="text-primary" />
                </div>
              </div>
            </div>
          </div>

          {/* Revenue Trend */}
          {revenueTrend.length > 0 ? (
            <div className="bg-card rounded-xl shadow-sm border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-1">Revenue Trend</h2>
              <p className="text-sm text-muted-foreground mb-4">
                Grouped by {groupBy} · hover or tap a point for exact values
              </p>
              <div className="w-full h-64 sm:h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={revenueTrend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                    <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" vertical={false} />
                    <XAxis
                      dataKey="period"
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                      tickLine={false}
                      axisLine={{ stroke: 'var(--border)' }}
                      minTickGap={24}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }}
                      tickLine={false}
                      axisLine={false}
                      width={48}
                      tickFormatter={(v) => formatShort(v)}
                    />
                    <Tooltip
                      contentStyle={{
                        background: 'var(--card)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--foreground)',
                        fontSize: 12,
                      }}
                      formatter={(value, name) => [formatPrice(value), name]}
                      labelStyle={{ color: 'var(--foreground)', fontWeight: 600 }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area
                      type="monotone"
                      dataKey="Revenue"
                      stroke="var(--primary)"
                      fill="var(--primary-soft)"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="Net"
                      stroke="var(--success)"
                      fill="transparent"
                      strokeWidth={2}
                      strokeDasharray="6 3"
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          ) : (
            <div className="bg-card rounded-xl shadow-sm border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-1">Revenue Trend</h2>
              <div className="text-center py-8 text-muted-foreground">
                <TrendingUp size={32} className="mx-auto mb-2" />
                <p>{emptyCopy}</p>
              </div>
            </div>
          )}

          {/* Revenue Period Data */}
          {revenueData?.period_data && revenueData.period_data.length > 0 && (
            <div className="bg-card rounded-xl shadow-sm border border-border p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">Revenue Breakdown</h2>
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-border">
                  <thead className="bg-muted">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Period</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Revenue</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Discounts (included)</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Tax</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Shipping</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Refunds</th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Net Revenue</th>
                    </tr>
                  </thead>
                  <tbody className="bg-card divide-y divide-border">
                    {revenueData.period_data.map((period, index) => (
                      <tr key={index} className="hover:bg-muted">
                        <td className="px-4 py-3 text-sm text-foreground">{period.period}</td>
                        <td className="px-4 py-3 text-sm text-right">{formatPrice(period.revenue)}</td>
                        <td className="px-4 py-3 text-sm text-right text-destructive">-{formatPrice(period.discounts)}</td>
                        <td className="px-4 py-3 text-sm text-right">{formatPrice(period.tax)}</td>
                         <td className="px-4 py-3 text-sm text-right">{formatPrice(period.shipping)}</td>
                         <td className="px-4 py-3 text-sm text-right">{formatPrice(period.refunds || 0)}</td>
                        <td className="px-4 py-3 text-sm font-semibold text-right">{formatPrice(period.net_revenue)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Products Tab */}
      {activeTab === 'products' && !reportErrors.includes('products') && (
        <div className="bg-card rounded-xl shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Top Selling Products</h2>
          {topProducts.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Package size={32} className="mx-auto text-muted-foreground mb-2" />
              <p>{emptyCopy}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-border">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">#</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-muted-foreground uppercase">Product</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Quantity Sold</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Revenue</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-muted-foreground uppercase">Avg Price</th>
                  </tr>
                </thead>
                <tbody className="bg-card divide-y divide-border">
                  {topProducts.map((product, index) => {
                    const imageUrl = getTopProductImage(product);
                    const imageKey = product.product_id ?? `idx-${index}`;
                    const showImage = imageUrl && !failedImages.has(String(imageKey));
                    return (
                    <tr key={product.product_id || index} className="hover:bg-muted">
                      <td className="px-4 py-3 text-sm font-bold text-muted-foreground">#{index + 1}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {showImage ? (
                            <img
                              src={imageUrl}
                              alt={product.product_name}
                              className="w-12 h-12 object-cover rounded-lg border border-border flex-shrink-0"
                              onError={() => handleImageError(imageKey)}
                            />
                          ) : (
                            <div className="w-12 h-12 bg-muted rounded-lg flex items-center justify-center border border-border flex-shrink-0">
                              <ImageIcon size={20} className="text-muted-foreground" />
                            </div>
                          )}
                          <div>
                            <p className="font-medium text-foreground">{product.product_name}</p>
                            <p className="text-xs text-muted-foreground">{product.product_slug}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-right">{product.total_quantity_sold}</td>
                      <td className="px-4 py-3 text-sm font-semibold text-right">{formatPrice(product.total_revenue)}</td>
                      <td className="px-4 py-3 text-sm text-right">{formatPrice(product.average_price)}</td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Orders Tab */}
      {activeTab === 'orders' && !orderStats && (
        <div className="bg-card rounded-xl shadow-sm border border-border p-6">
          <div className="text-center py-8 text-muted-foreground">
            <ShoppingBag size={32} className="mx-auto mb-2" />
            <p>{reportErrors.includes('orders') ? 'Order statistics failed to load.' : emptyCopy}</p>
            {reportErrors.includes('orders') && (
              <button
                type="button"
                onClick={fetchAllReports}
                className="mt-3 px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted transition-colors"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      )}
      {activeTab === 'orders' && orderStats && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="bg-card rounded-xl shadow-sm border border-border p-6">
            <h2 className="text-lg font-semibold text-foreground mb-1">Orders by Status</h2>
            <p className="text-sm text-muted-foreground mb-2">
              Total Orders: <span className="font-semibold text-foreground">{orderStats.total_orders}</span>
            </p>
            <OrderStatusChart orders={orderStatusCounts} />
          </div>
          <div className="bg-card rounded-xl shadow-sm border border-border p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Order Statistics</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {orderStats.by_status?.map((status) => (
                <div key={status.status} className="p-4 bg-muted rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium capitalize ${getStatusColor(status.status)}`}>
                      {status.status}
                    </span>
                    <span className="font-bold text-foreground">{status.count}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">Revenue: {formatPrice(status.revenue)}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Customers Tab */}
      {activeTab === 'customers' && !customerSummary && (
        <div className="bg-card rounded-xl shadow-sm border border-border p-6">
          <div className="text-center py-8 text-muted-foreground">
            <Users size={32} className="mx-auto mb-2" />
            <p>{reportErrors.includes('customers') ? 'Customer analytics failed to load.' : emptyCopy}</p>
            {reportErrors.includes('customers') && (
              <button
                type="button"
                onClick={fetchAllReports}
                className="mt-3 px-4 py-2 border border-input rounded-lg text-sm hover:bg-muted transition-colors"
              >
                Retry
              </button>
            )}
          </div>
        </div>
      )}
      {activeTab === 'customers' && customerSummary && (
        <div className="bg-card rounded-xl shadow-sm border border-border p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Customer Analytics</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Total Customers</p>
              <p className="text-xl font-bold text-foreground">{customerSummary.total_customers}</p>
            </div>
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Active Customers</p>
              <p className="text-xl font-bold text-foreground">{customerSummary.active_customers}</p>
            </div>
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">New Customers</p>
              <p className="text-xl font-bold text-foreground">{customerSummary.new_customers}</p>
            </div>
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Repeat Customers</p>
              <p className="text-xl font-bold text-foreground">{customerSummary.repeat_customers}</p>
            </div>
            <div className="p-4 bg-muted rounded-lg">
              <p className="text-sm text-muted-foreground">Retention Rate</p>
              <p className="text-xl font-bold text-foreground">{customerSummary.customer_retention_rate}%</p>
              <div
                className="mt-2 h-2 rounded-full bg-border overflow-hidden"
                role="progressbar"
                aria-valuenow={Number(customerSummary.customer_retention_rate) || 0}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Customer retention rate"
              >
                <div
                  className="h-full rounded-full bg-success transition-all"
                  style={{ width: `${Math.min(100, Math.max(0, Number(customerSummary.customer_retention_rate) || 0))}%` }}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Reports;

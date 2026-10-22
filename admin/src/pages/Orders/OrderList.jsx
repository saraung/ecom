// src/pages/Orders/OrderList.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { 
  Search, 
  Eye, 
  Filter, 
  ChevronDown,
  Clock,
  CheckCircle,
  Truck,
  XCircle,
  Package,
  RefreshCw
} from 'lucide-react';
import { getAdminOrders } from '../../api/orders';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { formatDate, formatPrice } from '../../utils/format';

const OrderList = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();
  // Export is keyed off products.export (floor: admin) so custom roles
  // granted that key see it — no role-string check.
  const canExport = canDo(user, 'products.export', 'admin');
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const search = searchParams.get('search') || '';
  const statusFilter = searchParams.get('status') || 'all';
  const currentPage = Math.max(1, Number.parseInt(searchParams.get('page') || '1', 10) || 1);
  const fillDesktopTable = orders.length >= 8;
  const [searchInput, setSearchInput] = useState(search);
  const [totalPages, setTotalPages] = useState(1);
  const [totalOrders, setTotalOrders] = useState(0);
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const itemsPerPage = 10;

  const statusOptions = [
    { value: 'all', label: 'All Status' },
    { value: 'pending', label: 'Pending' },
    { value: 'confirmed', label: 'Confirmed' },
    { value: 'processing', label: 'Processing' },
    { value: 'shipped', label: 'Shipped' },
    { value: 'out_for_delivery', label: 'Out For Delivery' },
    { value: 'delivered', label: 'Delivered' },
    { value: 'cancelled', label: 'Cancelled' },
    { value: 'rto', label: 'RTO (Returned)' },
    { value: 'refunded', label: 'Refunded' }
  ];

  useEffect(() => {
    fetchOrders();
  }, [statusFilter, currentPage, search]);

  useEffect(() => {
    setSearchInput(search);
  }, [search]);

  const updateListParams = (updates) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === '') next.delete(key);
      else next.set(key, String(value));
    });
    setSearchParams(next);
  };

  const fetchOrders = async () => {
    try {
      setLoading(true);
      const params = {
        page: currentPage,
        limit: itemsPerPage,
        status: statusFilter !== 'all' ? statusFilter : undefined,
        search: search || undefined
      };
      
      const response = await getAdminOrders(params);
      
      const data = response.data;
      setOrders(data.orders || []);
      setTotalOrders(data.pagination?.total || 0);
      const pageCount = Math.max(1, Number(data.pagination?.total_pages) || 1);
      setTotalPages(pageCount);
      if (currentPage > pageCount) {
        updateListParams({ page: pageCount === 1 ? null : pageCount });
      }
      
    } catch {
      toast.error('Failed to load orders');
      setOrders([]);
      setTotalOrders(0);
      setTotalPages(1);
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status) => {
    const config = {
      pending: { icon: Clock, color: 'bg-warning/20 text-warning' },
      confirmed: { icon: CheckCircle, color: 'bg-primary-soft text-primary-soft-foreground' },
      processing: { icon: Package, color: 'bg-primary-soft text-primary-soft-foreground' },
      shipped: { icon: Truck, color: 'bg-purple-500/15 text-purple-600 dark:text-purple-300' },
      out_for_delivery: { icon: Truck, color: 'bg-blue-500/15 text-blue-600 dark:text-blue-300' },
      delivered: { icon: CheckCircle, color: 'bg-success/15 text-success' },
      cancelled: { icon: XCircle, color: 'bg-destructive/15 text-destructive' },
      rto: { icon: RefreshCw, color: 'bg-amber-500/15 text-amber-600 dark:text-amber-300' },
      refunded: { icon: RefreshCw, color: 'bg-muted text-foreground' }
    };
    const { icon: Icon, color } = config[status?.toLowerCase()] || config.pending;
    return { Icon, color };
  };


  const handleSearch = () => {
    updateListParams({ search: searchInput.trim(), page: null });
  };

  const handleExport = () => {
    if (orders.length === 0) {
      toast.error('No orders to export');
      return;
    }

    const headers = ['Order #', 'Customer', 'Email', 'Total', 'Status', 'Payment', 'Date'];
    const rows = orders.map((order) => [
      order.order_number,
      order.user?.full_name || order.shipping_address?.full_name || 'Guest',
      order.user?.email || 'No email',
      order.grand_total || 0,
      order.status || '',
      order.payment_status || 'Pending',
      formatDate(order.placed_at || order.created_at)
    ]);

    const csvContent = [headers, ...rows]
      .map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
      .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `orders-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    toast.success('Orders exported successfully');
  };

  if (loading) {
    return <PageSkeleton type="orders" />;
  }

  return (
    <div className="lg:flex lg:min-h-[calc(100dvh-7rem)] lg:flex-col">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4 lg:mb-4 lg:gap-3">
        <div className="min-w-0">
          <h1 className="text-xl sm:text-2xl font-bold text-foreground break-words">Orders</h1>
          <p className="text-sm text-muted-foreground mt-1 lg:mt-0">{totalOrders} orders found</p>
        </div>
        {canExport && (
          <div className="flex gap-2">
            <button onClick={handleExport} className="btn-outline text-sm">Export</button>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-2 sm:gap-4 mb-6 lg:mb-4">
        <div className="relative w-full sm:flex-1 sm:max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
          <input
            type="text"
            placeholder="Search orders by #ID or customer name..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
          />
        </div>
        <div className="flex gap-2">
          <div className="relative">
            <button
              onClick={() => setShowStatusDropdown(!showStatusDropdown)}
              className="flex items-center gap-2 px-4 py-2.5 sm:py-2 border border-input rounded-lg hover:bg-muted transition-colors text-sm"
            >
              <Filter size={18} />
              <span>Status</span>
              <ChevronDown size={16} />
            </button>
            {showStatusDropdown && (
              <div className="absolute top-full left-0 mt-1 bg-card border border-border rounded-lg shadow-lg z-10 min-w-37.5 max-h-64 overflow-y-auto">
                {statusOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => {
                      updateListParams({ status: option.value === 'all' ? null : option.value, page: null });
                      setShowStatusDropdown(false);
                    }}
                    className={`w-full text-left px-4 py-2 text-foreground hover:bg-muted transition-colors ${
                      statusFilter === option.value ? 'bg-primary-soft text-primary' : ''
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="bg-card rounded-xl shadow-sm overflow-hidden lg:flex lg:min-h-0 lg:flex-1 lg:flex-col">
        {/* Desktop Table View */}
        <div className={`hidden md:block overflow-x-auto ${fillDesktopTable ? 'lg:min-h-0 lg:flex-1 lg:flex' : ''}`}>
          <table className={`w-full ${fillDesktopTable ? 'lg:h-full' : ''}`}>
            <thead className="bg-muted">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Order</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Customer</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Total</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Status</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Payment</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground uppercase tracking-wider">Date</th>
                <th className="px-4 py-2 text-right text-xs font-medium text-muted-foreground uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {orders.length === 0 ? (
                <tr>
                  <td colSpan="7" className="px-4 py-8 text-center text-muted-foreground">
                    No orders found
                  </td>
                </tr>
              ) : (
                orders.map((order) => {
                  const { Icon, color } = getStatusBadge(order.status);
                  return (
                    <tr key={order.id} className="hover:bg-muted transition-colors cursor-pointer" onClick={() => navigate(`/orders/${order.id}`, { state: { from: `${location.pathname}${location.search}` } })}>
                      <td className="px-4 py-1 lg:py-3">
                        <div className="flex flex-col">
                          <span className="whitespace-nowrap text-sm leading-5 font-medium text-foreground">#{order.order_number}</span>
                          <div className="flex items-center gap-1.5 leading-4">
                            <span className="text-xs leading-4 text-muted-foreground">{order.items?.length || 0} items</span>
                            {order.awb_code && (
                              <span className="text-[10px] font-mono font-medium px-1.5 py-0.2 rounded bg-purple-500/10 text-purple-600 dark:text-purple-300">
                                {order.awb_code}
                              </span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-1 lg:py-3">
                        <div className="flex flex-col">
                          <span className="block max-w-48 truncate text-sm leading-5 font-medium text-foreground">{order.user?.full_name || order.shipping_address?.full_name || 'Guest'}</span>
                          <span className="block max-w-48 truncate text-xs leading-4 text-muted-foreground">{order.user?.email || 'No email'}</span>
                        </div>
                      </td>
                      <td className="px-4 py-1 lg:py-3 font-semibold text-foreground">
                        {formatPrice(order.grand_total)}
                      </td>
                      <td className="px-4 py-1 lg:py-3">
                        <span
                        className={`whitespace-nowrap px-3 py-1 rounded-full text-xs font-medium flex items-center gap-1 ${color} w-fit`}
                          title={order.cancellation_reason || undefined}
                        >
                          <Icon size={14} />
                          {order.status}
                        </span>
                        {order.status?.toLowerCase() === 'cancelled' && order.cancellation_reason && (
                          <p
                            className="mt-1 text-xs text-muted-foreground max-w-45 truncate"
                            title={order.cancellation_reason}
                          >
                            {order.cancellation_reason}
                          </p>
                        )}
                      </td>
                      <td className="px-4 py-1 lg:py-3">
                        <span className={`whitespace-nowrap px-2 py-1 rounded-full text-xs font-medium ${
                          order.payment_status === 'paid' ? 'bg-success/15 text-success' :
                          order.payment_status === 'pending' ? 'bg-warning/20 text-warning' :
                          order.payment_status === 'failed' ? 'bg-destructive/15 text-destructive' :
                          'bg-muted text-foreground'
                        }`}>
                          {order.payment_status || 'Pending'}
                        </span>
                      </td>
                      <td className="whitespace-nowrap px-4 py-1 lg:py-3 text-sm leading-5 text-muted-foreground">
                        {formatDate(order.placed_at || order.created_at, {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric'
                        })}
                      </td>
                      <td className="px-4 py-1 lg:py-3 text-right" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => navigate(`/orders/${order.id}`, { state: { from: `${location.pathname}${location.search}` } })}
                          className="p-2 text-primary hover:bg-primary-soft rounded-lg transition-colors"
                          title="View Order"
                        >
                          <Eye size={18} />
                        </button>
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
          {orders.length === 0 ? (
            <div className="px-4 py-8 text-center text-muted-foreground">
              No orders found
            </div>
          ) : (
            orders.map((order) => {
              const { Icon, color } = getStatusBadge(order.status);
              return (
                <div
                  key={order.id}
                  className="p-4 space-y-3 cursor-pointer hover:bg-muted transition-colors"
                  onClick={() => navigate(`/orders/${order.id}`, { state: { from: `${location.pathname}${location.search}` } })}
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium text-foreground">#{order.order_number}</div>
                      <div className="text-sm text-muted-foreground">{order.items?.length || 0} items</div>
                    </div>
                    <span className="font-semibold text-foreground">{formatPrice(order.grand_total)}</span>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium inline-flex items-center gap-1 ${color}`}
                      title={order.cancellation_reason || undefined}
                    >
                      <Icon size={14} />
                      {order.status}
                    </span>
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      order.payment_status === 'paid' ? 'bg-success/15 text-success' :
                      order.payment_status === 'pending' ? 'bg-warning/20 text-warning' :
                      order.payment_status === 'failed' ? 'bg-destructive/15 text-destructive' :
                      'bg-muted text-foreground'
                    }`}>
                      {order.payment_status || 'Pending'}
                    </span>
                    <span className="text-xs text-muted-foreground ml-auto">
                      {formatDate(order.placed_at || order.created_at, {
                        day: '2-digit',
                        month: 'short',
                        year: 'numeric'
                      })}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="min-w-0">
                      <div className="font-medium text-foreground truncate">{order.user?.full_name || order.shipping_address?.full_name || 'Guest'}</div>
                      <div className="text-sm text-muted-foreground truncate">{order.user?.email || 'No email'}</div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); navigate(`/orders/${order.id}`, { state: { from: `${location.pathname}${location.search}` } }); }}
                      className="p-2 text-primary hover:bg-primary-soft rounded-lg transition-colors shrink-0"
                      title="View Order"
                    >
                      <Eye size={18} />
                    </button>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {totalPages > 1 && (
          <div className="px-4 py-3 border-t border-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Showing {((currentPage - 1) * itemsPerPage) + 1} - {Math.min(currentPage * itemsPerPage, totalOrders)} of {totalOrders} orders
            </div>
            <div className="flex gap-2">
              <button
                disabled={currentPage === 1}
                onClick={() => updateListParams({ page: currentPage - 1 })}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Previous
              </button>
              <span className="px-3 py-1 text-sm text-muted-foreground">
                Page {currentPage} of {totalPages}
              </span>
              <button
                disabled={currentPage === totalPages}
                onClick={() => updateListParams({ page: currentPage + 1 })}
                className="px-3 py-2 sm:py-1 border border-input rounded disabled:opacity-50 hover:bg-muted transition-colors"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default OrderList;

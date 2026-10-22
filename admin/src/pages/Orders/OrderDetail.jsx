// src/pages/Orders/OrderDetail.jsx
import React, { useState, useEffect } from 'react';
import { Link, useParams, useNavigate, useLocation } from 'react-router-dom';
import { renderToStaticMarkup } from 'react-dom/server';
import { 
  ArrowLeft, 
  Truck, 
  CheckCircle, 
  XCircle, 
  Clock, 
  Package,
  Printer,
  Mail,
  RefreshCw,
  User,
  MapPin,
  CreditCard,
  Phone,
  Image as ImageIcon
} from 'lucide-react';
import { getAdminOrderById, updateAdminOrderStatus } from '../../api/orders';
import { getRefunds } from '../../api/refunds';
import { getAuditLog } from '../../api/audit';
import AdminCancelDialog from '../../components/orders/AdminCancelDialog';
import ConfirmDialog from '../../components/ui/ConfirmDialog';
import RefundDialog from '../../components/orders/RefundDialog';
import { useAuth } from '../../context/AuthContext'; // 👈 ADDED
import { canDo } from '../../utils/permissions'; // 👈 ADDED
import OrderInvoice from '../../components/invoice/OrderInvoice';
import PackingSlip from '../../components/invoice/PackingSlip';
import toast from 'react-hot-toast';
import PageSkeleton from '../../components/ui/PageSkeleton';
import { formatPrice, formatDate } from '../../utils/format';
import ShiprocketDispatchModal from '../../components/orders/ShiprocketDispatchModal';
import TrackingModal from '../../components/orders/TrackingModal';
import FulfilmentStage from '../../components/orders/FulfilmentStage';
import { getOrderShippingLabel, getOrderShippingManifest, getSimulatedShippingDocument, requestOrderPickup, resolveShipmentStage } from '../../api/orders';
import { resolveApiUrl } from '../../api/client';


// Forward-only fulfilment workflow — mirrors the backend transition map
// (PUT /admin/orders/{id}/status). Only the legal next state(s) are
// offered, so statuses can't be "unknowingly" misclicked. Cancelled /
// refunded leave this control entirely (Cancel Order… dialog / Issue
// Refund); RTO is settable from shipped legs (courier phone reports).
const NEXT_STATUSES = {
  pending: ['confirmed'],
  confirmed: ['processing'],
  processing: ['shipped'],
  shipped: ['out_for_delivery', 'rto'],
  out_for_delivery: ['delivered', 'rto'],
  delivered: [],
  rto: [],
  cancelled: [],
  refunded: [],
};

// Moves past this point have physical-world effects — confirm first.
const CONFIRM_STATUSES = ['shipped', 'out_for_delivery', 'delivered', 'rto'];

const showShippingDocument = async (documentWindow, url, isSimulated) => {
  if (!isSimulated) {
    documentWindow.location.href = resolveApiUrl(url);
    return;
  }
  const response = await getSimulatedShippingDocument(url);
  documentWindow.document.open();
  documentWindow.document.write(response.data);
  documentWindow.document.close();
};


const OrderDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const requestedReturnPath = location.state?.from;
  const ordersReturnPath = typeof requestedReturnPath === 'string'
    && requestedReturnPath.startsWith('/')
    && !requestedReturnPath.startsWith('//')
    ? requestedReturnPath
    : '/orders';
  const { user } = useAuth(); // 👈 ADDED: session carries role + permissions
  const canCancel = canDo(user, 'orders.update', 'manager');
  // Permission gates matching each backend require_perm(...): status changes
  // and cancellations are orders.update, dispatch is shipping.manage, and the
  // customer-profile link needs users.view. Keyed off permissions rather than
  // the single legacy `role` string so stacked roles can't hide controls.
  const canUpdateStatus = canDo(user, 'orders.update', 'manager');
  const canRefund = canDo(user, 'orders.refund');
  const canDispatch = canDo(user, 'shipping.manage', 'manager');
  const canViewUsers = canDo(user, 'users.view', 'admin');
  const [cancelOpen, setCancelOpen] = useState(false);
  const [refundOpen, setRefundOpen] = useState(false);
  const [confirmState, setConfirmState] = useState(null);
  // Pending-approval refund row for this order, if one is in flight — the
  // Issue Refund button yields to it so nobody opens a parallel request
  // (the backend 409s duplicates, but the UI should say why).
  const [pendingRefund, setPendingRefund] = useState(null);
  // Order-scoped audit trail (best-effort; hidden when empty or forbidden —
  // staff without reports.view get a 403 here by design).
  const [activity, setActivity] = useState([]);
  const [order, setOrder] = useState(null);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [failedImages, setFailedImages] = useState(new Set());
  const [isDispatchModalOpen, setIsDispatchModalOpen] = useState(false);
  const [isTrackingModalOpen, setIsTrackingModalOpen] = useState(false);
  const [shippingActionLoading, setShippingActionLoading] = useState(false);

  // Fulfilment stage is computed by the backend (shipment_stage) so this page,
  // the order list and the simulator all agree on what state a parcel is in.
  const shipmentStage = resolveShipmentStage(order);


  useEffect(() => {
    fetchOrder();
  }, [id]);

  const fetchOrder = async () => {
    try {
      setLoading(true);
      const response = await getAdminOrderById(id);
      setOrder(response.data);
      // Pending approval state (best-effort; never blocks the page).
      try {
        const refundsRes = await getRefunds({ order_id: id, status_filter: 'pending_approval', limit: 1 });
        setPendingRefund(refundsRes.data?.refunds?.[0] || null);
      } catch {
        setPendingRefund(null);
      }
      // Activity timeline (best-effort; never blocks the page).
      try {
        const auditRes = await getAuditLog({ entity: 'order', entity_id: id, limit: 20 });
        const entries = auditRes.data?.entries || auditRes.data?.items || [];
        setActivity(Array.isArray(entries) ? entries : []);
      } catch {
        setActivity([]);
      }
    } catch {
      toast.error('Failed to load order');
      navigate(ordersReturnPath, { replace: true });
    } finally {
      setLoading(false);
    }
  };

  const handleStatusUpdate = async (newStatus) => {
    // 👈 Only callers with orders.update may change status
    if (!canUpdateStatus) {
      toast.error('You do not have permission to update order status');
      return;
    }

    // Terminal states can never be changed again (defensive guard — the UI also hides the options)
    if (order && ['cancelled', 'refunded'].includes(order.status?.toLowerCase())) {
      toast.error(`Order is ${order.status?.toLowerCase()}; status can no longer be changed`);
      return;
    }

    // Shipping moves have physical-world effects (courier dispatch,
    // customer expectations) — confirm with the consequence spelled out.
    // Earlier workflow steps are cheap to redo, so they skip the dialog.
    setConfirmState({ kind: 'status', newStatus });
  };

  const runConfirmed = async () => {
    const newStatus = confirmState?.newStatus;
    if (!newStatus) {
      setConfirmState(null);
      return;
    }
    try {
      setUpdating(true);
      await updateAdminOrderStatus(id, newStatus);
      toast.success(`Order status updated to ${newStatus}`);
      fetchOrder();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Failed to update order status');
    } finally {
      setUpdating(false);
      setConfirmState(null);
    }
  };

  const handlePrintInvoice = () => {
    if (!order) return;
    const printWindow = window.open('', '_blank', 'width=820,height=920');
    if (!printWindow) {
      toast.error('Popup blocked. Allow popups to print the invoice.');
      return;
    }
    const body = renderToStaticMarkup(<OrderInvoice order={order} />);
    const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
${renderToStaticMarkup(<title>Invoice #{order.order_number}</title>)}
<style>
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: #fff; }
  @page { size: A4 portrait; margin: 8mm 10mm; }
  @media print {
    html, body { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
  }
</style>
</head>
<body>
  ${body}
  <script>
    window.onload = function () { window.print(); };
  </script>
</body>
</html>`;
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
  };

  const handlePrintPackingSlip = () => {
    if (!order) return;
    const printWindow = window.open('', '_blank', 'width=760,height=920');
    if (!printWindow) {
      toast.error('Popup blocked. Allow popups to print the packing slip.');
      return;
    }
    const body = renderToStaticMarkup(<PackingSlip order={order} />);
    const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
${renderToStaticMarkup(<title>Packing Slip #{order.order_number}</title>)}
<style>
  * { box-sizing: border-box; }
  body { margin: 0; padding: 0; background: #f3f4f6; }
  @media print {
    body { background: #fff; }
    @page { margin: 14mm 12mm; }
  }
</style>
</head>
<body>
  ${body}
  <script>
    window.onload = function () { window.print(); };
  </script>
</body>
</html>`;
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
  };
  const handlePrintShippingLabel = async () => {
    const documentWindow = window.open('', '_blank');
    if (!documentWindow) return toast.error('Allow popups to open shipping documents.');
    documentWindow.opener = null;
    try {
      setShippingActionLoading(true);
      const res = await getOrderShippingLabel(order.id);
      if (res.data?.label_url) {
        await showShippingDocument(documentWindow, res.data.label_url, res.data.is_simulated);
      } else {
        documentWindow.close();
        toast.error('Shipping label not available yet');
      }
    } catch (err) {
      documentWindow.close();
      toast.error(err.response?.data?.detail || 'Failed to fetch shipping label');
    } finally {
      setShippingActionLoading(false);
    }
  };

  const handlePrintManifest = async () => {
    const documentWindow = window.open('', '_blank');
    if (!documentWindow) return toast.error('Allow popups to open shipping documents.');
    documentWindow.opener = null;
    try {
      setShippingActionLoading(true);
      const res = await getOrderShippingManifest(order.id);
      if (res.data?.manifest_url) {
        await showShippingDocument(documentWindow, res.data.manifest_url, res.data.is_simulated);
      } else {
        documentWindow.close();
        toast.error('Manifest not available yet');
      }
    } catch (err) {
      documentWindow.close();
      toast.error(err.response?.data?.detail || 'Failed to fetch manifest');
    } finally {
      setShippingActionLoading(false);
    }
  };

  const handleRequestPickup = async () => {
    try {
      setShippingActionLoading(true);
      await requestOrderPickup(order.id);
      toast.success('Courier pickup requested successfully!');
      fetchOrder();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Failed to schedule pickup');
    } finally {
      setShippingActionLoading(false);
    }
  };


  // 👇 Resolve product image for an order item (defensive across API field names)
  const getItemImage = (item) => {
    return (
      item?.product_image ||
      item?.product_image_url ||
      item?.image_url ||
      item?.image ||
      item?.product?.image ||
      (Array.isArray(item?.product?.images) && item.product.images[0]?.url) ||
      null
    );
  };

  // 👇 Track broken image URLs so the placeholder shows instead
  const handleImageError = (key) => {
    setFailedImages((prev) => new Set(prev).add(String(key)));
  };

  const getStatusBadge = (status) => {
    const config = {
      pending: { icon: Clock, color: 'bg-warning/20 text-warning' },
      confirmed: { icon: CheckCircle, color: 'bg-primary-soft text-primary-soft-foreground' },
      processing: { icon: Package, color: 'bg-primary-soft text-primary-soft-foreground' },
      shipped: { icon: Truck, color: 'bg-purple-500/15 text-purple-600 dark:text-purple-300' },
      out_for_delivery: { icon: Truck, color: 'bg-cyan-500/15 text-cyan-600 dark:text-cyan-300' },
      delivered: { icon: CheckCircle, color: 'bg-success/15 text-success' },
      cancelled: { icon: XCircle, color: 'bg-destructive/15 text-destructive' },
      rto: { icon: RefreshCw, color: 'bg-orange-500/15 text-orange-600 dark:text-orange-300' },
      refunded: { icon: RefreshCw, color: 'bg-muted text-foreground' }
    };
    const { icon: Icon, color } = config[status?.toLowerCase()] || config.pending;
    return { Icon, color };
  };

  const getPaymentBadge = (status) => {
    const config = {
      paid: 'bg-success/15 text-success',
      pending: 'bg-warning/20 text-warning',
      failed: 'bg-destructive/15 text-destructive',
      refunded: 'bg-muted text-foreground'
    };
    return config[status?.toLowerCase()] || config.pending;
  };

  // Humanize audit actions: "order.cancelled" → "Order cancelled".
  const formatActivityAction = (action) => {
    if (!action) return 'Activity';
    const text = String(action).replace(/^order\./, '').replace(/_/g, ' ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  };


  if (loading) {
    return <PageSkeleton type="order-detail" />;
  }

  if (!order) {
    return (
      <div className="text-center py-12">
        <Package size={48} className="mx-auto text-muted-foreground mb-4" />
        <h2 className="text-xl font-semibold text-muted-foreground">Order not found</h2>
        <button
          onClick={() => navigate(ordersReturnPath, { replace: true })}
          className="mt-4 text-primary hover:text-primary-hover"
        >
          Back to Orders
        </button>
      </div>
    );
  }

  const { Icon: StatusIcon, color: statusColor } = getStatusBadge(order.status);
  // Terminal states can never be changed again (defensive guard — the UI also hides the options)
  // Delivered/RTO have no onward step either (returns go through refunds).
  const TERMINAL_STATUSES = ['cancelled', 'refunded', 'delivered', 'rto'];
  const isTerminal = TERMINAL_STATUSES.includes(order.status?.toLowerCase());

  return (
    <div>
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-4 mb-6">
        <button
          onClick={() => navigate(ordersReturnPath, { replace: true })}
          className="p-1 -ml-1 text-muted-foreground hover:text-foreground shrink-0"
          aria-label="Back to orders"
        >
          <ArrowLeft size={24} />
        </button>
        <div className="flex-1 min-w-0 basis-40">
          <h1 className="text-lg sm:text-2xl font-bold text-foreground break-all">
            Order #{order.order_number}
          </h1>
          <p className="text-xs sm:text-sm text-muted-foreground break-words">
            Placed on {formatDate(order.placed_at || order.created_at, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {(order.status === 'delivered' || order.delivered_at) && <Link to={`/returns?order_id=${order.id}`} className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-muted"><Package size={16} /> Product returns</Link>}
          <span className={`px-3 py-1 rounded-full text-xs sm:text-sm font-medium flex items-center gap-1 ${statusColor}`}>
            <StatusIcon size={16} />
            {order.status}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6 min-w-0">
        {/* Order Details */}
        <div className="lg:col-span-2 space-y-4 sm:space-y-6 min-w-0">
          {/* Cancellation Details */}
          {(order.status?.toLowerCase() === 'cancelled' || order.cancellation_reason) && (
            <div className="bg-destructive/10 border border-destructive/30 rounded-xl p-4 sm:p-6">
              <div className="flex items-start gap-3">
                <XCircle size={20} className="text-destructive mt-0.5 shrink-0" />
                <div>
                  <h2 className="text-base font-semibold text-destructive">
                    Order Cancelled
                    {order.cancelled_at && (
                      <span className="ml-2 text-sm font-normal text-destructive">
                        on {new Date(order.cancelled_at).toLocaleString()}
                      </span>
                    )}
                  </h2>
                  <p className="mt-1 text-sm text-destructive">
                    <span className="font-medium">Reason:</span>{' '}
                    {order.cancellation_reason || 'No reason provided'}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Order Items */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Order Items</h2>
            <div className="divide-y divide-border">
              {order.items?.map((item) => {
                const imageUrl = getItemImage(item);
                const imageKey = item.id ?? item.product_id ?? item.product_name;
                const showImage = imageUrl && !failedImages.has(String(imageKey));
                return (
                <div key={item.id} className="py-4 first:pt-0 last:pb-0">
                  <div className="flex items-start gap-4">
                    {showImage ? (
                      <img
                        src={imageUrl}
                        alt={item.product_name}
                        className="w-16 h-16 object-cover rounded-lg border border-border shrink-0"
                        onError={() => handleImageError(imageKey)}
                      />
                    ) : (
                      <div className="w-16 h-16 bg-muted rounded-lg flex items-center justify-center border border-border shrink-0">
                        <ImageIcon size={24} className="text-muted-foreground" />
                      </div>
                    )}
                    <div className="flex-1">
                      <div className="flex items-start justify-between">
                        <div>
                          <h3 className="font-medium text-foreground">{item.product_name}</h3>
                          {item.variant_sku && (
                            <p className="text-sm text-muted-foreground">SKU: {item.variant_sku}</p>
                          )}
                          <p className="text-sm text-muted-foreground">Qty: {item.quantity}</p>
                        </div>
                        <div className="text-right">
                          <p className="font-semibold text-foreground">
                            {formatPrice(Math.round(Number(item.unit_price) * Number(item.quantity) * 100) / 100)}
                          </p>
                          <p className="text-sm text-muted-foreground">{formatPrice(item.unit_price)} each</p>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                );
              })}
            </div>
            <div className="mt-4 pt-4 border-t border-border space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Item Subtotal</span>
                <span className="font-medium">{formatPrice((order.subtotal || 0) + (order.discount_total || order.discount || 0))}</span>
              </div>
              {(order.discount_total || order.discount) > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">
                    {order.coupon_code ? `Coupon Discount (${order.coupon_code})` : 'Discount'}
                  </span>
                  <span className="font-medium text-success">-{formatPrice(order.discount_total || order.discount)}</span>
                </div>
              )}
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Subtotal</span>
                <span className="font-medium">{formatPrice(order.subtotal)}</span>
              </div>
              {(order.tax_total || order.tax) > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Tax</span>
                  <span className="font-medium">{formatPrice(order.tax_total || order.tax)}</span>
                </div>
              )}
              {(order.shipping_total || order.shipping) > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Shipping</span>
                  <span className="font-medium">{formatPrice(order.shipping_total || order.shipping)}</span>
                </div>
              )}
              {order.cod_fee > 0 && (
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">COD Fee</span>
                  <span className="font-medium">{formatPrice(order.cod_fee)}</span>
                </div>
              )}
              <div className="flex justify-between text-lg font-bold mt-2 pt-2 border-t border-border">
                <span>{String(order.payment_status || '').toLowerCase() === 'paid' ? 'Total Paid' : 'Total'}</span>
                <span>{formatPrice(order.grand_total || order.total)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="space-y-4 sm:space-y-6 min-w-0">
          {/* Customer Info */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Customer</h2>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <User size={16} className="text-muted-foreground" />
                <p className="font-medium text-foreground">{order.user?.full_name || order.shipping_address?.full_name || 'Guest'}</p>
              </div>
              <div className="flex items-center gap-2">
                <Mail size={16} className="text-muted-foreground" />
                <p className="text-sm text-muted-foreground">{order.user?.email || 'No email'}</p>
              </div>
              {order.user?.phone && (
                <div className="flex items-center gap-2">
                  <Phone size={16} className="text-muted-foreground" />
                  <p className="text-sm text-muted-foreground">{order.user.phone}</p>
                </div>
              )}
            </div>
            {order.user_id && canViewUsers && (
              <button
                onClick={() => navigate(`/users/${order.user_id}`)}
                className="mt-3 text-sm text-primary hover:text-primary-hover"
              >
                View Customer Profile
              </button>
            )}
          </div>

          {/* Shiprocket Logistics */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Truck size={18} className="text-primary" />
                Shiprocket Logistics
              </h2>
              {order.awb_code && (
                <button
                  onClick={() => setIsTrackingModalOpen(true)}
                  className="text-xs text-primary hover:underline font-medium"
                >
                  Track Live
                </button>
              )}
            </div>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Courier:</span>
                <span className="font-semibold text-foreground">{order.courier_name || 'Not assigned'}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">AWB:</span>
                <span className="font-mono font-semibold text-primary">{order.awb_code || 'Pending'}</span>
              </div>
              <div>
                <span className="text-muted-foreground block mb-1.5">Fulfilment:</span>
                <FulfilmentStage stage={shipmentStage} />
              </div>
              {order.shipped_at && (
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Shipped at:</span>
                  <span className="text-foreground text-xs">
                    {new Date(order.shipped_at).toLocaleString()}
                  </span>
                </div>
              )}
              {order.delivered_at && (
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">Delivered at:</span>
                  <span className="text-foreground text-xs">
                    {new Date(order.delivered_at).toLocaleString()}
                  </span>
                </div>
              )}

              {/* Action buttons inside Shiprocket Card - shipping.manage */}
              {canDispatch && (
                <div className="pt-2 border-t border-border flex flex-col gap-2">
                  {!order.shiprocket_shipment_id ? (
                    <button
                      disabled={['cancelled', 'refunded'].includes(order.status?.toLowerCase())}
                      onClick={() => setIsDispatchModalOpen(true)}
                      className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg bg-primary text-primary-foreground font-semibold text-xs hover:bg-primary/90 transition-all disabled:opacity-50"
                    >
                      <Truck size={16} />
                      Ship with Shiprocket
                    </button>
                  ) : (
                    <>
                      {!order.pickup_scheduled_date && (
                        <button
                          disabled={shippingActionLoading}
                          onClick={handleRequestPickup}
                          className="w-full flex items-center justify-center gap-2 py-2 px-3 rounded-lg border border-primary/30 bg-primary/10 text-primary font-medium text-xs hover:bg-primary/20 transition-all"
                        >
                          <Clock size={15} />
                          Request Courier Pickup
                        </button>
                      )}
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          disabled={shippingActionLoading}
                          onClick={handlePrintShippingLabel}
                          className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg border border-input text-xs font-medium hover:bg-muted transition-colors"
                        >
                          <Printer size={14} />
                          Label
                        </button>
                        <button
                          disabled={shippingActionLoading}
                          onClick={handlePrintManifest}
                          className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded-lg border border-input text-xs font-medium hover:bg-muted transition-colors"
                        >
                          <Package size={14} />
                          Manifest
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Payment Info */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Payment</h2>
            <div className="space-y-2 text-sm">
              <div className="flex items-center gap-2">
                <CreditCard size={16} className="text-muted-foreground" />
                <span className="text-muted-foreground">Method:</span>
                <span className="font-medium text-foreground capitalize">
                  {order.payment_method || 'Not specified'}
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-muted-foreground">Status:</span>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${getPaymentBadge(order.payment_status)}`}>
                  {order.payment_status || 'Pending'}
                </span>
              </div>
              {order.transaction_id && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Transaction ID</span>
                  <span className="font-medium text-foreground text-xs">{order.transaction_id}</span>
                </div>
              )}
            </div>
          </div>

          {/* Shipping Address */}
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">Shipping Address</h2>
            <div className="flex items-start gap-2">
              <MapPin size={16} className="text-muted-foreground mt-1 shrink-0" />
              <div className="space-y-1 text-sm">
                <p className="text-foreground font-medium">{order.shipping_address?.full_name || 'N/A'}</p>
                <p className="text-muted-foreground">{order.shipping_address?.line1 || order.shipping_address?.address_line1}</p>
                {order.shipping_address?.line2 && (
                  <p className="text-muted-foreground">{order.shipping_address.line2}</p>
                )}
                <p className="text-muted-foreground">
                  {order.shipping_address?.city}, {order.shipping_address?.state} {order.shipping_address?.postal_code || order.shipping_address?.pincode}
                </p>
                <p className="text-muted-foreground">{order.shipping_address?.country}</p>
                {order.shipping_address?.phone && (
                  <p className="text-muted-foreground">Phone: {order.shipping_address.phone}</p>
                )}
                {order.shipping_address?.label && (
                  <p className="text-xs text-muted-foreground">Label: {order.shipping_address.label}</p>
                )}
              </div>
            </div>
          </div>

          {/* Update Status - 👇 orders.update only */}
          {canUpdateStatus && (
            <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">Update Status</h2>
              {isTerminal ? (
                <div className="flex items-start gap-3">
                  <XCircle size={20} className="text-muted-foreground mt-0.5 shrink-0" />
                  <p className="text-sm text-muted-foreground">
                    This order is in a terminal state (<span className="capitalize font-medium">{order.status}</span>), so its status can no longer be changed.
                  </p>
                </div>
              ) : (
                <div>
                  <div className="flex flex-wrap gap-2">
                    {(NEXT_STATUSES[order.status?.toLowerCase()] || []).map((status) => {
                      const { Icon, color } = getStatusBadge(status);
                      return (
                        <button
                          key={status}
                          onClick={() => handleStatusUpdate(status)}
                          disabled={updating}
                          className="px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors bg-muted text-muted-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          <Icon size={16} />
                          {status.charAt(0).toUpperCase() + status.slice(1)}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-xs text-muted-foreground mt-3">
                    Only the next workflow step is offered — cancel via Cancel Order… below,
                    refunds via Issue Refund.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Actions - 👇 orders.update only */}
          {canUpdateStatus && (
            <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
              <h2 className="text-lg font-semibold text-foreground mb-4">Actions</h2>
              <div className="space-y-2">
                {canCancel && ['pending', 'confirmed', 'processing'].includes(order.status?.toLowerCase()) && (
                  <button
                    onClick={() => setCancelOpen(true)}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-destructive/10 text-destructive font-medium text-sm hover:bg-destructive/15 transition-colors"
                  >
                    <XCircle size={18} />
                    Cancel Order…
                  </button>
                )}
                {canRefund
                  && order.payment_method !== 'cod'
                  && ['paid', 'refund_failed'].includes(order.payment_status)
                  && (['cancelled', 'delivered'].includes(order.status?.toLowerCase())
                    || (order.status?.toLowerCase() === 'refunded' && order.payment_status === 'refund_failed'))
                  && (Number(order.grand_total || 0) - Number(order.refund_amount || 0) - Number(order.restocking_fee || 0)) > 0
                  && !pendingRefund && (
                  <button
                    onClick={() => setRefundOpen(true)}
                    className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary-hover transition-colors"
                  >
                    <RefreshCw size={18} />
                    Issue Refund…
                  </button>
                )}
                {pendingRefund && (
                  <div className="w-full flex items-start gap-2 px-4 py-3 rounded-lg bg-warning/10 border border-warning/30 text-sm">
                    <Clock size={16} className="text-warning mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <p className="text-muted-foreground">
                        Refund of <span className="font-semibold text-foreground">{formatPrice(pendingRefund.amount)}</span>{' '}
                        awaiting approval by a different admin — no money has moved yet.
                      </p>
                      <button
                        type="button"
                        onClick={() => navigate('/refunds?status=pending_approval')}
                        className="mt-1 text-primary hover:text-primary-hover font-medium text-sm"
                      >
                        Review on Refunds page →
                      </button>
                    </div>
                  </div>
                )}
                <button
                  onClick={handlePrintPackingSlip}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors"
                >
                  <Package size={18} />
                  Print Packing Slip
                </button>
                <button
                  onClick={handlePrintInvoice}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 border border-input rounded-lg hover:bg-muted transition-colors"
                >
                  <Printer size={18} />
                  Print Invoice
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Activity timeline — order-scoped audit trail (hidden when empty) */}
      {activity.length > 0 && (
        <div className="mt-4 sm:mt-6 bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
          <h2 className="text-lg font-semibold text-foreground mb-4">Activity</h2>
          <ol className="relative space-y-4 before:absolute before:left-[5px] before:top-2 before:bottom-2 before:w-px before:bg-border">
            {activity.map((entry) => (
              <li key={entry.id} className="relative pl-6">
                <span className="absolute left-0 top-1.5 w-[11px] h-[11px] rounded-full bg-primary border-2 border-card ring-1 ring-border" />
                <p className="text-sm font-medium text-foreground">
                  {formatActivityAction(entry.action)}
                </p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {entry.actor_email || 'System'}
                  {entry.created_at && (
                    <> · {formatDate(entry.created_at, { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })}</>
                  )}
                </p>
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* Shiprocket Modals */}
      <ShiprocketDispatchModal
        isOpen={isDispatchModalOpen}
        onClose={() => setIsDispatchModalOpen(false)}
        order={order}
        onSuccess={fetchOrder}
      />

      <TrackingModal
        isOpen={isTrackingModalOpen}
        onClose={() => setIsTrackingModalOpen(false)}
        orderId={order.id}
        orderNumber={order.order_number}
      />
      <AdminCancelDialog order={order} open={cancelOpen} onClose={() => setCancelOpen(false)} onDone={fetchOrder} />
      <RefundDialog order={order} open={refundOpen} onClose={() => setRefundOpen(false)} onDone={fetchOrder} />
      <ConfirmDialog
        open={!!confirmState}
        busy={updating}
        title={confirmState && CONFIRM_STATUSES.includes(confirmState.newStatus) ? `Move order to "${confirmState.newStatus}"?` : 'Change order status?'}
        message={
          confirmState
            ? CONFIRM_STATUSES.includes(confirmState.newStatus)
              ? `Move order ${order.order_number} to "${confirmState.newStatus}"?\n\n` +
                `This notifies the customer and, for shipped legs, should only be done when the parcel is actually moving.`
              : `Change order status to ${confirmState.newStatus}?`
            : ''
        }
        confirmLabel="Confirm"
        cancelLabel="Cancel"
        tone="primary"
        onConfirm={runConfirmed}
        onClose={() => { if (!updating) setConfirmState(null); }}
      />
    </div>
  );
};

export default OrderDetail;

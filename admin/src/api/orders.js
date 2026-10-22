// src/api/orders.js
import apiClient, { resolveApiUrl } from './client';

// ============ PUBLIC ORDER ENDPOINTS (Customer) ============

/**
 * Get current user's orders
 * @param {Object} params - Query parameters
 * @param {number} params.skip - Number of records to skip
 * @param {number} params.limit - Number of records to return
 * @returns {Promise}
 */
export const getMyOrders = (params) => {
  return apiClient.get('/orders', { params });
};

/**
 * Get specific order by ID (for current user)
 * @param {string} orderId - Order ID
 * @returns {Promise}
 */
export const getMyOrderById = (orderId) => {
  return apiClient.get(`/orders/${orderId}`);
};

/**
 * Get specific order by order number (for current user)
 * @param {string} orderNumber - Order number
 * @returns {Promise}
 */
export const getMyOrderByNumber = (orderNumber) => {
  return apiClient.get(`/orders/number/${orderNumber}`);
};

// ============ ADMIN ORDER ENDPOINTS ============

/**
 * Get all orders with filters and pagination (Admin only)
 * @param {Object} params - Query parameters
 * @param {number} params.page - Page number
 * @param {number} params.limit - Items per page
 * @param {string} params.status - Filter by status
 * @param {string} params.search - Search by order number or customer name
 * @param {string} params.from_date - Filter from date
 * @param {string} params.to_date - Filter to date
 * @returns {Promise}
 */
export const getAdminOrders = (params) => {
  return apiClient.get('/admin/orders', { params });
};

/**
 * Get order statistics (Admin only)
 * @returns {Promise}
 */
export const getAdminOrderStats = () => {
  return apiClient.get('/admin/orders/stats');
};

/**
 * Get detailed order information (Admin only)
 * @param {string} orderId - Order ID
 * @returns {Promise}
 */
export const getAdminOrderById = (orderId) => {
  return apiClient.get(`/admin/orders/${orderId}`);
};

/**
 * Update order status (Admin only)
 * @param {string} orderId - Order ID
 * @param {string} status - New status
 * @returns {Promise}
 */
export const updateAdminOrderStatus = (orderId, status) => {
  return apiClient.put(`/admin/orders/${orderId}/status`, { status });
};

// ============ SHIPROCKET & SHIPPING ENDPOINTS ============

/**
 * The happy-path fulfilment track, in order. Mirrors STAGE_PRESENTATION in
 * `FAST/Com/app/services/shipping_status.py`, which is what actually computes
 * the current `step` — this list only draws the rail beneath it.
 */
export const FULFILMENT_TRACK = [
  { key: 'ready', label: 'Ready to Ship', step: 1 },
  { key: 'pickup_scheduled', label: 'Pickup Scheduled', step: 2 },
  { key: 'in_transit', label: 'In Transit', step: 3 },
  { key: 'out_for_delivery', label: 'Out for Delivery', step: 4 },
  { key: 'delivered', label: 'Delivered', step: 5 },
];

/** Tailwind classes per tone, so colour is decided in exactly one place. */
export const STAGE_TONE_CLASSES = {
  neutral: 'bg-muted text-muted-foreground border-border',
  info: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30',
  warning: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
  success: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  danger: 'bg-destructive/15 text-destructive border-destructive/30',
};

/**
 * Fallback when the backend has not sent `shipment_stage` (e.g. an order that
 * predates the field). Derives a stage from the raw values the order API
 * already returns, so the UI degrades gracefully rather than rendering blank.
 */
export const deriveStageFallback = (order) => {
  if (!order) {
    return { stage: 'not_started', label: 'Not Shipped', step: null, tone: 'neutral', is_exception: false };
  }
  const shipment = (order.shipment_status || '').toUpperCase();
  const orderStatus = (order.status || '').toLowerCase();
  const exceptions = ['NOC', 'LOST', 'DAMAGED', 'NOT SERVICEABLE', 'MISSORT', 'ON HOLD', 'UNKNOWN'];
  // Exception first: an order can still read "shipped" while the courier has
  // reported a problem, and burying that under "In Transit" hides it.
  if (exceptions.includes(shipment)) {
    return { stage: 'exception', label: 'Delivery Issue', step: null, tone: 'danger', is_exception: true, raw_status: shipment };
  }
  if (['cancelled', 'refunded'].includes(orderStatus)) {
    return { stage: 'cancelled', label: 'Shipment Cancelled', step: null, tone: 'neutral', is_exception: false };
  }
  if (orderStatus === 'rto') {
    return { stage: 'returned', label: 'Returned to Origin', step: null, tone: 'danger', is_exception: false };
  }
  if (orderStatus === 'delivered') {
    return { stage: 'delivered', label: 'Delivered', step: 5, tone: 'success', is_exception: false };
  }
  if (orderStatus === 'out_for_delivery') {
    return { stage: 'out_for_delivery', label: 'Out for Delivery', step: 4, tone: 'warning', is_exception: false };
  }
  if (orderStatus === 'shipped') {
    return { stage: 'in_transit', label: 'In Transit', step: 3, tone: 'info', is_exception: false };
  }
  if (order.pickup_scheduled_date || shipment === 'PICKUP_SCHEDULED') {
    return { stage: 'pickup_scheduled', label: 'Pickup Scheduled', step: 2, tone: 'info', is_exception: false };
  }
  if (order.awb_code) {
    return { stage: 'ready', label: 'Ready to Ship', step: 1, tone: 'info', is_exception: false };
  }
  return { stage: 'not_started', label: 'Not Shipped', step: null, tone: 'neutral', is_exception: false };
};

/** Prefer the server-computed stage; fall back to the local derivation. */
export const resolveShipmentStage = (order) =>
  order?.shipment_stage || deriveStageFallback(order);

/**
 * The fulfilment pipeline a real Shiprocket parcel follows, and the event name
 * this app sends to the backend to simulate each step.
 *
 * Keep the `event` values in sync with `SIMULATOR_EVENTS` in
 * `FAST/Com/app/api/v1/admin/orders.py` — the backend maps each one to the
 * genuine Shiprocket `current_status` and replays it through the same handler
 * the live webhook uses. The `status` shown is that real Shiprocket string, so
 * what you see here is what Shiprocket would actually send.
 *
 * Only milestones that genuinely occur are listed. Label and manifest are
 * deliberately absent: the label/manifest endpoints only store a URL and never
 * move the shipment status, so simulating them would show a state the app can
 * never actually reach. "Awaiting Pickup" is absent for the same reason — the
 * admin's "Request Courier Pickup" button writes PICKUP_SCHEDULED directly.
 */
export const SHIPROCKET_LIFECYCLE = [
  { key: 'picked_up', event: 'picked_up', status: 'PICKED UP', label: 'Picked Up', phase: 'in-transit' },
  { key: 'in_transit', event: 'in_transit', status: 'IN TRANSIT', label: 'In Transit', phase: 'in-transit' },
  { key: 'out_for_delivery', event: 'out_for_delivery', status: 'OUT FOR DELIVERY', label: 'Out For Delivery', phase: 'last-mile' },
  { key: 'delivered', event: 'delivered', status: 'DELIVERED', label: 'Delivered', phase: 'last-mile' },
];

/**
 * Return-to-origin branch of the ORIGINAL forward shipment. This is not a
 * customer return AWB; customer reverse events are shown in the Customer
 * returns tab and use RETURN_* labels.
 */
export const SHIPROCKET_RTO_EVENTS = [
  { key: 'rto_initiated', event: 'rto_initiated', status: 'RTO INITIATED', label: 'RTO Initiated', phase: 'rto' },
  { key: 'rto_in_transit', event: 'rto_in_transit', status: 'RTO IN TRANSIT', label: 'RTO In Transit', phase: 'rto' },
  { key: 'rto_ofd', event: 'rto_ofd', status: 'RTO OFD', label: 'RTO Out for Delivery', phase: 'rto' },
  { key: 'rto_delivered', event: 'rto_delivered', status: 'RTO DELIVERED', label: 'RTO Delivered — restocks', phase: 'rto' },
  { key: 'rto_acknowledged', event: 'rto_acknowledged', status: 'RTO ACKNOWLEDGED', label: 'Acknowledge RTO', phase: 'rto' },
];

/**
 * Courier exceptions. These are recorded on the tracking timeline but do NOT
 * move the order status — a failed delivery attempt is not a status change.
 */
export const SHIPROCKET_EXCEPTION_EVENTS = [
  { key: 'delivery_failed', event: 'delivery_failed', status: 'UNDELIVERED', label: 'Delivery failed (NDR)', phase: 'exception' },
  { key: 'noc', event: 'noc', status: 'NOC', label: 'NOC / Failed Attempt', phase: 'exception' },
  { key: 'on_hold', event: 'on_hold', status: 'ON HOLD', label: 'On Hold', phase: 'exception' },
  { key: 'missorted', event: 'missorted', status: '3PL MISSORT', label: 'Missorted', phase: 'exception' },
  { key: 'damaged', event: 'damaged', status: 'DAMAGED', label: 'Damaged', phase: 'exception' },
  { key: 'lost', event: 'lost', status: 'LOST', label: 'Lost', phase: 'exception' },
];

/**
 * Check courier serviceability & rates
 */
export const checkShippingServiceability = (orderId) => {
  return apiClient.get(`/admin/orders/${orderId}/shipping/serviceability`);
};

/**
 * Push order to Shiprocket
 */
export const createShiprocketOrder = (orderId) => {
  return apiClient.post(`/admin/orders/${orderId}/shipping/create`);
};

/**
 * Assign AWB & Courier partner
 */
export const assignOrderAWB = (orderId, courierId = null, etd = null) => {
  return apiClient.post(`/admin/orders/${orderId}/shipping/assign-awb`, { courier_id: courierId, etd });
};

/**
 * Request courier pickup
 */
export const requestOrderPickup = (orderId) => {
  return apiClient.post(`/admin/orders/${orderId}/shipping/request-pickup`);
};

/**
 * Fetch shipping label URL
 */
export const getOrderShippingLabel = (orderId) => {
  return apiClient.get(`/admin/orders/${orderId}/shipping/label`);
};

/**
 * Fetch shipping manifest URL
 */
export const getOrderShippingManifest = (orderId) => {
  return apiClient.get(`/admin/orders/${orderId}/shipping/manifest`);
};

export const getSimulatedShippingDocument = (url) => {
  const path = new URL(resolveApiUrl(url), window.location.origin).pathname;
  if (!/^\/api\/v1\/admin\/orders\/shipping\/simulated-(label|manifest)\/[^/]+$/.test(path)) {
    throw new Error('Invalid simulator document path');
  }
  // Always use our API base, never attach a bearer token to a provider URL.
  return apiClient.get(path.replace(/^\/api\/v1/, ''), { responseType: 'text' });
};

/**
 * Get tracking timeline scans
 */
export const getOrderShippingTracking = (orderId) => {
  return apiClient.get(`/admin/orders/${orderId}/shipping/tracking`);
};

/**
 * Simulator: Fetch all shipments
 */
export const getSimulatorShipments = () => {
  return apiClient.get('/admin/orders/shipping/simulator/shipments');
};

/**
 * Simulator: Trigger mock tracking webhook event
 */
export const triggerSimulatorEvent = (orderId, payload) => {
  return apiClient.post(`/admin/orders/${orderId}/shipping/simulator/trigger-event`, payload);
};

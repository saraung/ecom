// src/api/orders.js
import api from './axios';

export const orderAPI = {
  // Get current user's orders (newest first)
  // ✅ Backend returns a plain JSON array (no pagination envelope) — pagination is
  //    manual via skip/limit and there is no total count
  getOrders: (skip = 0, limit = 20) => api.get('/orders', { params: { skip, limit } }),

  // Get one order by UUID — full OrderRead (user, addresses, items, updated_at…)
  getOrderById: (orderId) => api.get(`/orders/${orderId}`),

  // Get one order by human-readable order number (e.g. "ORD-20260829-4F2A")
  getOrderByNumber: (orderNumber) => api.get(`/orders/number/${orderNumber}`),

  // ✅ Cancel an order (only orders still in pending/confirmed/processing can be cancelled).
  //    Paid online orders get an automatic refund initiated by the backend.
  //    Body: { reason: "Changed my mind" } → the reason is stored on the order.
  //    Returns: { order_id, order_number, status: "cancelled", message,
  //               refund: { processed, amount, restocking_fee, fee_percentage,
  //                        refund_id, status, payment_status, message } | null }
  cancelOrder: (orderId, reason) => api.post(`/orders/${orderId}/cancel`, { reason }),

  // ✅ Refund phase for a cancelled paid order (GET /orders/{id} already includes
  //    payment_status / refund_amount / refund_id / restocking_fee — this endpoint is
  //    for on-demand polling when refund_initiated is still pending).
  //    Returns: { order_id, order_number, refund_id, refund_amount, restocking_fee,
  //               fee_percentage, payment_status, status, message }
  getRefundStatus: (orderId) => api.get(`/orders/${orderId}/refund-status`),
};

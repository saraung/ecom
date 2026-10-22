// src/api/refunds.js
import apiClient from './client';

/**
 * Unified admin cancel: status + optional money movement in one action.
 * @param {string} orderId
 * @param {Object} data - { reason, refund_choice: 'now'|'later', restock, notify_customer, idempotency_key }
 */
export const adminCancelOrder = (orderId, data) => {
  return apiClient.post(`/admin/orders/${orderId}/cancel`, data);
};

/**
 * Standalone refund without cancelling (cancelled-follow-up cleanup and
 * post-delivery returns). Executes within authority, else stages approval.
 * @param {string} orderId
 * @param {Object} data - { reason, amount?, idempotency_key? }
 */
export const issueOrderRefund = (orderId, data) => {
  return apiClient.post(`/admin/orders/${orderId}/refund`, data);
};

/**
 * Action queue: paid online orders holding captured money with no refund
 * in flight (cancelled-unrefunded cleanup + delivered returns).
 * @returns {Promise} { count, orders: [{order_id, order_number, status, customer_email, grand_total, refunded, remaining, ...}] }
 */
export const getRefundsAttention = () => {
  return apiClient.get('/admin/refunds/attention');
};

/**
 * The caller's own refund authority: { max_refund_amount: string|null,
 * unlimited: bool }. Display-only — the server re-checks on every approve.
 */
export const getMyRefundAuthority = () => {
  return apiClient.get('/admin/refunds/my-authority');
};

/**
 * Reconcile an order's refund ledger with provider-side truth.
 * Records gateway-side refunds that bypassed the app, then re-derives the
 * recorded total. Idempotent — re-running changes nothing.
 * @param {string} orderId
 */
export const reconcileOrderRefunds = (orderId) => {
  return apiClient.post(`/admin/orders/${orderId}/reconcile-refund`);
};

/**
 * List refund ledger rows (requires orders.refund).
 * @param {Object} params - { page, limit, status_filter, order_id }
 */
export const getRefunds = (params) => {
  return apiClient.get('/admin/refunds', { params });
};

/**
 * Approve + execute a pending refund. Approver must differ from requester.
 * @param {string} refundId
 */
export const approveRefund = (refundId) => {
  return apiClient.post(`/admin/refunds/${refundId}/approve`);
};

/**
 * Reject a pending refund (no money moves).
 * @param {string} refundId
 * @param {string} [note]
 */
export const rejectRefund = (refundId, note) => {
  return apiClient.post(`/admin/refunds/${refundId}/reject`, { note: note || null });
};

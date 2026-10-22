// src/api/notifications.js
import apiClient from './client';

// ============ NOTIFICATIONS (admin panel: staff audience) ============
// The admin bell shows operational alerts only (order_placed,
// order_cancelled). Shopper items (order status, promotions) stay in the
// storefront bell — see the `audience` filter on GET /notifications.

/**
 * Get the notifications feed for the current user (staff audience).
 * @param {Object} params
 * @param {number} params.skip - Records to skip (pagination)
 * @param {number} params.limit - Max records to return
 * @param {boolean} params.unread_only - Only unread notifications
 * @returns {Promise}
 */
export const getNotifications = (params) => {
  return apiClient.get('/notifications', { params: { ...params, audience: 'staff' } });
};

/**
 * Get the count of unread notifications for the current user (staff).
 * @returns {Promise} - { count: number }
 */
export const getUnreadNotificationsCount = () => {
  return apiClient.get('/notifications/unread-count', { params: { audience: 'staff' } });
};

/**
 * Mark a single notification as read.
 * @param {number|string} notificationId
 * @returns {Promise}
 */
export const markNotificationRead = (notificationId) => {
  return apiClient.put(`/notifications/${notificationId}/read`);
};

/**
 * Mark every notification of the current user as read (staff audience).
 * @returns {Promise}
 */
export const markAllNotificationsRead = () => {
  return apiClient.put('/notifications/mark-all-read', null, { params: { audience: 'staff' } });
};

/**
 * Delete a single notification.
 * @param {number|string} notificationId
 * @returns {Promise}
 */
export const deleteNotification = (notificationId) => {
  return apiClient.delete(`/notifications/${notificationId}`);
};

// ============ ADMIN: PROMOTIONAL BROADCASTS ============

/**
 * Send a promotional message to ALL users (in-app feed).
 * @param {Object} data
 * @param {string} data.title - Short headline (e.g. "Diwali Sale is live!")
 * @param {string} data.message - Message body shown in the user's notification UI
 * @param {string} [data.link] - Optional deep link for the user app (e.g. "/products?sale=diwali")
 * @param {boolean} [data.send_email] - Also email shoppers whose Email
 *   Notifications toggle is on (default false = feed only). Delivery runs
 *   in the background; outcome lands on the history row. Emails can't be
 *   retracted — only feed rows are removed on retract.
 * @returns {Promise} - { broadcast_id, recipients_count, emails_queued, ... }
 */
export const sendPromotionalNotification = (data) => {
  return apiClient.post('/admin/notifications/promotional', data);
};

/**
 * Live recipient counts for the compose form (counts only, no PII).
 * @returns {Promise} - { feed_recipients, email_recipients }
 */
export const getPromotionAudienceEstimate = () => {
  return apiClient.get('/admin/notifications/promotional/audience-estimate');
};

/**
 * History of promotional broadcasts sent by admins.
 * @param {Object} params
 * @param {number} params.skip
 * @param {number} params.limit
 * @returns {Promise}
 */
export const getSentPromotions = (params) => {
  return apiClient.get('/admin/notifications/promotional', { params });
};

/**
 * Retract a promotional broadcast — deletes every recipient's notification
 * for the given broadcast and removes it from the admin history.
 * @param {number|string} broadcastId - The broadcast (or history) id
 * @returns {Promise} - { deleted_count: number }
 */
export const deletePromotionalNotification = (broadcastId) => {
  return apiClient.delete(`/admin/notifications/promotional/${broadcastId}`);
};
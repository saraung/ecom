// src/api/users.js
import apiClient from './client';

/**
 * Get all users with pagination and filters (Admin only)
 * @param {Object} params - Query parameters
 * @param {number} params.page - Page number
 * @param {number} params.limit - Items per page
 * @param {string} params.search - Search by name, email, or username
 * @param {string} params.role - Filter by role
 * @param {boolean} params.is_active - Filter by active status
 * @returns {Promise}
 */
export const getUsers = (params) => {
  return apiClient.get('/admin/users', { params });
};

/**
 * Get user statistics (Admin only)
 * @returns {Promise}
 */
export const getUserStats = () => {
  return apiClient.get('/admin/users/stats');
};

/**
 * Get user by ID (Admin only)
 * @param {string} userId - User ID
 * @returns {Promise}
 */
export const getUserById = (userId) => {
  return apiClient.get(`/admin/users/${userId}`);
};

/**
 * Update user status (Admin only)
 * @param {string} userId - User ID
 * @param {boolean} isActive - Active status
 * @returns {Promise}
 */
export const updateUserStatus = (userId, isActive) => {
  return apiClient.put(`/admin/users/${userId}/status`, { is_active: isActive });
};

/**
 * Delete user (Admin only)
 * @param {string} userId - User ID
 * @returns {Promise}
 */
export const deleteUser = (userId) => {
  return apiClient.delete(`/admin/users/${userId}`);
};

/**
 * Get lifetime order statistics for a single user (Admin only)
 *
 * Returns:
 *   total_orders, total_spent (excludes cancelled/refunded), gross_total,
 *   refunded_total, average_order_value, total_items_purchased,
 *   first_order, last_order (null → "Never"), status_breakdown,
 *   most_ordered_product
 *
 * @param {string} userId - User ID
 * @returns {Promise}
 */
export const getUserOrderStats = (userId) => {
  return apiClient.get(`/admin/users/${userId}/stats`);
};

/**
 * Get all addresses for a specific user (Admin only)
 *
 * NOTE: The customer-facing `GET /addresses` only returns the *current*
 * user's own addresses and ignores `user_id` — this admin-scoped endpoint
 * is the correct way to view another user's saved addresses.
 *
 * @param {string} userId - User ID
 * @returns {Promise}
 */
export const getUserAddresses = (userId) => {
  return apiClient.get(`/admin/users/${userId}/addresses`);
};
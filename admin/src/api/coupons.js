// src/api/coupons.js
import apiClient from './client';

/**
 * Get all coupons
 * @param {Object} params - Query parameters
 * @returns {Promise}
 */
export const getCoupons = (params) => {
  return apiClient.get('/coupons', { params });
};

/**
 * Get coupon by ID
 * @param {string} couponId - Coupon ID
 * @returns {Promise}
 */
export const getCouponById = (couponId) => {
  return apiClient.get(`/coupons/${couponId}`);
};

/**
 * Create a new coupon
 * @param {Object} data - Coupon data
 * @param {string} [data.code] - Coupon code (required for manual coupons;
 *   omitted for automatic coupons — the backend generates AUTO-XXXXXX)
 * @param {string} [data.coupon_type] - 'manual' (default) or 'automatic'
 * @param {string} [data.trigger_type] - Automatic trigger:
 *   'min_cart_value' | 'min_item_count' | 'category_spend' | 'first_order'
 * @param {number} [data.trigger_min_cart_value] - Minimum cart value trigger
 * @param {number} [data.trigger_min_item_count] - Minimum item count trigger
 * @param {string} [data.trigger_category_id] - Category UUID for the
 *   category-spend trigger
 * @param {number} [data.trigger_category_spend] - Minimum spend within the
 *   category
 * @param {string} data.discount_type - 'percentage' or 'fixed'
 * @param {number} data.value - Discount value
 * @param {number} data.min_order_value - Minimum order value
 * @param {number} data.max_uses - Maximum uses
 * @param {number} data.max_uses_per_user - Max uses per user
 * @param {string} data.valid_until - Expiry date
 * @param {boolean} data.is_active - Active status
 * @returns {Promise}
 */
export const createCoupon = (data) => {
  return apiClient.post('/coupons', data);
};

/**
 * Update a coupon
 * @param {string} couponId - Coupon ID
 * @param {Object} data - Coupon data
 * @returns {Promise}
 */
export const updateCoupon = (couponId, data) => {
  return apiClient.put(`/coupons/${couponId}`, data);
};

/**
 * Delete a coupon
 * @param {string} couponId - Coupon ID
 * @returns {Promise}
 */
export const deleteCoupon = (couponId) => {
  return apiClient.delete(`/coupons/${couponId}`);
};

/**
 * Generate a random coupon code
 * @returns {Promise}
 */
export const generateCoupon = () => {
  return apiClient.post('/coupons/generate');
};

export const getRiskyCoupons = () => {
  return apiClient.get('/coupons/risky');
};

/**
 * Validate a coupon code
 * @param {string} code - Coupon code
 * @returns {Promise}
 */
export const validateCoupon = (code) => {
  return apiClient.post('/coupons/validate', { code });
};
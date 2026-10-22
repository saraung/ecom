// src/api/reviews.js
import apiClient from './client';

// ============ ADMIN: REVIEW MODERATION ============
// Requires reviews.moderate (admins only). Hidden reviews stay in the DB
// but vanish from every storefront read path.

/**
 * Paginated moderation queue (hidden included), newest first.
 * @param {Object} params
 * @param {number} params.page
 * @param {number} params.limit
 * @param {number} [params.rating] - 1-5 filter
 * @param {string} [params.product_id]
 * @param {boolean} [params.hidden] - true = hidden only, false = visible only
 * @param {string} [params.search] - title/comment/author email
 * @returns {Promise} - { items, total, page, limit, total_pages }
 */
export const getAdminReviews = (params) => {
  return apiClient.get('/admin/reviews', { params });
};

/**
 * Hide (or unhide) a review. Takes effect on the storefront instantly.
 * @param {string} reviewId
 * @param {boolean} isHidden
 * @returns {Promise}
 */
export const setReviewVisibility = (reviewId, isHidden) => {
  return apiClient.put(`/admin/reviews/${reviewId}/visibility`, {
    is_hidden: isHidden,
  });
};

/**
 * Hard-delete a review (spam/abuse with no record value). Audited.
 * @param {string} reviewId
 * @returns {Promise}
 */
export const deleteReview = (reviewId) => {
  return apiClient.delete(`/admin/reviews/${reviewId}`);
};

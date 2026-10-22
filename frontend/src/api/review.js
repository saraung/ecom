// api/review.js
import api from './axios';

export const reviewAPI = {
  // Create a review for a product — product_id goes in URL path, rating/title/comment in body
  // Requires a verified (delivered) purchase — backend returns 403 if not eligible
  createReview: (productId, reviewData) => api.post(`/reviews/${productId}`, reviewData),
  createReviewWithImages: (productId, reviewData, files = []) => {
    const form = new FormData();
    form.append('data', JSON.stringify(reviewData));
    files.forEach((file) => form.append('files', file));
    return api.post(`/reviews/${productId}/with-images`, form, { headers: { 'Content-Type': undefined } });
  },

  // Get all reviews for a product (paginated)
  getProductReviews: (productId, skip = 0, limit = 20) =>
    api.get(`/reviews/products/${productId}`, { params: { skip, limit } }),

  // Get average rating for a product
  getProductRating: (productId) => api.get(`/reviews/product/${productId}/rating`),

  // Get all reviews written by the current logged-in user (paginated)
  getMyReviews: (skip = 0, limit = 20) =>
    api.get('/reviews/my-reviews', { params: { skip, limit } }),

  // Update one of your own reviews — review_id goes in URL path
  updateReview: (reviewId, reviewData) => api.put(`/reviews/${reviewId}`, reviewData),

  // Delete one of your own reviews
  deleteReview: (reviewId) => api.delete(`/reviews/${reviewId}`),
};

export default reviewAPI;

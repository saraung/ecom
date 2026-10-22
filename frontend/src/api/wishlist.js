import api from './axios';

export const wishlistAPI = {
  // Get wishlist
  getWishlist: () => api.get('/wishlist'),
  
  // Add to wishlist - product_id goes in URL path, not body
  addToWishlist: (productId) => api.post(`/wishlist/${productId}`),
  
  // Remove from wishlist - product_id goes in URL path
  removeFromWishlist: (productId) => api.delete(`/wishlist/${productId}`),
  
  // Check if product is in wishlist
  checkInWishlist: (productId) => api.get(`/wishlist/check/${productId}`),
};
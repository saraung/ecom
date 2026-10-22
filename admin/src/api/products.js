// src/api/products.js
import apiClient from './client';

// ============ PUBLIC PRODUCT ENDPOINTS ============
export const getProducts = (params) => {
  return apiClient.get('/products', { params });
};

export const getProductBySlug = (slug) => {
  return apiClient.get(`/products/${slug}`);
};

export const getProductVariants = (productId) => {
  return apiClient.get(`/products/${productId}/variants`);
};

// ============ ADMIN PRODUCT MANAGEMENT ============
export const getAdminProducts = (params) => {
  return apiClient.get('/admin/products', { params });
};

export const getAdminProductBySlug = (slug) => {
  return apiClient.get(`/admin/products/by-slug/${slug}`);
};

export const createProduct = (data) => {
  // Trailing slash is required: backend defines POST "/" so POST
  // "/products" gets a 307 redirect to "/products/" and the browser
  // drops the Authorization header on the redirect -> 401.
  return apiClient.post('/products/', data);
};

export const updateProduct = (productId, data) => {
  return apiClient.put(`/products/${productId}`, data);
};

export const deleteProduct = (productId) => {
  return apiClient.delete(`/products/${productId}`);
};

// ============ ADMIN BULK OPERATIONS ============
export const bulkUpdateProductStatus = (productIds, isActive) => {
  return apiClient.post('/admin/products/bulk-update-status', productIds, {
    params: { is_active: isActive }
  });
};

export const bulkDeleteProducts = (productIds) => {
  return apiClient.post('/admin/products/bulk-delete', productIds);
};

export const exportAdminProducts = () => {
  return apiClient.get('/admin/products/export');
};

// ============ VARIANT MANAGEMENT ============
export const createVariant = (productId, data) => {
  return apiClient.post(`/products/${productId}/variants`, data);
};

export const updateVariant = (productId, variantId, data) => {
  return apiClient.put(`/products/${productId}/variants/${variantId}`, data);
};

export const deleteVariant = (productId, variantId) => {
  return apiClient.delete(`/products/${productId}/variants/${variantId}`);
};

// ============ IMAGE MANAGEMENT ============
export const getProductImages = (productId) => {
  return apiClient.get(`/products/${productId}/images`);
};

export const addProductImage = (productId, data) => {
  return apiClient.post(`/products/${productId}/images`, data);
};

export const uploadProductImage = (productId, file, altText = '') => {
  const form = new FormData();
  form.append('file', file);
  if (altText.trim()) form.append('alt_text', altText.trim());
  return apiClient.post(`/products/${productId}/images/upload`, form, {
    headers: { 'Content-Type': undefined },
  });
};

export const updateProductImage = (productId, imageId, data) => {
  return apiClient.put(`/products/${productId}/images/${imageId}`, data);
};

export const deleteProductImage = (productId, imageId) => {
  return apiClient.delete(`/products/${productId}/images/${imageId}`);
};

export const reorderProductImages = (productId, imageIds) => {
  return apiClient.post(`/products/${productId}/images/reorder`, imageIds);
};

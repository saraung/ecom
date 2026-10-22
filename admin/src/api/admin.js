// src/api/admin.js
import apiClient from './client';

// ============ DASHBOARD ============
export const getDashboardStats = () => {
  return apiClient.get('/admin/dashboard');
};

// ============ ADMIN ORDERS ============
export const getAdminOrders = (params) => {
  return apiClient.get('/admin/orders', { params });
};

export const getAdminOrderStats = () => {
  return apiClient.get('/admin/orders/stats');
};

export const getAdminOrderById = (orderId) => {
  return apiClient.get(`/admin/orders/${orderId}`);
};

export const updateAdminOrderStatus = (orderId, status) => {
  return apiClient.put(`/admin/orders/${orderId}/status`, { status });
};

// ============ ADMIN USERS ============
export const getAdminUsers = (params) => {
  return apiClient.get('/admin/users', { params });
};

export const getAdminUserStats = () => {
  return apiClient.get('/admin/users/stats');
};

export const getAdminUserById = (userId) => {
  return apiClient.get(`/admin/users/${userId}`);
};

export const updateAdminUserStatus = (userId, isActive) => {
  return apiClient.put(`/admin/users/${userId}/status`, { is_active: isActive });
};

export const deleteAdminUser = (userId) => {
  return apiClient.delete(`/admin/users/${userId}`);
};

// ============ ADMIN PRODUCTS (bulk operations) ============
// Note: Individual product CRUD is in products.js
// These are the admin-specific bulk operations
export const bulkUpdateProductStatus = (productIds, isActive) => {
  return apiClient.post('/admin/products/bulk-update-status', productIds, {
    params: { is_active: isActive }
  });
};

export const bulkDeleteProducts = (productIds) => {
  return apiClient.delete('/admin/products/bulk-delete', { data: productIds });
};

export const exportAdminProducts = () => {
  return apiClient.get('/admin/products/export');
};
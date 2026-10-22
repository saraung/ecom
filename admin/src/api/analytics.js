// src/api/analytics.js
import apiClient from './client';

// ============ DASHBOARD ============
export const getDashboardStats = () => {
  return apiClient.get('/admin/dashboard');
};

// ============ ANALYTICS ============
export const getDashboardAnalytics = () => {
  return apiClient.get('/analytics/dashboard');
};

export const getSalesReport = (params) => {
  return apiClient.get('/analytics/sales', { params });
};

export const getTopProducts = (params) => {
  return apiClient.get('/analytics/top-products', { params });
};

export const getOrderStatistics = (params) => {
  return apiClient.get('/analytics/orders', { params });
};

export const getRevenueReport = (params) => {
  return apiClient.get('/analytics/revenue', { params });
};

export const getCustomerSummary = (params) => {
  return apiClient.get('/analytics/customers', { params });
};
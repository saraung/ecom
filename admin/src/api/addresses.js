// src/api/addresses.js
import apiClient from './client';

/**
 * Get user addresses
 * @param {Object} params - Query parameters
 * @param {string} params.user_id - Filter by user ID
 * @returns {Promise}
 */
export const getAddresses = (params) => {
  return apiClient.get('/addresses', { params });
};

export const getAddressById = (addressId) => {
  return apiClient.get(`/addresses/${addressId}`);
};

export const createAddress = (data) => {
  return apiClient.post('/addresses', data);
};

export const updateAddress = (addressId, data) => {
  return apiClient.put(`/addresses/${addressId}`, data);
};

export const setDefaultAddress = (addressId) => {
  return apiClient.post(`/addresses/default/${addressId}`);
};

export const deleteAddress = (addressId) => {
  return apiClient.delete(`/addresses/${addressId}`);
};
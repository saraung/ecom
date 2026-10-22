import api from './axios';

export const addressAPI = {
  // Get all addresses
  getAddresses: () => api.get('/addresses'),
  
  // Create a new address
  createAddress: (data) => api.post('/addresses', data),
  
  // Update an address
  updateAddress: (addressId, data) => api.put(`/addresses/${addressId}`, data),
  
  // Delete an address
  deleteAddress: (addressId) => api.delete(`/addresses/${addressId}`),
  
  // Set default address
  setDefaultAddress: (addressId) => api.post(`/addresses/default/${addressId}`),
};
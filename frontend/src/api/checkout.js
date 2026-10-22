import api from './axios';

export const checkoutAPI = {
  /**
   * Create an order from the cart.
   * @param {Object} data - { shipping_address_id, billing_address_id, payment_method }
   */
  createOrder: (data) => api.post('/checkout', data),

  /**
   * Get checkout configuration (COD fee, limits, shipping, tax) from the server.
   * This is used to display accurate pricing rules without hardcoding.
   */
  getConfig: () => api.get('/checkout/config'),
};
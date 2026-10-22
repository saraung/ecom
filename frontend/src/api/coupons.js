import api from './axios';

export const couponAPI = {
  // ✅ User-facing - Validate coupon (public)
  validateCoupon: (code) => api.post('/coupons/validate', { code }),
};
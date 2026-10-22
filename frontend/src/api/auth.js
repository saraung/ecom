// src/api/auth.js
import api from './axios';

export const authAPI = {
  // Existing
  register: (data) => api.post('/auth/register', data), // Keep for backward compatibility
  
  // ✅ NEW OTP Registration Endpoints
  initiateRegistration: (data) => api.post('/auth/register/initiate', data),
  verifyRegistration: (data) => api.post('/auth/register/verify', data),
  resendOTP: (email) => api.post('/auth/register/resend-otp', { email }),
  
  // Existing
  // Storefront sessions are scoped with audience "storefront": a staff,
  // manager or admin account signs in here with just its password (no OTP
  // step) and keeps full shopping rights — the backend flags those orders via
  // Order.placed_by_staff for the refund/analytics guardrails. A storefront
  // token is refused by the backend on /admin/* routes, so it cannot be used
  // to reach the admin API. The admin panel keeps the OTP step-up.
  login: (data) =>
    api.post('/auth/login', { ...data, audience: 'storefront' }),
  googleLogin: (idToken) =>
    api.post('/auth/google', { id_token: idToken, audience: 'storefront' }),
  logout: (refreshToken) => api.post('/auth/logout', { refresh_token: refreshToken }),
  getMe: () => api.get('/auth/me'),
  updateProfile: (data) => api.put('/auth/profile', data),
  setPassword: (password) => api.post('/auth/set-password', { password }),
  forgotPassword: (email) => api.post('/auth/forgot-password', { email }),
  resetPassword: (data) => api.post('/auth/reset-password', data),
  changePassword: (data) => api.post('/auth/change-password', data),
};
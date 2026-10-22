// src/api/auth.js
import apiClient from './client';

/**
 * Register a new user
 * @param {Object} data - User registration data
 * @param {string} data.email - User email
 * @param {string} data.username - User username
 * @param {string} data.password - User password
 * @param {string} data.full_name - User full name
 * @param {string} data.phone - User phone number
 * @returns {Promise} 
 */
export const register = (data) => {
  return apiClient.post('/auth/register', data);
};

/**
 * Login user.
 *
 * Privileged accounts (any admin permission) do NOT receive tokens here —
 * the response is `{ otp_required: true, challenge_token, email_masked }`
 * and the session is completed via verifyLoginOtp().
 * Shoppers receive the TokenPair directly.
 *
 * @param {Object} data - Login credentials
 * @param {string} data.email - User email
 * @param {string} data.password - User password
 * @returns {Promise}
 */
export const login = (data) => {
  return apiClient.post('/auth/login', { ...data, audience: 'admin' });
};

/**
 * Complete the OTP step-up for a privileged login.
 * @param {string} challengeToken - Challenge from login()
 * @param {string} otpCode - 6-digit code from email
 * @returns {Promise} TokenPair
 */
export const verifyLoginOtp = (challengeToken, otpCode) => {
  return apiClient.post('/auth/login/verify-otp', {
    challenge_token: challengeToken,
    otp_code: otpCode,
  });
};

/**
 * Re-send the admin-login OTP for a live challenge (60s cooldown).
 * @param {string} challengeToken - Challenge from login()
 */
export const resendLoginOtp = (challengeToken) => {
  return apiClient.post('/auth/login/resend-otp', {
    challenge_token: challengeToken,
  });
};

/**
 * Google OAuth login
 * @param {string} idToken - Google ID token
 * @returns {Promise}
 */
export const googleLogin = (idToken) => {
  return apiClient.post('/auth/google', { id_token: idToken, audience: 'admin' });
};

/**
 * Set password for Google-authenticated users
 * @param {string} password - New password
 * @returns {Promise}
 */
export const setPassword = (password) => {
  return apiClient.post('/auth/set-password', { password });
};

/**
 * Refresh access token
 * @param {string} refreshToken - Refresh token
 * @returns {Promise}
 */
export const refreshToken = (refreshToken) => {
  return apiClient.post('/auth/refresh', { refresh_token: refreshToken });
};

/**
 * Logout user
 * @param {string} refreshToken - Refresh token to invalidate
 * @returns {Promise}
 */
export const logout = (refreshToken) => {
  return apiClient.post('/auth/logout', { refresh_token: refreshToken });
};

/**
 * Get current user profile
 * @returns {Promise}
 */
export const getCurrentUser = () => {
  return apiClient.get('/auth/me');
};

/**
 * Update user profile
 * @param {Object} data - Profile data
 * @param {string} data.username - New username
 * @param {string} data.full_name - New full name
 * @param {string} data.phone - New phone number
 * @returns {Promise}
 */
export const updateProfile = (data) => {
  return apiClient.put('/auth/profile', data);
};

/**
 * Change password
 * @param {Object} data - Password data
 * @param {string} data.current_password - Current password
 * @param {string} data.new_password - New password
 * @returns {Promise}
 */
export const changePassword = (data) => {
  return apiClient.post('/auth/change-password', data);
};
// src/api/client.js
import axios from 'axios';
import { createApiClient } from '@ecom/shared/http';
import { createSession } from '@ecom/shared/session';

// Absolute API origin. Dev defaults to the local backend; there is no Vite
// proxy any more. Production builds must set VITE_API_URL at build time,
// e.g. https://api.example.com/api/v1.
export const API_BASE_URL = (
  import.meta.env.VITE_API_URL || 'http://localhost:8001/api/v1'
).replace(/\/+$/, '');

// Single-flight refresh + logout are shared with the storefront
// (@ecom/shared/session); only the admin redirect/cache-clearing differ.
// The axios client below queues every 401 onto this one session instance.
export const session = createSession({
  refreshUrl: `${API_BASE_URL}/auth/refresh`,
  logoutUrl: '/login?reason=session_expired',
  replace: true,
  guardReentry: true,
  clearKeys: ['user'],
});

export const { refreshSession, hardLogout } = session;

const apiClient = createApiClient({
  axios,
  baseURL: API_BASE_URL,
  session,
});

// ============================================================
// Absolute-URL resolver for backend-returned links.
//
// Some endpoints return paths (e.g. the Shiprocket simulator serves
// `/api/v1/admin/orders/shipping/simulated-label/<id>`) while real providers
// return absolute URLs. `window.open()` resolves paths against the FRONTEND
// origin, so relative links must be re-anchored to the API origin.
// ============================================================
export const resolveApiUrl = (url) => {
  if (!url) return url;
  if (/^(https?:)?\/\//i.test(url)) return url; // already absolute
  const origin = API_BASE_URL.replace(/\/api\/v1\/?$/, '');
  return `${origin}${url.startsWith('/') ? '' : '/'}${url}`;
};

export default apiClient;

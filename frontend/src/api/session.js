// src/api/session.js
// One session instance for the whole storefront: the axios interceptor and the
// notification WebSocket service must share the SAME single-flight refresh, or
// a WebSocket reconnect and a 401 can rotate the refresh token twice.
//
// The algorithm lives in @ecom/shared/session so the admin panel cannot drift
// from it. Only the storefront-specific redirect is configured here.

import { createSession } from '@ecom/shared/session';

const session = createSession({
  refreshUrl: '/api/v1/auth/refresh',
  logoutUrl: '/login',
  replace: false,
  guardReentry: true,
});

export const { refreshSession, hardLogout } = session;

export default session;

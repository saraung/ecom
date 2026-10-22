/**
 * Single-flight token refresh + hard logout, shared by the storefront and the
 * admin panel.
 *
 * Why single-flight matters: when the access token expires, several requests
 * fail with 401 at the same moment. Firing one /auth/refresh per request with
 * the SAME refresh token makes the backend rotate/revoke it, so every "losing"
 * request fails and the user is logged out. Here all 401s coalesce onto one
 * refresh call and every queued request reuses the token it produced.
 *
 * The two apps differ only in where they redirect to and what they clear, so
 * those are options rather than forks of the same algorithm.
 *
 * This module intentionally has no package imports: it is consumed from
 * `packages/shared`, outside either app's `node_modules`, so a bare `axios`
 * import would not resolve. The refresh call uses `fetch`, and callers may
 * inject another `httpClient` for tests.
 */

const DEFAULT_HTTP_CLIENT = {
  async post(url, body) {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      // Match the shape axios produces so callers can keep checking
      // `error.response.status` (401/403/422 mean "refresh token is dead").
      const error = new Error(`Token refresh failed with status ${response.status}`);
      error.response = { status: response.status, data };
      throw error;
    }

    return { data };
  },
};

const DEFAULTS = {
  refreshUrl: '/api/v1/auth/refresh',
  accessTokenKey: 'access_token',
  refreshTokenKey: 'refresh_token',
  // Extra keys removed on logout (e.g. the admin's cached `user`).
  clearKeys: [],
  // Where to send the browser after a hard logout.
  logoutUrl: '/login',
  // `replace` avoids leaving the expired page in history.
  replace: false,
  // Skip the redirect when already on the login page (prevents reload loops).
  guardReentry: false,
  storage: null,
  httpClient: null,
};

/**
 * @param {object} [options]
 * @param {string} [options.refreshUrl]  Absolute or same-origin refresh endpoint.
 * @param {Storage} [options.storage]    Defaults to `localStorage`.
 * @param {import('axios').AxiosInstance} [options.httpClient]
 *        Client used for the refresh call (defaults to a bare axios instance so
 *        the refresh itself never runs through the 401 interceptor).
 */
export function createSession(options = {}) {
  const config = { ...DEFAULTS, ...options };
  const storage = config.storage || globalThis.localStorage;
  const http = config.httpClient || DEFAULT_HTTP_CLIENT;
  let refreshPromise = null;
  let loggedOut = false;

  const readToken = (key) => {
    const value = storage?.getItem(key);
    // Older privileged logins left the literal string "undefined" in storage.
    return value && value !== 'undefined' && value !== 'null' ? value : null;
  };

  const getAccessToken = () => readToken(config.accessTokenKey);
  const getRefreshToken = () => readToken(config.refreshTokenKey);

  /**
   * Resolves to the new access token, or `null` when there is no usable
   * refresh token (callers treat that as "log out").
   */
  const refreshSession = () => {
    if (refreshPromise) return refreshPromise;

    const refreshToken = getRefreshToken();
    if (!refreshToken) return Promise.resolve(null);

    refreshPromise = http
      .post(config.refreshUrl, { refresh_token: refreshToken })
      .then((response) => {
        // Accept flat ({ access_token }), camelCase ({ accessToken }) and
        // wrapped ({ data: { access_token } }) bodies.
        const body = response.data || {};
        const wrapped = body.data && (body.data.access_token || body.data.accessToken);
        const source = wrapped ? body.data : body;

        const accessToken = source.access_token || source.accessToken || null;
        const nextRefreshToken = source.refresh_token || source.refreshToken || null;

        if (accessToken) storage.setItem(config.accessTokenKey, accessToken);
        // Rotating backends hand back a new refresh token; persist it or the
        // next expiry refreshes with a revoked token.
        if (nextRefreshToken) storage.setItem(config.refreshTokenKey, nextRefreshToken);

        return accessToken;
      })
      .finally(() => {
        refreshPromise = null;
      });

    return refreshPromise;
  };

  const hardLogout = () => {
    if (loggedOut) return;
    loggedOut = true;

    [config.accessTokenKey, config.refreshTokenKey, ...config.clearKeys].forEach((key) => {
      storage?.removeItem(key);
    });

    if (typeof window === 'undefined') return;

    const path = config.logoutUrl.split('?')[0];
    if (config.guardReentry && window.location.pathname === path) return;

    if (config.replace) window.location.replace(config.logoutUrl);
    else window.location.assign(config.logoutUrl);
  };

  return { refreshSession, hardLogout, getAccessToken, getRefreshToken };
}

/**
 * Shared axios client factory: bearer header + one coordinated 401 retry.
 *
 * Both apps previously carried their own copy of this interceptor. Keeping it
 * here means a fix to the refresh contract (e.g. a new auth endpoint shape)
 * only has to be made once.
 *
 * `axios` is injected by the caller: this package sits outside the apps'
 * `node_modules`, so it cannot resolve a bare `axios` import itself.
 */

/** Endpoints that must never trigger a refresh attempt — they ARE the auth flow. */
export const DEFAULT_NO_REFRESH_PATHS = [
  '/auth/login',
  '/auth/register',
  '/auth/google',
  '/auth/refresh',
  '/auth/logout',
];

/** Statuses that prove the refresh token itself is dead (vs. a network blip). */
const DEFINITIVE_REFRESH_FAILURES = [401, 403, 422];

/**
 * @param {object} options
 * @param {import('axios').AxiosStatic} options.axios
 *        The app's axios instance/factory (injected for resolution reasons).
 * @param {string} options.baseURL
 * @param {ReturnType<import('./session.js').createSession>} options.session
 * @param {string[]} [options.noRefreshPaths]
 * @param {Record<string,string>} [options.headers]
 * @returns {import('axios').AxiosInstance}
 */
export function createApiClient({
  axios,
  baseURL,
  session,
  noRefreshPaths = DEFAULT_NO_REFRESH_PATHS,
  headers = {},
} = {}) {
  if (!axios) throw new Error('createApiClient requires the app axios instance');
  if (!baseURL) throw new Error('createApiClient requires a baseURL');
  if (!session) throw new Error('createApiClient requires a session');

  const client = axios.create({
    baseURL,
    headers: { 'Content-Type': 'application/json', ...headers },
  });

  client.interceptors.request.use(
    (config) => {
      const token = session.getAccessToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );

  client.interceptors.response.use(
    (response) => response,

    async (error) => {
      const originalRequest = error.config;
      const url = originalRequest?.url || '';
      const shouldNotRefresh = noRefreshPaths.some((path) => url.startsWith(path));

      if (
        error.response?.status === 401 &&
        originalRequest &&
        !originalRequest._retry &&
        !shouldNotRefresh
      ) {
        originalRequest._retry = true;

        try {
          const accessToken = await session.refreshSession();

          if (!accessToken) {
            session.hardLogout();
            return Promise.reject(error);
          }

          originalRequest.headers.Authorization = `Bearer ${accessToken}`;
          return client(originalRequest);
        } catch (refreshError) {
          // Only a definitive rejection of the refresh token logs the user out;
          // network errors and 5xx must not destroy a valid session.
          if (
            refreshError.response &&
            DEFINITIVE_REFRESH_FAILURES.includes(refreshError.response.status)
          ) {
            session.hardLogout();
          } else if (!session.getRefreshToken()) {
            session.hardLogout();
          }

          return Promise.reject(error);
        }
      }

      return Promise.reject(error);
    }
  );

  return client;
}

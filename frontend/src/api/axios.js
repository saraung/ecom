import axios from 'axios';
import { createApiClient } from '@ecom/shared/http';
import session from './session';

// Bearer header + coordinated 401 retry live in @ecom/shared/http; this module
// only fixes the storefront's base path and exports the configured instance.
// `axios` is injected because the shared package lives outside node_modules.
const api = createApiClient({
  axios,
  baseURL: '/api/v1',
  session,
});

export default api;

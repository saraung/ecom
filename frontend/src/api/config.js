// Single source of truth for the storefront's API origin.
//
// Dev: the browser calls the backend directly at http://localhost:8001; there
// is no Vite proxy any more.
// Prod: set VITE_API_URL at build time, e.g. https://api.example.com/api/v1.
const raw = (
  import.meta.env.VITE_API_URL || 'http://localhost:8001/api/v1'
).replace(/\/+$/, '');

export const API_BASE_URL = raw;

// Absolute origin without the /api/v1 suffix (used for legacy /uploads links
// and the notification WebSocket), even if VITE_API_URL is relative.
const absoluteBase = raw.startsWith('http')
  ? raw
  : `${window.location.origin}${raw}`;

export const API_ORIGIN = absoluteBase.replace(/\/api\/v1\/?$/, '');
export const WS_ORIGIN = API_ORIGIN.replace(/^http/, 'ws');

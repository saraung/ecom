// src/api/settings.js
import apiClient from './client';

// ============ ADMIN: STORE POLICY SETTINGS ============
// Requires settings.manage (admins only). These are the money rules that
// used to live only in env vars — tax, shipping, COD, restocking fees,
// refund window, order expiry. Every save is audited server-side.

/**
 * Current store policy + source ("database" once customized, else env).
 * @returns {Promise}
 */
export const getStoreSettings = () => {
  return apiClient.get('/admin/settings/store');
};

/**
 * Partial update — omitted fields keep their values.
 * tax_rate is a fraction (0.18 = 18%).
 * @param {Object} data
 * @returns {Promise}
 */
export const updateStoreSettings = (data) => {
  return apiClient.put('/admin/settings/store', data);
};

/**
 * Recent settings saves/restores, newest first (requires settings.manage).
 */
export const getStoreSettingsHistory = (limit = 5) => {
  return apiClient.get('/admin/settings/store/history', { params: { limit } });
};

/**
 * Undo one past save identified by its audit entry id. The restore is
 * itself audited, so it can be undone too.
 */
export const restoreStoreSettings = (auditId) => {
  return apiClient.post('/admin/settings/store/restore', { audit_id: auditId });
};

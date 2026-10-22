// src/api/audit.js
import apiClient from './client';

/**
 * Read-only admin audit log viewer (requires reports.view).
 * @param {Object} params - { page, limit, action, entity, actor_id }
 * @returns {Promise} { entries[], total, page, limit, total_pages }
 */
export const getAuditLog = (params) => {
  return apiClient.get('/admin/audit-log', { params });
};

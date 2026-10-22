// src/api/roles.js
import apiClient from './client';

/**
 * List the seeded permission catalog (requires roles.manage or
 * users.manage_roles).
 * @returns {Promise} [{id, key, label, module, description}]
 */
export const getPermissions = () => {
  return apiClient.get('/admin/permissions');
};

/**
 * List all roles with granted permission keys + user counts.
 * @returns {Promise} [{id, name, slug, is_system, permissions[], user_count}]
 */
export const getRoles = () => {
  return apiClient.get('/admin/roles');
};

/**
 * Get a single role.
 * @param {string} roleId - Role ID
 */
export const getRoleById = (roleId) => {
  return apiClient.get(`/admin/roles/${roleId}`);
};

/**
 * Create a custom role from catalog permission keys.
 * @param {Object} data
 * @param {string} data.name - Display name
 * @param {string} [data.slug] - URL-safe slug (auto-derived when omitted)
 * @param {string} [data.description]
 * @param {string[]} data.permission_keys - e.g. ['orders.view']
 */
export const createRole = (data) => {
  return apiClient.post('/admin/roles', data);
};

/**
 * Rename a role and/or REPLACE its permission set.
 * @param {string} roleId - Role ID
 * @param {Object} data - {name?, description?, permission_keys?}
 */
export const updateRole = (roleId, data) => {
  return apiClient.put(`/admin/roles/${roleId}`, data);
};

/**
 * Delete a custom role (system roles and in-use roles are protected).
 * @param {string} roleId - Role ID
 */
export const deleteRole = (roleId) => {
  return apiClient.delete(`/admin/roles/${roleId}`);
};

/**
 * Get a user's assigned role slugs.
 * @param {string} userId - User ID
 */
export const getUserRoles = (userId) => {
  return apiClient.get(`/admin/users/${userId}/roles`);
};

/**
 * REPLACE a user's role set.
 * @param {string} userId - User ID
 * @param {string[]} roleSlugs - e.g. ['manager', 'support']
 */
export const setUserRoles = (userId, roleSlugs) => {
  return apiClient.put(`/admin/users/${userId}/roles`, { role_slugs: roleSlugs });
};

// src/api/invites.js
import apiClient from './client';

/**
 * Invite a staffer by email + role slugs (requires users.manage_roles).
 * @param {Object} data - { email, role_slugs[], full_name? }
 */
export const createInvite = (data) => {
  return apiClient.post('/admin/invites', data);
};

/**
 * List staff invites, newest first (requires users.manage_roles).
 * @param {string} [statusFilter] - pending | accepted | expired | revoked
 */
export const getInvites = (statusFilter) => {
  return apiClient.get('/admin/invites', {
    params: statusFilter ? { status_filter: statusFilter } : undefined,
  });
};

/**
 * Rotate the invite token + expiry and re-send the email.
 * @param {string} inviteId
 */
export const resendInvite = (inviteId) => {
  return apiClient.post(`/admin/invites/${inviteId}/resend`);
};

/**
 * Revoke a pending invite.
 * @param {string} inviteId
 */
export const revokeInvite = (inviteId) => {
  return apiClient.delete(`/admin/invites/${inviteId}`);
};

/**
 * Public pre-check for an invite link: is it live, and for whom?
 * @param {string} token
 */
export const previewInvite = (token) => {
  return apiClient.get('/invites/accept', { params: { token } });
};

/**
 * Accept an invite (public).
 * - New staffer: { token, username, password, full_name? }
 * - Existing account: authenticated call with matching email, omit password fields.
 * @param {Object} data
 */
export const acceptInvite = (data) => {
  return apiClient.post('/invites/accept', data);
};

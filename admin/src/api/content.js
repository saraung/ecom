// src/api/content.js
import apiClient from './client';

// ============ ADMIN: CONTENT BLOCKS ============
// Requires content.manage. Slots are unique keys (e.g. announcement.bar,
// home.hero). Publish windows make campaigns self-expiring.

/**
 * All blocks incl. drafts/disabled/expired, newest first.
 * @returns {Promise} - { items, total, page, limit, total_pages }
 */
export const getContentBlocks = () => {
  return apiClient.get('/admin/content/blocks', { params: { limit: 100 } });
};

/**
 * Single block for the edit page.
 */
export const getContentBlock = (blockId) => {
  return apiClient.get(`/admin/content/blocks/${blockId}`);
};

/**
 * Create a block. Key must be unique (lowercase letters, digits, . _ -).
 */
export const createContentBlock = (data) => {
  return apiClient.post('/admin/content/blocks', data);
};

/**
 * Partial update. Null a window bound to re-open that end.
 */
export const updateContentBlock = (blockId, data) => {
  return apiClient.put(`/admin/content/blocks/${blockId}`, data);
};

/**
 * Delete a block. The slot falls back to hardcoded content (if any).
 */
export const deleteContentBlock = (blockId) => {
  return apiClient.delete(`/admin/content/blocks/${blockId}`);
};

/**
 * Upload a slot image (multipart). Server enforces the per-slot size cap
 * and returns an aspect warning (not an error) on mismatch.
 * @param {string} slot - e.g. 'announcement.bar', 'home.hero.mobile', or 'home.hero.overlay'
 * @param {File} file
 * @returns {Promise} - { url, width, height, size_bytes, aspect_warning }
 */
export const uploadContentImage = (slot, file) => {
  const form = new FormData();
  form.append('file', file);
  return apiClient.post('/admin/content/images', form, {
    params: { slot: slot || '' },
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

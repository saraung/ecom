// src/api/content.js
import api from './axios';

/**
 * Live storefront content blocks keyed by slot.
 * Drafts, disabled and expired blocks are excluded server-side.
 * @param {string[]} [keys] - e.g. ['announcement.bar', 'home.hero']
 * @returns {Promise<Object>} - { announcement.bar: {...}, ... } (missing keys = no live block)
 */
export const getContentBlocks = async (keys) => {
  const params = keys && keys.length ? { keys } : {};
  const response = await api.get('/content/blocks', { params });
  return response.data?.blocks || {};
};

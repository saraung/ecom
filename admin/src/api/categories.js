// src/api/categories.js
import apiClient from './client';

// ============ CATEGORY CRUD ============

/**
 * Create a new category
 * @param {Object} data - Category data
 * @param {string} data.name - Category name
 * @param {string} data.slug - Category slug
 * @param {string} data.parent_id - Parent category ID (optional)
 * @returns {Promise}
 */
export const createCategory = (data) => {
  return apiClient.post('/categories', data);
};

/**
 * Get all categories
 * @param {Object} params - Query parameters
 * @param {number} params.skip - Number of records to skip
 * @param {number} params.limit - Number of records to return
 * @returns {Promise}
 */
export const getCategories = (params = {}) => {
  return apiClient.get('/categories', { params });
};

/**
 * Get category by ID
 * @param {string} categoryId - Category ID
 * @returns {Promise}
 */
export const getCategoryById = (categoryId) => {
  return apiClient.get(`/categories/${categoryId}`);
};

/**
 * Update category
 * @param {string} categoryId - Category ID
 * @param {Object} data - Category data
 * @returns {Promise}
 */
export const updateCategory = (categoryId, data) => {
  return apiClient.put(`/categories/${categoryId}`, data);
};

/**
 * Delete category
 * @param {string} categoryId - Category ID
 * @returns {Promise}
 */
export const deleteCategory = (categoryId) => {
  return apiClient.delete(`/categories/${categoryId}`);
};

/**
 * Upload a category thumbnail to Cloudinary (com/categories/{id}).
 * Sets image_url on the category; previous asset is cleaned up server-side.
 * @param {string} categoryId - Category ID
 * @param {File} file - Image file
 * @returns {Promise<{image_url: string}>}
 */
export const uploadCategoryImage = (categoryId, file) => {
  const form = new FormData();
  form.append('file', file);
  return apiClient.post(`/categories/${categoryId}/image/upload`, form, {
    headers: { 'Content-Type': undefined },
  });
};
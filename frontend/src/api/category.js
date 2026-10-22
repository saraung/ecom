import api from './axios';

export const categoryAPI = {
  // Get all categories
  getCategories: () => api.get('/categories'),
  
  // Get a single category by ID
  getCategory: (categoryId) => api.get(`/categories/${categoryId}`),
};
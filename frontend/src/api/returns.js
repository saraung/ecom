import api from './axios';

export const returnAPI = {
  eligibility: (orderId) => api.get(`/orders/${orderId}/return-eligibility`),
  list: (orderId, page = 1) => api.get('/returns', { params: { order_id: orderId, page, limit: 5 } }),
  create: (orderId, form) => api.post(`/orders/${orderId}/returns`, form, { headers: { 'Content-Type': undefined } }),
  cancel: (returnId) => api.post(`/returns/${returnId}/cancel`, {}),
  tracking: (returnId, data) => api.post(`/returns/${returnId}/tracking`, { ...data, provider: 'manual' }),
  upload: (returnId, files) => {
    const form = new FormData();
    files.forEach((file) => form.append('files', file));
    return api.post(`/returns/${returnId}/evidence`, form, { headers: { 'Content-Type': undefined } });
  },
  evidence: (returnId, evidenceId) => api.get(`/returns/${returnId}/evidence/${evidenceId}`, { responseType: 'blob' }),
};

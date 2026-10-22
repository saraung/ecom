import apiClient from './client';

const path = (id) => `/admin/returns/${id}`;
export const returnAPI = {
  list: (params) => apiClient.get('/admin/returns', { params }),
  detail: (id) => apiClient.get(path(id)),
  decision: (id, data) => apiClient.post(`${path(id)}/decision`, data),
  cancel: (id, data) => apiClient.post(`${path(id)}/cancel`, data),
  tracking: (id, data) => apiClient.post(`${path(id)}/tracking`, data),
  createShipment: (id) => apiClient.post(`${path(id)}/shipping/shiprocket`, {}),
  simulatorShipments: () => apiClient.get('/admin/returns/shipping/simulator/shipments'),
  simulate: (id, data) => apiClient.post(`${path(id)}/shipping/simulator/trigger-event`, data),
  sync: (id) => apiClient.post(`${path(id)}/tracking/sync`, {}),
  receive: (id, data) => apiClient.post(`${path(id)}/receive`, data),
  inspection: (id, data) => apiClient.post(`${path(id)}/inspection`, data),
  refund: (id, data) => apiClient.post(`${path(id)}/refund`, data),
  evidence: (id, evidenceId) => apiClient.get(`${path(id)}/evidence/${evidenceId}`, { responseType: 'blob' }),
};

// src/api/cod.js
// COD reconciliation API. Customer cash collection (Payment) and courier
// remittance (payout batches) are separate backend concepts; these helpers
// never create payments.
import apiClient from './client';

export const getCodSummary = () => apiClient.get('/admin/cod/summary');

export const getCodAwaitingRemittance = (params) =>
  apiClient.get('/admin/cod/awaiting-remittance', { params });

export const getPendingCodOrders = () => apiClient.get('/admin/cod/pending');

export const collectCodBulk = (orderIds) =>
  apiClient.post('/admin/cod/collect-bulk', { order_ids: orderIds });

export const listCodRemittances = (params) =>
  apiClient.get('/admin/cod/remittances', { params });

export const getCodRemittance = (id) =>
  apiClient.get(`/admin/cod/remittances/${id}`);

export const previewCodImport = (file, mapping) => {
  const form = new FormData();
  form.append('file', file);
  if (mapping) form.append('mapping', JSON.stringify(mapping));
  return apiClient.post('/admin/cod/remittances/import/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const importCodRemittance = ({ file, crfId, remittanceDate, mapping, notes }) => {
  const form = new FormData();
  form.append('file', file);
  form.append('crf_id', crfId);
  form.append('remittance_date', remittanceDate);
  if (mapping) form.append('mapping', JSON.stringify(mapping));
  if (notes) form.append('notes', notes);
  return apiClient.post('/admin/cod/remittances/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
};

export const createManualCodRemittance = (payload) =>
  apiClient.post('/admin/cod/remittances', payload);

export const resolveCodRemittanceItem = (id, payload) =>
  apiClient.post(`/admin/cod/remittances/${id}/resolve`, payload);

export const confirmCodRemittance = (id, payload) =>
  apiClient.post(`/admin/cod/remittances/${id}/confirm`, payload);

export const voidCodRemittance = (id, note) =>
  apiClient.post(`/admin/cod/remittances/${id}/void`, null, { params: { note } });

export const simulateCodRemittance = (maxOrders = 5) =>
  apiClient.post('/admin/cod/remittances/simulate', null, { params: { max_orders: maxOrders } });

export const downloadCodTemplate = () =>
  apiClient.get('/admin/cod/remittances/sample-template', { responseType: 'blob' });

export const downloadCodFixture = () =>
  apiClient.get('/admin/cod/remittances/sample-fixture', { responseType: 'blob' });

export const downloadCodRemittance = (id) =>
  apiClient.get(`/admin/cod/remittances/${id}/export`, { responseType: 'blob' });

/** Save an axios blob response with a sensible filename. */
export const saveBlob = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

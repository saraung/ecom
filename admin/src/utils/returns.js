import { canDo } from './permissions.js';

export const RETURN_STATUS_LABELS = {
  requested: 'Requested', approved: 'Approved', rejected: 'Rejected', return_shipped: 'Return shipped',
  received: 'Received', inspection: 'Inspection', refund_pending: 'Refund pending', refunded: 'Refunded', cancelled: 'Cancelled',
};
export const RETURN_REASONS = {
  damaged: 'Damaged product', wrong_product: 'Wrong product received', defective: 'Product defective/not working',
  missing_accessory: 'Missing item/accessory', wrong_variant: 'Wrong size/variant', changed_mind: 'Changed my mind', other: 'Other',
};

// Explicit empty grants are authoritative for this feature; legacy-only sessions
// still use the existing permission helper's role-floor compatibility.
export const hasReturnPermission = (user, key) => Array.isArray(user?.permissions)
  ? user.permissions.includes(key) : canDo(user, key);

export const returnActions = (row, user) => {
  if (!row || !hasReturnPermission(user, 'orders.view')) return [];
  const actions = [];
  if (hasReturnPermission(user, 'orders.update')) {
    if (row.status === 'requested') actions.push('approve', 'reject');
    if (['requested', 'approved'].includes(row.status)) actions.push('cancel');
    if (['approved', 'return_shipped'].includes(row.status)) actions.push('receive');
    if (['received', 'inspection'].includes(row.status)) actions.push('inspection');
    if (hasReturnPermission(user, 'shipping.manage')) {
      if (row.status === 'approved' && (!row.tracking_number || (row.tracking_provider === 'shiprocket' && !row.pickup_requested_at))) {
        actions.push('createShipment');
        if (!row.shipping_requested_at && !row.shiprocket_order_id) actions.push('tracking');
      }
      if (row.tracking_provider === 'shiprocket' && row.tracking_number && !['rejected', 'cancelled', 'refunded'].includes(row.status)) actions.push('sync');
    }
  }
  if (hasReturnPermission(user, 'orders.refund') && row.status === 'inspection' && row.inspection_passed === true && row.received_at) actions.push('refund');
  return actions;
};

export const returnError = (error) => {
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((entry) => entry.msg).join('; ');
  return detail?.message || error.message || 'Could not complete this return action.';
};

export const runReturnAction = async (api, row, user, action, input = {}) => {
  if (!returnActions(row, user).includes(action)) throw new Error('This action is not available at the current return stage or permission level.');
  const note = (input.note || '').trim();
  if (note.length > 1000) throw new Error('Notes must be at most 1000 characters.');
  if (action === 'approve' || action === 'reject') {
    if (action === 'reject' && !note) throw new Error('Enter a rejection note for the customer.');
    return api.decision(row.id, { decision: action, note });
  }
  if (action === 'inspection') {
    if (typeof input.passed !== 'boolean' || !note) throw new Error('Choose an inspection outcome and enter a note.');
    return api.inspection(row.id, { passed: input.passed, note });
  }
  if (action === 'tracking') {
    const tracking = (input.tracking_number || '').trim();
    const courier = (input.courier_name || '').trim();
    if (!/^[A-Za-z0-9][A-Za-z0-9._-]*$/.test(tracking) || tracking.length > 100 || !courier || courier.length > 100) throw new Error('Enter a valid tracking number and courier name.');
    return api.tracking(row.id, { tracking_number: tracking, courier_name: courier, provider: input.provider || 'manual' });
  }
  if (action === 'refund') {
    const reference = (input.manual_transfer_reference || '').trim();
    if (row.payment_method === 'cod' && reference.length < 3) throw new Error('Record the reference of the actual COD repayment.');
    if (row.payment_method !== 'cod' && reference) throw new Error('Online returns refund the original payment.');
    return api.refund(row.id, reference ? { manual_transfer_reference: reference } : {});
  }
  if (action === 'sync') return api.sync(row.id);
  if (action === 'createShipment') return api.createShipment(row.id);
  return api[action](row.id, { note });
};

export const createReturnLoader = ({ load, onStart, onResult, onError }) => {
  let generation = 0;
  return {
    cancel: () => { generation += 1; },
    run: async (params) => {
      const current = ++generation;
      onStart();
      try {
        const response = await load(params);
        if (current === generation) onResult(response.data);
      } catch (error) {
        if (current === generation) onError(error);
      }
    },
  };
};

export const RETURN_SHIPPING_EVENTS = [
  { key: 'picked_up', event: 'picked_up', label: 'Return picked up', status: 'RETURN PICKED UP' },
  { key: 'in_transit', event: 'in_transit', label: 'Return in transit', status: 'RETURN IN TRANSIT' },
  { key: 'out_for_delivery', event: 'out_for_delivery', label: 'Return out for delivery', status: 'RETURN OUT FOR DELIVERY' },
  { key: 'delivered', event: 'delivered', label: 'Return delivered — received only', status: 'RETURN DELIVERED' },
];

export const runReturnSimulatorEvent = (api, row, step, location) => {
  if (row.shipment_type !== 'return' || !row.return_id || !row.awb_code) throw new Error('Select a reverse shipment with its own return AWB.');
  if (!RETURN_SHIPPING_EVENTS.some((event) => event.event === step.event && event.status === step.status)) throw new Error('Outbound RTO is not a customer return event.');
  return api.simulate(row.return_id, { event: step.event, activity: step.status, location });
};

export const loadSimulatorShipments = async ({ loadForward, loadReturns, canViewReturns }) => {
  const [forward, reverse] = await Promise.allSettled([
    Promise.resolve().then(loadForward),
    canViewReturns ? Promise.resolve().then(loadReturns) : Promise.resolve({ data: { shipments: [] } }),
  ]);
  const read = (result, label) => {
    if (result.status === 'rejected') return { shipments: [], provider: '', error: returnError(result.reason) };
    const data = result.value?.data;
    if (!Array.isArray(data?.shipments)) return { shipments: [], provider: '', error: `Invalid ${label} shipment response. Please refresh.` };
    return { shipments: data.shipments, provider: typeof data.provider === 'string' ? data.provider : '', error: null };
  };
  return { forward: read(forward, 'outbound'), reverse: read(reverse, 'return') };
};

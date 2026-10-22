export const RETURN_STATUS_LABELS = {
  requested: 'Requested', approved: 'Approved', rejected: 'Rejected', return_shipped: 'Return shipped',
  received: 'Received', inspection: 'Inspection', refund_pending: 'Refund pending', refunded: 'Refunded', cancelled: 'Cancelled',
};

const trackingMilestone = (status) => {
  const value = String(status || '').trim().toUpperCase();
  if (value.includes('PICKED UP') || value.includes('ORDER PICKED')) return { key: 'picked_up', label: 'Picked up', tone: 'pickup' };
  if (value.includes('IN TRANSIT') || value === 'SHIPPED' || value === 'DISPATCHED') return { key: 'in_transit', label: 'In transit', tone: 'in_transit' };
  if (value.includes('OUT FOR DELIVERY')) return { key: 'out_for_delivery', label: 'Out for delivery', tone: 'in_transit' };
  if (value.includes('DELIVERED')) return { key: 'received', label: 'Received', tone: 'success' };
  return null;
};

const customerHistoryEntry = (entry) => {
  const action = String(entry?.action || '').toLowerCase();
  const status = String(entry?.to_status || '').toLowerCase();
  const providerStatus = entry?.details?.status || '';
  const location = entry?.details?.location || '';
  let milestone;

  if (status === 'requested' || action === 'requested') {
    milestone = { key: 'requested', label: 'Return requested', tone: 'request' };
  } else if (action === 'approved') {
    milestone = { key: 'approved', label: 'Return approved', tone: 'approved' };
  } else if (action === 'pickup_requested') {
    milestone = { key: 'pickup_scheduled', label: 'Pickup scheduled', tone: 'pickup' };
  } else if (status === 'return_shipped' || action === 'return_shipped' || action === 'tracking_scan') {
    milestone = trackingMilestone(providerStatus) || { key: 'in_transit', label: 'Return shipped', tone: 'in_transit' };
  } else if (status === 'received') {
    milestone = { key: 'received', label: 'Received', tone: 'success' };
  } else if (status === 'inspection') {
    milestone = { key: 'inspection', label: 'Inspection completed', tone: 'success' };
  } else if (status === 'refund_pending') {
    milestone = { key: 'refund_pending', label: 'Refund processing', tone: 'refund' };
  } else if (status === 'refunded') {
    milestone = { key: 'refunded', label: 'Refund completed', tone: 'success' };
  } else if (status === 'rejected') {
    milestone = { key: 'rejected', label: 'Return rejected', tone: 'neutral' };
  } else if (status === 'cancelled') {
    milestone = { key: 'cancelled', label: 'Return cancelled', tone: 'neutral' };
  }

  if (!milestone) return null;
  return {
    ...milestone,
    created_at: entry.created_at,
    note: entry.note || '',
    location,
  };
};

// The API keeps every audit event. Customer UI gets meaningful milestones,
// while duplicate provider scans and internal booking checkpoints are folded
// into the adjacent milestone.
export const buildCustomerReturnHistory = (history = []) => {
  const result = [];
  for (const entry of Array.isArray(history) ? history : []) {
    const milestone = customerHistoryEntry(entry);
    if (!milestone) continue;
    const previous = result.at(-1);
    if (previous?.key === milestone.key) {
      result[result.length - 1] = {
        ...previous,
        ...milestone,
        note: milestone.note || previous.note,
      };
    } else {
      result.push(milestone);
    }
  }
  return result;
};

export const returnError = (error) => {
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((entry) => entry.msg).join('; ');
  return error.message || 'Could not complete the return action. Please retry.';
};

export const validateReturnFiles = (files, policy, existingCount = 0) => {
  if (files.length + existingCount > policy.max_images) throw new Error(`Select at most ${policy.max_images} images in total.`);
  for (const file of files) {
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) throw new Error('Use JPEG, PNG or WebP photos.');
    if (file.size > policy.max_image_bytes) throw new Error('One of the photos exceeds the image size limit.');
  }
};

export const buildReturnPayload = ({ eligibility, quantities, reason, description, files, key }) => {
  if (!eligibility?.eligible) throw new Error('No eligible items are available for return.');
  if (!eligibility.reasons.some((choice) => choice.value === reason)) throw new Error('Choose a return reason.');
  const items = Object.entries(quantities).map(([id, value]) => {
    const quantity = Number(value);
    const item = eligibility.items.find((entry) => entry.order_item_id === id);
    if (!item?.eligible || !Number.isInteger(quantity) || quantity < 1 || quantity > item.available_quantity) {
      throw new Error('Select valid quantities from the available purchased items.');
    }
    return { order_item_id: id, quantity };
  });
  if (!items.length) throw new Error('Select at least one item to return.');
  const details = description.trim();
  if (reason === 'other' && details.length < 10) throw new Error('Please explain Other in at least 10 characters.');
  if (details.length > 2000) throw new Error('Details must be at most 2000 characters.');
  validateReturnFiles(files, eligibility.policy);
  if (eligibility.policy.required_photo_reasons.includes(reason) && !files.length) throw new Error('A photo is required for this reason by the return policy.');
  return { idempotency_key: key, reason, description: details, items };
};

export const estimateReturn = (eligibility, quantities) => {
  const cents = (eligibility?.items || []).reduce((sum, item) => {
    const quantity = Number(quantities[item.order_item_id] || 0);
    if (!item.eligible || !Number.isInteger(quantity) || quantity < 1 || quantity > item.available_quantity) return sum;
    return sum + Math.floor(Math.round(Number(item.remaining_merchandise_amount) * 100) * quantity / item.available_quantity);
  }, 0);
  const fee = Math.round(cents * (eligibility?.policy.fee_percent || 0) / 100);
  return { amount: (cents - fee) / 100, fee: fee / 100 };
};

export const loadReturnWorkspace = async (api, orderId, page) => {
  const [eligibility, listing] = await Promise.all([api.eligibility(orderId), api.list(orderId, page)]);
  return { eligibility: eligibility.data, listing: listing.data };
};

export const createReturnWorkspaceLoader = ({ api, onStart, onResult, onError }) => {
  let generation = 0;
  return {
    cancel: () => { generation += 1; },
    run: async (orderId, page, silent = false) => {
      const current = ++generation;
      onStart(silent);
      try {
        const result = await loadReturnWorkspace(api, orderId, page);
        if (current === generation) onResult(result);
      } catch (error) {
        if (current === generation) onError(error);
      }
    },
  };
};

// Coalesce accidental parallel clicks; a network retry keeps the form's stable key.
export const createReturnSubmitter = (api) => {
  let inFlight = null;
  return (orderId, payload, files) => {
    if (inFlight) return inFlight;
    const form = new FormData();
    form.append('data', JSON.stringify(payload));
    files.forEach((file) => form.append('files', file));
    inFlight = Promise.resolve().then(() => api.create(orderId, form)).finally(() => { inFlight = null; });
    return inFlight;
  };
};

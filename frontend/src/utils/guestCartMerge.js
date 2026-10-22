// Persist the request identity before sending; remove only acknowledged quantities.
const newMergeKey = () => {
  if (globalThis.crypto.randomUUID) return globalThis.crypto.randomUUID();
  const bytes = globalThis.crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

export const createGuestCartMerger = ({ storage, addItem, newKey = newMergeKey }) => {
  let inFlight = null;
  const read = () => {
    const items = JSON.parse(storage.getItem('cart') || '[]');
    if (!Array.isArray(items)) throw new Error('Saved guest cart is not an array');
    return items;
  };
  const write = (items) => {
    if (items.length) storage.setItem('cart', JSON.stringify(items));
    else storage.removeItem('cart');
  };
  const run = async () => {
    const entries = read().map((item) => ({ ...item,
      mergeKey: item.mergeKey || newKey(),
      mergeQuantity: item.mergeQuantity ?? Number(item.quantity || 1),
    }));
    write(entries);
    let syncedCount = 0;
    const failed = [];
    for (const item of entries) {
      const variantId = item.variant?.id || item.variant_id || item.id;
      try {
        if (!variantId) throw new Error('Guest item has no variant');
        await addItem({ variant_id: variantId, quantity: item.mergeQuantity, merge_key: item.mergeKey });
        // Re-read to preserve additions made while this request was in flight.
        write(read().flatMap((current) => {
          if (current.mergeKey !== item.mergeKey) return [current];
          const remaining = Number(current.quantity || 1) - item.mergeQuantity;
          if (remaining <= 0) return [];
          return [{ ...current, quantity: remaining, mergeKey: newKey(), mergeQuantity: remaining }];
        }));
        syncedCount++;
      } catch (error) {
        failed.push({ item, error });
      }
    }
    return { syncedCount, failed, remaining: read() };
  };
  return () => {
    if (!inFlight) {
      // Web Locks serialize multiple tabs where supported; server receipts also
      // protect retries in browsers without this API.
      const locks = globalThis.navigator?.locks;
      inFlight = Promise.resolve().then(() => locks
        ? locks.request('ecommerce-guest-cart-merge', run) : run())
        .finally(() => { inFlight = null; });
    }
    return inFlight;
  };
};

// src/utils/region.js
// Single-currency-per-deployment regionalization (admin side).
//
// The backend owns the truth: public GET /checkout/config returns
// { currency, locale, tax_label, country }. Every money/date/tax render
// reads the cache below via utils/format.js — never a hardcoded ₹/en-IN.
// Defaults mirror an INR deployment so first paint matches legacy output.

let region = {
  currency: 'INR',
  locale: 'en-IN',
  taxLabel: 'GST',
  country: 'India',
};
let loaded = false;
let promise = null;
const listeners = new Set();

const notify = () => {
  listeners.forEach((fn) => {
    try {
      fn();
    } catch {
      // Listener errors must never break formatting.
    }
  });
};

export const getRegion = () => region;

export const setRegion = (patch = {}) => {
  region = {
    currency: patch.currency || region.currency,
    locale: patch.locale || region.locale,
    taxLabel: patch.tax_label || patch.taxLabel || region.taxLabel,
    country: patch.country || region.country,
  };
  notify();
  return region;
};

export const subscribeRegion = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

/**
 * Fetch once (public endpoint — no permission needed). Resolves to the
 * region, keeping INR defaults on failure.
 */
export const loadRegion = async (apiClient) => {
  if (loaded) return region;
  if (!promise) {
    promise = apiClient
      .get('/checkout/config')
      .then((res) => {
        setRegion(res.data || {});
        loaded = true;
        return region;
      })
      .catch(() => {
        loaded = true;
        return region;
      });
  }
  return promise;
};

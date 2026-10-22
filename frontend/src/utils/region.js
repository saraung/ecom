// src/utils/region.js
// Single-currency-per-deployment regionalization (storefront side).
//
// The backend owns the truth: GET /checkout/config returns
// { currency, locale, tax_label, country }. Everything that renders money,
// dates, tax names or the home country reads the cache below — never a
// hardcoded ₹/en-IN/GST. Defaults mirror an INR deployment so the first
// paint (before the config arrives) matches today's behavior.
import { checkoutAPI } from '../api/checkout';

let region = {
  currency: 'INR',
  locale: 'en-IN',
  taxLabel: 'GST',
  country: 'India',
  supportPhone: '',
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
  const next = {
    currency: patch.currency || region.currency,
    locale: patch.locale || region.locale,
    taxLabel: patch.tax_label || patch.taxLabel || region.taxLabel,
    country: patch.country || region.country,
    supportPhone: patch.support_phone || patch.supportPhone || region.supportPhone,
  };
  region = next;
  notify();
  return next;
};

export const subscribeRegion = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

/** Fetch once; resolves to the region (defaults on failure). */
export const loadRegion = () => {
  if (loaded) return Promise.resolve(region);
  if (!promise) {
    promise = checkoutAPI
      .getConfig()
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

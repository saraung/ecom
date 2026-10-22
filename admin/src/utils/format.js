// src/utils/format.js
// Shared money/number/date formatters — the ONLY place currency, locale
// and compact-notation live in the admin panel. Every page imports from
// here instead of hardcoding 'en-IN' / currency:'INR' / ₹ / Cr-L-K.
//
// The implementation lives in @ecom/shared/format (shared with the
// storefront); this wrapper binds it to the admin's region store.

import { getRegion } from './region';
import { createFormatters } from '@ecom/shared/format';

export const {
  formatPrice,
  formatShort,
  formatNumber,
  currencySymbol,
  taxLabel,
  storeCountry,
  formatDate,
  formatDay,
} = createFormatters(getRegion);

/**
 * Regionalised formatters shared by the storefront and the admin panel.
 *
 * The backend owns currency/locale (`GET /checkout/config`). Each app injects
 * its own region store getter, so this module stays free of app imports while
 * both apps render money and dates identically.
 */

/**
 * @param {() => { currency?: string, locale?: string, taxLabel?: string, country?: string }} getRegion
 */
export function createFormatters(getRegion) {
  const opts = () => {
    const region = getRegion() || {};
    return { currency: region.currency || 'INR', locale: region.locale || 'en-IN' };
  };

  /**
   * Full money value, e.g. ₹1,234.00. Pass `{ decimals: 0 }` for whole-unit
   * displays (KPI cards, counts-style prices).
   */
  const formatPrice = (value, { decimals = 2 } = {}) => {
    const { currency, locale } = opts();
    const amount = Number(value || 0);

    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }).format(amount);
    } catch {
      // Unknown currency code: fall back to a code-prefixed amount.
      return `${currency} ${amount.toFixed(decimals)}`;
    }
  };

  /** Compact money for charts/KPI cards, e.g. ₹1.2L / €1.2M. */
  const formatShort = (value) => {
    const { currency, locale } = opts();
    const amount = Number(value || 0);

    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
        notation: 'compact',
        maximumFractionDigits: 1,
      }).format(amount);
    } catch {
      return `${currency} ${amount.toFixed(0)}`;
    }
  };

  /** Plain grouped number (counts, quantities). */
  const formatNumber = (value) => {
    const { locale } = opts();
    try {
      return new Intl.NumberFormat(locale).format(Number(value || 0));
    } catch {
      return String(Number(value || 0));
    }
  };

  /** Currency symbol for labels like "Free shipping above (₹)". */
  const currencySymbol = () => {
    const { currency, locale } = opts();
    try {
      const parts = new Intl.NumberFormat(locale, {
        style: 'currency',
        currency,
      }).formatToParts(0);
      return (parts.find((part) => part.type === 'currency') || {}).value || currency;
    } catch {
      return currency;
    }
  };

  /** Customer-facing tax name: GST for INR deployments, VAT elsewhere. */
  const taxLabel = () => getRegion()?.taxLabel || 'GST';

  /** Store home country for address defaults. */
  const storeCountry = () => getRegion()?.country || 'India';

  /** Date only, e.g. 03 Mar 2026. */
  const formatDate = (value, options) => {
    if (!value) return '—';
    const { locale } = opts();

    try {
      return new Date(value).toLocaleDateString(
        locale,
        options || { day: '2-digit', month: 'short', year: 'numeric' }
      );
    } catch {
      return new Date(value).toLocaleDateString();
    }
  };

  /** Date + time, e.g. 3 Mar 2026, 14:05. */
  const formatDateTime = (value, options = {}) => {
    if (!value) return '—';
    const { locale } = opts();

    return new Date(value).toLocaleString(options.locale || locale, {
      day: 'numeric',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  /**
   * Short weekday date, e.g. "Mon, 3 Mar".
   * When the caller supplies options they are used verbatim (chart axes ask for
   * only `{ weekday: 'short' }`); with no options the shopper-facing default is
   * used. The legacy `{ year: true }` flag is still honoured.
   */
  const formatDay = (value, options) => {
    if (!value) return '—';
    const { locale } = opts();
    const dateOptions =
      options && Object.keys(options).length
        ? { ...options, ...(options.year === true ? { year: 'numeric' } : {}) }
        : { weekday: 'short', day: 'numeric', month: 'short' };

    try {
      return new Date(value).toLocaleDateString(locale, dateOptions);
    } catch {
      return new Date(value).toLocaleDateString();
    }
  };

  return {
    formatPrice,
    formatShort,
    formatNumber,
    currencySymbol,
    taxLabel,
    storeCountry,
    formatDate,
    formatDateTime,
    formatDay,
  };
}

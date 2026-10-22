// src/components/charts/TopProductsChart.jsx
//
// Ranked "Top Products" widget for the admin dashboard.
//
// Why a ranked list instead of a bar chart: with only a handful of products a
// vertical bar chart forces rotated/overlapping category labels and reads
// poorly. The layout below is the ecommerce-dashboard convention (Shopify,
// Stripe, Amazon Seller): rank + thumbnail + name + units, the revenue figure
// right-aligned, and a horizontal bar proportional to revenue as the visual
// ranking cue.
import React, { useState } from 'react';
import { ImageOff } from 'lucide-react';
import { formatShort, formatNumber } from '../../utils/format';

// Locale-aware compact money (lakh/crore under en-IN, K/M under en-US).
const formatCurrency = (value) => formatShort(value);

const TopProductsChart = ({ products = [], max = 4 }) => {
  // Keyed by image URL rather than product id: a broken URL stays hidden even
  // after the list is reordered or the date range changes, so no effect is
  // needed to reset this state when the data changes.
  const [failedImages, setFailedImages] = useState(() => new Set());

  const top = Array.isArray(products) ? products.slice(0, max) : [];
  if (top.length === 0) return null;

  // Bars are relative to the best seller, so rank #1 is always full width.
  const maxRevenue = Math.max(...top.map((p) => Number(p?.revenue) || 0), 0);

  return (
    <div className="space-y-3 sm:space-y-4">
      {top.map((product, index) => {
        const revenue = Number(product?.revenue) || 0;
        const units = Number(product?.units_sold) || 0;
        const barWidth = maxRevenue > 0 ? Math.max((revenue / maxRevenue) * 100, 3) : 0;

        const imageUrl = product?.image_url || product?.image || null;
        const imageKey = product?.product_id ?? `idx-${index}`;
        const showImage = Boolean(imageUrl) && !failedImages.has(imageUrl);

        return (
          <div key={imageKey}>
            <div className="flex items-center gap-3">
              {/* Rank */}
              <span
                className={`w-4 flex-shrink-0 text-center text-xs font-semibold tabular-nums ${
                  index === 0 ? 'text-primary' : 'text-muted-foreground'
                }`}
              >
                {index + 1}
              </span>

              {/* Thumbnail (graceful placeholder when the product has no image) */}
              {showImage ? (
                <img
                  src={imageUrl}
                  alt={product.product_name}
                  loading="lazy"
                  onError={() =>
                    setFailedImages((prev) => new Set(prev).add(imageUrl))
                  }
                  className="w-11 h-11 flex-shrink-0 rounded-lg border border-border object-cover bg-muted"
                />
              ) : (
                <div className="w-11 h-11 flex-shrink-0 rounded-lg border border-border bg-muted flex items-center justify-center">
                  <ImageOff size={16} className="text-muted-foreground" />
                </div>
              )}

              {/* Name, units, revenue */}
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-3">
                  <p
                    className="min-w-0 truncate text-sm font-medium text-foreground"
                    title={product?.product_name}
                  >
                    {product?.product_name || 'Unknown product'}
                  </p>
                  <p className="flex-shrink-0 text-sm font-semibold tabular-nums text-foreground">
                    {formatCurrency(revenue)}
                  </p>
                </div>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {formatNumber(units)} {units === 1 ? 'unit' : 'units'} sold
                </p>
              </div>
            </div>

            {/* Proportional ranking bar (mount sweep via .animate-bar-fill;
                width transition covers in-place updates) */}
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-500 ease-out animate-bar-fill"
                style={{ width: `${barWidth}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default TopProductsChart;

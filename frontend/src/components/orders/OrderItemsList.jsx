import React from 'react';
import { Link } from 'react-router-dom';
import { formatPrice } from '../../utils/format';

// Order items are variant snapshots — name, SKU, and variant_attributes are
// always present. product_image and product_slug are OPTIONAL: they are
// resolved live by the API from item -> variant -> product, so this component
// must render correctly whether or not they exist (image_url is accepted as a
// legacy alias).
//
//   props:
//     items    — order.items array (defensive: null/undefined renders the empty note)
//     maxItems — limit rows and show "+ N more item(s)" (used by the list card preview)
//     showSku  — also render the variant SKU line (used by the order detail page)

const PLACEHOLDER_IMG =
  'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64"%3E%3Crect width="64" height="64" fill="%23F1EFE9"/%3E%3C/svg%3E';

const OrderItemsList = ({ items, maxItems, showSku = false }) => {
  const list = Array.isArray(items) ? items : [];
  const previewItems = maxItems ? list.slice(0, maxItems) : list;
  const hiddenCount = list.length - previewItems.length;

  if (list.length === 0) {
    return <p className="text-sm text-muted-foreground">No items on this order</p>;
  }

  return (
    <div className="space-y-3">
      {previewItems.map((item) => {
        const hasLink = Boolean(item.product_slug);

        const row = (
          <div className="flex items-start gap-3 text-sm">
            <img
              src={item.product_image || item.image_url || PLACEHOLDER_IMG}
              alt=""
              className="w-12 h-12 rounded-xl object-cover bg-primary-soft border border-border/70 shrink-0"
              onError={(e) => { e.target.src = PLACEHOLDER_IMG; }}
            />
            <div className="flex-1 min-w-0 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className={`font-medium text-foreground truncate ${hasLink ? 'group-hover:underline' : ''}`}>
                  {item.product_name}
                </p>
                {showSku && item.variant_sku && (
                  <p className="text-xs text-muted-foreground mt-0.5">SKU: {item.variant_sku}</p>
                )}
                <div className="flex flex-wrap items-center gap-2 mt-0.5">
                  <span className="text-muted-foreground">
                    Qty {item.quantity} × {formatPrice(item.unit_price)}
                  </span>
                  {item.variant_attributes &&
                    Object.entries(item.variant_attributes).map(([key, value]) => (
                      <span
                        key={key}
                        className="text-xs bg-primary-soft text-muted-foreground px-2 py-0.5 rounded-full capitalize"
                      >
                        {key}: <span className="font-medium">{String(value)}</span>
                      </span>
                    ))}
                </div>
              </div>
              <span className="font-medium text-foreground whitespace-nowrap">
                {formatPrice(item.line_total)}
              </span>
            </div>
          </div>
        );

        return hasLink ? (
          <Link
            key={item.id}
            to={`/products/${item.product_slug}`}
            className="group block -mx-1 px-1 py-0.5 hover:bg-primary-soft/50 transition-colors rounded-xl"
          >
            {row}
          </Link>
        ) : (
          <div key={item.id}>{row}</div>
        );
      })}
      {hiddenCount > 0 && (
        <p className="text-xs text-muted-foreground font-medium">
          + {hiddenCount} more item{hiddenCount > 1 ? 's' : ''}
        </p>
      )}
    </div>
  );
};

export default OrderItemsList;
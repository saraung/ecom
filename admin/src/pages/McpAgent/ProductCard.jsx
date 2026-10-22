// src/pages/McpAgent/ProductCard.jsx
// Product card(s) attached to an assistant reply (backend-sourced only).
// Single product → inline card; several → snap carousel capped by the
// backend (MAX_PRODUCT_CARDS=4). Thumb + name + price + stock + one CTA,
// matching the chat-card pattern (image mandatory, ≤2 metadata lines).
import React, { useState } from 'react';
import { Image as ImageIcon } from 'lucide-react';
import { formatPrice } from '../../utils/format';

const MAX_CAROUSEL = 4;

const stockBadge = (card) => {
  if (card.is_active === false) return { label: 'Inactive', cls: 'badge-danger' };
  if (card.stock == null) return null;
  const stock = Number(card.stock);
  if (stock <= 0) return { label: 'Out of stock', cls: 'badge-danger' };
  if (stock <= 5) return { label: `${stock} left`, cls: 'badge-warning' };
  return { label: `${stock} in stock`, cls: 'badge-success' };
};

const CardThumb = ({ card }) => {
  const [failed, setFailed] = useState(false);
  if (!card.image_url || failed) {
    return (
      <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-lg bg-muted border border-border flex items-center justify-center shrink-0">
        <ImageIcon size={22} className="text-muted-foreground" />
      </div>
    );
  }
  return (
    <img
      src={card.image_url}
      alt={card.name || 'Product image'}
      loading="lazy"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      className="w-20 h-20 sm:w-24 sm:h-24 rounded-lg border border-border object-cover shrink-0"
    />
  );
};

const ProductCard = ({ card, onView }) => {
  const badge = stockBadge(card);
  const clickable = !!(card.slug && onView);
  return (
    <div
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={clickable ? () => onView(card.slug) : undefined}
      onKeyDown={clickable ? (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onView(card.slug);
        }
      } : undefined}
      title={clickable ? `View ${card.name || 'product'}` : undefined}
      className={`flex items-center gap-3 p-2.5 rounded-xl border border-border bg-card min-w-0 ${
        clickable ? 'cursor-pointer hover:bg-muted transition-colors' : ''
      }`}
    >
      <CardThumb card={card} />
      <div className="flex-1 min-w-0">
        <p className="font-medium text-sm text-foreground truncate">{card.name || 'Product'}</p>
        <p className="text-sm text-muted-foreground mt-0.5">
          {card.price != null ? formatPrice(card.price) : '—'}
        </p>
        {badge && (
          <span className={`badge ${badge.cls} mt-1 inline-block`}>{badge.label}</span>
        )}
      </div>
    </div>
  );
};

const ProductCards = ({ cards, onView }) => {
  if (!Array.isArray(cards) || cards.length === 0) return null;
  const shown = cards.slice(0, MAX_CAROUSEL);
  if (shown.length === 1) {
    return (
      <div className="mt-2.5 max-w-sm">
        <ProductCard card={shown[0]} onView={onView} />
      </div>
    );
  }
  return (
    <div className="mt-2.5 flex gap-2 overflow-x-auto snap-x pb-1 -mx-1 px-1">
      {shown.map((card) => (
        <div key={card.id || card.slug || card.name} className="w-56 sm:w-64 shrink-0 snap-start">
          <ProductCard card={card} onView={onView} />
        </div>
      ))}
    </div>
  );
};

export default ProductCards;

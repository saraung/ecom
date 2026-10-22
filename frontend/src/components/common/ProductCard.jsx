import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../../api/axios';
import { useCart } from '../../hooks/useCart';
import { formatPrice } from '../../utils/format';
import WishlistButton from './WishlistButton';

const PLACEHOLDER_IMG =
  'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="300" height="300" viewBox="0 0 300 300"%3E%3Crect width="300" height="300" fill="%23f4f4f5"/%3E%3Ctext x="50%25" y="50%25" font-family="Arial" font-size="16" font-weight="bold" fill="%23a1a1aa" text-anchor="middle" dy=".3em"%3EProduct Image%3C/text%3E%3C/svg%3E';

const ProductCard = ({ product, showQuickAdd = true, className = '' }) => {
  const { addToCart } = useCart();
  const [status, setStatus] = useState('idle'); // idle | adding | added

  const getProductImage = () =>
    product.images && product.images.length > 0 ? product.images[0].url : null;

  const handleQuickAddToCart = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (status === 'adding') return;

    let productToUse = product;
    let variant = product.variants && product.variants.length > 0 ? product.variants[0] : null;

    // Wishlist items come from a summary API that omits variants, so fetch the
    // full product to obtain a real variant id for cart insertion.
    if (!variant) {
      try {
        const res = await api.get(`/products/${product.slug || product.id}`);
        productToUse = res.data;
        variant =
          productToUse.variants && productToUse.variants.length > 0
            ? productToUse.variants[0]
            : null;
      } catch (err) {
        console.error('Error fetching product for quick add:', err);
      }
    }

    const variantId = variant?.id || productToUse.id;

    setStatus('adding');
    const cartItem = {
      id: productToUse.id,
      name: productToUse.name,
      price: parseFloat(variant?.effective_price || productToUse.price),
      slug: productToUse.slug,
      quantity: 1,
      variant: variant || null,
      variant_id: variantId,
      image: productToUse.images?.[0]?.url || null,
    };

    const result = await addToCart(cartItem);
    if (result.success) {
      setStatus('added');
      setTimeout(() => setStatus('idle'), 2500);
    } else {
      setStatus('idle');
    }
  };

  const imageUrl = getProductImage();
  const discount = product.discount_percentage || 0;
  const isInStock = product.is_active !== false;
  const avgRating = Number(product.average_rating) || 0;

  return (
    <div className={`group relative w-full rounded-[2rem] bg-card p-4 transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)] hover:-translate-y-2 hover:shadow-[0_30px_60px_rgba(0,0,0,0.08)] dark:hover:shadow-[0_30px_60px_rgba(0,0,0,0.4)] border border-border ${className}`}>
      
      {/* Floating Wishlist Button */}
      <div className="absolute top-5 right-5 z-20">
        <div className="bg-card/90 backdrop-blur-md rounded-full shadow-lg shadow-black/[0.06] dark:shadow-black/40 border border-border/80 flex items-center justify-center">
          <WishlistButton product={product} size="sm" />
        </div>
      </div>

      <Link to={`/products/${product.slug}`} className="block relative focus:outline-none">
        <div className="relative aspect-[4/5] overflow-hidden rounded-2xl bg-primary-soft">
          <img
            src={imageUrl || PLACEHOLDER_IMG}
            alt={product.name}
            loading="lazy"
            className={`h-full w-full object-cover transition-transform duration-700 ease-out group-hover:scale-110 ${!isInStock ? 'grayscale opacity-70' : ''}`}
            onError={(e) => {
              e.target.src = PLACEHOLDER_IMG;
            }}
          />

          {/* Premium Gradient Overlay on Hover for Text Contrast */}
          <div className="absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100 pointer-events-none" />

          {/* Floating Tags */}
          <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 pointer-events-none">
            {discount > 0 && (
              <span className="bg-primary/90 backdrop-blur-md text-primary-foreground text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-full shadow-xl">
                {discount}% Off
              </span>
            )}
            {!isInStock && (
              <span className="bg-destructive/90 backdrop-blur-md text-white text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-full shadow-xl">
                Sold Out
              </span>
            )}
          </div>

          {/* Quick Add Button (Still hover-only for desktop to keep image clean) */}
          {showQuickAdd && isInStock && (
            <button
              type="button"
              onClick={handleQuickAddToCart}
              disabled={status === 'adding'}
              aria-label={`Add ${product.name} to cart`}
              className="absolute bottom-4 left-1/2 w-[90%] -translate-x-1/2 translate-y-8 opacity-0
                         group-hover:translate-y-0 group-hover:opacity-100
                         focus-visible:translate-y-0 focus-visible:opacity-100
                         transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)]
                         bg-card/95 backdrop-blur-xl text-foreground text-xs font-bold tracking-widest uppercase
                         py-3.5 rounded-full shadow-lg border border-border/50
                         hover:bg-primary hover:text-primary-foreground
                         focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-primary
                         disabled:opacity-70 disabled:cursor-not-allowed z-20"
            >
              {status === 'adding' ? 'Adding...' : status === 'added' ? 'Added' : 'Quick Add'}
            </button>
          )}
        </div>
      </Link>

      {/* Product Meta */}
      <div className="pt-6 pb-2 px-2">
        <div className="flex justify-between items-start gap-4 mb-2">
          <Link
            to={`/products/${product.slug}`}
            className="block focus-visible:outline focus-visible:outline-offset-2 focus-visible:outline-primary flex-1 min-w-0"
          >
            <h3 className="truncate text-lg font-bold text-foreground tracking-tight transition-colors group-hover:text-foreground/60">
              {product.name}
            </h3>
          </Link>
          
          <div className="flex items-center gap-1 shrink-0 mt-1">
            <span className="text-warning text-sm leading-none" aria-hidden="true">★</span>
            <span className="text-xs font-bold text-foreground">
              {avgRating > 0 ? avgRating.toFixed(1) : 'New'}
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-xl font-bold text-foreground whitespace-nowrap tracking-tight">
            {formatPrice(product.price)}
          </span>
          {product.compare_at_price && (
            <span className="text-sm font-medium text-muted-foreground line-through whitespace-nowrap">
              {formatPrice(product.compare_at_price)}
            </span>
          )}
        </div>

        {product.is_on_sale && product.savings_amount && (
          <p className="mt-2 text-xs font-bold uppercase tracking-wider text-success">
            Save {formatPrice(product.savings_amount)}
          </p>
        )}
      </div>

      {/* Premium Toast Notification (Pill style) */}
      <div 
        className={`fixed bottom-8 left-1/2 -translate-x-1/2 z-50 transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)] ${
          status === 'added' ? 'translate-y-0 opacity-100 scale-100' : 'translate-y-10 opacity-0 scale-95 pointer-events-none'
        }`}
      >
        <div className="bg-primary/95 backdrop-blur-md text-primary-foreground px-6 py-3 rounded-full shadow-2xl flex items-center gap-3 border border-border">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-card text-foreground text-xs font-bold">✓</span>
          <span className="text-sm font-bold tracking-wide">Added to bag</span>
        </div>
      </div>
    </div>
  );
};

export default ProductCard;
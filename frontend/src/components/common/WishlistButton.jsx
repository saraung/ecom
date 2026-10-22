import React, { useState } from 'react';
import { Heart } from 'lucide-react';
import { useWishlist } from '../../hooks/useWishlist';

const WishlistButton = ({ product, size = 'sm' }) => {
  const { isInWishlist, addToWishlist, removeFromWishlist } = useWishlist();
  const [loading, setLoading] = useState(false);

  const inWishlist = isInWishlist(product.id);

  const sizeMap = {
    sm: 'w-8 h-8',
    md: 'w-9 h-9',
    lg: 'w-11 h-11',
  };

  const handleToggle = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setLoading(true);

    if (inWishlist) {
      await removeFromWishlist(product.id);
    } else {
      await addToWishlist(product);
    }

    setLoading(false);
  };

  return (
    <button
      onClick={handleToggle}
      disabled={loading}
      className={`${sizeMap[size]} flex items-center justify-center rounded-full transition-all duration-300 ease-out cursor-pointer hover:scale-110 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed`}
      aria-label={inWishlist ? 'Remove from wishlist' : 'Add to wishlist'}
    >
      {loading ? (
        <span className="w-3.5 h-3.5 border-2 border-border border-t-foreground rounded-full animate-spin" />
      ) : (
        <Heart
          size={size === 'sm' ? 15 : size === 'md' ? 17 : 19}
          strokeWidth={1.8}
          aria-hidden="true"
          className={`transition-all duration-300 ${
            inWishlist
              ? 'fill-destructive stroke-destructive scale-110'
              : 'fill-none stroke-muted-foreground hover:stroke-destructive/70'
          }`}
        />
      )}
    </button>
  );
};

export default WishlistButton;
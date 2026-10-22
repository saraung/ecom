import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useWishlist } from '../../hooks/useWishlist';
import { useAuth } from '../../hooks/useAuth';
import ProductCard from '../../components/common/ProductCard';

const Wishlist = () => {
  const { wishlist, loading, loadWishlist } = useWishlist();
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);

  useEffect(() => {
    loadWishlist();
  }, []);

  useEffect(() => {
    if (!isAuthenticated && !loading && wishlist.length === 0) {
      const timer = setTimeout(() => {
        setShowLoginPrompt(true);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [isAuthenticated, loading, wishlist.length]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background transition-colors duration-700">
        <div className="flex flex-col items-center gap-4">
          <div className="h-12 w-12 rounded-full border-[3px] border-border border-t-foreground animate-spin" />
          <p className="text-muted-foreground font-medium tracking-wide text-sm uppercase">
            Loading your wishlist
          </p>
        </div>
      </div>
    );
  }

  if (!wishlist || wishlist.length === 0) {
    return (
      <div className="flex-1 bg-background transition-colors duration-700 px-4 py-12 sm:py-16 flex flex-col items-center">
        <div className="my-auto text-center p-8 sm:p-10 bg-card rounded-[2rem] sm:rounded-[2.5rem] shadow-sm border border-border max-w-md w-full">
          <div className="text-5xl sm:text-6xl mb-6" aria-hidden="true">❤️</div>
          <h2 className="text-xl sm:text-2xl font-extrabold text-foreground mb-2 tracking-tight">
            Your wishlist is empty
          </h2>
          <p className="text-sm text-muted-foreground mb-8 font-medium">
            Start saving your favorite items.
          </p>

          {!isAuthenticated && showLoginPrompt && (
            <div className="mb-8 p-4 sm:p-5 bg-background rounded-2xl border border-border">
              <p className="text-sm text-muted-foreground">
                🔒 <span className="font-medium">Want to keep your wishlist forever?</span>
                <br />
                <span className="text-xs">Login to save it safely across devices.</span>
              </p>
              <button
                onClick={() => navigate('/login', { state: { from: '/wishlist' } })}
                className="mt-4 bg-primary text-primary-foreground px-8 py-3 rounded-full text-xs font-bold uppercase tracking-widest hover:scale-105 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl"
              >
                Login to Save
              </button>
            </div>
          )}

          <Link
            to="/products"
            className="inline-block bg-primary text-primary-foreground px-10 py-4 rounded-full text-sm font-bold uppercase tracking-widest hover:scale-105 hover:-translate-y-0.5 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl"
          >
            Browse Products
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-7xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        <div className="mb-8 sm:mb-10 border-b border-border pb-6 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
          <div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">
              My Wishlist
            </h1>
            <p className="text-sm text-muted-foreground font-medium mt-2">
              Your saved favorites, ready when you are.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="inline-flex items-center h-9 px-4 rounded-full bg-primary-soft text-primary text-xs font-bold uppercase tracking-widest whitespace-nowrap">
              {wishlist.length} {wishlist.length === 1 ? 'item' : 'items'}
            </span>

            {!isAuthenticated && (
              <button
                onClick={() => navigate('/login', { state: { from: '/wishlist' } })}
                className="inline-flex items-center h-9 px-4 rounded-full text-xs font-bold uppercase tracking-widest border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors whitespace-nowrap"
              >
                🔒 Login to Save
              </button>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 xs:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 sm:gap-4 md:gap-6">
          {wishlist.map((product) => (
            <ProductCard key={product.id} product={product} showQuickAdd={true} />
          ))}
        </div>
      </div>
    </div>
  );
};

export default Wishlist;
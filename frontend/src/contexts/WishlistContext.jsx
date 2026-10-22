import React, { createContext, useState, useEffect } from 'react';
import { wishlistAPI } from '../api/wishlist';

export const WishlistContext = createContext();

export const WishlistProvider = ({ children }) => {
  const [wishlist, setWishlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [wishlistIds, setWishlistIds] = useState(new Set());

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    if (token) {
      loadWishlist();
    } else {
      loadLocalWishlist();
    }
  }, []);

  // Listen for auth changes
  useEffect(() => {
    const handleAuthChange = () => {
      const token = localStorage.getItem('access_token');
      if (token) {
        syncWishlistToDatabase();
      } else {
        loadLocalWishlist();
      }
    };
    
    window.addEventListener('authChanged', handleAuthChange);
    return () => window.removeEventListener('authChanged', handleAuthChange);
  }, []);

  const loadLocalWishlist = () => {
    const localWishlist = JSON.parse(localStorage.getItem('wishlist') || '[]');
    setWishlist(localWishlist);
    setWishlistIds(new Set(localWishlist.map(item => item.id)));
    setLoading(false);
  };

  const loadWishlist = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('access_token');
      if (!token) {
        loadLocalWishlist();
        return;
      }

      const response = await wishlistAPI.getWishlist();
      
      const items = response.data.items || [];
      
      // ✅ Normalize database items to match product structure expected by ProductCard
      const normalizedItems = items.map(item => ({
        id: item.product_id || item.id,
        name: item.product_name || 'Product',
        price: parseFloat(item.product_price) || 0,
        slug: item.product_slug || '',
        description: item.product_description || '',
        images: item.product_image ? [{ url: item.product_image }] : [],
        discount_percentage: item.discount_percentage || 0,
        compare_at_price: item.compare_at_price || null,
        is_active: true,
        is_on_sale: item.is_on_sale || false,
        savings_amount: item.savings_amount || null,
        variants: item.variants || [],
        // Keep the original data for reference
        _original: item
      }));
      
      
      setWishlist(normalizedItems);
      setWishlistIds(new Set(normalizedItems.map(item => item.id)));
    } catch (error) {
      console.error('Error loading wishlist:', error);
      loadLocalWishlist();
    } finally {
      setLoading(false);
    }
  };

  const syncWishlistToDatabase = async () => {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    const localWishlist = JSON.parse(localStorage.getItem('wishlist') || '[]');
    if (localWishlist.length === 0) {
      await loadWishlist();
      return;
    }

    try {
      for (const item of localWishlist) {
        await wishlistAPI.addToWishlist(item.id);
      }
      localStorage.removeItem('wishlist');
      await loadWishlist();
      window.dispatchEvent(new Event('wishlistUpdated'));
    } catch (error) {
      console.error('Error syncing wishlist:', error);
      await loadWishlist();
    }
  };

  const addToWishlist = async (product) => {
    const token = localStorage.getItem('access_token');

    if (!token) {
      // Guest - save to localStorage
      const localWishlist = JSON.parse(localStorage.getItem('wishlist') || '[]');
      const exists = localWishlist.some(item => item.id === product.id);
      
      if (!exists) {
        localWishlist.push(product);
        localStorage.setItem('wishlist', JSON.stringify(localWishlist));
        setWishlist(localWishlist);
        setWishlistIds(new Set(localWishlist.map(item => item.id)));
        return { success: true, message: 'Added to wishlist!' };
      }
      return { success: false, message: 'Already in wishlist' };
    }

    // Logged in - save to database
    try {
      await wishlistAPI.addToWishlist(product.id);
      await loadWishlist();
      window.dispatchEvent(new Event('wishlistUpdated'));
      return { success: true, message: 'Added to wishlist!' };
    } catch (error) {
      console.error('Error adding to wishlist:', error);
      if (error.response) {
        console.error('Error response:', error.response.data);
        console.error('Error status:', error.response.status);
      }
      return { success: false, message: 'Failed to add to wishlist' };
    }
  };

  const removeFromWishlist = async (productId) => {
    const token = localStorage.getItem('access_token');

    if (!token) {
      // Guest - remove from localStorage
      const localWishlist = JSON.parse(localStorage.getItem('wishlist') || '[]');
      const updatedWishlist = localWishlist.filter(item => item.id !== productId);
      localStorage.setItem('wishlist', JSON.stringify(updatedWishlist));
      setWishlist(updatedWishlist);
      setWishlistIds(new Set(updatedWishlist.map(item => item.id)));
      return { success: true };
    }

    // Logged in - remove from database
    try {
      await wishlistAPI.removeFromWishlist(productId);
      await loadWishlist();
      window.dispatchEvent(new Event('wishlistUpdated'));
      return { success: true };
    } catch (error) {
      console.error('Error removing from wishlist:', error);
      if (error.response) {
        console.error('Error response:', error.response.data);
        console.error('Error status:', error.response.status);
      }
      return { success: false };
    }
  };

  const isInWishlist = (productId) => {
    return wishlistIds.has(productId);
  };

  const getWishlist = () => wishlist;
  const getWishlistCount = () => wishlist.length;

  return (
    <WishlistContext.Provider value={{
      wishlist,
      loading,
      addToWishlist,
      removeFromWishlist,
      isInWishlist,
      getWishlist,
      getWishlistCount,
      loadWishlist,
      syncWishlistToDatabase,
    }}>
      {children}
    </WishlistContext.Provider>
  );
};
import React, { createContext, useState, useEffect } from 'react';
import api from '../api/axios';
import toast from 'react-hot-toast';
import { createGuestCartMerger } from '../utils/guestCartMerge';

export const CartContext = createContext();

export const CartProvider = ({ children }) => {
  const [mergeGuestCart] = useState(() => createGuestCartMerger({
    storage: localStorage,
    addItem: (payload) => api.post('/cart/items', payload),
  }));
  const [cart, setCart] = useState([]);
  const [loading, setLoading] = useState(true);
  const [itemCount, setItemCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [isUserLoggedIn, setIsUserLoggedIn] = useState(false);
  const [couponCode, setCouponCode] = useState(null);
  const [automaticCoupon, setAutomaticCoupon] = useState(null);

  // Backend cart summary values
  const [subtotal, setSubtotal] = useState(0);
  const [discountTotal, setDiscountTotal] = useState(0);
  const [taxTotal, setTaxTotal] = useState(0);
  const [shippingTotal, setShippingTotal] = useState(0);

  // ============================================================
  // INITIAL AUTH CHECK
  // ============================================================

  useEffect(() => {
    const token = localStorage.getItem('access_token');

    setIsUserLoggedIn(!!token);
  }, []);

  // ============================================================
  // AUTH CHANGE LISTENER
  // ============================================================

  useEffect(() => {
    const handleAuthChange = () => {
      const newToken = localStorage.getItem('access_token');

      setIsUserLoggedIn(!!newToken);

      if (newToken) {
        setTimeout(() => {
          syncCartToDatabase();
        }, 100);
      } else {
        loadCart();
      }
    };

    window.addEventListener('authChanged', handleAuthChange);

    return () => {
      window.removeEventListener('authChanged', handleAuthChange);
    };
  }, []);

  // ============================================================
  // LOAD CART WHEN LOGIN STATUS CHANGES
  // ============================================================

  useEffect(() => {
    loadCart();
  }, [isUserLoggedIn]);

  // ============================================================
  // LOAD CART
  // Backend route:
  // GET /cart
  // ============================================================

  const loadCart = async () => {
    setLoading(true);

    try {
      const token = localStorage.getItem('access_token');

      // --------------------------------------------------------
      // LOGGED-IN USER
      // --------------------------------------------------------

      if (token) {
        // IMPORTANT:
        // Backend is @router.get("")
        // Therefore use /cart, NOT /cart/
        const response = await api.get('/cart');

        let cartItems = [];

        if (
          response.data &&
          response.data.items
        ) {
          cartItems = response.data.items.map(
            (item) => ({
              cartItemId: item.id,

              id:
                item.variant_id ||
                item.id,

              name:
                item.product_name ||
                'Product',

              price:
                parseFloat(
                  item.price_at_add ||
                  item.price ||
                  0
                ),

              quantity:
                parseInt(item.quantity) || 1,

              image:
                item.product_image ||
                null,

              variant: {
                id: item.variant_id,

                sku:
                  item.variant_sku ||
                  '',

                attributes:
                  item.variant_attributes ||
                  {},
              },

              variant_id:
                item.variant_id,

              slug:
                item.product_slug ||
                null,

              attributes:
                item.variant_attributes ||
                {},
            })
          );
        } else if (
          Array.isArray(response.data)
        ) {
          cartItems = response.data;
        }

        setCart(cartItems);

        // ------------------------------------------------------
        // COUPON
        // ------------------------------------------------------

        setCouponCode(
          response.data?.coupon_code || null
        );

        // Server-decided automatic coupon - display only, never evaluated
        // or removed client-side.
        setAutomaticCoupon(
          response.data?.automatic_coupon || null
        );

        // ------------------------------------------------------
        // BACKEND TOTALS
        // ------------------------------------------------------

        setSubtotal(
          parseFloat(
            response.data?.subtotal
          ) || 0
        );

        setDiscountTotal(
          parseFloat(
            response.data?.discount_total
          ) || 0
        );

        setTaxTotal(
          parseFloat(
            response.data?.tax_total
          ) || 0
        );

        setShippingTotal(
          parseFloat(
            response.data?.shipping_total
          ) || 0
        );

        // ------------------------------------------------------
        // ITEM COUNT + TOTAL
        // ------------------------------------------------------

        if (response.data) {
          const count =
            parseInt(
              response.data.item_count
            ) ||
            cartItems.reduce(
              (sum, item) =>
                sum +
                (parseInt(item.quantity) || 0),
              0
            );

          setItemCount(count);

          const totalAmount =
            parseFloat(
              response.data.total
            ) || 0;

          setTotal(totalAmount);

        } else {
          updateTotals();
        }
      }

      // --------------------------------------------------------
      // GUEST USER
      // --------------------------------------------------------

      else {
        const localCart = JSON.parse(
          localStorage.getItem('cart') ||
            '[]'
        );

        setCart(localCart);

        setCouponCode(null);

        setAutomaticCoupon(null);

        setDiscountTotal(0);
        setTaxTotal(0);
        setShippingTotal(0);

        setSubtotal(
          localCart.reduce(
            (sum, item) =>
              sum +
              (parseFloat(item.price) || 0) *
                (parseInt(item.quantity) || 0),
            0
          )
        );

        updateTotals();
      }
    } catch (error) {
      console.error(
        '❌ Error loading cart:',
        error
      );

      // Fall back to local cart
      const localCart = JSON.parse(
        localStorage.getItem('cart') ||
          '[]'
      );

      setCart(localCart);

      setCouponCode(null);

      setAutomaticCoupon(null);

      setDiscountTotal(0);
      setTaxTotal(0);
      setShippingTotal(0);

      setSubtotal(
        localCart.reduce(
          (sum, item) =>
            sum +
            (parseFloat(item.price) || 0) *
              (parseInt(item.quantity) || 0),
          0
        )
      );

      updateTotals();
    } finally {
      setLoading(false);
    }
  };

  // ============================================================
  // UPDATE LOCAL CART TOTALS
  // ============================================================

  const updateTotals = () => {
    const count = cart.reduce(
      (sum, item) => {
        const qty =
          parseInt(item.quantity) || 0;

        return sum + qty;
      },
      0
    );

    const totalPrice = cart.reduce(
      (sum, item) => {
        const price =
          parseFloat(item.price) || 0;

        const qty =
          parseInt(item.quantity) || 0;

        return sum + price * qty;
      },
      0
    );

    setItemCount(count);
    setTotal(totalPrice);
    setSubtotal(totalPrice);

    setDiscountTotal(0);
    setTaxTotal(0);
    setShippingTotal(0);
  };

  // ============================================================
  // SYNC LOCAL CART → DATABASE
  // Backend route:
  // POST /cart/items
  // ============================================================

  const syncCartToDatabase = async () => {
    const token =
      localStorage.getItem('access_token');

    if (!token) {
      return;
    }

    try {
      const result = await mergeGuestCart();
      if (result.failed.length) {
        toast.error(`${result.failed.length} guest cart item(s) could not be added and remain saved for retry.`);
      }

      await loadCart();

      window.dispatchEvent(
        new Event('cartUpdated')
      );
    } catch (error) {
      toast.error('Your guest cart could not be merged. Its saved items have been kept.');
      console.error(
        '❌ Error in sync process:',
        error
      );

      if (error.response) {
        console.error(
          '❌ Error response data:',
          JSON.stringify(
            error.response.data,
            null,
            2
          )
        );

        console.error(
          '❌ Error response status:',
          error.response.status
        );
      }

      await loadCart();
    }
  };

  // ============================================================
  // ADD TO CART
  // Backend route:
  // POST /cart/items
  // ============================================================

  const addToCart = async (item) => {
    const token =
      localStorage.getItem('access_token');

    let variantId = null;

    if (item.variant?.id) {
      variantId = item.variant.id;
    } else if (item.variant_id) {
      variantId = item.variant_id;
    } else if (item.id) {
      variantId = item.id;
    }

    if (!variantId) {
      console.error(
        '❌ No variant_id found for item:',
        item
      );

      return {
        success: false,
        message:
          'Invalid product: no variant ID',
      };
    }

    // ----------------------------------------------------------
    // GUEST CART
    // ----------------------------------------------------------

    if (!token) {
      const existingCart =
        JSON.parse(
          localStorage.getItem('cart') ||
            '[]'
        );

      const existingIndex =
        existingCart.findIndex(
          (existing) =>
            existing.id === item.id &&
            existing.variant_id === variantId
        );

      const cartItem = {
        ...item,
        variant_id: variantId,
      };

      if (existingIndex > -1) {
        existingCart[
          existingIndex
        ].quantity += item.quantity;
      } else {
        existingCart.push(cartItem);
      }

      localStorage.setItem(
        'cart',
        JSON.stringify(existingCart)
      );

      setCart(existingCart);

      updateTotals();

      return {
        success: true,
        message: 'Added to cart!',
      };
    }

    // ----------------------------------------------------------
    // LOGGED-IN CART
    // ----------------------------------------------------------

    try {
      const payload = {
        variant_id: variantId,
        quantity: item.quantity || 1,
      };

      // Backend: @router.post("/items")
      await api.post(
        '/cart/items',
        payload
      );

      await loadCart();

      return {
        success: true,
        message: 'Added to cart!',
      };
    } catch (error) {
      console.error(
        '❌ Error adding to cart:',
        error
      );

      if (error.response) {
        console.error(
          '❌ Error response data:',
          JSON.stringify(
            error.response.data,
            null,
            2
          )
        );

        console.error(
          '❌ Error response status:',
          error.response.status
        );
      }

      return {
        success: false,
        message:
          'Failed to add to cart',
      };
    }
  };

  // ============================================================
  // UPDATE QUANTITY
  // Backend route:
  // PUT /cart/items/{item_id}
  // ============================================================

  const updateQuantity = async (
    itemId,
    variantId,
    quantity
  ) => {
    const token =
      localStorage.getItem('access_token');

    if (token) {
      try {
        const payload = {
          quantity,
        };

        // Backend: @router.put("/items/{item_id}")
        await api.put(
          `/cart/items/${itemId}`,
          payload
        );

        await loadCart();
      } catch (error) {
        console.error(
          '❌ Error updating cart:',
          error
        );

        if (error.response) {
          console.error(
            '❌ Error response:',
            error.response.data
          );
        }
      }
    } else {
      const existingCart =
        JSON.parse(
          localStorage.getItem('cart') ||
            '[]'
        );

      const itemIndex =
        existingCart.findIndex(
          (item) =>
            item.id === itemId &&
            (
              item.variant?.id === variantId ||
              item.variant_id === variantId
            )
        );

      if (itemIndex > -1) {
        if (quantity <= 0) {
          existingCart.splice(
            itemIndex,
            1
          );
        } else {
          existingCart[
            itemIndex
          ].quantity = quantity;
        }

        localStorage.setItem(
          'cart',
          JSON.stringify(existingCart)
        );

        setCart(existingCart);

        updateTotals();
      }
    }
  };

  // ============================================================
  // REMOVE FROM CART
  // Backend route:
  // DELETE /cart/items/{item_id}
  // ============================================================

  const removeFromCart = async (
    itemId,
    variantId
  ) => {
    const token =
      localStorage.getItem('access_token');

    if (token) {
      try {
        // Backend: @router.delete("/items/{item_id}")
        await api.delete(
          `/cart/items/${itemId}`
        );

        await loadCart();
      } catch (error) {
        console.error(
          '❌ Error removing from cart:',
          error
        );

        if (error.response) {
          console.error(
            '❌ Error response:',
            error.response.data
          );
        }
      }
    } else {
      const existingCart =
        JSON.parse(
          localStorage.getItem('cart') ||
            '[]'
        );

      const newCart =
        existingCart.filter(
          (item) =>
            !(
              item.id === itemId &&
              (
                item.variant?.id === variantId ||
                item.variant_id === variantId
              )
            )
        );

      localStorage.setItem(
        'cart',
        JSON.stringify(newCart)
      );

      setCart(newCart);

      updateTotals();
    }
  };

  // ============================================================
  // CLEAR CART
  // Backend route:
  // DELETE /cart
  // ============================================================

  const clearCart = async () => {
    const token =
      localStorage.getItem('access_token');

    if (token) {
      try {
        // Backend: @router.delete("")
        await api.delete('/cart');

        await loadCart();
      } catch (error) {
        console.error(
          '❌ Error clearing cart:',
          error
        );
      }
    } else {
      localStorage.removeItem('cart');

      setCart([]);

      setCouponCode(null);

      setAutomaticCoupon(null);

      setDiscountTotal(0);
      setTaxTotal(0);
      setShippingTotal(0);
      setSubtotal(0);
      setItemCount(0);
      setTotal(0);
    }
  };

  // ============================================================
  // APPLY COUPON
  // Backend route:
  // POST /cart/coupon
  // ============================================================

  const applyCoupon = async (code) => {
    const token =
      localStorage.getItem('access_token');

    if (!token) {
      return {
        success: false,
        message:
          'Please login to apply coupons',
      };
    }

    try {
      // Backend: @router.post("/coupon")
      const response =
        await api.post(
          '/cart/coupon',
          {
            coupon_code: code,
          }
        );

      await loadCart();

      return {
        success: true,
        data: response.data,
      };
    } catch (error) {
      console.error(
        '❌ Error applying coupon:',
        error
      );

      let message =
        'Failed to apply coupon';

      if (error.response?.data?.detail) {
        message =
          error.response.data.detail;
      }

      return {
        success: false,
        message,
      };
    }
  };

  // ============================================================
  // REMOVE COUPON
  // Backend route:
  // DELETE /cart/coupon
  // ============================================================

  const removeCoupon = async () => {
    const token =
      localStorage.getItem('access_token');

    if (!token) {
      return {
        success: false,
        message:
          'Please login to remove coupons',
      };
    }

    try {
      // Backend: @router.delete("/coupon")
      await api.delete(
        '/cart/coupon'
      );

      await loadCart();

      return {
        success: true,
      };
    } catch (error) {
      console.error(
        '❌ Error removing coupon:',
        error
      );

      return {
        success: false,
        message:
          'Failed to remove coupon',
      };
    }
  };

  // ============================================================
  // HELPERS
  // ============================================================

  const getTotal = () => total;

  const getItemCount = () => itemCount;

  // ============================================================
  // REFRESH CART
  // ============================================================

  const refreshCart = () => {
    const token =
      localStorage.getItem('access_token');

    setIsUserLoggedIn(!!token);

    loadCart();
  };

  // ============================================================
  // FORCE SYNC
  // ============================================================

  const forceSync = async () => {
    const token =
      localStorage.getItem('access_token');

    if (token) {
      setIsUserLoggedIn(true);

      await syncCartToDatabase();
    } else {
      setIsUserLoggedIn(false);

      await loadCart();
    }
  };

  // ============================================================
  // PROVIDER
  // ============================================================

  return (
    <CartContext.Provider
      value={{
        cart,
        loading,
        itemCount,
        total,

        // Backend cart summary
        subtotal,
        discountTotal,
        taxTotal,
        shippingTotal,

        couponCode,
        automaticCoupon,

        addToCart,
        updateQuantity,
        removeFromCart,
        clearCart,

        syncCartToDatabase,
        loadCart,
        refreshCart,
        forceSync,

        applyCoupon,
        removeCoupon,

        getTotal,
        getItemCount,
      }}
    >
      {children}
    </CartContext.Provider>
  );
};

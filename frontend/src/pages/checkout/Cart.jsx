import React, { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCart } from '../../hooks/useCart';
import { useAuth } from '../../hooks/useAuth';
import { useModalA11y } from '../../hooks/useModalA11y';
import { couponAPI } from '../../api/coupons';
import toast from 'react-hot-toast';
import { formatPrice } from '../../utils/format';

const Cart = () => {
  const { 
    cart, 
    itemCount, 
    subtotal: cartSubtotal,
    discountTotal: cartDiscount,
    taxTotal: cartTax,
    shippingTotal: cartShipping,
    total: cartTotal,
    updateQuantity, 
    removeFromCart, 
    loading, 
    loadCart,
    clearCart,
    applyCoupon,
    removeCoupon,
    couponCode,
    automaticCoupon
  } = useCart();
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [couponInput, setCouponInput] = useState('');
  const [couponError, setCouponError] = useState('');
  const [couponSuccess, setCouponSuccess] = useState('');
  const [appliedCoupon, setAppliedCoupon] = useState(null);
  const [applyingCoupon, setApplyingCoupon] = useState(false);

  // Escape closes, focus trapped/restored, scroll locked while the sign-in prompt is open.
  const loginDialogRef = useModalA11y(() => setShowLoginModal(false), showLoginModal);

  const subtotal = Number(cartSubtotal) || 0;
  const discountTotal = Number(cartDiscount) || 0;
  const taxTotal = Number(cartTax) || 0;
  const shippingTotal = Number(cartShipping) || 0;
  const finalTotal = Number(cartTotal) || 0;
  const hasDiscount = discountTotal > 0;
  const isFreeShipping = shippingTotal === 0;

  useEffect(() => {
    const handleCartUpdate = () => {
      loadCart();
    };
    window.addEventListener('cartUpdated', handleCartUpdate);
    return () => window.removeEventListener('cartUpdated', handleCartUpdate);
  }, []);

  useEffect(() => {
    if (couponCode) {
      setAppliedCoupon({ code: couponCode });
      setCouponSuccess(`Coupon ${couponCode} applied!`);
      setCouponInput(couponCode);
    } else {
      setAppliedCoupon(null);
      setCouponSuccess('');
      setCouponInput('');
    }
  }, [couponCode]);

  const handleUpdateQuantity = (item, newQuantity) => {
    if (newQuantity < 1) return;
    const itemId = item.cartItemId || item.id;
    const variantId = item.variant_id || item.variant?.id;
    updateQuantity(itemId, variantId, newQuantity);
  };

  const handleRemoveItem = (item) => {
    const itemId = item.cartItemId || item.id;
    const variantId = item.variant_id || item.variant?.id;
    removeFromCart(itemId, variantId);
  };

  const handleCheckout = () => {
    if (!isAuthenticated) {
      setShowLoginModal(true);
      return;
    }
    navigate('/checkout');
  };

  const handleLoginRedirect = () => {
    setShowLoginModal(false);
    localStorage.setItem('redirectAfterLogin', '/checkout');
    navigate('/login', { state: { from: '/checkout' } });
  };

  const handleClearCart = async () => {
    if (window.confirm('Are you sure you want to empty your bag?')) {
      await clearCart();
      setAppliedCoupon(null);
      setCouponSuccess('');
      setCouponInput('');
    }
  };

  const handleApplyCoupon = async () => {
    setCouponError('');
    setCouponSuccess('');
    if (!couponInput.trim()) {
      setCouponError('Please enter a coupon code');
      return;
    }
    if (appliedCoupon) {
      setCouponError('Coupon already applied');
      return;
    }
    if (!isAuthenticated) {
      setCouponError('Please sign in to apply coupons');
      return;
    }
    try {
      setApplyingCoupon(true);
      const validateResponse = await couponAPI.validateCoupon(couponInput.trim());
      if (!validateResponse.data.valid) {
        setCouponError(validateResponse.data.message || 'Invalid coupon code');
        return;
      }
      const applyResponse = await applyCoupon(couponInput.trim());
      if (applyResponse.success) {
        setAppliedCoupon({ 
          code: couponInput.trim(),
          discount_type: validateResponse.data.discount_type,
          value: validateResponse.data.value,
        });
        setCouponSuccess(`Code ${couponInput.trim()} applied successfully!`);
        setCouponError('');
        toast.success(`Coupon ${couponInput.trim()} applied!`);
      } else {
        setCouponError(applyResponse.message || 'Failed to apply coupon');
      }
    } catch (error) {
      console.error('Error applying coupon:', error);
      setCouponError('Failed to apply coupon');
      toast.error('Failed to apply coupon');
    } finally {
      setApplyingCoupon(false);
    }
  };

  const handleRemoveCoupon = async () => {
    try {
      const response = await removeCoupon();
      if (response.success) {
        setAppliedCoupon(null);
        setCouponSuccess('');
        setCouponInput('');
        toast.success('Coupon removed');
      } else {
        toast.error(response.message || 'Failed to remove coupon');
      }
    } catch (error) {
      console.error('Error removing coupon:', error);
      toast.error('Failed to remove coupon');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background transition-colors duration-700">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 rounded-full border-[3px] border-border border-t-primary animate-spin" />
          <p className="text-muted-foreground font-medium tracking-wide text-xs uppercase">Loading Bag</p>
        </div>
      </div>
    );
  }

  if (!cart || cart.length === 0) {
    return (
      <div className="flex-1 bg-background transition-colors duration-700 py-12 sm:py-16 px-4 flex flex-col items-center">
        <div className="my-auto text-center p-8 sm:p-10 bg-card rounded-[2rem] sm:rounded-[2.5rem] shadow-sm border border-border max-w-md w-full">
          <div className="text-5xl sm:text-6xl mb-6">🛍️</div>
          <h2 className="text-xl sm:text-2xl font-extrabold text-foreground mb-2 tracking-tight">Your bag is empty</h2>
          <p className="text-sm text-muted-foreground mb-8 font-medium">Looks like you haven't added any premium pieces yet.</p>
          <Link 
            to="/products" 
            className="w-full block bg-primary text-primary-foreground px-6 sm:px-8 py-4 rounded-full font-bold uppercase tracking-widest text-xs sm:text-sm hover:scale-105 transition-all duration-300 shadow-xl"
          >
            Start Shopping
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background min-h-screen selection:bg-primary selection:text-primary-foreground transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">

        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6 sm:mb-10 border-b border-border pb-6">
          <div>
            <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">Review your bag.</h1>
            <p className="text-muted-foreground font-medium mt-2 text-sm">
              {itemCount} {itemCount === 1 ? 'item' : 'items'} curated for you
            </p>
          </div>
          <button 
            onClick={handleClearCart} 
            className="text-xs font-bold uppercase tracking-widest text-destructive hover:text-destructive transition-colors self-start sm:self-auto"
          >
            Clear Bag
          </button>
        </div>

        <div className="flex flex-col lg:flex-row gap-8 lg:gap-10 items-start">

          {/* Cart Items List */}
          <div className="w-full lg:w-3/5 flex flex-col gap-4 sm:gap-5">
            {cart.map((item, index) => (
              <div 
                key={index} 
                className="group flex items-start sm:items-stretch gap-4 sm:gap-6 p-4 sm:p-6 rounded-[1.5rem] sm:rounded-[2rem] bg-card border border-border shadow-sm hover:shadow-[0_15px_30px_rgba(0,0,0,0.04)] dark:hover:shadow-[0_15px_30px_rgba(0,0,0,0.4)] transition-all duration-300"
              >
                {/* Image */}
                <div className="w-24 h-24 sm:w-32 sm:h-32 rounded-xl sm:rounded-2xl bg-primary-soft flex items-center justify-center shrink-0 overflow-hidden border border-border/50">
                  {item.image ? (
                    <img src={item.image} alt={item.name} className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 ease-out" onError={(e) => e.target.style.display = 'none'} />
                  ) : (
                    <span className="text-2xl sm:text-3xl text-muted-foreground">🛍️</span>
                  )}
                </div>

                {/* Item Details */}
                <div className="flex flex-col justify-between flex-1 min-w-0">
                  
                  {/* Top Row: Title, Price, Close Button */}
                  <div className="flex justify-between items-start gap-3">
                    <div className="flex flex-col min-w-0">
                      <Link to={`/products/${item.slug || ''}`} className="block text-base sm:text-lg font-bold text-foreground hover:text-muted-foreground transition-colors truncate">
                        {item.name}
                      </Link>
                      <p className="text-sm sm:text-lg font-extrabold text-foreground mt-0.5 sm:mt-1">
                        {formatPrice(item.price)}
                      </p>
                    </div>

                    <button 
                      onClick={() => handleRemoveItem(item)} 
                      className="w-8 h-8 rounded-full bg-primary-soft text-muted-foreground hover:bg-destructive-soft hover:text-destructive flex items-center justify-center transition-colors shrink-0 -mt-1 -mr-1 sm:mt-0 sm:mr-0"
                      aria-label="Remove item"
                    >
                      ✕
                    </button>
                  </div>

                  {/* Variant Attributes */}
                  {(item.variant?.sku || (item.variant?.attributes && Object.keys(item.variant.attributes).length > 0)) && (
                    <div className="mt-2 flex flex-wrap gap-1.5 sm:gap-2">
                      {item.variant?.sku && (
                        <span className="text-[9px] sm:text-[10px] font-bold uppercase tracking-wider bg-primary-soft text-muted-foreground px-2 py-1 rounded-md shrink-0">
                          SKU: {item.variant.sku}
                        </span>
                      )}
                      {item.variant?.attributes && Object.entries(item.variant.attributes).map(([key, value]) => (
                        <span key={key} className="text-[9px] sm:text-[10px] font-bold uppercase tracking-wider bg-primary-soft text-muted-foreground px-2 py-1 rounded-md shrink-0">
                          {value}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Quantity & Item Total */}
                  <div className="flex flex-wrap items-center justify-between gap-3 mt-4 sm:mt-6">
                    <div className="flex items-center bg-primary-soft border border-border rounded-full h-9 sm:h-10 w-24 sm:w-28 shrink-0">
                      <button 
                        onClick={() => handleUpdateQuantity(item, (item.quantity || 1) - 1)} 
                        disabled={item.quantity <= 1}
                        className="w-8 sm:w-10 h-full flex items-center justify-center text-muted-foreground hover:text-foreground disabled:opacity-50 transition-colors text-base sm:text-lg"
                      >−</button>
                      <span className="flex-1 text-center text-sm font-bold text-foreground">{item.quantity}</span>
                      <button 
                        onClick={() => handleUpdateQuantity(item, (item.quantity || 1) + 1)} 
                        className="w-8 sm:w-10 h-full flex items-center justify-center text-muted-foreground hover:text-foreground transition-colors text-base sm:text-lg"
                      >+</button>
                    </div>

                    {(item.quantity || 1) > 1 && (
                      <p className="text-xs sm:text-sm font-bold text-foreground text-right">
                        Total: {formatPrice((item.price || 0) * (item.quantity || 1))}
                      </p>
                    )}
                  </div>

                </div>
              </div>
            ))}
          </div>

          {/* Order Summary (Sticky) */}
          <div className="w-full lg:w-2/5 lg:sticky lg:top-24">
            <div className="bg-card rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-8 border border-border shadow-sm">
              <h3 className="text-xl font-extrabold text-foreground mb-6 tracking-tight">Order Summary</h3>

              {/* Coupon Section */}
              <div className="mb-6 sm:mb-8 p-4 bg-primary-soft/50 rounded-2xl border border-border">
                <div className="flex gap-2">
                  <input
                    type="text"
                    placeholder="Promo code"
                    value={couponInput}
                    onChange={(e) => setCouponInput(e.target.value.toUpperCase())}
                    disabled={!!appliedCoupon || applyingCoupon || !isAuthenticated}
                    className="flex-1 min-w-0 bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground disabled:opacity-60"
                  />
                  <button
                    onClick={handleApplyCoupon}
                    disabled={!!appliedCoupon || applyingCoupon || !isAuthenticated}
                    className="shrink-0 bg-primary text-primary-foreground rounded-xl px-4 sm:px-6 font-bold text-xs tracking-widest uppercase hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {applyingCoupon ? '...' : 'Apply'}
                  </button>
                </div>
                {automaticCoupon && (
                  <div className="flex justify-between items-center mt-3 bg-success-soft p-2.5 rounded-lg border border-success/30">
                    <p className="text-xs font-bold text-success">
                      ⚡ {automaticCoupon.code} auto-applied — you save {formatPrice(automaticCoupon.discount_amount)}
                    </p>
                    <span className="text-[10px] font-bold uppercase tracking-wider text-success shrink-0 ml-2">
                      Automatic
                    </span>
                  </div>
                )}
                {!isAuthenticated && <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-3">🔒 Sign in to apply coupons</p>}
                {couponError && <p className="text-xs font-medium text-destructive mt-2 ml-1">{couponError}</p>}
                {couponSuccess && (
                  <div className="flex justify-between items-center mt-3 bg-success-soft p-2.5 rounded-lg border border-success/30">
                    <p className="text-xs font-bold text-success">✓ {couponSuccess}</p>
                    <button 
                      onClick={handleRemoveCoupon} 
                      className="text-[10px] font-bold uppercase tracking-wider text-success hover:text-success transition-colors shrink-0 ml-2"
                    >
                      Remove
                    </button>
                  </div>
                )}
              </div>

              {/* Line Items */}
              <div className="flex flex-col gap-4 font-medium text-muted-foreground">
                <div className="flex justify-between text-sm">
                  <span>Subtotal</span>
                  <span className="text-foreground">{formatPrice(subtotal)}</span>
                </div>
                {hasDiscount && (
                  <div className="flex justify-between text-sm text-success font-bold">
                    <span>
                    Discount{' '}
                    {couponCode ? (
                      <span className="opacity-70 font-normal">({couponCode})</span>
                    ) : (
                      automaticCoupon && (
                        <span className="opacity-70 font-normal">({automaticCoupon.code})</span>
                      )
                    )}
                  </span>
                    <span>−{formatPrice(discountTotal)}</span>
                  </div>
                )}
                <div className="flex justify-between text-sm">
                  <span>Tax (Estimated)</span>
                  <span className="text-foreground">{formatPrice(taxTotal)}</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span>Shipping</span>
                  <span className={isFreeShipping ? 'text-success font-bold' : 'text-foreground'}>
                    {isFreeShipping ? 'Complimentary' : formatPrice(shippingTotal)}
                  </span>
                </div>

                <div className="border-t border-border pt-6 mt-2 flex flex-wrap justify-between items-end gap-2">
                  <span className="text-base font-extrabold text-foreground tracking-tight">Total</span>
                  <span className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight break-all text-right">{formatPrice(finalTotal)}</span>
                </div>
                {hasDiscount && (
                  <p className="text-xs font-bold uppercase tracking-wider text-success text-right mt-1">
                    You save {formatPrice(discountTotal)}
                  </p>
                )}
              </div>

              {!isAuthenticated && (
                <div className="mt-6 p-4 rounded-xl bg-warning-soft border border-warning/30">
                  <p className="text-[10px] sm:text-xs font-bold text-warning uppercase tracking-wider text-center">
                    🔒 Sign in required to checkout
                  </p>
                </div>
              )}

              <button
                onClick={handleCheckout}
                disabled={cart.length === 0}
                className={`w-full mt-6 py-4 sm:py-5 rounded-full font-bold text-xs sm:text-sm tracking-widest uppercase transition-all duration-300 ease-out shadow-xl
                  ${cart.length === 0 
                    ? 'bg-primary-soft text-muted-foreground cursor-not-allowed shadow-none'
                    : 'bg-primary text-primary-foreground hover:bg-primary-hover hover:-translate-y-1 hover:shadow-[0_20px_40px_rgba(0,0,0,0.2)] dark:hover:shadow-[0_20px_40px_rgba(255,255,255,0.15)]'
                  }`}
              >
                {!isAuthenticated ? 'Sign in to Checkout' : 'Proceed to Checkout'}
              </button>

              <div className="mt-6 sm:mt-8 pt-5 sm:pt-6 border-t border-border flex flex-col gap-3">
                <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground">
                  <span className="text-base sm:text-lg">🛡️</span> Secure checkout & encrypted payments
                </div>
                <div className="flex items-center gap-3 text-xs font-medium text-muted-foreground">
                  <span className="text-base sm:text-lg">🚚</span> {isFreeShipping ? 'Complimentary premium shipping applied' : 'Fast, reliable delivery to your door'}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Premium Login Modal */}
      {showLoginModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-foreground/40 backdrop-blur-xl transition-opacity" onClick={() => setShowLoginModal(false)} />
          <div
            ref={loginDialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="Sign in required"
            className="relative bg-card w-full max-w-sm p-6 sm:p-8 rounded-[1.5rem] sm:rounded-[2rem] shadow-xl transform scale-100 animate-[popUp_0.3s_ease-out] border border-border"
          >
            <button 
              type="button"
              onClick={() => setShowLoginModal(false)}
              className="absolute top-4 right-4 w-8 h-8 bg-primary-soft rounded-full flex items-center justify-center text-muted-foreground hover:bg-primary-soft hover:text-foreground transition-colors"
              aria-label="Close"
            >
              ✕
            </button>
            <div className="text-center mt-2">
              <div className="w-14 h-14 sm:w-16 sm:h-16 bg-primary-soft rounded-full flex items-center justify-center mx-auto mb-4">
                <span className="text-2xl sm:text-3xl">🔒</span>
              </div>
              <h3 className="text-lg sm:text-xl font-extrabold tracking-tight text-foreground mb-2">Sign in required</h3>
              <p className="text-xs sm:text-sm text-muted-foreground font-medium mb-6">Access your account to seamlessly complete your order.</p>

              <div className="space-y-3">
                <button
                  type="button"
                  onClick={handleLoginRedirect}
                  className="w-full bg-primary text-primary-foreground py-3.5 rounded-full font-bold uppercase tracking-widest text-xs hover:scale-105 transition-all shadow-lg"
                >
                  Continue to Sign In
                </button>
                <button
                  type="button"
                  onClick={() => setShowLoginModal(false)}
                  className="w-full bg-transparent text-muted-foreground py-3 rounded-full font-bold uppercase tracking-widest text-xs hover:text-foreground transition-colors"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Cart;
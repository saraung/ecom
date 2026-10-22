import React, { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { loadStripe } from '@stripe/stripe-js';
import { useAuth } from '../../hooks/useAuth';
import { useCart } from '../../hooks/useCart';
import { useTheme } from '../../hooks/useTheme';
import { addressAPI } from '../../api/addresses';
import { checkoutAPI } from '../../api/checkout';
import { orderAPI } from '../../api/orders';
import { paymentAPI } from '../../api/payments';
import { formatPrice, formatDateTime, PAYMENT_STATUS_LABELS, storeCountry } from '../../utils/format';
import { getRegion, setRegion } from '../../utils/region';
import { OrderItemsList, OrderTotals, CancellationPolicyNotice } from '../../components/orders';
import toast from 'react-hot-toast';

const loadRazorpayScript = () => {
  return new Promise((resolve) => {
    const script = document.createElement('script');
    script.src = 'https://checkout.razorpay.com/v1/checkout.js';
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
};

// Resolve a theme token to its computed value so the Stripe iframe matches
// the live palette (light/dark) instead of hardcoded hex that drifts from
// styles/theme.css.
const readThemeVar = (name, fallback) => {
  if (typeof window === 'undefined' || !document.documentElement) return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
};

const getStripeAppearance = (isDark) => {
  const fallback = isDark
    ? {
        colorPrimary: '#f0f0f0',
        colorBackground: '#242424',
        colorText: '#f5f5f5',
        colorDanger: '#ef4444',
        border: '#3a3a3a',
        muted: '#6f6f6f',
        selected: '#2c2c2c',
      }
    : {
        colorPrimary: '#111111',
        colorBackground: '#ffffff',
        colorText: '#1a1a1a',
        colorDanger: '#dc2626',
        border: '#e0ddd5',
        muted: '#8a8780',
        selected: '#f1f0ec',
      };
  const palette = {
    colorPrimary: readThemeVar('--primary', fallback.colorPrimary),
    colorBackground: readThemeVar('--card', fallback.colorBackground),
    colorText: readThemeVar('--foreground', fallback.colorText),
    colorDanger: readThemeVar('--destructive', fallback.colorDanger),
    border: readThemeVar('--border', fallback.border),
    muted: readThemeVar('--muted-foreground', fallback.muted),
    selected: readThemeVar('--muted', fallback.selected),
  };
  return {
    theme: 'flat',
    variables: {
      colorPrimary: palette.colorPrimary,
      colorBackground: palette.colorBackground,
      colorText: palette.colorText,
      colorDanger: palette.colorDanger,
      fontFamily: '"Geist", ui-sans-serif, system-ui, sans-serif',
      borderRadius: '12px',
      spacingUnit: '4px',
      spacingGridRow: '14px',
    },
    rules: {
      '.Input': { borderColor: palette.border, boxShadow: 'none' },
      '.Input:hover': { borderColor: palette.colorPrimary },
      '.Input:focus': { borderColor: palette.colorPrimary, boxShadow: 'none' },
      '.Label': { color: palette.muted, fontWeight: '600' },
      '.Tab': { borderColor: palette.border, padding: '10px 12px' },
      '.Tab:hover': { borderColor: palette.colorPrimary },
      '.Tab--selected': { backgroundColor: palette.selected, borderColor: palette.border },
      '.Tab--selected:hover': { borderColor: palette.colorPrimary },
      '.Error': { color: palette.colorDanger },
    },
  };
};

const Checkout = () => {
  const { user } = useAuth();
  const { resolvedTheme } = useTheme();
  const {
    cart,
    itemCount,
    subtotal: cartSubtotal,
    discountTotal: cartDiscount,
    taxTotal: cartTax,
    shippingTotal: cartShipping,
    total: cartTotal,
    couponCode,
    clearCart,
    loadCart,
  } = useCart();
  const [loading, setLoading] = useState(false);
  const [addresses, setAddresses] = useState([]);
  const [addressesLoading, setAddressesLoading] = useState(true);
  const [selectedAddressId, setSelectedAddressId] = useState(null);
  const [paymentMethod, setPaymentMethod] = useState('online');
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [formData, setFormData] = useState({
    label: '',
    line1: '',
    line2: '',
    city: '',
    state: '',
    postal_code: '',
    country: storeCountry(),
    is_default: false
  });
  const [formErrors, setFormErrors] = useState({});
  const [placedOrder, setPlacedOrder] = useState(null);
  const [paymentIntent, setPaymentIntent] = useState(null);
  const [paymentStep, setPaymentStep] = useState('');
  const [stripeModal, setStripeModal] = useState(null); // { order, intent }
  const [stripeBusy, setStripeBusy] = useState(false);
  const stripeRef = useRef(null);
  const stripeElementsRef = useRef(null);

  const [checkoutConfig, setCheckoutConfig] = useState(null);

  const codFeeAmount = checkoutConfig ? Number(checkoutConfig.cod_fee) : null;
  const codMinOrderValue = checkoutConfig ? Number(checkoutConfig.cod_min_order_value) : 0;
  const codMaxOrderValue = checkoutConfig ? Number(checkoutConfig.cod_max_order_value) : null;
  const codConfigReady = codFeeAmount !== null;

  const subtotal = Number(cartSubtotal) || 0;
  const discountTotal = Number(cartDiscount) || 0;
  const taxTotal = Number(cartTax) || 0;
  const shippingTotal = Number(cartShipping) || 0;
  const grandTotal = Number(cartTotal) || 0;
  const hasDiscount = discountTotal > 0;
  const isFreeShipping = shippingTotal === 0;

  const codUnavailable =
    codConfigReady && (grandTotal > codMaxOrderValue || grandTotal < codMinOrderValue);
  const codFee = paymentMethod === 'cod' && codConfigReady ? codFeeAmount : 0;
  const payableTotal = grandTotal + codFee;

  useEffect(() => {
    fetchAddresses();
    checkoutAPI.getConfig()
      .then((res) => {
        setCheckoutConfig(res.data);
        // Region drives currency/locale/labels app-wide (RegionGate also
        // loads it at boot; whichever arrives first wins, values agree).
        setRegion(res.data || {});
      })
      .catch((err) => {
        console.error('Error loading checkout config:', err);
        toast.error('Could not load checkout settings. Some options may be unavailable.');
      });
  }, []);

  useEffect(() => {
    loadCart();
  }, []);

  useEffect(() => {
    if (paymentMethod === 'cod' && codConfigReady && grandTotal > codMaxOrderValue) {
      setPaymentMethod('online');
      toast.error(
        `Cash on Delivery is available only for orders up to ${formatPrice(codMaxOrderValue)}. Please pay online.`
      );
    }
  }, [paymentMethod, grandTotal, codConfigReady, codMaxOrderValue]);

  const fetchAddresses = async () => {
    try {
      setAddressesLoading(true);
      const response = await addressAPI.getAddresses();
      const addressList = response.data || [];
      setAddresses(addressList);
      const defaultAddress = addressList.find(addr => addr.is_default);
      if (defaultAddress) {
        setSelectedAddressId(defaultAddress.id);
      } else if (addressList.length > 0) {
        setSelectedAddressId(addressList[0].id);
      }
    } catch (error) {
      console.error('Error fetching addresses:', error);
      toast.error('Failed to load addresses');
    } finally {
      setAddressesLoading(false);
    }
  };

  const validateForm = () => {
    const errors = {};
    if (!formData.label.trim()) errors.label = 'Label is required';
    if (!formData.line1.trim()) errors.line1 = 'Address line 1 is required';
    if (!formData.city.trim()) errors.city = 'City is required';
    if (!formData.state.trim()) errors.state = 'State is required';
    if (!formData.postal_code.trim()) errors.postal_code = 'Postal code is required';
    setFormErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleAddAddress = async (e) => {
    e.preventDefault();
    if (!validateForm()) {
      toast.error('Please fix the errors in the form');
      return;
    }
    try {
      const response = await addressAPI.createAddress(formData);
      toast.success('Address added successfully!');
      setAddresses([...addresses, response.data]);
      setSelectedAddressId(response.data.id);
      setShowAddressForm(false);
      resetForm();
    } catch (error) {
      console.error('Error adding address:', error);
      toast.error(error.response?.data?.detail || 'Failed to add address');
    }
  };

  const resetForm = () => {
    setFormData({
      label: '',
      line1: '',
      line2: '',
      city: '',
      state: '',
      postal_code: '',
      country: storeCountry(),
      is_default: false
    });
    setFormErrors({});
  };

  const isStripeIntent = (intent) =>
    intent?.provider === 'stripe' || intent?.payment_intent_id?.startsWith('pi_');
  const isDummyIntent = (intent) => intent?.is_dummy === true || intent?.provider === 'dummy';

  const confirmDummyPayment = async (order, intent) => {
    setPaymentStep('Confirming your payment…');
    const confirmRes = await paymentAPI.confirmPayment({ payment_intent_id: intent.payment_intent_id });
    const payment = confirmRes.data || {};
    setPlacedOrder((prev) =>
      prev
        ? {
            ...prev,
            status: 'confirmed',
            payment_status: 'paid',
            paid_with: payment.payment_method || null,
            transaction_id: payment.transaction_id || null,
          }
        : prev
    );
    toast.success('🎉 Payment successful! Order confirmed.');
  };

  const startPayment = async (order) => {
    setPaymentStep('Preparing secure payment…');
    const response = await paymentAPI.createIntent({ order_id: order.id });
    const intent = response.data;
    setPaymentIntent(intent);
    if (isStripeIntent(intent)) {
      openStripePayment(order, intent);
    } else if (isDummyIntent(intent)) {
      confirmDummyPayment(order, intent);
    } else {
      const isLoaded = await loadRazorpayScript();
      if (!isLoaded) throw new Error('Failed to load payment gateway');
      openRazorpayModal(order, intent);
    }
  };

  const openStripePayment = async (order, intent) => {
    const keyId = import.meta.env.VITE_STRIPE_PUBLISHABLE_KEY;
    if (!keyId || keyId === 'pk_test_XXX') {
      setPaymentStep('');
      toast.error('Stripe is not configured (VITE_STRIPE_PUBLISHABLE_KEY missing).');
      return;
    }
    try {
      const stripe = await loadStripe(keyId);
      if (!stripe) throw new Error('Stripe.js failed to load');
      stripeRef.current = stripe;
      setStripeModal({ order, intent });
    } catch (error) {
      console.error('Stripe load error:', error);
      setPaymentStep('');
      toast.error('Could not start the payment. Please try again.');
    }
  };

  const closeStripeModal = () => {
    setStripeModal(null);
  };

  // Mount the Stripe Payment Element once the modal is visible
  useEffect(() => {
    if (!stripeModal) return;
    const container = document.getElementById('stripe-payment-element');
    if (!container) return;
    let mountedElement = null;
    (async () => {
      const stripe = stripeRef.current;
      if (!stripe) return;
      const currentContainer = document.getElementById('stripe-payment-element');
      if (!currentContainer || !currentContainer.isConnected) return;
      const elements = stripe.elements({
        clientSecret: stripeModal.intent.client_secret,
        appearance: getStripeAppearance(resolvedTheme === 'dark'),
      });
      const element = elements.create('payment', {
        layout: { type: 'tabs' },
        labels: 'floating',
      });
      element.mount(currentContainer);
      mountedElement = element;
      stripeElementsRef.current = { elements, element };
    })();
    return () => {
      if (mountedElement) mountedElement.unmount();
      stripeElementsRef.current = null;
    };
  }, [stripeModal, resolvedTheme]);

  // Resume an unpaid order: /checkout?repay=<order_id> (Pay Now from order list/detail)
  const [searchParams] = useSearchParams();
  const repayStartedRef = useRef(false);

  useEffect(() => {
    const orderId = searchParams.get('repay');
    if (!orderId || repayStartedRef.current) return;
    repayStartedRef.current = true;
    (async () => {
      setLoading(true);
      try {
        const res = await orderAPI.getOrderById(orderId);
        const order = res.data;
        setPlacedOrder(order);
        if (order.status !== 'pending' || order.payment_status !== 'pending') {
          toast.error('This order is not waiting for payment anymore.');
          return;
        }
        await startPayment(order);
      } catch (error) {
        console.error('Repay error:', error);
        toast.error(error.response?.data?.detail || 'Could not load the order to pay.');
      } finally {
        setLoading(false);
      }
    })();
  }, [searchParams]);

  const handleStripePay = async () => {
    if (!stripeModal) return;
    const stripe = stripeRef.current;
    const { elements } = stripeElementsRef.current || {};
    if (!stripe || !elements) return;
    setStripeBusy(true);
    try {
      const { error: submitError } = await elements.submit();
      if (submitError) {
        toast.error(submitError.message || 'Please check your payment details.');
        return;
      }
      const { error } = await stripe.confirmPayment({
        elements,
        clientSecret: stripeModal.intent.client_secret,
        redirect: 'if_required',
        confirmParams: { return_url: window.location.origin + '/orders' },
      });
      if (error) {
        toast.error(error.message || 'Payment failed. Please try again.');
        return;
      }
      setPaymentStep('Confirming your payment…');
      const confirmRes = await paymentAPI.confirmPayment({
        payment_intent_id: stripeModal.intent.payment_intent_id,
        transaction_id: stripeModal.intent.payment_intent_id,
      });
      const payment = confirmRes.data || {};
      setPlacedOrder((prev) =>
        prev
          ? {
              ...prev,
              status: 'confirmed',
              payment_status: 'paid',
              paid_with: payment.payment_method || null,
              transaction_id: payment.transaction_id || null,
            }
          : prev
      );
      closeStripeModal();
      toast.success('🎉 Payment successful! Order confirmed.');
    } catch (error) {
      console.error('Stripe payment error:', error);
      const detail = error.response?.data?.detail;
      toast.error(
        detail
          ? `Payment not confirmed: ${detail}`
          : 'We could not verify your payment just now. If you were charged, the order will be confirmed automatically within a few minutes.'
      );
    } finally {
      setPaymentStep('');
      setStripeBusy(false);
    }
  };

  const renderStripeModal = () => {
    if (!stripeModal) return null;
    const payable = Number(paymentIntent?.amount) || Number(stripeModal.order?.grand_total) || 0;
    return (
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
        onClick={closeStripeModal}
      >
        <div
          className="w-full max-w-lg bg-card rounded-3xl p-6 sm:p-8 border border-border shadow-2xl animate-[popUp_0.2s_ease-out]"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-extrabold text-foreground tracking-tight">🔒 Pay Securely</h3>
            <div className="flex items-center gap-2">
              <span className="text-sm font-extrabold text-foreground bg-muted rounded-full px-4 py-1.5">
                {formatPrice(payable)}
              </span>
              <button
                onClick={closeStripeModal}
                className="text-muted-foreground hover:text-foreground text-sm font-bold"
              >
                ✕
              </button>
            </div>
          </div>
          <div id="stripe-payment-element" className="min-h-[200px]" />
          <button
            onClick={handleStripePay}
            disabled={stripeBusy}
            className="w-full mt-5 py-4 rounded-full font-bold text-sm tracking-widest uppercase bg-primary text-primary-foreground hover:bg-primary-hover transition-all duration-300 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {stripeBusy ? 'Processing…' : `Pay Now • ${formatPrice(payable)}`}
          </button>
          <button
            onClick={closeStripeModal}
            className="w-full mt-3 py-3 rounded-full font-bold text-xs uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  };

  const openRazorpayModal = (order, intent) => {
    const keyId = import.meta.env.VITE_RAZORPAY_KEY_ID;
    if (!keyId) {
      setPaymentStep('');
      toast.error('Payment gateway is not configured (VITE_RAZORPAY_KEY_ID missing).');
      return;
    }
    const options = {
      key: keyId,
      order_id: intent.payment_intent_id,
      amount: Math.round(Number(intent.amount) * 100),
      currency: intent.currency || 'INR',
      name: 'E-Shop',
      description: `Order #${order.order_number}`,
      handler: async (rp) => {
        try {
          setPaymentStep('Confirming your payment…');
          const confirmRes = await paymentAPI.confirmPayment({
            payment_intent_id: intent.payment_intent_id,
            transaction_id: rp?.razorpay_payment_id,
          });
          const payment = confirmRes.data || {};
          setPlacedOrder((prev) =>
            prev
              ? {
                  ...prev,
                  status: 'confirmed',
                  payment_status: 'paid',
                  paid_with: payment.payment_method || null,
                  transaction_id: payment.transaction_id || null,
                }
              : prev
          );
          toast.success('🎉 Payment successful! Order confirmed.');
        } catch (error) {
          console.error('Payment confirmation failed:', error);
          toast.error(
            'We could not verify your payment just now. If you were charged, the order will be confirmed automatically within a few minutes.'
          );
        } finally {
          setPaymentStep('');
        }
      },
      modal: {
        ondismiss: () => {
          setPaymentStep('');
          toast.error('Payment cancelled. Your order is saved — you can retry the payment below.');
        },
      },
      prefill: {
        name: user?.full_name || user?.username,
        email: user?.email,
        contact: user?.phone || '',
      },
      theme: {
        color: readThemeVar('--primary', '#18181b'), // brand primary from theme.css
      },
    };
    const razorpay = new window.Razorpay(options);
    razorpay.open();
  };

  const handleRetryPayment = async () => {
    if (!placedOrder) return;
    try {
      setLoading(true);
      let intent = paymentIntent;
      if (!intent) {
        setPaymentStep('Preparing secure payment…');
        const response = await paymentAPI.createIntent({ order_id: placedOrder.id });
        intent = response.data;
        setPaymentIntent(intent);
      }
      if (isStripeIntent(intent)) {
        openStripePayment(placedOrder, intent);
      } else if (isDummyIntent(intent)) {
        confirmDummyPayment(placedOrder, intent);
      } else {
        const isLoaded = await loadRazorpayScript();
        if (!isLoaded) throw new Error('Failed to load payment gateway');
        openRazorpayModal(placedOrder, intent);
      }
    } catch (error) {
      console.error('Error retrying payment:', error);
      toast.error('Could not start the payment. Please try again.');
    } finally {
      setLoading(false);
      setPaymentStep('');
    }
  };

  const handlePlaceOrder = async () => {
    if (!selectedAddressId) {
      toast.error('Please select a shipping address');
      return;
    }
    if (cart.length === 0) {
      toast.error('Your cart is empty');
      return;
    }
    let createdOrder = null;
    try {
      setLoading(true);
      setPaymentStep('Placing your order…');
      const orderData = {
        shipping_address_id: selectedAddressId,
        billing_address_id: selectedAddressId,
        payment_method: paymentMethod,
      };
      
      const response = await checkoutAPI.createOrder(orderData);
      const order = response.data;
      createdOrder = order;
      setPlacedOrder(order);

      orderAPI
        .getOrderByNumber(order.order_number)
        .then((fullRes) => {
          setPlacedOrder((prev) => {
            if (!prev || prev.id !== order.id) return prev;
            const merged = { ...prev, ...fullRes.data };
            if (prev.payment_status === 'paid' && merged.payment_status !== 'paid') {
              merged.payment_status = 'paid';
            }
            return merged;
          });
        })
        .catch((err) => console.warn('Could not load full order for confirmation:', err));

      await clearCart();

      if (order.payment_status === 'cod_pending') {
        toast.success('🎉 Order placed successfully! Pay on delivery.');
        return;
      }
      await startPayment(order);
    } catch (error) {
      console.error('Checkout error:', error);
      if (!createdOrder) {
        toast.error(getCheckoutErrorMessage(error));
      } else {
        toast.error('Order placed, but we could not start the payment. You can retry below.');
      }
    } finally {
      setLoading(false);
      setPaymentStep('');
    }
  };

  const getCheckoutErrorMessage = (error) => {
    const detail = error.response?.data?.detail;
    if (Array.isArray(detail)) {
      return detail.map((err) => err.msg || err.message).join(', ');
    }
    return detail || 'Failed to place order. Please try again.';
  };

  if (addressesLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background transition-colors duration-700">
        <div className="flex flex-col items-center gap-3">
          <div className="h-10 w-10 rounded-full border-[3px] border-border border-t-foreground animate-spin" />
          <p className="text-muted-foreground font-medium tracking-wide text-xs uppercase">Loading Checkout</p>
        </div>
      </div>
    );
  }

  // Success / Order Placed State
  if (placedOrder) {
    const isPaid = placedOrder.payment_status === 'paid';
    const isCod = placedOrder.payment_status === 'cod_pending';
    const isPending = placedOrder.payment_status === 'pending';

    return (
      <>
      <div className="bg-background min-h-screen py-20 px-4 transition-colors duration-700">
        <div className="max-w-2xl mx-auto bg-card rounded-[2rem] shadow-sm border border-border overflow-hidden">
          
          <div className={`p-10 text-center ${isPaid ? 'bg-success-soft' : isCod ? 'bg-primary-soft/50' : 'bg-warning-soft'}`}>
            <div className="text-5xl mb-4">{isPaid ? '✅' : isCod ? '💵' : '⏳'}</div>
            <h2 className="text-2xl font-extrabold text-foreground mb-2 tracking-tight">
              {isPaid ? 'Payment Successful!' : isCod ? 'Order Confirmed!' : 'Order Placed — Payment Pending'}
            </h2>
            <p className="text-sm text-muted-foreground font-medium max-w-md mx-auto">
              {isPaid && 'Your payment has been received and your order is confirmed.'}
              {isCod && `Please keep ${formatPrice(placedOrder.grand_total)} ready at delivery.`}
              {isPending && 'Complete the secure payment to confirm your order.'}
            </p>
            <p className="text-xs font-bold uppercase tracking-widest text-muted-foreground mt-6">
              Order Number: <span className="text-foreground">{placedOrder.order_number}</span>
            </p>
          </div>

          <div className="p-8">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-8 bg-primary-soft/50 p-6 rounded-2xl border border-border">
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Status</span>
                <span className="text-sm font-bold text-foreground capitalize">{placedOrder.status}</span>
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Payment</span>
                <span className="text-sm font-bold text-foreground">{PAYMENT_STATUS_LABELS[placedOrder.payment_status] || placedOrder.payment_status}</span>
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Method</span>
                <span className="text-sm font-bold text-foreground">{placedOrder.payment_method === 'cod' ? 'Cash on Delivery' : 'Online'}</span>
              </div>
              <div>
                <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Date</span>
                <span className="text-sm font-bold text-foreground">{formatDateTime(placedOrder.placed_at)}</span>
              </div>
              {placedOrder.transaction_id && (
                <div className="col-span-2 md:col-span-4">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block mb-1">Transaction ID</span>
                  <span className="text-sm font-bold text-foreground break-all">{placedOrder.transaction_id}</span>
                </div>
              )}
            </div>

            {Array.isArray(placedOrder.items) && placedOrder.items.length > 0 && (
              <div className="mb-8">
                <h3 className="text-sm font-bold uppercase tracking-widest text-foreground mb-4">Items</h3>
                <OrderItemsList items={placedOrder.items} />
              </div>
            )}

            <div className="border-t border-border pt-6">
              <OrderTotals order={placedOrder} codFee={placedOrder.cod_fee} />
            </div>

            {isPending && (
              <button
                onClick={handleRetryPayment}
                disabled={loading}
                className="w-full mt-8 py-5 rounded-full font-bold text-sm tracking-widest uppercase transition-all duration-300 ease-out shadow-xl bg-primary text-primary-foreground hover:bg-primary-hover hover:-translate-y-1 hover:shadow-[0_20px_40px_rgba(0,0,0,0.2)] dark:hover:shadow-[0_20px_40px_rgba(255,255,255,0.15)] disabled:opacity-70 disabled:cursor-not-allowed disabled:transform-none"
              >
                {loading || paymentStep ? paymentStep || 'Preparing…' : `Pay Now • ${formatPrice(placedOrder.grand_total)}`}
              </button>
            )}

            <div className="flex flex-col sm:flex-row gap-4 mt-8">
              <Link to="/orders" className="flex-1 text-center py-4 rounded-full font-bold uppercase tracking-widest text-xs bg-primary-soft text-foreground hover:bg-primary-soft transition-colors">
                View Orders
              </Link>
              <Link to="/products" className={`flex-1 text-center py-4 rounded-full font-bold uppercase tracking-widest text-xs transition-colors ${!isPending ? 'bg-primary text-primary-foreground hover:bg-primary-hover shadow-xl' : 'bg-primary-soft text-foreground hover:bg-primary-soft'}`}>
                Continue Shopping
              </Link>
            </div>

            {isPending && (
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground text-center mt-6">
                🔒 Secure payment via {isStripeIntent(paymentIntent) ? 'Stripe' : 'Razorpay'}
              </p>
            )}
          </div>
        </div>
      </div>
      {renderStripeModal()}
      </>
    );
  }

  // Empty Cart State
  if (cart.length === 0) {
    return (
      <div className="min-h-screen bg-background transition-colors duration-700 pt-24 pb-20 px-4 flex flex-col items-center justify-center">
        <div className="text-center p-8 sm:p-10 bg-card rounded-[2rem] sm:rounded-[2.5rem] shadow-sm border border-border max-w-md w-full">
          <div className="text-5xl sm:text-6xl mb-6">🛒</div>
          <h2 className="text-xl sm:text-2xl font-extrabold text-foreground mb-2 tracking-tight">Your cart is empty</h2>
          <p className="text-sm text-muted-foreground mb-8 font-medium">Add some items before checking out.</p>
          <Link 
            to="/products" 
            className="w-full block bg-primary text-primary-foreground px-6 sm:px-8 py-4 rounded-full font-bold uppercase tracking-widest text-xs sm:text-sm hover:scale-105 transition-all duration-300 shadow-xl"
          >
            Continue Shopping
          </Link>
        </div>
      </div>
    );
  }

  // Main Checkout Flow
  return (
    <>
    <div className="bg-background min-h-screen selection:bg-primary selection:text-primary-foreground transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        
        {/* Header */}
        <div className="mb-8 sm:mb-10 border-b border-border pb-6">
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">Checkout</h1>
        </div>

        <div className="flex flex-col lg:flex-row gap-8 lg:gap-12 items-start">
          
          {/* Left Column - Addresses & Payment */}
          <div className="w-full lg:w-3/5 flex flex-col gap-6 sm:gap-8">
            
            {/* Address Section */}
            <div className="bg-card rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-8 border border-border shadow-sm">
              <h2 className="text-lg font-extrabold text-foreground mb-6 tracking-tight">Shipping Details</h2>

              {addresses.length > 0 ? (
                <div className="flex flex-col gap-4">
                  {addresses.map((address) => (
                    <label
                      key={address.id}
                      className={`relative flex items-start gap-4 p-5 rounded-2xl border-2 cursor-pointer transition-all duration-300 ease-out
                        ${selectedAddressId === address.id 
                          ? 'border-primary bg-primary-soft/50 shadow-md scale-[1.01]' 
                          : 'border-border hover:border-border bg-transparent'}`}
                    >
                      <input
                        type="radio"
                        name="address"
                        value={address.id}
                        checked={selectedAddressId === address.id}
                        onChange={() => setSelectedAddressId(address.id)}
                        className="mt-1 w-4 h-4 text-foreground bg-primary-soft border-border focus:ring-primary accent-primary"
                      />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <strong className="text-sm font-bold text-foreground truncate">{address.label || 'Address'}</strong>
                          {address.is_default && (
                            <span className="bg-primary-soft text-foreground/80 px-2 py-0.5 rounded text-[9px] font-bold uppercase tracking-wider shrink-0">
                              Default
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground font-medium truncate">{address.line1}</p>
                        {address.line2 && <p className="text-sm text-muted-foreground font-medium truncate">{address.line2}</p>}
                        <p className="text-sm text-muted-foreground font-medium mt-1 truncate">
                          {address.city}, {address.state} {address.postal_code}
                        </p>
                        <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mt-2">{address.country}</p>
                      </div>
                    </label>
                  ))}

                  <button
                    onClick={() => setShowAddressForm(!showAddressForm)}
                    className="self-start text-xs font-bold uppercase tracking-widest text-foreground hover:opacity-70 transition-opacity mt-2"
                  >
                    {showAddressForm ? 'Cancel' : '+ Add New Address'}
                  </button>
                </div>
              ) : (
                <div className="text-center py-8">
                  <p className="text-sm font-medium text-muted-foreground mb-4">You have no saved addresses.</p>
                  <button 
                    onClick={() => setShowAddressForm(!showAddressForm)} 
                    className="text-xs font-bold uppercase tracking-widest text-foreground border-b-2 border-primary pb-1 hover:opacity-70 transition-opacity"
                  >
                    {showAddressForm ? 'Cancel' : 'Add your first address'}
                  </button>
                </div>
              )}

              {showAddressForm && (
                <div className="mt-4 p-6 bg-primary-soft/50 rounded-2xl border border-border animate-[popUp_0.2s_ease-out]">
                  <form onSubmit={handleAddAddress} className="flex flex-col gap-4">
                        <div>
                          <input
                            type="text"
                            placeholder="Label (e.g. Home, Work) *"
                            value={formData.label}
                            onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                            className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                          />
                          {formErrors.label && <p className="text-destructive text-xs mt-1.5 ml-1 font-medium">{formErrors.label}</p>}
                        </div>
                        
                        <div>
                          <input
                            type="text"
                            placeholder="Address Line 1 *"
                            value={formData.line1}
                            onChange={(e) => setFormData({ ...formData, line1: e.target.value })}
                            className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                          />
                          {formErrors.line1 && <p className="text-destructive text-xs mt-1.5 ml-1 font-medium">{formErrors.line1}</p>}
                        </div>

                        <div>
                          <input
                            type="text"
                            placeholder="Address Line 2 (Optional)"
                            value={formData.line2}
                            onChange={(e) => setFormData({ ...formData, line2: e.target.value })}
                            className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                          />
                        </div>

                        <div className="flex flex-col sm:flex-row gap-4">
                          <div className="flex-1">
                            <input
                              type="text"
                              placeholder="City *"
                              value={formData.city}
                              onChange={(e) => setFormData({ ...formData, city: e.target.value })}
                              className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                            />
                            {formErrors.city && <p className="text-destructive text-xs mt-1.5 ml-1 font-medium">{formErrors.city}</p>}
                          </div>
                          <div className="flex-1">
                            <input
                              type="text"
                              placeholder="State *"
                              value={formData.state}
                              onChange={(e) => setFormData({ ...formData, state: e.target.value })}
                              className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                            />
                            {formErrors.state && <p className="text-destructive text-xs mt-1.5 ml-1 font-medium">{formErrors.state}</p>}
                          </div>
                        </div>

                        <div className="flex flex-col sm:flex-row gap-4">
                          <div className="flex-1">
                            <input
                              type="text"
                              placeholder="Postal Code *"
                              value={formData.postal_code}
                              onChange={(e) => setFormData({ ...formData, postal_code: e.target.value })}
                              className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                            />
                            {formErrors.postal_code && <p className="text-destructive text-xs mt-1.5 ml-1 font-medium">{formErrors.postal_code}</p>}
                          </div>
                          <div className="flex-1">
                            <input
                              type="text"
                              placeholder="Country"
                              value={formData.country}
                              onChange={(e) => setFormData({ ...formData, country: e.target.value })}
                              className="w-full bg-card border border-border rounded-xl px-4 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                            />
                          </div>
                        </div>

                        <button 
                          type="submit" 
                          className="mt-2 bg-primary text-primary-foreground py-4 rounded-full font-bold uppercase tracking-widest text-xs hover:scale-[1.02] transition-transform shadow-md"
                        >
                          Save Address
                        </button>
                      </form>
                    </div>
                  )}
            </div>

            {/* Payment Method Section */}
            <div className="bg-card rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-8 border border-border shadow-sm">
              <h2 className="text-lg font-extrabold text-foreground mb-6 tracking-tight">Payment Method</h2>
              
              <div className="flex flex-col gap-4">
                <label className={`relative flex items-center gap-4 p-5 rounded-2xl border-2 cursor-pointer transition-all duration-300 ease-out
                  ${paymentMethod === 'online' 
                    ? 'border-primary bg-primary-soft/50 shadow-md scale-[1.01]' 
                    : 'border-border hover:border-border bg-transparent'}`}
                >
                  <input 
                    type="radio" 
                    name="payment" 
                    value="online" 
                    checked={paymentMethod === 'online'} 
                    onChange={() => setPaymentMethod('online')} 
                    className="w-4 h-4 text-foreground bg-primary-soft border-border focus:ring-primary accent-primary"
                  />
                  <div className="flex-1">
                    <span className="text-sm font-bold text-foreground block">💳 Pay Securely Online</span>
                    <span className="text-xs font-medium text-muted-foreground mt-1 block">
                      {getRegion().currency === 'INR'
                        ? 'UPI, Cards, Net Banking & Wallets'
                        : 'Cards & Wallets'}
                    </span>
                  </div>
                </label>

                <label className={`relative flex items-center gap-4 p-5 rounded-2xl border-2 transition-all duration-300 ease-out
                  ${paymentMethod === 'cod' 
                    ? 'border-primary bg-primary-soft/50 shadow-md scale-[1.01]' 
                    : 'border-border hover:border-border bg-transparent'}
                  ${(codUnavailable || !codConfigReady) ? 'opacity-50 grayscale cursor-not-allowed hover:border-border' : 'cursor-pointer'}`}
                >
                  <input 
                    type="radio" 
                    name="payment" 
                    value="cod" 
                    checked={paymentMethod === 'cod'} 
                    onChange={() => setPaymentMethod('cod')} 
                    disabled={codUnavailable || !codConfigReady} 
                    className="w-4 h-4 text-foreground bg-primary-soft border-border focus:ring-primary accent-primary disabled:opacity-50"
                  />
                  <div className="flex-1">
                    <span className="text-sm font-bold text-foreground block">
                      💵 Cash on Delivery
                      {codConfigReady && (
                        <span className="font-medium text-muted-foreground ml-1">
                          (+{formatPrice(codFeeAmount)} fee)
                        </span>
                      )}
                    </span>
                    <span className="text-xs font-medium text-muted-foreground mt-1 block">Pay when your order arrives</span>
                    {codUnavailable && codConfigReady && (
                      <span className="text-[10px] font-bold uppercase tracking-wider text-warning mt-2 block">
                        Unavailable above {formatPrice(codMaxOrderValue)}
                      </span>
                    )}
                    {!codConfigReady && (
                      <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-2 block">
                        Loading availability…
                      </span>
                    )}
                  </div>
                </label>
              </div>

              <div className="mt-6">
                <CancellationPolicyNotice />
              </div>
            </div>

          </div>

          {/* Right Column - Order Summary (Sticky) */}
          <div className="w-full lg:w-2/5 lg:sticky lg:top-24">
            <div className="bg-card rounded-[1.5rem] sm:rounded-[2rem] p-5 sm:p-8 border border-border shadow-sm">
              <h3 className="text-xl font-extrabold text-foreground mb-6 tracking-tight">Review Order</h3>

              {/* Line Items Preview */}
              <div className="max-h-[220px] overflow-y-auto custom-scrollbar mb-6 pr-2">
                {cart.map((item, index) => (
                  <div key={item.cartItemId || item.id || index} className="flex items-center gap-4 py-3 border-b border-border last:border-0">
                    <div className="w-12 h-12 rounded-xl bg-primary-soft border border-border/50 flex items-center justify-center shrink-0 overflow-hidden">
                      {item.image ? (
                        <img src={item.image} alt={item.name} className="w-full h-full object-cover" onError={(e) => e.target.style.display = 'none'} />
                      ) : (
                        <span className="text-lg opacity-50">🛍️</span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-bold text-foreground truncate">{item.name}</div>
                      <div className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-0.5">Qty: {item.quantity}</div>
                    </div>
                    <div className="text-sm font-extrabold text-foreground shrink-0">
                      {formatPrice((item.price || 0) * (item.quantity || 1))}
                    </div>
                  </div>
                ))}
              </div>

              {/* Totals */}
              <div className="flex flex-col gap-4 font-medium text-muted-foreground border-t border-border pt-6">
                <div className="flex justify-between text-sm">
                  <span>Subtotal <span className="opacity-70">({itemCount} items)</span></span>
                  <span className="text-foreground">{formatPrice(subtotal)}</span>
                </div>
                {hasDiscount && (
                  <div className="flex justify-between text-sm text-success font-bold">
                    <span>Discount {couponCode && <span className="opacity-70 font-normal">({couponCode})</span>}</span>
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
                {paymentMethod === 'cod' && codConfigReady && (
                  <div className="flex justify-between text-sm">
                    <span>COD Handling Fee</span>
                    <span className="text-foreground">{formatPrice(codFeeAmount)}</span>
                  </div>
                )}

                <div className="border-t border-border pt-6 mt-2 flex flex-wrap justify-between items-end gap-2">
                  <span className="text-base font-extrabold text-foreground tracking-tight">Total</span>
                  <span className="text-2xl sm:text-3xl font-extrabold text-foreground tracking-tight break-all text-right">
                    {formatPrice(payableTotal)}
                  </span>
                </div>
                {hasDiscount && (
                  <p className="text-xs font-bold uppercase tracking-wider text-success text-right mt-1">
                    You save {formatPrice(discountTotal)}
                  </p>
                )}
              </div>

              {/* Action Button */}
              <button
                onClick={handlePlaceOrder}
                disabled={loading || !selectedAddressId || cart.length === 0}
                className={`w-full mt-8 py-4 sm:py-5 rounded-full font-bold text-xs sm:text-sm tracking-widest uppercase transition-all duration-300 ease-out shadow-xl
                  ${(loading || !selectedAddressId || cart.length === 0)
                    ? 'bg-primary-soft text-muted-foreground cursor-not-allowed shadow-none'
                    : 'bg-primary text-primary-foreground hover:bg-primary-hover hover:-translate-y-1 hover:shadow-[0_20px_40px_rgba(0,0,0,0.2)] dark:hover:shadow-[0_20px_40px_rgba(255,255,255,0.15)]'
                  }`}
              >
                {loading ? (paymentStep || 'Processing…') : `Place Order • ${formatPrice(payableTotal)}`}
              </button>

              <div className="mt-6 pt-6 border-t border-border flex flex-col gap-3">
                <div className="flex items-center justify-center gap-2 text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  <span className="text-sm">🛡️</span> 256-bit Secure Encryption
                </div>
              </div>
              
              <Link to="/cart" className="block text-center mt-6 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors">
                ← Return to Bag
              </Link>
            </div>
          </div>

        </div>
      </div>
      </div>
      {renderStripeModal()}
      </>
  );
};

export default Checkout;
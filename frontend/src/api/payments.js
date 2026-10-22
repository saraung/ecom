import api from './axios';

export const paymentAPI = {
  // ✅ Step A — create a payment intent (Razorpay order) for a placed order
  // request:  { order_id: "<order uuid>" }
  // response: { client_secret, payment_intent_id, order_id, amount (deployment currency), currency, is_dummy }
  createIntent: (data) => api.post('/payments/create-intent', data),

  // ✅ Step C — confirm the payment after the Razorpay modal succeeds
  // request:  { payment_intent_id: "order_XXXX" }
  // response: PaymentRead { id, order_id, provider, provider_payment_id, amount,
  //           currency, status, payment_method, last_four, paid_at, ... }
  confirmPayment: (data) => api.post('/payments/confirm', data),
};
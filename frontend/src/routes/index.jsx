// src/routes/index.jsx
import React, { Suspense, lazy } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import Layout from '../components/layout/Layout';
import Home from '../pages/home/Home';

// Eager: the landing page and the sign-in gate. Lazy-loading either makes the
// most common entry points flash a fallback for no benefit.
import Login from '../pages/auth/Login';

// Everything else is split per route so the initial bundle only carries the
// shell + home. Each page is fetched the first time it is visited and cached
// by the browser thereafter.
const ProductList = lazy(() => import('../pages/product/ProductList'));
const ProductDetail = lazy(() => import('../pages/product/ProductDetail'));
const Cart = lazy(() => import('../pages/checkout/Cart'));
const Wishlist = lazy(() => import('../pages/customer/Wishlist'));
const Checkout = lazy(() => import('../pages/checkout/Checkout'));
const Orders = lazy(() => import('../pages/customer/Orders'));
const OrderDetail = lazy(() => import('../pages/customer/OrderDetail'));
const Notifications = lazy(() => import('../pages/customer/Notifications'));
const Profile = lazy(() => import('../pages/customer/Profile'));
const Settings = lazy(() => import('../pages/customer/Settings'));
const Addresses = lazy(() => import('../pages/customer/Addresses'));
const NotFound = lazy(() => import('../pages/NotFound'));

// Auth screens (full-screen, no Layout)
const RegisterWithOTP = lazy(() => import('../pages/auth/RegisterWithOTP'));
const ForgotPassword = lazy(() => import('../pages/auth/ForgotPassword'));
const ResetPassword = lazy(() => import('../pages/auth/ResetPassword'));

import PrivateRoute from './PrivateRoute';
import PublicRoute from './PublicRoute';

const ScrollToTop = () => {
  const { pathname } = useLocation();

  React.useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  return null;
};

/** Shown only while a route chunk is downloading. */
const RouteFallback = () => (
  <div className="min-h-[60vh] flex items-center justify-center">
    <div
      className="h-10 w-10 animate-spin rounded-full border-2 border-border border-b-primary"
      role="status"
      aria-label="Loading page"
    />
  </div>
);

const AppRoutes = () => {
  return (
    <>
      <ScrollToTop />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<Layout><Home /></Layout>} />
          <Route path="/products" element={<Layout><ProductList /></Layout>} />
          <Route path="/products/:slug" element={<Layout><ProductDetail /></Layout>} />
          <Route path="/cart" element={<Layout><Cart /></Layout>} />
          <Route path="/wishlist" element={<Layout><Wishlist /></Layout>} />

          {/* Auth Routes - No Layout needed (full screen) */}
          <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />

          {/* OTP-based registration */}
          <Route path="/register" element={<PublicRoute><RegisterWithOTP /></PublicRoute>} />

          <Route path="/forgot-password" element={<PublicRoute><ForgotPassword /></PublicRoute>} />
          <Route path="/reset-password" element={<PublicRoute><ResetPassword /></PublicRoute>} />

          {/* Protected Routes - With Layout (require login) */}
          <Route path="/checkout" element={<PrivateRoute><Layout><Checkout /></Layout></PrivateRoute>} />
          <Route path="/orders" element={<PrivateRoute><Layout><Orders /></Layout></PrivateRoute>} />
          <Route path="/orders/:id" element={<PrivateRoute><Layout><OrderDetail /></Layout></PrivateRoute>} />
          <Route path="/notifications" element={<PrivateRoute><Layout><Notifications /></Layout></PrivateRoute>} />
          <Route path="/profile" element={<PrivateRoute><Layout><Profile /></Layout></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute><Layout><Settings /></Layout></PrivateRoute>} />
          <Route path="/addresses" element={<PrivateRoute><Layout><Addresses /></Layout></PrivateRoute>} />

          {/* Catch-all: keep the shell so the shopper can navigate out of a bad link. */}
          <Route path="*" element={<Layout><NotFound /></Layout>} />
        </Routes>
      </Suspense>
    </>
  );
};

export default AppRoutes;

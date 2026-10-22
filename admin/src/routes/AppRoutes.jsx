// src/routes/AppRoutes.jsx
import React, { lazy, Suspense } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { hasMinRole, canDo, firstAllowedPath } from '../utils/permissions';
import AdminLayout from '../components/layout/AdminLayout';
import ErrorBoundary from '../components/ErrorBoundary';
import PageSkeleton from '../components/ui/PageSkeleton';
import { skeletonForPath } from '../components/skeletons/skeletonRoutes';
import PageLoader from '../components/ui/PageLoader';
// Eager: the sign-in gate. Lazy-loading it flashes a fallback on every
// hard reload of /login for zero benefit (it must load before anything).
import Login from '../pages/Login/Login';

const Dashboard = lazy(() => import('../pages/Dashboard/Dashboard'));
const ProductList = lazy(() => import('../pages/Products/ProductList'));
const ProductForm = lazy(() => import('../pages/Products/ProductForm'));
const ProductDetail = lazy(() => import('../pages/Products/ProductDetail'));
const OrderList = lazy(() => import('../pages/Orders/OrderList'));
const OrderDetail = lazy(() => import('../pages/Orders/OrderDetail'));
const ReturnList = lazy(() => import('../pages/Returns/ReturnList'));
const ReturnDetail = lazy(() => import('../pages/Returns/ReturnDetail'));
const Refunds = lazy(() => import('../pages/Refunds/Refunds'));
const CodReconciliation = lazy(() => import('../pages/Cod/CodReconciliation'));
const CodImport = lazy(() => import('../pages/Cod/CodImport'));
const CodManualBatch = lazy(() => import('../pages/Cod/CodManualBatch'));
const CodRemittanceDetail = lazy(() => import('../pages/Cod/CodRemittanceDetail'));
const UserList = lazy(() => import('../pages/Users/UserList'));
const UserDetail = lazy(() => import('../pages/Users/UserDetail'));
const Invites = lazy(() => import('../pages/Invites/Invites'));
// Public: reached from the invitation email, before the visitor has a session.
const AcceptInvite = lazy(() => import('../pages/Invites/AcceptInvite'));
const AuditLog = lazy(() => import('../pages/Audit/AuditLog'));
const CouponList = lazy(() => import('../pages/Coupons/CouponList'));
const CouponForm = lazy(() => import('../pages/Coupons/CouponForm'));
const Promotions = lazy(() => import('../pages/Promotions/Promotions'));
const CategoryList = lazy(() => import('../pages/Categories/CategoryList'));
const CategoryForm = lazy(() => import('../pages/Categories/CategoryForm'));
const CategoryProducts = lazy(() => import('../pages/Categories/CategoryProducts'));
const Reports = lazy(() => import('../pages/Reports/Reports'));
const RoleList = lazy(() => import('../pages/Roles/RoleList'));
const RoleForm = lazy(() => import('../pages/Roles/RoleForm'));
const Reviews = lazy(() => import('../pages/Reviews/Reviews'));
const StoreSettings = lazy(() => import('../pages/StoreSettings/StoreSettings'));
const Content = lazy(() => import('../pages/Content/Content'));
const ContentForm = lazy(() => import('../pages/Content/ContentForm'));
const Settings = lazy(() => import('../pages/Settings/Settings'));
const Unauthorized = lazy(() => import('../pages/Unauthorized/Unauthorized'));
const ShiprocketSimulator = lazy(() => import('../pages/Shipping/ShiprocketSimulator'));
// MCP Agent — streaming admin chat page backed by /mcp/chat/*.
const McpAgent = lazy(() => import('../pages/McpAgent/McpAgent'));


// NOTE: Auth gating for the admin area lives in AdminLayout (not a wrapper
// around it) so the sidebar + header stay mounted and visible while the
// /auth/me check and lazy page chunks load on refresh.

const RoleBasedRoute = ({ children, minRole, requirePerm, redirectTo = '/unauthorized' }) => {
  const { user, userRole, isAuthenticated, loading } = useAuth();
  const location = useLocation();

  // Revalidating a cached session in the background: let the page render
  // from cache instead of flashing the auth skeleton on every reload.
  // Only sessions with no cached user at all wait for the check — using
  // the route-matched skeleton so the shape still blends into the page.
  if (loading && !user) {
    const { type, props } = skeletonForPath(location.pathname);
    return <PageSkeleton type={type} {...props} />;
  }

  // 👇 2. Check authentication
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // 👇 3. Landing redirect: anyone without dashboard.view (legacy staff,
  // custom roles) goes to their first permitted tab instead of staring at
  // Unauthorized. firstAllowedPath mirrors the sidebar order, so the tab
  // and the landing page can never disagree.
  if (location.pathname === '/' && !canDo(user, 'dashboard.view', 'manager')) {
    return <Navigate to={firstAllowedPath(user)} replace />;
  }

  // 👇 4. Check permission: dynamic key when the session carries
  // permissions, otherwise the legacy minimum role.
  const allowed = requirePerm
    ? canDo(user, requirePerm, minRole || 'admin')
    : hasMinRole(userRole, minRole);
  if (!allowed) {
    return <Navigate to={redirectTo} replace />;
  }

  return children;
};

const withErrorBoundary = (element) => (
  <ErrorBoundary>{element}</ErrorBoundary>
);

const AppRoutes = () => {
  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route path="/login" element={withErrorBoundary(<Login />)} />
        {/* Staff-invite acceptance — public, mirrors the emailed token link. */}
        <Route path="/accept-invite" element={withErrorBoundary(<AcceptInvite />)} />
        <Route path="/unauthorized" element={withErrorBoundary(<Unauthorized />)} />
        
        <Route path="/" element={<AdminLayout />}>
          <Route index element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="dashboard.view">
              <Dashboard />
            </RoleBasedRoute>
          )} />
          
          {/* Products - Staff+ (perm-gated like every other tab: even
              customers must not open these by URL while the tab hides) */}
          <Route path="products">
            <Route index element={withErrorBoundary(
              <RoleBasedRoute minRole="staff" requirePerm="products.view">
                <ProductList />
              </RoleBasedRoute>
            )} />
            <Route path="new" element={withErrorBoundary(
              <RoleBasedRoute minRole="staff" requirePerm="products.create">
                <ProductForm />
              </RoleBasedRoute>
            )} />
            <Route path=":slug" element={withErrorBoundary(
              <RoleBasedRoute minRole="staff" requirePerm="products.view">
                <ProductDetail />
              </RoleBasedRoute>
            )} />
            <Route path=":slug/edit" element={withErrorBoundary(
              <RoleBasedRoute minRole="staff" requirePerm="products.update">
                <ProductForm />
              </RoleBasedRoute>
            )} />
          </Route>
          
          {/* Categories - Manager+ */}
          <Route path="categories">
            <Route index element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="categories.view">
                <CategoryList />
              </RoleBasedRoute>
            )} />
            <Route path="new" element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="categories.manage">
                <CategoryForm />
              </RoleBasedRoute>
            )} />
            <Route path=":categoryId/products" element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="categories.view">
                <CategoryProducts />
              </RoleBasedRoute>
            )} />
            <Route path=":id/edit" element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="categories.manage">
                <CategoryForm />
              </RoleBasedRoute>
            )} />
          </Route>
          
          {/* Orders - Manager+ */}
          <Route path="orders">
            <Route index element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="orders.view">
                <OrderList />
              </RoleBasedRoute>
            )} />
            <Route path=":id" element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="orders.view">
                <OrderDetail />
              </RoleBasedRoute>
            )} />
          </Route>
          
          {/* Users - Admin only */}
          <Route path="returns" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="orders.view"><ReturnList /></RoleBasedRoute>
          )} />
          <Route path="returns/:id" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="orders.view"><ReturnDetail /></RoleBasedRoute>
          )} />
          <Route path="users">
            <Route index element={withErrorBoundary(
              <RoleBasedRoute minRole="admin" requirePerm="users.view">
                <UserList />
              </RoleBasedRoute>
            )} />
            <Route path=":id" element={withErrorBoundary(
              <RoleBasedRoute minRole="admin" requirePerm="users.view">
                <UserDetail />
              </RoleBasedRoute>
            )} />
          </Route>

          {/* Roles - roles.manage */}
          <Route path="roles">
            <Route index element={withErrorBoundary(
              <RoleBasedRoute minRole="admin" requirePerm="roles.manage">
                <RoleList />
              </RoleBasedRoute>
            )} />
            <Route path="new" element={withErrorBoundary(
              <RoleBasedRoute minRole="admin" requirePerm="roles.manage">
                <RoleForm />
              </RoleBasedRoute>
            )} />
            <Route path=":id/edit" element={withErrorBoundary(
              <RoleBasedRoute minRole="admin" requirePerm="roles.manage">
                <RoleForm />
              </RoleBasedRoute>
            )} />
          </Route>
          
          {/* Coupons - Manager+ */}
          <Route path="coupons">
            <Route index element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="coupons.view">
                <CouponList />
              </RoleBasedRoute>
            )} />
            <Route path="new" element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="coupons.manage">
                <CouponForm />
              </RoleBasedRoute>
            )} />
            <Route path=":id/edit" element={withErrorBoundary(
              <RoleBasedRoute minRole="manager" requirePerm="coupons.manage">
                <CouponForm />
              </RoleBasedRoute>
            )} />
          </Route>
          
          {/* Promotions - Manager+ */}
          <Route path="promotions" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="promotions.send">
              <Promotions />
            </RoleBasedRoute>
          )} />
          
          {/* Reports - Manager+ */}
          <Route path="reports" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="reports.view">
              <Reports />
            </RoleBasedRoute>
          )} />
          {/* Refunds ledger - orders.refund */}
          <Route path="refunds" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="orders.refund">
              <Refunds />
            </RoleBasedRoute>
          )} />
          {/* COD reconciliation - Sales. Customer collection and courier
              remittance are separate; cod.reconcile gates every money action. */}
          <Route path="cod" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="cod.view">
              <CodReconciliation />
            </RoleBasedRoute>
          )} />
          <Route path="cod/import" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="cod.reconcile">
              <CodImport />
            </RoleBasedRoute>
          )} />
          <Route path="cod/new" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="cod.reconcile">
              <CodManualBatch />
            </RoleBasedRoute>
          )} />
          <Route path="cod/:id" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="cod.view">
              <CodRemittanceDetail />
            </RoleBasedRoute>
          )} />
          {/* Audit log - reports.view */}
          <Route path="audit-log" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="reports.view">
              <AuditLog />
            </RoleBasedRoute>
          )} />
          {/* Staff invites - users.manage_roles */}
          <Route path="invites" element={withErrorBoundary(
            <RoleBasedRoute minRole="admin" requirePerm="users.manage_roles">
              <Invites />
            </RoleBasedRoute>
          )} />
          {/* Review moderation - reviews.moderate (admin-only; managers
              don't hold this permission) */}
          <Route path="reviews" element={withErrorBoundary(
            <RoleBasedRoute minRole="admin" requirePerm="reviews.moderate">
              <Reviews />
            </RoleBasedRoute>
          )} />
          {/* Store policy - settings.manage (admin-only). Separate from the
              self-profile Settings page: these are the money rules. */}
          <Route path="store-settings" element={withErrorBoundary(
            <RoleBasedRoute minRole="admin" requirePerm="settings.manage">
              <StoreSettings />
            </RoleBasedRoute>
          )} />
          {/* Content blocks - content.manage (managers hold this too) */}
          <Route path="content" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="content.manage">
              <Content />
            </RoleBasedRoute>
          )} />
          <Route path="content/new" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="content.manage">
              <ContentForm />
            </RoleBasedRoute>
          )} />
          <Route path="content/:id/edit" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="content.manage">
              <ContentForm />
            </RoleBasedRoute>
          )} />
          {/* Shiprocket Simulator - Manager+ */}
          <Route path="shipping-simulator" element={withErrorBoundary(
            <RoleBasedRoute minRole="manager" requirePerm="shipping.manage">
              <ShiprocketSimulator />
            </RoleBasedRoute>
          )} />

          {/* MCP Agent — session-gated like Settings (any authenticated staff
              member); the backend enforces MCP tool permissions per call. */}
          <Route path="mcp-agent" element={withErrorBoundary(<McpAgent />)} />

          
          {/* Settings - self profile only (own name/phone, own password, own
              theme + notification toggles). Nothing admin-scoped lives here
              and the backend endpoints behind it (/auth/profile,
              /auth/change-password) only require authentication, so no
              permission key is required - AdminLayout already requires a
              session, and a dynamic role slug that isn't one of the 4 legacy
              slugs must not be locked out of its own account page. */}
          <Route path="settings" element={withErrorBoundary(<Settings />)} />
        </Route>
      </Routes>
    </Suspense>
  );
};

export default AppRoutes;

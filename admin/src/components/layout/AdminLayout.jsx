import React, { useState, useEffect, useLayoutEffect, useRef, Suspense } from 'react';
import { Outlet, Navigate, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import Header from './Header';
import ErrorBoundary from '../ErrorBoundary';
import PageSkeleton from '../ui/PageSkeleton';
import { skeletonForPath } from '../skeletons/skeletonRoutes';
import { useAuth } from '../../context/AuthContext';
import apiClient from '../../api/client';
import { loadRegion } from '../../utils/region';

// Route-aware skeletons: the layout's fallback mirrors each page's own
// loading skeleton (one dedicated skeleton per sidebar tab), so a refresh
// shows ONE continuous, page-shaped skeleton instead of a generic one being
// swapped for the page's own skeleton. The map itself lives in
// components/skeletons/skeletonRoutes (shared with AppRoutes).
const AdminLayout = () => {
  const { user, isAuthenticated, loading } = useAuth();
  const location = useLocation();
  const { type: skeletonType, props: skeletonProps } = skeletonForPath(location.pathname);
  const mainRef = useRef(null);

  // Open by default on desktop, closed on mobile (drawer mode)
  const [sidebarOpen, setSidebarOpen] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 1024
  );

  // Deployment region (currency/locale/tax label) loads once per session
  // from the public checkout config; formatters fall back to INR defaults
  // until it arrives, then this re-render swaps in live values.
  const [, setRegionReady] = useState(false);
  useEffect(() => {
    loadRegion(apiClient).then(() => setRegionReady(true));
  }, []);

  // The main element owns scrolling in the admin shell. Start every new
  // history entry at the top, including Back/Forward and another order detail.
  useLayoutEffect(() => {
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [location.key]);

  // Auth check finished without a session → go to login
  // (moved here from ProtectedRoute so the layout chrome stays mounted
  // while the /auth/me check runs instead of flashing a blank screen)
  if (!loading && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // Still revalidating a cached session (e.g. right after a page refresh)?
  // Render the real page immediately — no auth skeleton flash. Only
  // first-ever visits (no cached user) get the skeleton.
  const revalidating = loading && !!user;

  return (
    <div className="flex h-dvh bg-background overflow-hidden">
      {/* Mobile backdrop - closes the drawer when clicked */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/40 z-30 lg:hidden"
          aria-hidden="true"
          onClick={() => setSidebarOpen(false)}
        />
      )}
      <Sidebar isOpen={sidebarOpen} setIsOpen={setSidebarOpen} />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0 min-h-0">
        <Header toggleSidebar={() => setSidebarOpen(!sidebarOpen)} />
        <main
          ref={mainRef}
          className="flex-1 overflow-y-auto overscroll-contain overflow-x-clip p-4 sm:p-6 min-w-0"
        >
          <ErrorBoundary>
            {loading && !revalidating ? (
              // First visit with no cached session: skeleton the content
              // area using the same shape as the destination page.
              <PageSkeleton type={skeletonType} {...skeletonProps} />
            ) : (
              // Own Suspense boundary: lazy page chunks resolve HERE so the
              // fallback never replaces the sidebar/header on refresh or
              // navigation. The fallback mirrors the page's own skeleton, so
              // it blends into one continuous skeleton instead of two.
              <Suspense fallback={<PageSkeleton type={skeletonType} {...skeletonProps} />}>
                <Outlet />
              </Suspense>
            )}
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
};

export default AdminLayout;

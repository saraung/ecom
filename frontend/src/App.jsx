import React, { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { loadRegion } from './utils/region';
import { AuthProvider } from './contexts/AuthContext';
import { CartProvider } from './contexts/CartContext';
import { WishlistProvider } from './contexts/WishlistContext';
import { NotificationProvider } from './contexts/NotificationContext';
import AppRoutes from './routes/index.jsx';
import ErrorBoundary from './components/common/ErrorBoundary';
import './index.css';

// Catalog data is cacheable; cart/checkout are not and stay on their existing
// imperative path. `staleTime` keeps a list page from refetching the instant
// the shopper navigates back to it, while `refetchOnWindowFocus: false` avoids
// surprise background requests that would reorder a live catalog.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      gcTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function ThemedToaster() {
  return (
    <Toaster
      position="top-center"
      toastOptions={{
        duration: 4000,
        style: {
          borderRadius: '12px',
          padding: '12px 16px',
          background: 'var(--card)',
          color: 'var(--foreground)',
          border: '1px solid var(--border)',
        },
        success: { iconTheme: { primary: 'var(--success)', secondary: 'var(--card)' } },
        error: { iconTheme: { primary: 'var(--destructive)', secondary: 'var(--card)' } },
      }}
    />
  );
}

/**
 * Loads the deployment region (currency/locale/tax label/country) once at
 * boot and re-renders when it arrives, so first-paint defaults are
 * replaced by live values without any page needing its own fetch.
 */
function RegionGate({ children }) {
  const [, setRegionReady] = useState(false);
  useEffect(() => {
    loadRegion().then(() => setRegionReady(true));
  }, []);
  return children;
}

function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
      <RegionGate>
      <CartProvider>
        <WishlistProvider>
          <AuthProvider>
            <NotificationProvider>
              {/* Global toast host — every toast.error/success/promise call in the app renders here */}
              <ThemedToaster />
              <AppRoutes />
            </NotificationProvider>
          </AuthProvider>
        </WishlistProvider>
      </CartProvider>
      </RegionGate>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
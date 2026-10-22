import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { orderAPI } from '../../api/orders';
import { OrderCard } from '../../components/orders';
import { OrdersListSkeleton } from '../../components/common/Skeleton';

const PAGE_SIZE = 20;

const Orders = () => {
  const [orders, setOrders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const [hasMore, setHasMore] = useState(false);

  const fetchOrders = async (nextSkip = 0, append = false, silent = false) => {
    if (!silent) {
      if (append) {
        setLoadingMore(true);
      } else {
        setLoading(true);
      }
    }
    try {
      const response = await orderAPI.getOrders(nextSkip, PAGE_SIZE);
      const list = Array.isArray(response.data) ? response.data : [];
      setOrders((prev) => (append ? [...prev, ...list] : list));
      setHasMore(list.length === PAGE_SIZE);
      setError(null);
    } catch (err) {
      console.error('Error fetching orders:', err);
      const detail = err.response?.data?.detail;
      if (!silent) setError(typeof detail === 'string' ? detail : 'Failed to load orders');
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    fetchOrders(0);
  }, []);

  const loadMore = () => fetchOrders(orders.length, true);

  if (loading) {
    return (
      <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
        <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
          <div className="mb-8 sm:mb-10 border-b border-border pb-6">
            <div className="animate-pulse h-9 md:h-11 w-48 rounded-xl bg-muted" />
            <div className="animate-pulse h-4 w-72 max-w-full mt-3 rounded-lg bg-muted" />
          </div>
          <OrdersListSkeleton count={3} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background transition-colors duration-700 px-4 py-10">
        <div className="w-full max-w-md text-center p-8 sm:p-10 bg-card rounded-[2.5rem] shadow-sm border border-border">
          <div className="text-4xl mb-4" aria-hidden="true">⚠️</div>
          <h2 className="text-xl sm:text-2xl font-extrabold tracking-tight text-foreground">
            Could not load your orders
          </h2>
          <p className="text-sm text-muted-foreground font-medium mt-2 mb-8">
            {error}
          </p>
          <button
            onClick={() => fetchOrders(0)}
            className="bg-primary text-primary-foreground px-10 py-4 rounded-full text-sm font-bold uppercase tracking-widest hover:scale-105 hover:-translate-y-0.5 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl"
          >
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (orders.length === 0) {
    return (
      <div className="min-h-screen bg-background transition-colors duration-700 px-4 py-10 flex flex-col items-center justify-center">
        <div className="text-center p-8 sm:p-10 bg-card rounded-4xl sm:rounded-[2.5rem] shadow-sm border border-border max-w-md w-full">
          <div className="text-5xl sm:text-6xl mb-6" aria-hidden="true">🛒</div>
          <h2 className="text-xl sm:text-2xl font-extrabold text-foreground mb-2 tracking-tight">
            No orders yet
          </h2>
          <p className="text-sm text-muted-foreground mb-8 font-medium">
            Your orders will appear here once you check out.
          </p>
          <Link
            to="/products"
            className="block w-full bg-primary text-primary-foreground px-6 sm:px-8 py-4 rounded-full font-bold uppercase tracking-widest text-xs sm:text-sm hover:scale-105 transition-all duration-300 shadow-xl"
          >
            Start Shopping
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        {/* Header */}
        <div className="mb-8 sm:mb-10 border-b border-border pb-6">
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">
            My Orders
          </h1>
          <p className="text-sm text-muted-foreground font-medium mt-2">
            Track, review, or manage your recent purchases.
          </p>
        </div>

        <div className="flex flex-col gap-6 sm:gap-8">
          {orders.map((order) => (
            <OrderCard
              key={order.id}
              order={order}
              onOrderStatusChanged={() => fetchOrders(0, false, true)}
            />
          ))}
        </div>

        {hasMore && (
          <div className="text-center mt-12">
            <button
              onClick={loadMore}
              disabled={loadingMore}
              className="bg-primary text-primary-foreground px-10 py-4 rounded-full text-sm font-bold uppercase tracking-widest hover:scale-105 hover:-translate-y-0.5 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl disabled:opacity-60 disabled:cursor-not-allowed disabled:scale-100 disabled:translate-y-0"
            >
              {loadingMore ? 'Loading…' : 'Load More Orders'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Orders;
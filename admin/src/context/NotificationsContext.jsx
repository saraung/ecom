// src/context/NotificationsContext.jsx
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  getNotifications,
  getUnreadNotificationsCount,
  markNotificationRead,
  markAllNotificationsRead,
} from '../api/notifications';
import { useAuth } from './AuthContext';
import { canDo } from '../utils/permissions';

const POLL_INTERVAL_MS = 30000; // poll every 30s
const PAGE_SIZE = 20;

const NotificationsContext = createContext();

/**
 * Normalise the different list shapes a backend may return:
 * [...], { items: [...] }, { data: [...] }, { results: [...], count } etc.
 */
const parseListResponse = (data) => {
  if (!data) return { items: [], total: 0, unreadCount: null };
  if (Array.isArray(data)) {
    return { items: data, total: data.length, unreadCount: null };
  }
  const items = data.items || data.results || data.data || data.notifications || [];
  const safeItems = Array.isArray(items) ? items : [];
  return {
    items: safeItems,
    total: data.total ?? data.count ?? safeItems.length,
    unreadCount: typeof data.unread_count === 'number' ? data.unread_count : null,
  };
};

export const NotificationsProvider = ({ children }) => {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  // Tracks which notifications we have already rendered, so the poller can
  // detect brand-new ones (new orders / cancellations) and toast them.
  const seenIdsRef = useRef(new Set());
  const initializedRef = useRef(false);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) return;
    // Don't fire authenticated polls with no token — the browser would
    // just log 401s for /notifications + /unread-count every 30s.
    if (!localStorage.getItem('access_token')) return;
    if (!initializedRef.current) setLoading(true);

    try {
      const [listResult, countResult] = await Promise.allSettled([
        getNotifications({ skip: 0, limit: PAGE_SIZE }),
        getUnreadNotificationsCount(),
      ]);

      let items = [];
      let totalCount = 0;
      let unread = null;

      if (listResult.status === 'fulfilled') {
        const parsed = parseListResponse(listResult.value?.data);
        items = parsed.items;
        totalCount = parsed.total;
        unread = parsed.unreadCount;
      }
      if (countResult.status === 'fulfilled') {
        const payload = countResult.value?.data;
        const count =
          typeof payload === 'number'
            ? payload
            : payload?.count ?? payload?.unread_count ?? null;
        if (typeof count === 'number') unread = count;
      }

      // Toast brand-new unread notifications (skip the very first load so
      // existing backlog doesn't spam the screen).
      if (initializedRef.current) {
        const fresh = items.filter(
          (n) => n && !n.is_read && !seenIdsRef.current.has(String(n.id))
        );
        fresh.slice(0, 3).forEach((n) => {
          const handleClick = () => openNotification(n);
          const icon = n.type === 'order_cancelled' ? '🚫' : n.type === 'order_placed' ? '🛒' : '📣';
          toast.custom(
            (t) => (
              <button
                type="button"
                onClick={handleClick}
                style={{
                  background: 'var(--card)',
                  color: 'var(--foreground)',
                  border: '1px solid var(--border)',
                  borderRadius: '8px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 12px',
                  textAlign: 'left',
                  width: '340px',
                  maxWidth: 'calc(100vw - 40px)',
                  overflowWrap: 'anywhere',
                }}
              >
                <span style={{ fontSize: '18px', lineHeight: 1, flexShrink: 0 }}>{icon}</span>
                <span style={{ minWidth: 0, lineHeight: 1.35 }}>
                  <strong style={{ display: 'block', fontSize: '12px' }}>{n.title}</strong>
                  {n.message && (
                    <span
                      style={{
                        display: 'block',
                        fontSize: '11px',
                        color: 'var(--muted-foreground)',
                      }}
                    >
                      {n.message}
                    </span>
                  )}
                </span>
              </button>
            ),
            { duration: 5000 }
          );
        });
      }

      items.forEach((n) => n && seenIdsRef.current.add(String(n.id)));
      initializedRef.current = true;

      setNotifications(items);
      setTotal(totalCount);
      setUnreadCount(
        typeof unread === 'number'
          ? unread
          : items.filter((n) => n && !n.is_read).length
      );
    } catch {
      // Polling must fail silently — never spam errors every 30s.
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  // Poll only while logged in; pause when the tab is hidden; refresh
  // immediately when the admin comes back to the window.
  useEffect(() => {
    if (!isAuthenticated) {
      setNotifications([]);
      setUnreadCount(0);
      setTotal(0);
      seenIdsRef.current = new Set();
      initializedRef.current = false;
      return undefined;
    }

    refresh();
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
    }, POLL_INTERVAL_MS);
    const onFocus = () => refresh();
    window.addEventListener('focus', onFocus);

    return () => {
      clearInterval(interval);
      window.removeEventListener('focus', onFocus);
    };
  }, [isAuthenticated, refresh]);

  const markAsRead = useCallback(
    async (notificationId) => {
      // Optimistic update, reconcile with server afterwards.
      setNotifications((prev) =>
        prev.map((n) => (n.id === notificationId ? { ...n, is_read: true } : n))
      );
      setUnreadCount((c) => Math.max(0, c - 1));
      try {
        await markNotificationRead(notificationId);
      } catch {
        refresh();
        toast.error('Failed to mark notification as read');
      }
    },
    [refresh]
  );

  const markAllAsRead = useCallback(async () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    try {
      await markAllNotificationsRead();
    } catch {
      refresh();
      toast.error('Failed to mark all as read');
    }
  }, [refresh]);

  // Clicking a toast opens its target (order detail page, promotional link…)
  // and marks the notification as read. Targets needing a permission the
  // session lacks are refused inline instead of landing on a wall.
  const targetPerm = (target) => {
    if (!target) return null;
    const path = target.split('?')[0];
    if (path.startsWith('/orders')) return 'orders.view';
    if (path.startsWith('/refunds')) return 'orders.refund';
    if (path.startsWith('/returns')) return 'orders.view';
    if (path.startsWith('/promotions')) return 'promotions.send';
    if (path.startsWith('/coupons')) return 'coupons.view';
    if (path.startsWith('/users')) return 'users.view';
    if (path.startsWith('/invites')) return 'users.manage_roles';
    if (path.startsWith('/reviews')) return 'reviews.moderate';
    return null;
  };

  const openNotification = useCallback(
    (n) => {
      if (n.id != null && !n.is_read) markAsRead(n.id);
      const target = n.link || (n.order_id ? `/orders/${n.order_id}` : null);
      toast.dismiss();
      if (!target) return;
      const perm = targetPerm(target);
      if (perm && !canDo(user, perm)) {
        toast.error("You don't have permission to open this notification");
        return;
      }
      navigate(target);
    },
    [navigate, markAsRead, user]
  );

  const value = {
    notifications,
    unreadCount,
    total,
    loading,
    refresh,
    markAsRead,
    markAllAsRead,
  };

  return (
    <NotificationsContext.Provider value={value}>
      {children}
    </NotificationsContext.Provider>
  );
};

export const useNotifications = () => {
  const context = useContext(NotificationsContext);
  if (!context) {
    throw new Error('useNotifications must be used within NotificationsProvider');
  }
  return context;
};
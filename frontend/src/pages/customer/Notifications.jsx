// src/pages/customer/Notifications.jsx
import React, { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import notificationService from '../../services/notificationService';
import { useNotifications } from '../../contexts/NotificationContext';
import { formatDateTime } from '../../utils/format';

const Notifications = () => {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const { subscribe } = useNotifications();
  const navigate = useNavigate();

  const refresh = useCallback(async () => {
    try {
      const items = await notificationService.getFeed(0, 50);
      setNotifications(items);
    } catch (error) {
      console.error('Failed to load notifications:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Live push from the shared WebSocket singleton (one socket per user,
  // owned by NotificationProvider) — prepend anything that arrives.
  useEffect(() => {
    return subscribe((notification) => {
      setNotifications((prev) =>
        prev.some((n) => n.id === notification.id)
          ? prev
          : [notification, ...prev]
      );
    });
  }, [subscribe]);

  // ✅ Poll while this page is open so new notifications appear without a refresh
  //    (the WebSocket push covers this when the backend supports it). 12s interval,
  //    and reload immediately when the tab becomes visible again.
  useEffect(() => {
    const poll = () => {
      if (document.visibilityState === 'visible') {
        refresh();
      }
    };
    const interval = setInterval(poll, 12000);
    document.addEventListener('visibilitychange', poll);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', poll);
    };
  }, [refresh]);

  const handleClick = async (notification) => {
    if (!notification.is_read) {
      try {
        await notificationService.markAsRead(notification.id);
        setNotifications((prev) =>
          prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
        );
      } catch (error) {
        console.error('Failed to mark notification as read:', error);
      }
    }
    // ✅ Deep-link when the backend provides one, fall back to the order page.
    //    Leading "/" is enforced so relative backend links resolve from the root
    //    instead of stacking onto the current path.
    if (notification.link) {
      const link = notification.link.startsWith('/') || /^(https?:|mailto:|tel:|#|\?)/i.test(notification.link)
        ? notification.link
        : `/${notification.link}`;
      navigate(link);
    } else if (notification.order_id) {
      navigate(`/orders/${notification.order_id}`);
    }
  };

  const handleDelete = async (notificationId) => {
    try {
      await notificationService.deleteNotification(notificationId);
      setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
    } catch (error) {
      console.error('Failed to delete notification:', error);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await notificationService.markAllAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  return (
    <div className="max-w-4xl mx-auto px-4 py-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 mb-5">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-foreground">Notifications</h1>
          {unreadCount > 0 && (
            <span className="badge badge-danger text-sm font-bold px-2 py-0.5 rounded-full">
              {unreadCount} unread
            </span>
          )}
        </div>
        {unreadCount > 0 && (
          <button
            onClick={handleMarkAllRead}
            className="text-sm text-accent bg-transparent border-none cursor-pointer no-underline"
          >
            Mark all as read
          </button>
        )}
      </div>

      {loading ? (
        <div className="min-h-[40vh] flex items-center justify-center">
          <div className="text-center">
            <div className="inline-block w-8 h-8 border-2 border-input border-t-foreground animate-spin rounded-full"></div>
            <p className="mt-3 text-muted-foreground">Loading notifications...</p>
          </div>
        </div>
      ) : notifications.length === 0 ? (
        <div className="border border-border p-12 text-center max-w-md mx-auto bg-card">
          <div className="text-5xl mb-3">🔔</div>
          <h2 className="text-xl font-bold text-foreground mb-1">No notifications yet</h2>
          <p className="text-muted-foreground mb-4">
            We'll keep you posted — order updates, promotions and more land here.
          </p>
          <Link
            to="/products"
            className="inline-block bg-primary text-primary-foreground px-6 py-2 font-medium no-underline"
          >
            Browse Products
          </Link>
        </div>
      ) : (
        <div className="bg-card border border-border">
          {notifications.map((notification) => (
            <div
              key={notification.id}
              role="button"
              tabIndex={0}
              onClick={() => handleClick(notification)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  handleClick(notification);
                }
              }}
              className={`flex items-start gap-3 p-4 border-b border-border cursor-pointer transition-colors ${
                notification.is_read ? 'bg-background hover:bg-muted' : 'bg-primary-soft hover:bg-primary-soft'
              }`}
            >
              <span className="text-xl shrink-0 mt-0.5">
                {notification.type === 'promotion' ? '📣' : '🔔'}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {!notification.is_read && (
                    <span className="w-2 h-2 rounded-full dot-accent shrink-0" />
                  )}
                  <p
                    className={`text-sm ${
                      notification.is_read
                        ? 'font-medium text-foreground'
                        : 'font-bold text-foreground'
                    }`}
                  >
                    {notification.title}
                  </p>
                </div>
                <p className="text-sm text-muted-foreground mt-0.5">{notification.message}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {formatDateTime(notification.created_at)}
                </p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDelete(notification.id);
                }}
                aria-label="Delete notification"
                className="shrink-0 bg-transparent border-none cursor-pointer text-muted-foreground hover:text-muted-foreground"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default Notifications;

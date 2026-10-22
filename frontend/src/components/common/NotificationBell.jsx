// src/components/common/NotificationBell.jsx
// ⚠️ Not currently wired into the app — the header bell lives in
//    src/components/layout/Header.jsx. Kept aligned with the customer
//    notification API so it can be dropped in if needed.
//    GET /notifications, GET /notifications/unread-count,
//    PUT /notifications/{id}/read, PUT /notifications/mark-all-read,
//    DELETE /notifications/{id}
import React, { useState, useEffect, useCallback } from 'react';
import notificationService from '../../services/notificationService';
import { useNotifications } from '../../contexts/NotificationContext';

const NotificationBell = () => {
  const [notifications, setNotifications] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const { subscribe } = useNotifications();

  const refresh = useCallback(async () => {
    const [feed, count] = await Promise.allSettled([
      notificationService.getFeed(0, 20),
      notificationService.getUnreadCount(),
    ]);
    if (feed.status === 'fulfilled') setNotifications(feed.value);
    if (count.status === 'fulfilled') setUnreadCount(count.value);
  }, []);

  useEffect(() => {
    refresh();

    // 12s polling refresh while the tab is visible (instant reload when it becomes visible)
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') refresh();
    }, 12000);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    // Optional real-time push (the WebSocket connection is owned by the
    // shared notification singleton via NotificationProvider)
    const removeListener = subscribe((notification) => {
      setNotifications((prev) =>
        prev.some((n) => n.id === notification.id) ? prev : [notification, ...prev]
      );
      if (!notification.is_read) {
        setUnreadCount((u) => u + 1);
      }
    });

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
      removeListener();
    };
  }, [refresh, subscribe]);

  const handleNotificationClick = async (notification) => {
    if (!notification.is_read) {
      await notificationService.markAsRead(notification.id).catch(() => {});
      setUnreadCount((prev) => Math.max(0, prev - 1));
      setNotifications((prev) =>
        prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n))
      );
    }
    setShowDropdown(false);
    if (notification.link) {
      const link = notification.link.startsWith('/') || /^(https?:|mailto:|tel:|#|\?)/i.test(notification.link)
        ? notification.link
        : `/${notification.link}`;
      window.location.href = link;
    } else if (notification.order_id) {
      window.location.href = `/orders/${notification.order_id}`;
    }
  };

  const handleDelete = async (notificationId) => {
    await notificationService.deleteNotification(notificationId).catch(() => {});
    const removed = notifications.find((n) => n.id === notificationId);
    setNotifications((prev) => prev.filter((n) => n.id !== notificationId));
    if (removed && !removed.is_read) {
      setUnreadCount((u) => Math.max(0, u - 1));
    }
  };

  const handleMarkAllRead = async () => {
    await notificationService.markAllAsRead().catch(() => {});
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
  };

  return (
    <div className="relative">
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="relative p-2 text-muted-foreground hover:text-foreground"
        aria-label="Notifications"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-destructive/100 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
            {unreadCount}
          </span>
        )}
      </button>

      {showDropdown && (
        <div className="absolute right-0 mt-2 w-80 bg-card rounded-lg shadow-xl border z-50">
          <div className="flex items-center justify-between p-4 border-b">
            <h3 className="font-semibold">Notifications</h3>
            {unreadCount > 0 && (
              <button
                onClick={handleMarkAllRead}
                className="text-xs text-blue-600 bg-none border-none cursor-pointer no-underline"
              >
                Mark all as read
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">No notifications</div>
            ) : (
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleNotificationClick(notification)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleNotificationClick(notification);
                    }
                  }}
                  className={`w-full text-left p-4 border-b ${
                    !notification.is_read ? 'bg-primary-soft' : 'hover:bg-background'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <p className="font-medium text-sm flex-1">{notification.title}</p>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(notification.id);
                      }}
                      aria-label="Delete notification"
                      className="bg-transparent border-none cursor-pointer text-muted-foreground"
                    >
                      ✕
                    </button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">{notification.message}</p>
                  <p className="text-xs text-muted-foreground mt-1">
                    {notification.created_at
                      ? new Date(notification.created_at).toLocaleDateString()
                      : ''}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default NotificationBell;

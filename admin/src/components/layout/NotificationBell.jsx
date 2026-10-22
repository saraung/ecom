// src/components/layout/NotificationBell.jsx
import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import {
  Bell,
  ShoppingBag,
  Ban,
  Megaphone,
  CheckCheck,
  RefreshCw,
  Inbox,
} from 'lucide-react';
import { useNotifications } from '../../context/NotificationsContext';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import { formatDate } from '../../utils/format';

const TYPE_CONFIG = {
  order_placed: {
    icon: ShoppingBag,
    className: 'text-success bg-success/15',
    label: 'New order',
  },
  order_cancelled: {
    icon: Ban,
    className: 'text-destructive bg-destructive/15',
    label: 'Order cancelled',
  },
  promotion: {
    icon: Megaphone,
    className: 'text-warning bg-warning/20',
    label: 'Promotion',
  },
};

const getIconConfig = (notification) =>
  TYPE_CONFIG[notification?.type] || {
    icon: Bell,
    className: 'text-primary bg-primary-soft',
  };

const formatTimeAgo = (dateString) => {
  if (!dateString) return '';
  const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return formatDate(dateString, {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
};

const NotificationBell = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const {
    notifications,
    unreadCount,
    total,
    refresh,
    markAsRead,
    markAllAsRead,
  } = useNotifications();
  const [open, setOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const containerRef = useRef(null);

  // Close the panel on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined;
    const handleOutside = (event) => {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false);
      }
    };
    const handleKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', handleOutside);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
      document.removeEventListener('keydown', handleKey);
    };
  }, [open]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await refresh();
    setRefreshing(false);
  };

  // Route prefix → permission needed to open it. Clicking a target
  // you can't open used to land on the Unauthorized wall (or nowhere
  // when the item had no target at all) — instead explain inline.
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

  const openTarget = (notification) => {
    // Reading the item always marks it read — even when there is
    // nowhere to navigate (e.g. informational notifications).
    if (notification.id != null && !notification.is_read) {
      markAsRead(notification.id);
    }
    const target =
      notification.link || (notification.order_id ? `/orders/${notification.order_id}` : null);
    if (!target) return false;
    const perm = targetPerm(target);
    if (perm && !canDo(user, perm)) {
      toast.error("You don't have permission to open this notification");
      return false;
    }
    navigate(target);
    return true;
  };

  const handleItemClick = (notification) => {
    setOpen(false);
    openTarget(notification);
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="relative w-9 h-9 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        title="Notifications"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute top-0.5 right-0.5 bg-destructive text-white text-[10px] font-semibold rounded-full min-w-[18px] h-[18px] px-1 flex items-center justify-center">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed left-4 right-4 top-[4.5rem] w-auto sm:absolute sm:left-auto sm:right-0 sm:top-full sm:mt-2 sm:w-96 bg-card border border-border rounded-xl shadow-lg z-50 overflow-hidden">
          {/* Panel header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-foreground">Notifications</h3>
              {unreadCount > 0 && (
                <span className="text-xs bg-destructive/15 text-destructive px-2 py-0.5 rounded-full font-medium">
                  {unreadCount} new
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={handleRefresh}
                className="p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                title="Refresh"
              >
                <RefreshCw size={15} className={refreshing ? 'animate-spin' : ''} />
              </button>
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded transition-colors"
                  title="Mark all as read"
                >
                  <CheckCheck size={15} />
                  <span className="hidden sm:inline">Mark all read</span>
                </button>
              )}
            </div>
          </div>

          {/* List */}
          <div className="max-h-96 overflow-y-auto divide-y divide-border">
            {notifications.length === 0 ? (
              <div className="py-10 text-center">
                <Inbox size={28} className="mx-auto text-muted-foreground mb-2" />
                <p className="text-sm text-muted-foreground">No notifications yet</p>
                <p className="text-xs text-muted-foreground mt-1">
                  New orders and cancellations will appear here
                </p>
              </div>
            ) : (
              notifications.map((notification) => {
                const { icon: Icon, className } = getIconConfig(notification);
                return (
                  <button
                    key={notification.id}
                    onClick={() => handleItemClick(notification)}
                    className={`w-full text-left px-4 py-3 flex items-start gap-3 transition-colors hover:bg-muted ${
                      !notification.is_read ? 'bg-primary-soft/40' : ''
                    }`}
                  >
                    <span
                      className={`w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 ${className}`}
                    >
                      <Icon size={17} />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-foreground truncate">
                          {notification.title || 'Notification'}
                        </span>
                        <span className="text-[11px] text-muted-foreground flex-shrink-0">
                          {formatTimeAgo(notification.created_at)}
                        </span>
                      </span>
                      {notification.message && (
                        <span className="block text-xs text-muted-foreground mt-0.5 line-clamp-2">
                          {notification.message}
                        </span>
                      )}
                    </span>
                    {!notification.is_read && (
                      <span className="w-2 h-2 rounded-full bg-primary flex-shrink-0 mt-1.5" />
                    )}
                  </button>
                );
              })
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="px-4 py-2 border-t border-border text-center">
              <span className="text-xs text-muted-foreground">
                Showing latest {notifications.length} of {total}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;

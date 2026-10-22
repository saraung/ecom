import api from '../api/axios';
import { refreshSession, hardLogout } from '../api/session';
import { WS_ORIGIN } from '../api/config';

// ============================================================
// Normalize a backend-provided link so it can be handed to
// Router's navigate() / window.location safely.
//
// Backend links may be app-relative ("products/…"), and passing
// those straight to navigate() resolves them against the CURRENT
// route. App-internal paths are forced to start with "/" so they
// resolve from the root.
// ============================================================

const normalizeLink = (link) => {
  if (!link) return '';

  // Leave absolute URLs, hash links, protocol links and query-only links untouched
  if (/^(https?:|mailto:|tel:|#|\?)/i.test(link)) {
    return link;
  }

  return link.startsWith('/') ? link : `/${link}`;
};

// ============================================================
// Canonical notification shape used by the user-app UI:
//
// {
//   id,
//   type,
//   title,
//   message,
//   link,
//   order_id,
//   is_read,
//   created_at
// }
//
// Legacy WebSocket payloads (read/body/timestamp/data) are
// normalized too.
// ============================================================

const normalizeNotification = (n) => {
  if (!n) return n;

  return {
    ...n,

    is_read:
      typeof n.is_read === 'boolean'
        ? n.is_read
        : typeof n.read === 'boolean'
          ? n.read
          : false,

    message: n.message ?? n.body ?? '',

    link: normalizeLink(
      n.link ??
      n.data?.url ??
      n.data?.link ??
      ''
    ),

    created_at: n.created_at ?? n.timestamp ?? null,
  };
};

// ============================================================
// Accept any feed shape the backend may return:
//
// - plain array
// - { items: [...] }
// - { results: [...] }
// - { data: [...] }
// ============================================================

const normalizeFeed = (payload) => {
  const list = Array.isArray(payload)
    ? payload
    : payload?.items ??
      payload?.results ??
      payload?.data ??
      [];

  return list.map(normalizeNotification);
};

// ============================================================
// Notification Service (module-level singleton)
//
// Owns exactly ONE WebSocket per logged-in user. React triggers
// connect()/disconnect() via NotificationContext; the service
// dedupes connections and reconnects (with backoff) only on an
// actual drop. Close 4401 refreshes the token before reconnecting.
// ============================================================

const RECONNECT_DELAYS = [1000, 2000, 4000];
const HEARTBEAT_INTERVAL = 25000;

class NotificationService {
  constructor() {
    this.ws = null;
    this.listeners = new Set();
    this.statusListeners = new Set();
    this.userId = null;
    this.connectedUserId = null;
    this.enabled = false;
    this.manualClose = false;
    this.reconnectAttempts = 0;
    this.reconnectTimeout = null;
    this.pingInterval = null;
    this.generation = 0;
    this.status = 'DISCONNECTED';
  }

  setStatus(next) {
    if (next === this.status) return;
    this.status = next;
    this.statusListeners.forEach((listener) => {
      try {
        listener(next);
      } catch {
        // ignore listener errors
      }
    });
  }

  // ============================================================
  // Connect — idempotent. No-op if a socket is already
  // OPEN/CONNECTING for the same user.
  // ============================================================

  connect({ userId, token } = {}) {
    const targetUser = userId || this.userId;
    const accessToken =
      token || localStorage.getItem('access_token');

    if (!targetUser || !accessToken) {
      console.warn(
        '🔔 Cannot connect: missing userId or access_token'
      );
      return;
    }

    this.userId = targetUser;
    this.enabled = true;
    this.manualClose = false;

    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING) &&
      this.connectedUserId === targetUser
    ) {
      return;
    }

    this.cancelReconnect();

    if (this.ws) {
      this.teardownSocket(this.ws);
    }

    this.openSocket(accessToken, targetUser);
  }

  openSocket(token, userId) {
    const generation = ++this.generation;

    const wsUrl =
      `${WS_ORIGIN}/api/v1/notifications/ws?token=${encodeURIComponent(token)}`;

    let socket;
    try {
      socket = new WebSocket(wsUrl);
    } catch (error) {
      console.error('🔔 Failed to create WebSocket:', error);
      this.ws = null;
      this.scheduleReconnect();
      return;
    }

    this.ws = socket;
    this.connectedUserId = userId;
    this.setStatus('CONNECTING');

    socket.onopen = () => {
      if (generation !== this.generation) {
        socket.close(1000, 'Stale connection');
        return;
      }

      this.reconnectAttempts = 0;
      this.setStatus('CONNECTED');
      this.startHeartbeat();

      if (socket.readyState === WebSocket.OPEN) {
        socket.send(
          JSON.stringify({
            user_id: userId,
            type: 'register',
          })
        );
      }
    };

    socket.onmessage = (event) => {
      const raw = event.data;

      // Raw text ping → answer with pong to keep the server-side
      // keepalive happy.
      if (raw === 'ping') {
        this.replyPong(socket);
        return;
      }

      if (raw === 'pong') {
        return;
      }

      let payload;
      try {
        payload = JSON.parse(raw);
      } catch {
        return;
      }

      if (payload?.type === 'ping') {
        this.replyPong(socket);
        return;
      }

      if (payload?.type === 'connected') {
        this.setStatus('CONNECTED');
        return;
      }

      this.notifyListeners(normalizeNotification(payload));
    };

    socket.onerror = () => {
      // onclose always follows onerror; reconnect is handled there.
    };

    socket.onclose = (event) => {
      if (generation !== this.generation) {
        return;
      }

      this.ws = null;
      this.connectedUserId = null;
      this.stopHeartbeat();
      this.setStatus('DISCONNECTED');
      this.handleClose(event);
    };
  }

  // ============================================================
  // Close handling — reconnect ONLY on an actual drop.
  // ============================================================

  handleClose(event) {
    if (!this.enabled || this.manualClose) {
      return;
    }

    // 1000/1001 = our own close or intentional server close.
    if (event.code === 1000 || event.code === 1001) {
      return;
    }

    // 4401 = token invalid/expired → refresh, then reconnect.
    if (event.code === 4401) {
      this.refreshAndReconnect();
      return;
    }

    this.scheduleReconnect();
  }

  scheduleReconnect() {
    if (!this.enabled || this.manualClose || this.ws) {
      return;
    }

    const index = Math.min(
      this.reconnectAttempts,
      RECONNECT_DELAYS.length - 1
    );
    const delay = RECONNECT_DELAYS[index];
    this.reconnectAttempts += 1;

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null;
      if (!this.enabled || this.manualClose) return;
      this.connect({ userId: this.userId });
    }, delay);
  }

  async refreshAndReconnect() {
    try {
      const token = await refreshSession();

      if (!token) {
        this.disconnect();
        hardLogout();
        return;
      }

      if (this.enabled && !this.manualClose) {
        this.connect({ userId: this.userId, token });
      }
    } catch (error) {
      console.warn(
        '🔔 Token refresh failed:',
        error?.response?.status || error?.message || error
      );
      if (this.enabled && !this.manualClose) {
        this.scheduleReconnect();
      }
    }
  }

  // ============================================================
  // Disconnect — marks the socket as intentionally closed so no
  // reconnect is scheduled.
  // ============================================================

  disconnect() {
    this.enabled = false;
    this.manualClose = true;

    this.cancelReconnect();
    this.stopHeartbeat();

    if (this.ws) {
      this.teardownSocket(this.ws);
    }

    this.reconnectAttempts = 0;
    this.userId = null;
    this.connectedUserId = null;
    this.setStatus('DISCONNECTED');
  }

  teardownSocket(socket) {
    this.generation += 1;
    this.ws = null;

    try {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;

      if (
        socket.readyState === WebSocket.OPEN ||
        socket.readyState === WebSocket.CONNECTING
      ) {
        socket.close(1000, 'Disconnected');
      }
    } catch {
      // ignore cleanup errors
    }
  }

  cancelReconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  // ============================================================
  // Keepalive — application-level ping → pong plus a client
  // heartbeat to avoid idle drops by proxies/servers.
  // ============================================================

  startHeartbeat() {
    this.stopHeartbeat();
    this.pingInterval = setInterval(
      () => this.sendPing(),
      HEARTBEAT_INTERVAL
    );
  }

  stopHeartbeat() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  sendPing() {
    const socket = this.ws;
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send('ping');
      } catch {
        // ignore
      }
    }
  }

  replyPong(socket) {
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send('pong');
      } catch {
        // ignore
      }
    }
  }

  // ============================================================
  // Listeners
  // ============================================================

  addListener(callback) {
    this.listeners.add(callback);
    return () => {
      this.listeners.delete(callback);
    };
  }

  addStatusListener(callback) {
    this.statusListeners.add(callback);
    return () => {
      this.statusListeners.delete(callback);
    };
  }

  notifyListeners(notification) {
    this.listeners.forEach((listener) => {
      try {
        listener(notification);
      } catch (error) {
        console.error(
          '🔔 Listener error:',
          error?.message || error
        );
      }
    });
  }

  // ============================================================
  // Get notification feed
  //
  // Backend route:
  //   @router.get("")
  //
  // Canonical URL:
  //   /api/v1/notifications
  //
  // IMPORTANT: No trailing slash.
  // ============================================================

  // Storefront bell: shopper audience only (own order updates +
  // promotions). Staff operational alerts stay in the admin panel bell.
  async getFeed(skip = 0, limit = 20) {
    try {
      const response = await api.get('/notifications', {
        params: { skip, limit, audience: 'shopper' },
      });
      return normalizeFeed(response.data);
    } catch (error) {
      console.error(
        '🔔 Failed to fetch notification feed:',
        error
      );
      return [];
    }
  }

  // ============================================================
  // Alias kept for existing callers
  // ============================================================

  async getHistory(skip = 0, limit = 20) {
    return this.getFeed(skip, limit);
  }

  // ============================================================
  // Mark notification as read
  //
  // Backend route:
  //   @router.put("/{notification_id}/read")
  //
  // Canonical URL:
  //   /api/v1/notifications/{id}/read
  //
  // IMPORTANT: No trailing slash.
  // ============================================================

  async markAsRead(notificationId) {
    try {
      const response = await api.put(
        `/notifications/${notificationId}/read`
      );
      return response.data;
    } catch (error) {
      console.error(
        '🔔 Failed to mark notification as read:',
        error
      );
      throw error;
    }
  }

  // ============================================================
  // Mark all notifications as read
  //
  // Backend route:
  //   @router.put("/mark-all-read")
  //
  // Canonical URL:
  //   /api/v1/notifications/mark-all-read
  //
  // IMPORTANT: No trailing slash.
  // ============================================================

  async markAllAsRead() {
    try {
      const response = await api.put(
        '/notifications/mark-all-read',
        null,
        { params: { audience: 'shopper' } }
      );
      return response.data;
    } catch (error) {
      console.error(
        '🔔 Failed to mark all notifications as read:',
        error
      );
      throw error;
    }
  }

  // ============================================================
  // Get unread count
  //
  // Backend route:
  //   @router.get("/unread-count")
  //
  // Canonical URL:
  //   /api/v1/notifications/unread-count
  //
  // IMPORTANT: No trailing slash.
  // ============================================================

  async getUnreadCount() {
    try {
      const response = await api.get(
        '/notifications/unread-count',
        { params: { audience: 'shopper' } }
      );
      const data = response.data;

      if (typeof data === 'number') {
        return data;
      }

      return data?.count ?? data?.unread_count ?? 0;
    } catch (error) {
      console.error(
        '🔔 Failed to get unread count:',
        error
      );
      return 0;
    }
  }

  // ============================================================
  // Delete notification
  //
  // Backend route:
  //   @router.delete("/{notification_id}")
  //
  // Canonical URL:
  //   /api/v1/notifications/{id}
  //
  // IMPORTANT: No trailing slash.
  // ============================================================

  async deleteNotification(notificationId) {
    try {
      const response = await api.delete(
        `/notifications/${notificationId}`
      );
      return response.data;
    } catch (error) {
      console.error(
        '🔔 Failed to delete notification:',
        error
      );
      throw error;
    }
  }

  // ============================================================
  // Get WebSocket connection status
  // ============================================================

  getConnectionStatus() {
    return this.status;
  }
}

// ============================================================
// Create singleton instance
// ============================================================

const notificationService = new NotificationService();

// ============================================================
// Export default
// ============================================================

export default notificationService;

// ============================================================
// Export class for testing
// ============================================================

export { NotificationService };
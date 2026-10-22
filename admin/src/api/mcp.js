// src/api/mcp.js
import apiClient, { API_BASE_URL, refreshSession } from './client';

// MCP agent chat. Auth reuses the shared apiClient interceptor (Bearer
// access token + transparent refresh) — no token handling here.
// `history` is prior turns [{ role: 'user'|'assistant', content }] so
// follow-ups ("next 5") resolve against the conversation.
export const sendMcpChat = (message, history = [], signal) => {
  return apiClient.post('/mcp/chat', { message, history }, signal ? { signal } : undefined);
};

// SSE twin of sendMcpChat. fetch (not axios) so the response body can be
// consumed as a stream; the shared 401 refresh is applied manually once.
// Callbacks: onStep, onToken, onFinal, onError (all optional). Resolves when
// the stream ends; throws on network/abort errors (AbortError propagates).
export const streamMcpChat = async (message, history = [], options = {}) => {
  const { signal, onStep, onToken, onFinal, onError } = options;

  const doFetch = (token) =>
    fetch(`${API_BASE_URL}/mcp/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ message, history }),
      signal,
    });

  let response = await doFetch(localStorage.getItem('access_token'));

  if (response.status === 401) {
    const newToken = await refreshSession();
    if (!newToken) {
      throw new Error('Session expired');
    }
    response = await doFetch(newToken);
  }

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => '');
    const error = new Error(text || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }

  const dispatch = (rawEvent) => {
    let eventName = 'message';
    const dataLines = [];
    for (const line of rawEvent.split('\n')) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).replace(/^ /, ''));
      }
    }
    if (dataLines.length === 0) return;

    let payload;
    try {
      payload = JSON.parse(dataLines.join('\n'));
    } catch {
      return; // ignore malformed frame; stream continues
    }

    const type = payload.type || eventName;
    if (type === 'step' && onStep) onStep(payload);
    else if (type === 'token' && onToken) onToken(payload);
    else if (type === 'final' && onFinal) onFinal(payload);
    else if (type === 'error' && onError) onError(payload);
  };

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    // Normalize CRLF so proxies that rewrite line endings can't hide the
    // blank-line frame separator.
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');

    let sep;
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      if (rawEvent.trim()) dispatch(rawEvent);
    }
  }

  buffer += decoder.decode();
  if (buffer.trim()) dispatch(buffer);
};

// Execute a button-confirmed cancellation. Auth reuses the interceptor;
// the preview_token binds the click to a fresh, validated preview.
export const confirmMcpCancel = ({ order_id, preview_token, reason = '' }) => {
  return apiClient.post('/mcp/cancel', { order_id, preview_token, reason });
};

// Execute a button-confirmed refund. The preview_token binds the click to
// a fresh preview (same user/order/amount/reason); amount and reason must
// match the preview or the backend rejects the request.
export const confirmMcpRefund = ({ order_id, amount, reason = '', preview_token }) => {
  return apiClient.post('/mcp/refund', { order_id, amount, reason, preview_token });
};

// Generic executor for button-confirmed MCP write previews. Auth reuses
// the interceptor; the preview_token binds the click to a fresh preview
// that the backend revalidates (user, target, exact changes, fingerprint).
export const executeMcpWrite = (endpoint, payload) => {
  return apiClient.post(`/mcp/${endpoint}`, payload);
};

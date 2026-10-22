// src/pages/McpAgent/McpAgent.jsx
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Send, Loader, History, Plus, Square, Trash2, ExternalLink, X, RotateCcw } from 'lucide-react';
import toast from 'react-hot-toast';
import {
  sendMcpChat,
  streamMcpChat,
  confirmMcpCancel,
  confirmMcpRefund,
  executeMcpWrite,
} from '../../api/mcp';
import AssistantMarkdown from './Markdown';
import ProductCards from './ProductCard';
import { useAuth } from '../../context/AuthContext';
import {
  DEFAULT_TITLE,
  chatOwnerKey,
  deleteConversation,
  emptyStore,
  loadStore,
  restoreConversation,
  retitleConversation,
  sanitizeProductCard,
  saveActiveMessages,
  setActiveConversation,
  startConversation,
  titleFromMessages,
  toLlmHistory,
} from '../../utils/mcpChatStore';

// Conversation thread list (shared by the desktop sidebar and the
// mobile overlay drawer — one component, two placements).
const ThreadList = ({ conversations, activeId, busy, onSwitch, onDelete, onClose }) => (
  <>
    <div className="px-3 py-2.5 border-b border-border flex items-center justify-between shrink-0">
      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        Conversations
      </span>
      <span className="flex items-center gap-1">
        <span className="text-[11px] text-muted-foreground">{conversations.length}</span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close history"
            className="lg:hidden p-1 -mr-1 text-muted-foreground hover:text-foreground rounded-md hover:bg-muted"
          >
            <X size={16} />
          </button>
        )}
      </span>
    </div>
    <div className="overflow-y-auto overscroll-contain py-1.5 min-h-0 flex-1">
      {conversations.length === 0 && (
        <p className="px-3 py-4 text-xs text-muted-foreground">No saved conversations yet.</p>
      )}
      {conversations.map((conv) => {
        const isActive = conv.id === activeId;
        return (
          <div
            key={conv.id}
            className={`group flex items-center gap-1 mx-1.5 rounded-lg ${
              isActive ? 'bg-primary-soft' : 'hover:bg-muted'
            }`}
          >
            <button
              type="button"
              onClick={() => onSwitch(conv.id)}
              disabled={busy}
              title={conv.title}
              className="flex-1 min-w-0 text-left px-2.5 py-2 disabled:opacity-50"
            >
              <span
                className={`block truncate text-[13px] ${
                  isActive ? 'text-primary font-medium' : 'text-foreground'
                }`}
              >
                {conv.title}
              </span>
              <span className="block text-[11px] text-muted-foreground">
                {threadTime(conv.updatedAt)}
              </span>
            </button>
            <button
              type="button"
              aria-label={`Delete ${conv.title}`}
              onClick={() => onDelete(conv.id)}
              disabled={busy}
              className="p-1.5 mr-1 rounded-md text-muted-foreground hover:text-destructive transition disabled:opacity-50 lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100"
            >
              <Trash2 size={14} />
            </button>
          </div>
        );
      })}
    </div>
  </>
);

// Admin chat page for the MCP agent. Auth reuses the shared apiClient
// interceptor (Bearer access token + refresh) — this page never reads,
// stores, or refreshes the JWT itself.
const SUGGESTIONS = [
  'Show the status of my last order',
  'How many pending orders are there?',
  "Show today's orders",
];

// Static placeholder reply — deliberately generic: no fake database results.
const PLACEHOLDER_REPLY =
  'MCP wiring is not connected yet. Your message was captured locally and nothing was sent to the server.';

const extractError = (error) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (error?.response?.status === 401) return 'Your session expired. Please sign in again.';
  if (error?.response?.status === 403) return 'You do not have permission to use the MCP agent.';
  if (error?.response) return 'Something went wrong. Please try again.';
  // Non-axios errors come from the SSE path (streamMcpChat): the backend's
  // `error` frame message, an HTTP status, or a network failure.
  if (error?.status === 401) return 'Your session expired. Please sign in again.';
  if (error?.status === 403) return 'You do not have permission to use the MCP agent.';
  if (error?.message === 'Session expired') return 'Your session expired. Please sign in again.';
  // Backend `error` frame from the SSE stream carries a user-safe message.
  if (error?.agentMessage) return error.agentMessage;
  if (error?.status) return 'Something went wrong. Please try again.';
  return 'Could not reach the server. Check your connection and try again.';
};

// Compact relative timestamp for thread rows (Today 14:02 / Yesterday 09:15 / Oct 3).
const threadTime = (ts) => {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return '';
  const now = new Date();
  const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  if (d.toDateString() === now.toDateString()) return time;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday ${time}`;
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
};

// Button-confirmed MCP write previews (product/inventory tools). Each
// entry maps the pending_action tool to its executor endpoint, the
// payload the backend revalidates, and the UI labels. Cancel/refund
// keep their dedicated handlers; behavior there is unchanged.
const WRITE_ACTIONS = {
  update_product: {
    endpoint: 'products/update',
    confirmLabel: 'Confirm Update',
    payload: (action) => ({
      product_id: action.product?.id,
      changes: action.changes,
      preview_token: action.preview_token,
    }),
    title: (action) => `Apply these changes to ${action.product?.name || 'this product'}?`,
    successText: (data, action) =>
      `Product ${data.product?.name || action.product?.name || ''} updated.`.trim(),
  },
  update_product_price: {
    endpoint: 'products/price',
    confirmLabel: 'Confirm Price Change',
    payload: (action) => ({
      product_id: action.product?.id,
      price: action.changes?.price,
      compare_at_price: action.changes?.compare_at_price,
      variant_id: action.variant?.id || null,
      preview_token: action.preview_token,
    }),
    title: (action) => `Change the price${action.variant ? ` of ${action.variant.sku}` : ''}${
      action.product?.name ? ` (${action.product.name})` : ''
    }?`,
    successText: (data, action) =>
      `Price updated${action.variant ? ` for ${action.variant.sku}` : ''}.`.trim(),
  },
  delete_product: {
    endpoint: 'products/delete',
    confirmLabel: 'Confirm Deactivation',
    payload: (action) => ({
      product_id: action.product?.id,
      preview_token: action.preview_token,
    }),
    title: (action) =>
      `Deactivate ${action.product?.name || 'this product'} (hidden from catalog, nothing deleted)?`,
    successText: (data, action) =>
      `Product ${data.product?.name || action.product?.name || ''} deactivated.`.trim(),
  },
  adjust_stock: {
    endpoint: 'inventory/adjust',
    confirmLabel: 'Confirm Adjustment',
    payload: (action) => ({
      variant_id: action.variant?.id,
      delta: action.delta,
      reason: action.reason || '',
      preview_token: action.preview_token,
    }),
    title: (action) =>
      `Adjust stock of ${action.variant?.sku || 'this variant'} by ${
        action.delta > 0 ? `+${action.delta}` : action.delta
      } (→ ${action.resulting_stock})?`,
    successText: (data, action) =>
      `Stock of ${data.variant?.sku || action.variant?.sku || ''} is now ${
        data.variant?.stock ?? action.resulting_stock ?? ''
      }.`.trim(),
  },
};

// Permission tier badge for pending-action cards (agent-dashboard
// pattern: destructive = red, asks every time; write = previewed).
// Pure UI mapping off the tool name — no permission logic lives here.
const ACTION_TIERS = {
  cancel_order: 'destructive',
  issue_refund: 'destructive',
  delete_product: 'destructive',
};
const actionTier = (tool) => (ACTION_TIERS[tool] ? 'destructive' : 'write');

const McpAgent = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const userRef = useRef(user);
  useEffect(() => {
    userRef.current = user;
  });
  const ownerKey = chatOwnerKey(user);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [thinking, setThinking] = useState(false);
  // Streaming turn: `streamStep` is the current tool label ("Looking up
  // orders…"), `draft` is the answer text rendered so far. Both clear when
  // the turn commits or aborts.
  const [streamStep, setStreamStep] = useState(null);
  const [draft, setDraft] = useState('');
  const [confirmingIndex, setConfirmingIndex] = useState(null);
  const [showThreads, setShowThreads] = useState(false);
  // Persisted transcript store (per admin). Starts empty so one admin's
  // saved conversation can never flash on another admin's screen; the
  // effect below loads the signed-in owner's transcript.
  const [store, setStore] = useState(() => emptyStore());
  const storeRef = useRef(store);
  const ownerRef = useRef(null);
  // Single pending-undo slot for thread deletion: { toastId, conversation
  // (sanitized, no live actions), index, wasActive }. Cleared on owner
  // change so an undo can never resurrect another admin's thread.
  const pendingUndoRef = useRef(null);
  // In-flight chat request controller for the Stop button. Aborting only
  // stops waiting client-side; the server may finish, but no write ever
  // applies without a preview-confirm click.
  const abortRef = useRef(null);

  useEffect(() => {
    storeRef.current = store;
  });

  // Swap transcripts when the signed-in admin changes (login, logout,
  // account switch). Logged-out state always shows an empty transcript.
  // Syncing from the persisted external store justifies setState here.
  // eslint-disable-next-line react/set-state-in-effect
  useEffect(() => {
    if (ownerRef.current === ownerKey) return;
    ownerRef.current = ownerKey;
    if (pendingUndoRef.current?.toastId) toast.dismiss(pendingUndoRef.current.toastId);
    pendingUndoRef.current = null;
    if (!ownerKey) {
      setStore(emptyStore());
      setMessages([]);
      return;
    }
    const loaded = loadStore(userRef.current);
    storeRef.current = loaded;
    setStore(loaded);
    const active = loaded.conversations.find((c) => c.id === loaded.activeId);
    setMessages(active ? active.messages : []);
  }, [ownerKey]);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, thinking, draft, streamStep]);

  // Never leave a dangling request on unmount.
  useEffect(() => () => {
    abortRef.current?.abort();
  }, []);

  const handleSend = async (e) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text) return;
    runPrompt(text, { appendUser: true });
  };

  // Commit a completed assistant turn (shared by the streaming and
  // non-streaming paths). `data` is the final event or the JSON body.
  const commitReply = (text, data) => {
    const reply = data?.reply?.trim() || PLACEHOLDER_REPLY;
    const pendingAction = data?.pending_action || null;
    // Backend-attached product cards (whitelisted display data only —
    // never LLM-written URLs). Sanitized again client-side.
    const rawCards = data?.product_cards;
    const cards = Array.isArray(rawCards)
      ? rawCards.map(sanitizeProductCard).filter(Boolean).slice(0, 4)
      : [];
    const userMsg = { role: 'user', text };
    const asstMsg = { role: 'assistant', text: reply, action: pendingAction };
    if (cards.length > 0) asstMsg.cards = cards;
    // NOTE: the user message was already appended optimistically above;
    // only the assistant reply goes here (appending userMsg again would
    // render every sent message twice).
    setMessages((prev) => [...prev, asstMsg]);
    // Auto-title untitled threads from the first user message.
    setStore((prev) => {
      const conv = prev.conversations.find((c) => c.id === prev.activeId);
      if (!conv || conv.title !== DEFAULT_TITLE) return prev;
      const title = titleFromMessages([...conv.messages, userMsg, asstMsg]);
      if (title === DEFAULT_TITLE) return prev;
      return retitleConversation(userRef.current, prev, conv.id, title);
    });
  };

  // Shared send core: history excludes error bubbles, so a retry sends
  // exactly what the original send did (no poisoned precedent).
  const runPrompt = async (text, { appendUser = true } = {}) => {
    if (!text || thinking) return;
    ensureConversation();
    // Prior turns via the shared helper (errors excluded — they are
    // client renderings, not LLM context; action payloads never sent).
    // Blank fallbacks ("(no response)", unsent placeholder) are excluded
    // too so a failed turn never poisons the retry as negative precedent.
    const history = toLlmHistory(messages, undefined, [PLACEHOLDER_REPLY, '(no response)']);
    if (appendUser) setMessages((prev) => [...prev, { role: 'user', text }]);
    setInput('');
    setThinking(true);
    setStreamStep(null);
    setDraft('');
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      // Prefer SSE: tokens render as they arrive. If the stream fails
      // before producing anything (e.g. an older backend without
      // /mcp/chat/stream), fall back once to the JSON endpoint.
      let finalEvent = null;
      let streamError = null;
      let streamed = '';
      let sawToken = false;

      try {
        await streamMcpChat(text, history, {
          signal: controller.signal,
          onStep: (event) => setStreamStep(event.label || event.tool || 'Working…'),
          onToken: (event) => {
            sawToken = true;
            streamed += event.text || '';
            setDraft(streamed);
            setStreamStep(null);
          },
          onFinal: (event) => {
            finalEvent = event;
          },
          onError: (event) => {
            streamError = new Error(event.message || 'The agent could not finish.');
            streamError.agentMessage = event.message || null;
          },
        });
      } catch (error) {
        const aborted =
          error?.name === 'AbortError' || controller.signal.aborted;
        // Only fall back on transport/HTTP failures — a structured `error`
        // event means the turn already ran server-side; retrying it would
        // replay the tool calls.
        if (!aborted && !streamError && !sawToken && !finalEvent) {
          // Nothing rendered yet — retry on the non-streaming endpoint
          // (also covers a backend that predates /mcp/chat/stream).
          const response = await sendMcpChat(text, history, controller.signal);
          finalEvent = response?.data || null;
        } else {
          throw error;
        }
      }

      if (streamError) throw streamError;
      commitReply(text, finalEvent || {});
    } catch (error) {
      // User-pressed Stop: stay silent (no error bubble) — the prompt is
      // intact above and can simply be re-sent. The server may still
      // finish in the background, but nothing applies without a
      // preview-confirm click, so abandoning is safe.
      const aborted =
        error?.code === 'ERR_CANCELED' || error?.name === 'AbortError';
      if (!aborted) {
        setMessages((prev) => [...prev, { role: 'assistant', text: extractError(error), error: true }]);
      }
    } finally {
      abortRef.current = null;
      setThinking(false);
      setStreamStep(null);
      setDraft('');
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  // Re-send the prompt behind a failed bubble as a fresh turn (the
  // failed bubble is dropped; history excludes errors either way).
  const handleRetry = (errorIndex) => {
    if (thinking || confirmingIndex !== null) return;
    const prior = [...messages.slice(0, errorIndex)]
      .reverse()
      .find((m) => m.role === 'user' && m.text?.trim());
    if (!prior) return;
    setMessages((prev) => prev.filter((_, i) => i !== errorIndex));
    runPrompt(prior.text.trim(), { appendUser: false });
  };

  const resolveAction = (index, patch) => {
    setMessages((prev) => prev.map((m, i) => (i === index ? { ...m, action: { ...m.action, ...patch } } : m)));
  };

  const handleConfirmCancel = async (index) => {
    const action = messages[index]?.action;
    if (!action || action.resolved || confirmingIndex !== null) return;
    setConfirmingIndex(index);
    try {
      const response = await confirmMcpCancel({
        order_id: action.order_id,
        preview_token: action.preview_token,
      });
      const data = response?.data || {};
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text: `Order ${data.order_number || action.order_number || ''} cancelled.`.trim(),
        },
      ]);
      resolveAction(index, { resolved: 'confirmed' });
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', text: extractError(error), error: true }]);
    } finally {
      setConfirmingIndex(null);
    }
  };

  const handleKeepOrder = (index) => {
    // Local dismiss only — no request, no state change server-side.
    resolveAction(index, { resolved: 'dismissed' });
  };

  // Button-confirmed MCP write previews (product/inventory tools). Each
  // entry maps the pending_action tool to its executor endpoint, the
  // payload the backend revalidates, and the UI labels. Cancel/refund
  // keep their dedicated handlers above; behavior there is unchanged.

  const handleConfirmWrite = async (index) => {
    const action = messages[index]?.action;
    const config = (action && WRITE_ACTIONS[action.tool]) || null;
    if (!action || !config || action.resolved || confirmingIndex !== null) return;
    setConfirmingIndex(index);
    try {
      const response = await executeMcpWrite(config.endpoint, config.payload(action));
      const data = response?.data || {};
      setMessages((prev) => [...prev, { role: 'assistant', text: config.successText(data, action) }]);
      resolveAction(index, { resolved: 'confirmed' });
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', text: extractError(error), error: true }]);
    } finally {
      setConfirmingIndex(null);
    }
  };

  const actionTitle = useCallback((action) => {
    if (!action) return '';
    if (action.tool === 'issue_refund') {
      return `Confirm refund of ${action.refund_to_customer || action.amount || ''}${
        action.order_number ? ` for order ${action.order_number}` : ''
      }${action.requires_approval ? ' (needs second-admin approval)' : ''}?`;
    }
    if (action.tool === 'cancel_order') {
      return action.order_number
        ? `Confirm cancellation of order ${action.order_number}${
            action.status ? ` (currently ${action.status})` : ''
          }?`
        : 'Confirm this cancellation?';
    }
    const config = WRITE_ACTIONS[action.tool];
    return config ? config.title(action) : 'Confirm this action?';
  }, []);

  const actionConfirmLabel = (action) => {
    if (!action) return 'Confirm';
    if (action.tool === 'issue_refund') return 'Confirm Refund';
    if (action.tool === 'cancel_order') return 'Confirm Cancellation';
    const config = WRITE_ACTIONS[action.tool];
    return config ? config.confirmLabel : 'Confirm';
  };

  const handleActionConfirm = (index) => {
    const action = messages[index]?.action;
    if (!action) return;
    if (action.tool === 'issue_refund') return handleConfirmRefund(index);
    if (action.tool === 'cancel_order') return handleConfirmCancel(index);
    return handleConfirmWrite(index);
  };

  // Deep-link for a pending card (existing routes only): orders and
  // products open in place; the preview stays live behind them.
  const actionViewTarget = (action) => {
    if (!action) return null;
    if (
      (action.tool === 'cancel_order' || action.tool === 'issue_refund') &&
      action.order_id
    ) {
      return {
        to: `/orders/${action.order_id}`,
        label: action.order_number ? `View order ${action.order_number}` : 'View order',
      };
    }
    const slug = action.product?.slug;
    if (
      (action.tool === 'update_product' ||
        action.tool === 'update_product_price' ||
        action.tool === 'delete_product') &&
      slug
    ) {
      return { to: `/products/${slug}`, label: 'View product' };
    }
    return null;
  };

  // Quick delta chips on stock previews: request a FRESH preview for the
  // picked delta (same endpoint, same two-step safety) and swap it into
  // the card in place. Failures toast and keep the current preview.
  const QUICK_DELTAS = [-5, -1, 1, 5];
  const handleDeltaPick = async (index, delta) => {
    const action = messages[index]?.action;
    if (!action || action.tool !== 'adjust_stock' || action.resolved || confirmingIndex !== null) return;
    if (delta === action.delta) return;
    setConfirmingIndex(index);
    try {
      const response = await executeMcpWrite('inventory/adjust', {
        variant_id: action.variant?.id,
        delta,
        reason: action.reason || 'Quick adjust from chat',
      });
      const data = response?.data || {};
      if (data.success === false) {
        toast.error(data.error || 'Could not preview that adjustment');
        return;
      }
      resolveAction(index, {
        delta: data.delta ?? delta,
        resulting_stock: data.resulting_stock,
        preview_token: data.preview_token,
        reason: data.reason || action.reason,
        variant: data.variant || action.variant,
        resolved: null,
      });
    } catch (error) {
      toast.error(extractError(error));
    } finally {
      setConfirmingIndex(null);
    }
  };

  const handleConfirmRefund = async (index) => {
    const action = messages[index]?.action;
    if (!action || action.resolved || confirmingIndex !== null) return;
    setConfirmingIndex(index);
    try {
      const response = await confirmMcpRefund({
        order_id: action.order_id,
        amount: action.amount,
        reason: action.reason || '',
        preview_token: action.preview_token,
      });
      const data = response?.data || {};
      const label = data.order_number || action.order_number || '';
      const text = data.approval_staged
        ? `Refund of ${data.amount || action.amount || ''} for order ${label} staged for second-admin approval. No money moved yet.`.trim()
        : `Refund of ${data.amount || action.amount || ''} processed for order ${label}.`.trim();
      setMessages((prev) => [...prev, { role: 'assistant', text }]);
      resolveAction(index, { resolved: 'confirmed' });
    } catch (error) {
      setMessages((prev) => [...prev, { role: 'assistant', text: extractError(error), error: true }]);
    } finally {
      setConfirmingIndex(null);
    }
  };

  const applySuggestion = (suggestion) => {
    setInput(suggestion);
    inputRef.current?.focus();
  };

  // Persist the active transcript after every change. Live executable
  // actions degrade to inert display metadata via actionTitle — preview
  // tokens are never written (see utils/mcpChatStore). actionTitle is a
  // pure per-action formatter; omitting it from deps is intentional.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!ownerKey) return;
    const describeAction = (action) => {
      if (!action || typeof action !== 'object') return null;
      return { title: actionTitle(action), tool: action.tool };
    };
    setStore((prev) => saveActiveMessages(userRef.current, prev, messages, describeAction));
  }, [messages, ownerKey, actionTitle]);

  // Guarantee an active conversation before sending (e.g. right after
  // Clear Chat). Returns the store to send under.
  const ensureConversation = () => {
    const current = storeRef.current;
    if (current && current.activeId) return current;
    const { store: next } = startConversation(userRef.current, current);
    storeRef.current = next;
    setStore(next);
    return next;
  };

  const handleNewChat = () => {
    if (thinking || confirmingIndex !== null) return;
    const { store: next } = startConversation(userRef.current, storeRef.current);
    storeRef.current = next;
    setStore(next);
    setMessages([]);
    setInput('');
  };

  const busy = thinking || confirmingIndex !== null;

  const handleSwitchThread = (id) => {
    // Never abandon an in-flight response or confirmation mid-flight.
    if (busy) return;
    const current = storeRef.current;
    if (!current || current.activeId === id) return;
    const target = current.conversations.find((c) => c.id === id);
    if (!target) return;
    const next = setActiveConversation(userRef.current, current, id);
    storeRef.current = next;
    setStore(next);
    setMessages(target.messages);
    setInput('');
    // Mobile: collapse the inline panel so the thread takes the space.
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      setShowThreads(false);
    }
  };

  const handleDeleteThread = (id) => {
    if (busy) return;
    const current = storeRef.current;
    const target = current?.conversations.find((c) => c.id === id);
    if (!target) return;
    const index = current.conversations.findIndex((c) => c.id === id);
    const wasActive = current.activeId === id;
    // Sanitize live executable actions to inert display metadata so an
    // undo can never resurrect a stale preview button (same rule as
    // persistence: preview tokens never come back).
    const inert = {
      ...target,
      messages: (target.messages || []).map((m) => {
        if (m?.role === 'assistant' && m.action && typeof m.action === 'object' && !m.action.resolved) {
          const { action: _dropped, ...rest } = m;
          return { ...rest, actionDisplay: { title: actionTitle(m.action), tool: m.action.tool } };
        }
        return m;
      }),
    };
    // A second delete supersedes a pending undo (single slot).
    if (pendingUndoRef.current?.toastId) toast.dismiss(pendingUndoRef.current.toastId);
    let next = deleteConversation(userRef.current, current, id);
    if (wasActive) {
      if (next.conversations.length > 0) {
        // Fall back to the newest remaining thread; never resurrect the deleted one.
        const fallback = next.conversations[0];
        next = setActiveConversation(userRef.current, next, fallback.id);
        setMessages(fallback.messages);
      } else {
        // Last thread deleted: present a clean empty conversation.
        const started = startConversation(userRef.current, next);
        next = started.store;
        setMessages([]);
      }
    }
    storeRef.current = next;
    setStore(next);
    setInput('');
    const toastId = toast(
      (t) => (
        <span style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          Deleted &ldquo;{target.title}&rdquo;.
          <button
            type="button"
            onClick={() => handleUndoDelete(t.id)}
            style={{ fontWeight: 600, textDecoration: 'underline', cursor: 'pointer' }}
          >
            Undo
          </button>
        </span>
      ),
      { duration: 6000 },
    );
    pendingUndoRef.current = { toastId, conversation: inert, index, wasActive };
  };

  const handleUndoDelete = (toastId) => {
    const pending = pendingUndoRef.current;
    pendingUndoRef.current = null;
    if (toastId) toast.dismiss(toastId);
    if (!pending) return;
    const next = restoreConversation(
      userRef.current,
      storeRef.current,
      pending.conversation,
      pending.index,
      pending.wasActive,
    );
    storeRef.current = next;
    setStore(next);
    if (pending.wasActive) setMessages(pending.conversation.messages);
    setInput('');
  };

  return (
    <div className="flex flex-col h-[calc(100dvh-9rem)] min-h-[560px]">
      <div className="mb-6 min-w-0 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-bold text-foreground break-words">MCP Agent</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Ask questions and administer your ecommerce data — orders, products, customers and more.
          </p>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => setShowThreads((v) => !v)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border font-medium text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition"
              aria-expanded={showThreads}
            >
              <History size={14} />
              History
            </button>
            <button
              type="button"
              onClick={handleNewChat}
              disabled={thinking || confirmingIndex !== null}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border font-medium text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition disabled:opacity-50"
            >
              <Plus size={14} />
              New Chat
            </button>
          </div>
        </div>
        {/* Status indicator (static visual; session auth is handled by apiClient). */}
        <span
          className="shrink-0 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground border border-border"
          title="MCP agent (uses your admin session)"
        >
          <span className="w-2 h-2 rounded-full bg-success" />
          MCP
        </span>
      </div>

      <div className="flex flex-1 flex-col lg:flex-row gap-4 items-stretch min-h-0">
        {/* Desktop: in-flow sidebar. Mobile: overlay drawer (below). */}
        {showThreads && (
          <aside className="hidden lg:flex w-60 shrink-0 min-h-0 bg-card border border-border rounded-lg flex-col overflow-hidden">
            <ThreadList
              conversations={store.conversations}
              activeId={store.activeId}
              busy={busy}
              onSwitch={handleSwitchThread}
              onDelete={handleDeleteThread}
            />
          </aside>
        )}
        {/* Mobile: bottom sheet (NOT another side drawer — the app
            sidebar already occupies that pattern, and an inline panel
            would starve the thread). Thread keeps full height beneath. */}
        {showThreads && (
          <div className="lg:hidden fixed inset-0 z-40" role="dialog" aria-label="Conversations">
            <div
              className="absolute inset-0 bg-black/40"
              aria-hidden="true"
              onClick={() => setShowThreads(false)}
            />
            <div className="absolute inset-x-0 bottom-0 max-h-[65vh] bg-card border-t border-border rounded-t-2xl shadow-2xl flex flex-col overflow-hidden">
              <div className="pt-2 pb-1 flex justify-center shrink-0" aria-hidden="true">
                <span className="w-10 h-1 rounded-full bg-border" />
              </div>
              <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
                <ThreadList
                  conversations={store.conversations}
                  activeId={store.activeId}
                  busy={busy}
                  onSwitch={handleSwitchThread}
                  onDelete={handleDeleteThread}
                  onClose={() => setShowThreads(false)}
                />
              </div>
            </div>
          </div>
        )}
        <div className="flex-1 min-w-0 w-full bg-card border border-border rounded-lg flex flex-col min-h-0">
        {/* Conversation fills the bounded card; only this area scrolls,
            so the composer below is always visible — no sticky needed,
            nothing can slide underneath it. */}
        <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto overscroll-contain p-4 space-y-3 rounded-t-lg">
          {messages.length === 0 && !thinking && (
            <div className="flex-1 min-h-[240px] flex flex-col items-center justify-center text-center gap-3 py-8">
              <span className="w-11 h-11 rounded-full bg-primary-soft text-primary flex items-center justify-center">
                <Bot size={22} />
              </span>
              <p className="text-sm text-muted-foreground max-w-sm">
                Start a conversation below, or try one of these example prompts.
              </p>
              <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                {SUGGESTIONS.map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => applySuggestion(suggestion)}
                    className="text-xs px-3 py-1.5 rounded-full border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] px-3.5 py-2.5 rounded-2xl text-sm whitespace-pre-wrap break-words ${
                  message.role === 'user'
                    ? 'bg-primary text-primary-foreground rounded-br-md'
                    : message.error
                      ? 'bg-destructive/10 text-destructive border border-destructive/30 rounded-bl-md'
                      : 'bg-muted text-foreground rounded-bl-md'
                }`}
              >
                {message.role === 'user' ? (
                  message.text
                ) : message.error ? (
                  <div>
                    <AssistantMarkdown text={message.text} />
                    <button
                      type="button"
                      onClick={() => handleRetry(index)}
                      disabled={thinking || confirmingIndex !== null}
                      title="Re-send this prompt as a fresh turn"
                      className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-destructive/40 font-medium text-xs hover:bg-destructive/10 transition disabled:opacity-50"
                    >
                      <RotateCcw size={13} />
                      Retry
                    </button>
                  </div>
                ) : (
                  <AssistantMarkdown text={message.text} />
                )}
                {/* Backend-attached product cards (image + price + stock).
                    Rendered above any preview so the visual leads. */}
                {message.role === 'assistant' && !message.error &&
                  Array.isArray(message.cards) && message.cards.length > 0 && (
                  <ProductCards
                    cards={message.cards}
                    onView={(slug) => navigate(`/products/${slug}`)}
                  />
                )}
                {message.role === 'assistant' && !message.action && message.actionDisplay && (
                  <div className="mt-2.5 pt-2.5 border-t border-border">
                    <p className="text-xs text-muted-foreground">
                      {message.actionDisplay.title || 'Previous preview'}
                      <span className="ml-1 opacity-70">
                        (historical — request a new preview to act)
                      </span>
                    </p>
                  </div>
                )}
                {message.role === 'assistant' && message.action && !message.action.resolved && (
                  <div className="mt-2.5 pt-2.5 border-t border-border space-y-2">
                    <p>
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border ${
                          actionTier(message.action.tool) === 'destructive'
                            ? 'bg-destructive/10 text-destructive border-destructive/30'
                            : 'bg-primary-soft text-primary border-border'
                        }`}
                      >
                        {actionTier(message.action.tool) === 'destructive'
                          ? 'Destructive · always asks'
                          : 'Write · previewed, asks once'}
                      </span>
                    </p>
                    <p className="text-xs text-muted-foreground">{actionTitle(message.action)}</p>
                    {/* Pending preview's own product thumb (backend data). */}
                    {message.action.product?.image_url && (
                      <img
                        src={message.action.product.image_url}
                        alt={message.action.product.name || 'Product image'}
                        loading="lazy"
                        referrerPolicy="no-referrer"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none';
                        }}
                        className="h-16 w-16 rounded-lg border border-border object-cover"
                      />
                    )}
                    {message.action.changes && typeof message.action.changes === 'object' &&
                      Object.keys(message.action.changes).length > 0 && (
                      <dl className="text-xs space-y-1 rounded-lg bg-foreground/5 px-3 py-2">
                        {Object.entries(message.action.changes).map(([field, value]) => (
                          <div key={field} className="flex justify-between gap-4">
                            <dt className="text-muted-foreground">{field}</dt>
                            <dd className="font-medium break-all">{String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                    )}
                    {message.action.tool === 'issue_refund' &&
                      (message.action.order_total || message.action.restocking_fee ||
                        message.action.refund_to_customer) && (
                      <dl className="text-xs space-y-1 rounded-lg bg-foreground/5 px-3 py-2">
                        {message.action.order_total && (
                          <div className="flex justify-between gap-4">
                            <dt className="text-muted-foreground">Order total</dt>
                            <dd className="font-medium">${message.action.order_total}</dd>
                          </div>
                        )}
                        {message.action.restocking_fee && (
                          <div className="flex justify-between gap-4">
                            <dt className="text-muted-foreground">Restocking fee retained</dt>
                            <dd className="font-medium">${message.action.restocking_fee}</dd>
                          </div>
                        )}
                        {message.action.refund_to_customer && (
                          <div className="flex justify-between gap-4">
                            <dt className="text-muted-foreground">Refund to customer</dt>
                            <dd className="font-semibold">${message.action.refund_to_customer}</dd>
                          </div>
                        )}
                        <div className="flex justify-between gap-4">
                          <dt className="text-muted-foreground">Additional fee at execution</dt>
                          <dd className="font-medium">
                            ${message.action.additional_fee_at_execution || '0.00'}
                          </dd>
                        </div>
                      </dl>
                    )}
                    {/* Quick delta chips (stock only): swap in a fresh preview
                        for the picked delta — same two-step safety. */}
                    {message.action.tool === 'adjust_stock' && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-xs text-muted-foreground">Quick adjust:</span>
                        {QUICK_DELTAS.map((d) => {
                          const label = d > 0 ? `+${d}` : `${d}`;
                          const selected = d === message.action.delta;
                          return (
                            <button
                              key={d}
                              type="button"
                              disabled={confirmingIndex !== null}
                              onClick={() => handleDeltaPick(index, d)}
                              title={`Preview ${label}`}
                              className={`px-2 py-1 rounded-lg border font-medium text-xs transition disabled:opacity-50 ${
                                selected
                                  ? 'bg-primary-soft text-primary border-border'
                                  : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                              }`}
                            >
                              {confirmingIndex === index ? (
                                <Loader className="animate-spin" size={12} />
                              ) : (
                                label
                              )}
                            </button>
                          );
                        })}
                      </div>
                    )}
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        disabled={confirmingIndex !== null}
                        onClick={() => handleActionConfirm(index)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-destructive text-white font-medium text-xs hover:opacity-90 transition disabled:opacity-50"
                      >
                        {confirmingIndex === index ? (
                          <Loader className="animate-spin" size={14} />
                        ) : null}
                        {actionConfirmLabel(message.action)}
                      </button>
                      <button
                        type="button"
                        disabled={confirmingIndex !== null}
                        onClick={() => handleKeepOrder(index)}
                        className="px-3 py-1.5 rounded-lg border border-border font-medium text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition disabled:opacity-50"
                      >
                        {message.action.tool === 'cancel_order' || message.action.tool === 'issue_refund'
                          ? 'Keep Order'
                          : 'Dismiss'}
                      </button>
                      {(() => {
                        const target = actionViewTarget(message.action);
                        if (!target) return null;
                        return (
                          <button
                            type="button"
                            disabled={confirmingIndex !== null}
                            onClick={() => navigate(target.to)}
                            title={target.label}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg font-medium text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition disabled:opacity-50"
                          >
                            <ExternalLink size={13} />
                            <span className="hidden sm:inline">{target.label}</span>
                          </button>
                        );
                      })()}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {thinking && (
            <div className="flex justify-start">
              {draft ? (
                // Tokens are arriving: render the partial answer with a
                // caret so the user reads while the model is still going.
                <div className="max-w-[80%] px-3.5 py-2.5 rounded-2xl rounded-bl-md text-sm bg-muted text-foreground break-words">
                  <AssistantMarkdown text={draft} />
                  <span className="inline-block w-1.5 h-4 ml-0.5 align-text-bottom bg-muted-foreground/70 animate-pulse" />
                </div>
              ) : (
                <div className="bg-muted text-foreground px-4 py-3 rounded-2xl rounded-bl-md flex items-center gap-2 text-sm">
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-muted-foreground/70 animate-bounce" />
                    <span className="w-2 h-2 rounded-full bg-muted-foreground/70 animate-bounce [animation-delay:150ms]" />
                    <span className="w-2 h-2 rounded-full bg-muted-foreground/70 animate-bounce [animation-delay:300ms]" />
                  </span>
                  {streamStep && (
                    <span className="text-xs text-muted-foreground" aria-live="polite">
                      {streamStep}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Example prompts (visible once the thread starts too) */}
        {messages.length > 0 && (
          <div className="px-4 pb-3 flex gap-2 overflow-x-auto">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                onClick={() => applySuggestion(suggestion)}
                className="shrink-0 text-xs px-3 py-1.5 rounded-full border border-border text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        {/* Input row — plain last child of the bounded card: always
            visible, never floating, nothing scrolls beneath it. */}
        <form
          onSubmit={handleSend}
          className="bg-card border-t border-border rounded-b-xl p-3 flex items-center gap-2"
          style={{ paddingBottom: 'calc(0.75rem + env(safe-area-inset-bottom, 0px))' }}
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about orders, products, customers…"
            enterKeyHint="send"
            className="flex-1 min-w-0 bg-transparent border border-border rounded-lg px-3.5 py-2.5 text-base sm:text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
          {thinking ? (
            <button
              type="button"
              onClick={handleStop}
              className="shrink-0 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 min-h-[44px] sm:min-h-0 rounded-lg border border-destructive/40 text-destructive font-medium text-sm hover:bg-destructive/10 transition-colors"
              title="Stop waiting (the server may finish, but nothing applies without your confirm)"
            >
              <Square size={16} />
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="shrink-0 inline-flex items-center justify-center gap-1.5 px-4 py-2.5 min-h-[44px] sm:min-h-0 rounded-lg bg-primary text-primary-foreground font-medium text-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Send size={16} />
              Send
            </button>
          )}
        </form>
        </div>
      </div>
    </div>
  );
};

export default McpAgent;

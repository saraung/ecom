// src/utils/mcpChatStore.js
// Persistent MCP chat transcript store (localStorage, per admin).
//
// Design: the backend stays stateless, so the transcript lives here.
// Only safe display data is persisted — {role, text} plus inert display
// metadata. Preview tokens and executable pending actions are NEVER
// saved: restored previews render as plain history with no buttons.
// The JWT is never visible to this page (apiClient interceptor owns it).

export const STORE_VERSION = 1;
export const STORE_PREFIX = 'mcp-chats:v1:';
export const MAX_STORED_CONVERSATIONS = 10;
export const MAX_STORED_TURNS = 50;
export const HISTORY_SEND_LIMIT = 10;
export const MAX_TITLE_LENGTH = 48;
export const DEFAULT_TITLE = 'New chat';

// Title from the first user message (single line, truncated). Pure
// display metadata derived from the admin's own words — never sent
// anywhere except local persistence alongside the transcript.
export const titleFromMessages = (messages) => {
  if (!Array.isArray(messages)) return DEFAULT_TITLE;
  const first = messages.find((m) => m && m.role === 'user' && String(m.text ?? '').trim());
  if (!first) return DEFAULT_TITLE;
  const singleLine = String(first.text).trim().split('\n')[0].trim();
  if (!singleLine) return DEFAULT_TITLE;
  return singleLine.length > MAX_TITLE_LENGTH
    ? `${singleLine.slice(0, MAX_TITLE_LENGTH).trimEnd()}…`
    : singleLine;
};

const safeStorage = () => {
  try {
    if (typeof window !== 'undefined' && window.localStorage) return window.localStorage;
  } catch {
    // Private mode / blocked storage: chat simply won't persist.
  }
  return null;
};

// Stable per-admin scope. Falls back to email when id is unavailable;
// returns '' when there is no signed-in admin (nothing is persisted).
export const chatOwnerKey = (user) => {
  if (!user) return '';
  const id = user.id || user.email || '';
  return String(id).trim();
};

export const chatsKey = (user) => {
  const owner = chatOwnerKey(user);
  return owner ? `${STORE_PREFIX}${owner}` : '';
};

// Strip a live message down to persistable display data. `describeAction`
// converts a live executable action into inert display metadata
// ({title, tool}); without it, live actions persist as plain text only.
// Preview tokens and executability are NEVER saved.
// Product cards (backend-attached display data: CDN thumb + names +
// prices) persist whitelisted the same way — no tokens ever ride along.
export const sanitizeProductCard = (card) => {
  if (!card || typeof card !== 'object') return null;
  const clean = {};
  const pick = (key) => {
    const v = card[key];
    if (v == null) return;
    clean[key] = String(v).slice(0, 500);
  };
  pick('id');
  pick('name');
  pick('slug');
  pick('price');
  pick('compare_at_price');
  pick('image_url');
  if (card.stock != null && Number.isFinite(Number(card.stock))) {
    clean.stock = Number(card.stock);
  }
  if (typeof card.is_active === 'boolean') clean.is_active = card.is_active;
  if (!clean.id && !clean.name) return null;
  return clean;
};
export const toStoredMessage = (message, describeAction) => {
  if (!message || (message.role !== 'user' && message.role !== 'assistant')) return null;
  const stored = { role: message.role, text: String(message.text ?? '') };
  const action = message.action;
  if (message.role === 'assistant' && action && typeof action === 'object' && !action.resolved) {
    let display = null;
    if (typeof describeAction === 'function') {
      try {
        const described = describeAction(action);
        if (described && typeof described === 'object') {
          display = {};
          if (typeof described.title === 'string' && described.title) {
            display.title = described.title.slice(0, 500);
          }
          if (typeof described.tool === 'string' && described.tool) {
            display.tool = described.tool.slice(0, 100);
          }
        }
      } catch {
        display = null;
      }
    }
    if (display && Object.keys(display).length > 0) stored.actionDisplay = display;
  }
  if (Array.isArray(message.cards) && message.cards.length > 0) {
    const cards = message.cards.map(sanitizeProductCard).filter(Boolean).slice(0, 4);
    if (cards.length > 0) stored.cards = cards;
  }
  return stored;
};

// Restore a stored message for display. Never resurrects executability:
// no preview_token is ever stored, and no buttons render without one.
export const fromStoredMessage = (stored) => {
  if (!stored || (stored.role !== 'user' && stored.role !== 'assistant')) return null;
  const message = { role: stored.role, text: String(stored.text ?? '') };
  if (stored.actionDisplay && typeof stored.actionDisplay === 'object') {
    message.actionDisplay = { ...stored.actionDisplay };
  }
  if (Array.isArray(stored.cards) && stored.cards.length > 0) {
    const cards = stored.cards.map(sanitizeProductCard).filter(Boolean).slice(0, 4);
    if (cards.length > 0) message.cards = cards;
  }
  return message;
};

// LLM-bound history: last N non-error text turns. Blank assistant turns
// (backend "(no response)" fallback, unsent local placeholders) are
// excluded: replaying a failed turn teaches the model the failed path.
// Callers pass their inert marker texts via `exclude`.
export const toLlmHistory = (messages, limit = HISTORY_SEND_LIMIT, exclude = []) => {
  if (!Array.isArray(messages)) return [];
  const excluded = new Set(
    (Array.isArray(exclude) ? exclude : []).map((t) => String(t ?? '').trim()),
  );
  return messages
    .filter((m) => m && !m.error)
    .map((m) => ({ role: m.role, content: String(m.text ?? '') }))
    .filter((m) => m.content.trim() && !excluded.has(m.content.trim()))
    .slice(-limit);
};

export const emptyStore = () => ({ version: STORE_VERSION, activeId: null, conversations: [] });

export const newConversation = () => ({
  id: typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `c-${Date.now()}-${Math.floor(Math.random() * 1e9)}`,
  title: DEFAULT_TITLE,
  updatedAt: Date.now(),
  messages: [],
});

const normalizeStore = (raw) => {
  if (!raw || typeof raw !== 'object' || !Array.isArray(raw.conversations)) return emptyStore();
  const conversations = [];
  for (const conv of raw.conversations) {
    if (!conv || typeof conv !== 'object' || typeof conv.id !== 'string') continue;
    const messages = [];
    if (Array.isArray(conv.messages)) {
      for (const m of conv.messages.slice(-MAX_STORED_TURNS)) {
        const restored = fromStoredMessage(m);
        if (restored) messages.push(restored);
      }
    }
    conversations.push({
      id: conv.id,
      title: typeof conv.title === 'string' ? conv.title : DEFAULT_TITLE,
      updatedAt: typeof conv.updatedAt === 'number' ? conv.updatedAt : 0,
      messages,
    });
    if (conversations.length >= MAX_STORED_CONVERSATIONS) break;
  }
  const active = conversations.find((c) => c.id === raw.activeId) || null;
  return { version: STORE_VERSION, activeId: active ? active.id : null, conversations };
};

export const loadStore = (user) => {
  const key = chatsKey(user);
  if (!key) return emptyStore();
  const storage = safeStorage();
  if (!storage) return emptyStore();
  try {
    const raw = storage.getItem(key);
    if (!raw) return emptyStore();
    return normalizeStore(JSON.parse(raw));
  } catch {
    return emptyStore();
  }
};

const writeStore = (user, store) => {
  const key = chatsKey(user);
  const storage = safeStorage();
  if (!key || !storage) return false;
  try {
    storage.setItem(key, JSON.stringify(store));
    return true;
  } catch {
    return false; // Quota/blocked storage: chat keeps working in memory.
  }
};

// Persist the active conversation's transcript (newest MAX_STORED_TURNS).
export const saveActiveMessages = (user, store, messages, describeAction) => {
  if (!store || !store.activeId) return store;
  const stored = [];
  for (const m of Array.isArray(messages) ? messages : []) {
    const s = toStoredMessage(m, describeAction);
    if (s) stored.push(s);
  }
  const next = {
    ...store,
    conversations: store.conversations.map((c) =>
      c.id === store.activeId
        ? { ...c, messages: stored.slice(-MAX_STORED_TURNS), updatedAt: Date.now() }
        : c,
    ),
  };
  writeStore(user, next);
  return next;
};

export const startConversation = (user, store) => {
  const conv = newConversation();
  const conversations = [conv, ...(store?.conversations || [])].slice(0, MAX_STORED_CONVERSATIONS);
  const next = { version: STORE_VERSION, activeId: conv.id, conversations };
  writeStore(user, next);
  return { store: next, conversation: conv };
};

export const deleteConversation = (user, store, id) => {
  const conversations = (store?.conversations || []).filter((c) => c.id !== id);
  const activeId = store?.activeId === id ? null : store?.activeId || null;
  const next = { ...store, version: STORE_VERSION, activeId, conversations };
  writeStore(user, next);
  return next;
};

// Restore a previously deleted conversation (undo window). The caller
// holds the deleted object + its former index in memory — nothing
// server-side, since transcripts are local-only. Reinsertion keeps the
// original position; an unknown id (double-undo) is a no-op, never a
// duplicate. Trims oldest-first at the cap like startConversation, but a
// restored thread is never itself trimmed.
export const restoreConversation = (user, store, conversation, index, makeActive = false) => {
  if (!conversation || typeof conversation !== 'object' || typeof conversation.id !== 'string') {
    return store;
  }
  const conversations = [...(store?.conversations || [])];
  if (conversations.some((c) => c && c.id === conversation.id)) return store;
  const at = Number.isInteger(index) && index >= 0 && index <= conversations.length
    ? index
    : 0;
  conversations.splice(at, 0, conversation);
  while (conversations.length > MAX_STORED_CONVERSATIONS) {
    const dropAt = conversations.findIndex((c) => c && c.id !== conversation.id);
    if (dropAt === -1) break;
    conversations.splice(dropAt, 1);
  }
  const next = {
    ...store,
    version: STORE_VERSION,
    activeId: makeActive ? conversation.id : store?.activeId || null,
    conversations,
  };
  writeStore(user, next);
  return next;
};

// Switch the active transcript. Unknown ids are ignored so a stale UI
// reference can never surface another (or deleted) conversation.
export const setActiveConversation = (user, store, id) => {
  const target = (store?.conversations || []).find((c) => c.id === id);
  if (!target) return store;
  const next = { ...store, version: STORE_VERSION, activeId: target.id };
  writeStore(user, next);
  return next;
};

// Rename a thread. Titles are display-only metadata.
export const retitleConversation = (user, store, id, title) => {
  const clean = typeof title === 'string' && title.trim()
    ? title.trim().slice(0, MAX_TITLE_LENGTH)
    : DEFAULT_TITLE;
  const next = {
    ...store,
    version: STORE_VERSION,
    conversations: (store?.conversations || []).map((c) =>
      c.id === id ? { ...c, title: clean } : c,
    ),
  };
  writeStore(user, next);
  return next;
};

// Remove everything persisted for one admin (logout hygiene).
export const clearOwnerStore = (user) => {
  const key = chatsKey(user);
  const storage = safeStorage();
  if (!key || !storage) return;
  try {
    storage.removeItem(key);
  } catch {
    // Ignore: nothing security-sensitive depends on removal succeeding,
    // because keys are namespaced per admin (see chatsKey).
  }
};

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DEFAULT_TITLE,
  MAX_STORED_CONVERSATIONS,
  MAX_STORED_TURNS,
  MAX_TITLE_LENGTH,
  HISTORY_SEND_LIMIT,
  chatOwnerKey,
  chatsKey,
  toStoredMessage,
  fromStoredMessage,
  toLlmHistory,
  emptyStore,
  newConversation,
  loadStore,
  saveActiveMessages,
  startConversation,
  deleteConversation,
  restoreConversation,
  setActiveConversation,
  retitleConversation,
  titleFromMessages,
  clearOwnerStore,
} from './mcpChatStore.js';

const adminA = { id: 'admin-1', email: 'a@example.com' };
const adminB = { id: 'admin-2', email: 'b@example.com' };
const describe = (action) => ({ title: `Confirm ${action.tool}`, tool: action.tool });

const withMemoryStorage = () => {
  const data = {};
  globalThis.window = {
    localStorage: {
      getItem: (k) => (k in data ? data[k] : null),
      setItem: (k, v) => { data[k] = String(v); },
      removeItem: (k) => { delete data[k]; },
    },
  };
  return data;
};

test('owner keys scope transcripts per admin', () => {
  assert.equal(chatsKey(adminA), 'mcp-chats:v1:admin-1');
  assert.equal(chatsKey({ email: 'x@y.z' }), 'mcp-chats:v1:x@y.z');
  assert.equal(chatsKey(null), '');
  assert.equal(chatOwnerKey(null), '');
});

test('executable actions never persist, not even partially', () => {
  withMemoryStorage();
  const msg = {
    role: 'assistant',
    text: 'preview',
    action: {
      tool: 'issue_refund', order_id: 'oid', amount: '10',
      preview_token: 'SECRET-TOKEN', resolved: undefined,
    },
  };
  const stored = toStoredMessage(msg, describe);
  assert.deepEqual(Object.keys(stored).sort(), ['actionDisplay', 'role', 'text']);
  assert.deepEqual(stored.actionDisplay, { title: 'Confirm issue_refund', tool: 'issue_refund' });
  const blob = JSON.stringify(stored);
  assert.ok(!blob.includes('SECRET-TOKEN') && !blob.includes('preview_token'));
  // Resolved actions degrade to plain text.
  assert.deepEqual(
    toStoredMessage({ role: 'assistant', text: 't', action: { tool: 'x', resolved: 'confirmed' } }, describe),
    { role: 'assistant', text: 't' },
  );
  // Without a describer, no display metadata is invented.
  assert.deepEqual(
    toStoredMessage({ role: 'assistant', text: 't', action: { tool: 'x' } }),
    { role: 'assistant', text: 't' },
  );
  assert.equal(toStoredMessage({ role: 'system', text: 'pwn' }, describe), null);
});

test('restore never resurrects executability', () => {
  const restored = fromStoredMessage({
    role: 'assistant', text: 'old preview',
    actionDisplay: { title: 'Confirm issue_refund', tool: 'issue_refund' },
  });
  assert.deepEqual(restored, {
    role: 'assistant', text: 'old preview',
    actionDisplay: { title: 'Confirm issue_refund', tool: 'issue_refund' },
  });
  assert.ok(!JSON.stringify(restored).includes('preview_token'));
  assert.deepEqual(fromStoredMessage({ role: 'user' }), { role: 'user', text: '' });
  assert.deepEqual(fromStoredMessage({ role: 'evil', text: 'x' }), null);
  assert.deepEqual(fromStoredMessage(null), null);
});

test('LLM history stays last-10 text-only, errors excluded', () => {
  const messages = [{ role: 'assistant', text: 'boom', error: true }];
  for (let i = 0; i < 14; i++) messages.push({ role: i % 2 ? 'assistant' : 'user', text: `m${i}` });
  const history = toLlmHistory(messages);
  assert.equal(history.length, HISTORY_SEND_LIMIT);
  assert.deepEqual(Object.keys(history[0]).sort(), ['content', 'role']);
  assert.ok(history.every((m) => m.content !== 'boom'));
  assert.deepEqual(toLlmHistory(null), []);
});

test('LLM history excludes blank fallbacks and caller markers', () => {
  const messages = [
    { role: 'user', text: 'show today orders' },
    { role: 'assistant', text: '(no response)' },
    { role: 'assistant', text: '' },
    { role: 'assistant', text: '  ' },
    { role: 'assistant', text: 'MCP wiring is not connected yet.' },
    { role: 'user', text: 'show today orders' },
  ];
  const history = toLlmHistory(messages, undefined, ['MCP wiring is not connected yet.', '(no response)']);
  assert.deepEqual(history, [
    { role: 'user', content: 'show today orders' },
    { role: 'user', content: 'show today orders' },
  ]);
});

test('round trip persists newest turns and isolates admins', () => {
  const data = withMemoryStorage();
  let store = loadStore(adminA);
  assert.deepEqual(store, emptyStore());
  ({ store } = startConversation(adminA, store));
  const messages = [];
  for (let i = 0; i < MAX_STORED_TURNS + 10; i++) {
    messages.push({ role: i % 2 ? 'assistant' : 'user', text: `t${i}` });
  }
  store = saveActiveMessages(adminA, store, messages, describe);
  assert.ok(data['mcp-chats:v1:admin-1'].length > 0);
  assert.ok(!('mcp-chats:v1:admin-2' in data));
  const reloaded = loadStore(adminA);
  assert.equal(reloaded.conversations[0].messages.length, MAX_STORED_TURNS);
  assert.equal(reloaded.conversations[0].messages.at(-1).text, `t${MAX_STORED_TURNS + 9}`);
  assert.deepEqual(loadStore(adminB), emptyStore());
});

test('corrupt storage degrades to empty without throwing', () => {
  const data = withMemoryStorage();
  data['mcp-chats:v1:admin-1'] = '{not json';
  assert.deepEqual(loadStore(adminA), emptyStore());
  data['mcp-chats:v1:admin-1'] = JSON.stringify({ conversations: 'nope' });
  assert.deepEqual(loadStore(adminA), emptyStore());
});

test('new chat archives current and starts empty; clear deletes transcript', () => {
  withMemoryStorage();
  let store = loadStore(adminA);
  ({ store } = startConversation(adminA, store));
  const firstId = store.activeId;
  store = saveActiveMessages(adminA, store, [{ role: 'user', text: 'hi' }], describe);
  let next;
  ({ store, conversation: next } = startConversation(adminA, store));
  assert.notEqual(next.id, firstId);
  assert.deepEqual(next.messages, []);
  assert.equal(store.conversations.length, 2);
  store = deleteConversation(adminA, store, next.id);
  assert.equal(store.conversations.length, 1);
  assert.equal(store.activeId, null);
  store = deleteConversation(adminA, store, firstId);
  assert.deepEqual(loadStore(adminA).conversations, []);
});

test('conversation list is capped and newest-first', () => {
  withMemoryStorage();
  let store = loadStore(adminA);
  for (let i = 0; i < MAX_STORED_CONVERSATIONS + 3; i++) {
    ({ store } = startConversation(adminA, store));
  }
  const reloaded = loadStore(adminA);
  assert.equal(reloaded.conversations.length, MAX_STORED_CONVERSATIONS);
});

test('logout hygiene removes only that admin key', () => {
  const data = withMemoryStorage();
  let storeA = loadStore(adminA);
  ({ store: storeA } = startConversation(adminA, storeA));
  let storeB = loadStore(adminB);
  ({ store: storeB } = startConversation(adminB, storeB));
  clearOwnerStore(adminA);
  assert.ok(!('mcp-chats:v1:admin-1' in data));
  assert.ok('mcp-chats:v1:admin-2' in data);
  clearOwnerStore(null);
});

test('newConversation ids are unique', () => {
  assert.notEqual(newConversation().id, newConversation().id);
});

test('setActiveConversation switches only to known threads', () => {
  const conv = (id) => ({ id, title: 't', updatedAt: 0, messages: [] });
  const store = { version: 1, activeId: 'a', conversations: [conv('a'), conv('b')] };
  assert.equal(setActiveConversation(null, store, 'b').activeId, 'b');
  assert.equal(setActiveConversation(null, store, 'zzz'), store);
  assert.equal(
    setActiveConversation(null, store, 'b').conversations.map((c) => c.id).join(','),
    'a,b',
  );
  const renamed = retitleConversation(null, store, 'a', '  Refunds Q3  ');
  assert.equal(renamed.conversations[0].title, 'Refunds Q3');
  assert.equal(retitleConversation(null, store, 'a', '  ').conversations[0].title, DEFAULT_TITLE);
  assert.equal(
    retitleConversation(null, store, 'zzz', 'x').conversations.map((c) => c.id).join(','),
    'a,b',
  );
});

test('titleFromMessages derives display titles from user words', () => {
  assert.equal(titleFromMessages([]), DEFAULT_TITLE);
  assert.equal(titleFromMessages([{ role: 'assistant', text: 'hi' }]), DEFAULT_TITLE);
  assert.equal(titleFromMessages([{ role: 'user', text: 'Show pending orders' }]), 'Show pending orders');
  assert.equal(
    titleFromMessages([{ role: 'user', text: 'line one\nline two' }]),
    'line one',
  );
  const long = titleFromMessages([{ role: 'user', text: `x${'y'.repeat(200)}` }]);
  assert.ok(long.length <= MAX_TITLE_LENGTH + 1);
  assert.equal(titleFromMessages(null), DEFAULT_TITLE);
});

test('restoreConversation reinserts at the former index and reactivates', () => {
  withMemoryStorage();
  const conv = (id) => ({ id, title: id, updatedAt: 0, messages: [{ role: 'user', text: id }] });
  let store = { version: 1, activeId: 'b', conversations: [conv('a'), conv('b'), conv('c')] };
  const deleted = store.conversations[1];
  store = deleteConversation(adminA, store, 'b');
  assert.deepEqual(store.conversations.map((c) => c.id), ['a', 'c']);
  store = restoreConversation(adminA, store, deleted, 1, true);
  assert.deepEqual(store.conversations.map((c) => c.id), ['a', 'b', 'c']);
  assert.equal(store.activeId, 'b');
  assert.deepEqual(store.conversations[1].messages, [{ role: 'user', text: 'b' }]);
  assert.deepEqual(loadStore(adminA).conversations.map((c) => c.id), ['a', 'b', 'c']);
});

test('restoreConversation is a no-op on duplicates and bad shapes', () => {
  withMemoryStorage();
  const conv = (id) => ({ id, title: id, updatedAt: 0, messages: [] });
  const store = { version: 1, activeId: 'a', conversations: [conv('a')] };
  assert.equal(restoreConversation(adminA, store, conv('a'), 0), store);
  assert.equal(restoreConversation(adminA, store, null, 0), store);
  assert.equal(restoreConversation(adminA, store, { title: 'no-id' }, 0), store);
  // Out-of-range index degrades to newest-first without crashing.
  const next = restoreConversation(adminA, store, conv('z'), 99);
  assert.equal(next.conversations[0].id, 'z');
});

test('restoreConversation trims oldest-first at the cap, never the restored', () => {
  withMemoryStorage();
  let store = loadStore(adminA);
  for (let i = 0; i < MAX_STORED_CONVERSATIONS; i++) {
    ({ store } = startConversation(adminA, store));
  }
  const victim = store.conversations[store.conversations.length - 1];
  const victimIndex = store.conversations.length - 1;
  store = deleteConversation(adminA, store, victim.id);
  store = restoreConversation(adminA, store, victim, victimIndex);
  assert.equal(store.conversations.length, MAX_STORED_CONVERSATIONS);
  assert.ok(store.conversations.some((c) => c.id === victim.id));
});

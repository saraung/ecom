import test from 'node:test';
import assert from 'node:assert/strict';
import { restoreChatSession } from './chatSession.js';

test('uses valid server session and its persisted history', async () => {
  const history = [{ role: 'user', content: 'Hello' }];
  const result = await restoreChatSession({ getHistory: async () => ({ data: history }) }, 'signed');
  assert.deepEqual(result, { sessionId: 'signed', history });
});

test('legacy or expired IDs are replaced by server-issued sessions', async () => {
  const result = await restoreChatSession({
    getHistory: async () => { throw { response: { status: 404 } }; },
    createSession: async () => ({ data: { session_id: 'server-issued' } }),
  }, 'old-browser-id');
  assert.deepEqual(result, { sessionId: 'server-issued', history: [] });
});

test('rate limits and outages do not trigger session rotation', async () => {
  let creations = 0;
  const error = { response: { status: 429 } };
  await assert.rejects(restoreChatSession({
    getHistory: async () => { throw error; },
    createSession: async () => { creations += 1; },
  }, 'signed'), caught => caught === error);
  assert.equal(creations, 0);
});

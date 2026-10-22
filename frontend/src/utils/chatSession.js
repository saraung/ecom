export async function restoreChatSession(chatAPI, savedId) {
  if (savedId) {
    try {
      const response = await chatAPI.getHistory(savedId);
      return { sessionId: savedId, history: response.data };
    } catch (error) {
      if (![401, 403, 404, 422].includes(error.response?.status)) throw error;
    }
  }
  const response = await chatAPI.createSession();
  if (typeof response.data?.session_id !== 'string') throw new Error('Invalid chat session');
  return { sessionId: response.data.session_id, history: [] };
}

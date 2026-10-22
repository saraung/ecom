// api/chat.js
import api from './axios';

export const chatAPI = {
  createSession: () => api.post('/chat/session'),
  // ✅ Send session ID with every request
  sendMessage: (message, sessionId) => {
    return api.post('/chat', { 
      message, 
      session_id: sessionId 
    });
  },
  
  // ✅ Get history for specific session
  getHistory: (sessionId) => {
    return api.get('/chat/history', { 
      headers: { 'X-Chat-Session': sessionId }
    });
  },
  
  // Capabilities stay out of URLs/access logs. Backend retains query compatibility.
  clearHistory: (sessionId) => {
    return api.delete('/chat/history', { 
      headers: { 'X-Chat-Session': sessionId }
    });
  },
};

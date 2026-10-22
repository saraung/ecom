import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { chatAPI } from '../../api/chat';
import { useAuth } from '../../hooks/useAuth';
import { restoreChatSession } from '../../utils/chatSession';

// Normalize one raw history/reply item from ANY backend shape into
// { sender: 'user' | 'bot', text: string }.
// Backend has used shapes like:
//   { sender, text } | { role, content } | { sender, message } |
//   { role: 'assistant', reply/answer/response } ...
// Returns null when the item carries no readable text (so the caller
// can filter it out instead of rendering an empty bubble).
const normalizeMessage = (raw) => {
  if (!raw) return null;
  if (typeof raw === 'string') {
    const text = raw.trim();
    return text ? { sender: 'bot', text } : null;
  }

  const role = (raw.sender ?? raw.role ?? raw.from ?? '').toString().toLowerCase();
  const sender = role === 'user' || role === 'human' || role === 'customer' ? 'user' : 'bot';

  const text = (
    raw.text ??
    raw.content ??
    raw.message ??
    raw.reply ??
    raw.answer ??
    raw.response ??
    ''
  ).toString().trim();

  if (!text) return null;
  return { sender, text };
};

// Accept any feed shape the backend may return:
// plain array | { history: [] } | { messages: [] } | { data: [] } | { items: [] }
const normalizeHistory = (payload) => {
  const data = payload?.data ?? payload;
  const list = Array.isArray(data)
    ? data
    : data?.history ??
      data?.messages ??
      data?.data ??
      data?.items ??
      [];
  if (!Array.isArray(list)) return [];
  return list.map(normalizeMessage).filter(Boolean);
};

// Accept any reply shape: { reply } | { response } | { answer } | { message } | string
const normalizeReply = (payload) => {
  const data = payload?.data ?? payload;
  if (typeof data === 'string') return data.trim();
  return (
    data?.reply ??
    data?.response ??
    data?.answer ??
    data?.message ??
    data?.text ??
    ''
  ).toString().trim();
};

const GREETING = { sender: 'bot', text: 'Hi! 👋 How can I help you today?' };

const Chatbot = () => {
  const { user } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const messagesEndRef = useRef(null);
  const historyVersion = useRef(0);

  const [sessionId, setSessionId] = useState('');

  // Auto-scroll to latest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, typing]);

  // Load chat history when chat opens
  // Show a loading state while fetching so we never render
  // half-mapped / empty placeholder bubbles.
  const [historyLoading, setHistoryLoading] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    let cancelled = false;
    historyVersion.current += 1;

    const fetchHistory = async () => {
      setHistoryLoading(true);
      setTyping(false);
      setSessionId('');
      setMessages([GREETING]);
      try {
        const owner = user?.id || 'guest';
        const saved = sessionStorage.getItem('chat_session_owner') === owner ? sessionStorage.getItem('chat_session_id') : '';
        const restored = await restoreChatSession(chatAPI, saved);
        if (cancelled) return;
        sessionStorage.setItem('chat_session_id', restored.sessionId);
        sessionStorage.setItem('chat_session_owner', owner);
        setSessionId(restored.sessionId);
        const normalized = normalizeHistory(restored.history);
        // normalizeHistory unwraps axios ({ data }) and filters empties.
        // Keep greeting if backend has no history yet.
        setMessages(normalized.length > 0 ? normalized : [GREETING]);
      } catch (err) {
        if (!cancelled) {
          setMessages([{ sender: 'bot', text: err.response?.data?.detail || 'Chat is temporarily unavailable. Please reopen it to try again.' }]);
        }
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    };
    fetchHistory();

    return () => {
      cancelled = true;
      historyVersion.current += 1;
    };
  }, [isOpen, user?.id]);

  const sendMessage = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || typing || historyLoading || !sessionId) return;

    const version = historyVersion.current;
    setMessages((prev) => [...prev, { sender: 'user', text }].slice(-20));
    setInput('');
    setTyping(true);

    try {
      // ✅ Send session ID with message
      const response = await chatAPI.sendMessage(text, sessionId);
      if (version !== historyVersion.current) return;
      const reply = normalizeReply(response);
      setMessages((prev) => [
        ...prev,
        {
          sender: 'bot',
          text: reply || 'Sorry, I could not generate a reply. Please try again.',
        },
      ].slice(-20));
    } catch (err) {
      if (version !== historyVersion.current) return;
      setMessages((prev) => [
        ...prev,
        { sender: 'bot', text: err.response?.data?.detail || 'Sorry, something went wrong. Please try again.' },
      ].slice(-20));
    } finally {
      if (version === historyVersion.current) setTyping(false);
    }
  };

  const [clearing, setClearing] = useState(false);

  const clearChat = async () => {
    if (clearing || typing || historyLoading || !sessionId) return;
    setClearing(true);
    // Optimistic clear: reset UI immediately so the button always
    // "works", even if the backend call fails (e.g. 422 for a
    // session the server already forgot).
    setMessages([GREETING]);
    setTyping(false);
    try {
      // ✅ Clear history for this session
      await chatAPI.clearHistory(sessionId);
    } catch (err) {
      console.error(
        'Failed to clear history on server:',
        err?.response?.status,
        err?.response?.data || err?.message
      );
    } finally {
      setClearing(false);
    }
  };

  // ✅ Custom renderer for markdown content
  // NOTE: react-markdown v10 passes a `node` prop to custom components —
  // strip it so React doesn't warn about unknown DOM props.
  // Also removed the invalid `'p, ul, ol, li'` key (not a real tag).
  const renderMessageContent = (text) => {
    const safeText = (text ?? '').toString();
    if (!safeText.trim()) return null;
    return (
      <ReactMarkdown
        components={{
          p: ({ node, children }) => <span className="block">{children}</span>,
          strong: ({ node, children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ node, children }) => <em className="italic">{children}</em>,
          ul: ({ node, children }) => <ul className="list-disc pl-4 my-1 space-y-0.5">{children}</ul>,
          ol: ({ node, children }) => <ol className="list-decimal pl-4 my-1 space-y-0.5">{children}</ol>,
          li: ({ node, children }) => <li className="text-sm">{children}</li>,
          br: () => <br />,
          a: ({ node, children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
              {children}
            </a>
          ),
        }}
      >
        {safeText}
      </ReactMarkdown>
    );
  };

  return (
    <>
      {/* Floating Button */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          className="fixed bottom-5 right-5 z-50 w-14 h-14 bg-primary rounded-full shadow-lg hover:bg-primary-hover hover:scale-110 transition flex items-center justify-center text-primary-foreground text-2xl"
          aria-label="Open chat"
        >
          💬
        </button>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-5 right-5 z-50 w-[85vw] max-w-sm h-125 max-h-[70vh] bg-card rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-border">
          {/* Header */}
          <div className="bg-primary text-primary-foreground px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-9 h-9 bg-card/20 rounded-full flex items-center justify-center text-lg">🤖</div>
              <div>
                <p className="font-semibold text-sm">Shop Assistant</p>
                <p className="text-xs text-primary-foreground/70">Online</p>
              </div>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={clearChat}
                disabled={clearing}
                className="hover:bg-card/20 rounded-full w-8 h-8 flex items-center justify-center transition text-sm disabled:opacity-50"
                aria-label="Clear chat"
                title={clearing ? 'Clearing…' : 'Clear chat'}
              >
                {clearing ? '…' : '🗑️'}
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="hover:bg-card/20 rounded-full w-8 h-8 flex items-center justify-center transition"
                aria-label="Close chat"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 bg-background">
            {historyLoading ? (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-muted-foreground">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <p className="text-xs">Loading conversation…</p>
              </div>
            ) : (
              messages
                .filter((msg) => msg && (msg.text ?? '').toString().trim())
                .map((msg, i) => (
              <div key={i} className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div
                  className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm ${
                    msg.sender === 'user'
                      ? 'bg-primary text-primary-foreground rounded-br-sm'
                      : 'bg-card text-foreground border border-border rounded-bl-sm'
                  }`}
                >
                  {msg.sender === 'bot' ? (
                    renderMessageContent(msg.text)
                  ) : (
                    <span>{msg.text}</span>
                  )}
                </div>
              </div>
                ))
            )}

            {/* Typing indicator */}
            {typing && (
              <div className="flex justify-start">
                <div className="bg-card border border-border px-4 py-3 rounded-2xl rounded-bl-sm flex gap-1">
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <form onSubmit={sendMessage} className="p-3 border-t border-border flex gap-2 bg-card">
            <input
              type="text"
              maxLength={2000}
              disabled={historyLoading || !sessionId}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Type a message..."
              className="flex-1 px-3 py-2 border border-border rounded-full text-sm focus:outline-none focus:ring-2 focus:ring-ring"
            />
            <button
              type="submit"
              disabled={!input.trim() || typing || historyLoading || !sessionId}
              className="bg-primary text-primary-foreground px-4 py-2 rounded-full hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition text-sm font-medium"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </>
  );
};

export default Chatbot;

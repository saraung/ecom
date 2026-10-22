import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { GoogleOAuthProvider } from '@react-oauth/google';
import App from './App';
import { ThemeProvider } from './contexts/ThemeContext';
import './index.css';

// Apply saved theme BEFORE first paint (avoids light-flash in dark mode)
try {
  const stored = localStorage.getItem('ec-theme');
  let theme = stored === 'light' || stored === 'dark' || stored === 'system' ? stored : null;
  if (!theme) {
    try {
      const legacy = JSON.parse(localStorage.getItem('preferences') || '{}');
      if (legacy?.theme === 'light' || legacy?.theme === 'dark' || legacy?.theme === 'system') {
        theme = legacy.theme;
      }
    } catch { /* ignore */ }
  }
  const resolved =
    theme === 'dark' ? 'dark'
    : theme === 'system' && window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark'
    : 'light';
  document.documentElement.classList.toggle('dark', resolved === 'dark');
  document.documentElement.style.colorScheme = resolved;
} catch { /* ignore */ }

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <GoogleOAuthProvider clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID}>
      <BrowserRouter>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </BrowserRouter>
    </GoogleOAuthProvider>
  </React.StrictMode>
);
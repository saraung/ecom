// src/context/ThemeContext.jsx
// ThemeProvider — manages "light" | "dark" | "system" mode.
// The class `.dark` is toggled on <html>, which flips every CSS
// variable in src/styles/theme.css. Preference is persisted in
// localStorage so the choice survives refreshes.
import React, { createContext, useContext, useEffect, useState, useCallback, useRef } from 'react';

const STORAGE_KEY = 'ec-admin-theme';

const SMOOTH_SWITCH_MS = 300;

function getStoredTheme() {
  try {
    const t = window.localStorage.getItem(STORAGE_KEY);
    return t === 'dark' || t === 'light' || t === 'system' ? t : 'system';
  } catch {
    return 'system';
  }
}

function getSystemTheme() {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

const ThemeContext = createContext({
  theme: 'system',
  resolvedTheme: 'light',
  setTheme: () => {},
  toggleTheme: () => {},
});

export const ThemeProvider = ({ children }) => {
  const [theme, setThemeState] = useState(getStoredTheme);
  const [resolvedTheme, setResolvedTheme] = useState(() =>
    getStoredTheme() === 'system' ? getSystemTheme() : getStoredTheme()
  );

  // Timestamp of the last theme switch, for debouncing rapid re-toggles.
  const lastSwitchAt = useRef(0);

  // Apply the class to <html> whenever the theme changes
  useEffect(() => {
    const root = document.documentElement;

    const apply = (resolved) => {
      root.classList.toggle('dark', resolved === 'dark');
      root.style.colorScheme = resolved;
      setResolvedTheme(resolved);
    };

    // Smooth color transition while switching
    // Debounce: if the user flips back before the fade finishes, don't
    // re-arm the class or restart the timer — let the previous fade run out
    // instead of compounding several overlapping transitions.
    const now = Date.now();
    const isQuickRestart = now - lastSwitchAt.current < SMOOTH_SWITCH_MS;
    lastSwitchAt.current = now;
    let t;
    if (!isQuickRestart) {
      root.classList.add('theme-transition');
      t = setTimeout(() => root.classList.remove('theme-transition'), SMOOTH_SWITCH_MS);
    }

    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      apply(mq.matches ? 'dark' : 'light');
      const onChange = (e) => apply(e.matches ? 'dark' : 'light');
      mq.addEventListener('change', onChange);
      return () => {
        mq.removeEventListener('change', onChange);
        clearTimeout(t);
      };
    }

    apply(theme === 'dark' ? 'dark' : 'light');
    return () => clearTimeout(t);
  }, [theme]);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable — theme still applies for this session */
    }
  }, []);

  // For quick header toggle: flips between the *resolved* light/dark
  const toggleTheme = useCallback(() => {
    setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
  }, [resolvedTheme, setTheme]);

  return (
    <ThemeContext.Provider value={{ theme, resolvedTheme, setTheme, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = () => useContext(ThemeContext);
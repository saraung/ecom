import React, { createContext, useCallback, useEffect, useMemo, useState } from 'react';

export const ThemeContext = createContext({
  theme: 'system',
  resolvedTheme: 'light',
  setTheme: () => {},
  toggleTheme: () => {},
});

const STORAGE_KEY = 'ec-theme'; // 'light' | 'dark' | 'system'
const LEGACY_KEY = 'preferences';

function readStoredTheme() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw;
    // Migrate from legacy Settings `preferences.theme` blob if present
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      const parsed = JSON.parse(legacy);
      if (parsed?.theme === 'light' || parsed?.theme === 'dark' || parsed?.theme === 'system') {
        return parsed.theme;
      }
    }
  } catch {
    /* ignore */
  }
  // Default to light — only follow the OS if the user explicitly picks "System".
  return 'light';
}

function getSystemTheme() {
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return 'light';
}

function applyResolvedTheme(resolved) {
  const root = document.documentElement;
  // Smooth switch (matches theme.css .theme-transition helper)
  root.classList.add('theme-transition');
  window.clearTimeout(applyResolvedTheme._t);
  applyResolvedTheme._t = window.setTimeout(() => root.classList.remove('theme-transition'), 300);

  root.classList.toggle('dark', resolved === 'dark');
  root.style.colorScheme = resolved;
}

export const ThemeProvider = ({ children }) => {
  const [theme, setThemeState] = useState(() => readStoredTheme());
  const [systemDark, setSystemDark] = useState(() => getSystemTheme() === 'dark');

  // Track OS preference so `system` mode follows it live
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = (e) => setSystemDark(e.matches);
    mq.addEventListener?.('change', onChange);
    return () => mq.removeEventListener?.('change', onChange);
  }, []);

  const resolvedTheme = theme === 'system' ? (systemDark ? 'dark' : 'light') : theme;

  // Apply to <html> + persist (both new key and legacy preferences blob)
  useEffect(() => {
    applyResolvedTheme(resolvedTheme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
      const legacyRaw = localStorage.getItem(LEGACY_KEY);
      let legacy = {};
      try {
        legacy = legacyRaw ? JSON.parse(legacyRaw) : {};
      } catch {
        legacy = {};
      }
      localStorage.setItem(LEGACY_KEY, JSON.stringify({ ...legacy, theme }));
    } catch {
      /* ignore */
    }
  }, [theme, resolvedTheme]);

  const setTheme = useCallback((next) => {
    if (next === 'light' || next === 'dark' || next === 'system') setThemeState(next);
  }, []);

  const toggleTheme = useCallback(() => {
    setThemeState((prev) => {
      const resolved = prev === 'system' ? (getSystemTheme() === 'dark' ? 'dark' : 'light') : prev;
      return resolved === 'dark' ? 'light' : 'dark';
    });
  }, []);

  const value = useMemo(
    () => ({ theme, resolvedTheme, setTheme, toggleTheme }),
    [theme, resolvedTheme, setTheme, toggleTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

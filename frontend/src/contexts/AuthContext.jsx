import React, { createContext, useState, useEffect } from 'react';
import { authAPI } from '../api/auth';

export const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('access_token');

    // A privileged (staff/admin) login attempt used to persist the literal string
    // "undefined" here — treat that as "no session" and clear the residue.
    if (token && token !== 'undefined' && token !== 'null') {
      fetchUser();
    } else {
      if (token) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
      }
      setLoading(false);
    }
  }, []);

  const fetchUser = async () => {
    try {
      const response = await authAPI.getMe();
      setUser(response.data);

      // Dispatch event to trigger cart sync
      window.dispatchEvent(new Event('authChanged'));
    } catch (error) {
      console.error('❌ Failed to fetch user:', error);
      // ✅ Only clear the session when auth was definitively rejected — the axios
      //    interceptor has already tried the refresh. Network/server errors must NOT
      //    silently log the user out.
      if (error.response?.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  };

  const login = (data) => {
    // Storefront logins send audience "storefront", so every account — shopper
    // or staff — gets real tokens back (no OTP challenge on this channel).
    // If a 200 arrives without a token, something is wrong upstream: fail loudly
    // rather than persisting the string "undefined" as a bearer token, which
    // used to cause a silent 401 → refresh → hardLogout bounce.
    if (!data?.access_token) {
      const err = new Error('Sign-in did not return a session.');
      err.code = 'NO_SESSION_TOKEN';
      throw err;
    }

    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    fetchUser();
  };

  const logout = async () => {
    try {
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        await authAPI.logout(refreshToken);
      }
    } catch (error) {
      console.error('❌ Logout error:', error);
    } finally {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      setUser(null);
      window.dispatchEvent(new Event('authChanged'));
    }
  };

  const updateUser = (updatedUser) => {
    setUser(updatedUser);
  };

  const value = {
    user,
    loading,
    login,
    logout,
    updateUser,
    isAuthenticated: !!user,
    // Legacy single-role field from /auth/me. Login.jsx uses it to route staff
    // away from the landing page; fine-grained privileges live in `permissions`.
    userRole: user?.role ?? null,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
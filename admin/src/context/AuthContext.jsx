// src/context/AuthContext.jsx
import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../api/client';
import { login as apiLogin, googleLogin as apiGoogleLogin, verifyLoginOtp as apiVerifyLoginOtp, resendLoginOtp as apiResendLoginOtp } from '../api/auth';
import { canDo } from '../utils/permissions';
import { logout as apiLogout } from '../api/auth';
import { clearOwnerStore } from '../utils/mcpChatStore';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  // Synchronously hydrate the cached profile (written to localStorage on
  // every login and /auth/me response) so role-aware UI — sidebar links,
  // header name/avatar — renders statically on refresh instead of blinking
  // in after /auth/me responds. The token is still re-validated in the
  // background by fetchUser(), which refreshes the cache with fresh data.
  const [user, setUser] = useState(() => {
    if (!localStorage.getItem('access_token')) return null;
    try {
      const cached = localStorage.getItem('user');
      return cached ? JSON.parse(cached) : null;
    } catch {
      return null;
    }
  });
  const [loading, setLoading] = useState(() => !!localStorage.getItem('access_token'));
  // Optimistic session: a stored token means "probably authenticated".
  // Pages render immediately from the cached profile while fetchUser()
  // revalidates in the background — no skeleton flash on reload. A truly
  // dead token is caught by the apiClient interceptor (hardLogout →
  // redirect), so the optimistic window only ever shows stale-but-real UI.
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => !!localStorage.getItem('access_token')
  );
  const [userRole, setUserRole] = useState(() => user?.role || null);
  // Dynamic RBAC: permission keys + role slugs from /auth/me.
  // Cached sessions (old shape) simply yield empty arrays and every gate
  // falls back to the legacy role string until fetchUser refreshes.
  const [permissions, setPermissions] = useState(() => user?.permissions || []);
  const [roles, setRoles] = useState(() => user?.roles || (user?.role ? [user.role] : []));

  useEffect(() => {
    // loading is already initialized to the correct value (true only when a
    // token exists), so this effect just re-validates the session.
    if (localStorage.getItem('access_token')) {
      fetchUser();
    }
  }, []);

  const syncUserState = (userData) => {
    setUser(userData);
    setUserRole(userData?.role || null);
    setPermissions(userData?.permissions || []);
    setRoles(
      userData?.roles || (userData?.role ? [userData.role] : [])
    );
    if (userData) {
      localStorage.setItem('user', JSON.stringify(userData));
    }
  };

  const fetchUser = async () => {
    try {
      // If the access token expired, the apiClient response interceptor
      // transparently refreshes it and retries this request, so this
      // call succeeds with the renewed session.
      const response = await api.get('/auth/me');
      syncUserState(response.data);
      setIsAuthenticated(true);
    } catch (error) {
      // Definitive auth failure is already handled by the interceptor
      // (hardLogout → redirect to /login). A network-level failure (no
      // response) keeps the optimistic session — the next API call will
      // re-trigger validation instead of kicking the user out on a blip.
      if (error?.response) {
        // Do not leave the dashboard rendered from a cached profile after
        // the API has rejected the session. The interceptor normally performs
        // this cleanup, but keeping it here also covers a failed revalidation
        // during startup and makes the next navigation deterministic.
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        setUser(null);
        setUserRole(null);
        setPermissions([]);
        setRoles([]);
        setIsAuthenticated(false);
      }
    } finally {
      setLoading(false);
    }
  };

  const login = async (email, password) => {
    try {
      const response = await apiLogin({ email, password });
      const data = response.data;

      // Privileged accounts stop at the OTP challenge — no tokens yet.
      if (data?.otp_required) {
        return {
          success: true,
          otpRequired: true,
          challengeToken: data.challenge_token,
          emailMasked: data.email_masked,
        };
      }

      // Shoppers (and legacy backends) receive tokens immediately.
      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
      }
      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token);
      }

      // Fetch user data from /auth/me using the token
      const userResponse = await api.get('/auth/me');
      const userData = userResponse.data;

      if (userData) {
        syncUserState(userData);
      }

      setIsAuthenticated(true);
      return { success: true };
    } catch (error) {

      // Clean up on error
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      setUser(null);
      setUserRole(null);
      setPermissions([]);
      setRoles([]);
      setIsAuthenticated(false);

      let errorMessage = 'Login failed. Please try again.';

      if (error.response?.status === 401) {
        errorMessage = 'Invalid email or password. Please try again.';
      } else if (error.response?.status === 403) {
        errorMessage = 'Your account is disabled. Please contact support.';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }

      return {
        success: false,
        error: errorMessage,
      };
    }
  };

  // Step 2 of the admin OTP flow: exchange challenge + email code for
  // session tokens, then hydrate exactly like a direct login.
  const verifyLoginOtp = async (challengeToken, otpCode) => {
    try {
      const response = await apiVerifyLoginOtp(challengeToken, otpCode);
      const data = response.data;

      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
      }
      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token);
      }

      const userResponse = await api.get('/auth/me');
      if (userResponse.data) {
        syncUserState(userResponse.data);
      }

      setIsAuthenticated(true);
      return { success: true };
    } catch (error) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      setUser(null);
      setUserRole(null);
      setPermissions([]);
      setRoles([]);
      setIsAuthenticated(false);
      let errorMessage = 'Verification failed. Please try again.';
      if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      return { success: false, error: errorMessage };
    }
  };

  // Re-send the admin-login code for a live challenge (60s cooldown).
  const resendLoginOtp = async (challengeToken) => {
    try {
      await apiResendLoginOtp(challengeToken);
      return { success: true };
    } catch (error) {
      let errorMessage = 'Could not resend the code. Please try again.';
      if (error.response?.status === 429) {
        errorMessage = error.response?.data?.detail || 'Please wait before requesting a new code.';
      } else if (error.response?.status === 401) {
        errorMessage = 'Session expired. Please sign in again.';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }
      return { success: false, error: errorMessage };
    }
  };

  const googleLogin = async (idToken) => {
    try {
      const response = await apiGoogleLogin(idToken);
      const data = response.data;

      // Privileged Google accounts also stop at the OTP challenge.
      if (data?.otp_required) {
        return {
          success: true,
          otpRequired: true,
          challengeToken: data.challenge_token,
          emailMasked: data.email_masked,
        };
      }

      if (data.access_token) {
        localStorage.setItem('access_token', data.access_token);
      }
      if (data.refresh_token) {
        localStorage.setItem('refresh_token', data.refresh_token);
      }

      const userResponse = await api.get('/auth/me');
      const userData = userResponse.data;

      if (userData) {
        syncUserState(userData);
      }

      setIsAuthenticated(true);
      return { success: true };
    } catch (error) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      setUserRole(null);
      setPermissions([]);
      setRoles([]);

      let errorMessage = 'Google login failed. Please try again.';
      if (error.response?.status === 403) {
        errorMessage = 'Your account is disabled. Please contact support.';
      } else if (error.response?.data?.detail) {
        errorMessage = error.response.data.detail;
      }

      return { success: false, error: errorMessage };
    }
  };

  // Merge partial user updates (e.g. profile changes from Settings) into
  // state and localStorage so the UI reflects them immediately.
  const updateUser = (updates) => {
    setUser((prev) => {
      if (!prev) return prev;
      const next = { ...prev, ...updates };
      localStorage.setItem('user', JSON.stringify(next));
      return next;
    });
  };

  const logout = () => {
    const refreshToken = localStorage.getItem('refresh_token');
    if (refreshToken) {
      // Keep local logout immediate; the API accepts the refresh credential itself.
      apiLogout(refreshToken).catch(() => {});
    }
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
    clearOwnerStore(user);
    setUser(null);
    setUserRole(null);
    setPermissions([]);
    setRoles([]);
    setIsAuthenticated(false);
  };

  // Permission gate with legacy-role fallback (see utils/permissions).
  const hasPermission = (key) => canDo(
    { role: userRole, permissions },
    key,
  );

  const value = {
    user,
    userRole,
    permissions,
    roles,
    hasPermission,
    loading,
    isAuthenticated,
    login,
    verifyLoginOtp,
    resendLoginOtp,
    googleLogin,
    logout,
    updateUser,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
};

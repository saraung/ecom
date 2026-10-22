// src/pages/auth/Login.jsx
import React, { useState, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { GoogleLogin, useGoogleOneTapLogin } from '@react-oauth/google';
import { Sparkles, Truck, ShieldCheck, ArrowLeft } from 'lucide-react';
import { authAPI } from '../../api/auth';
import { useAuth } from '../../hooks/useAuth';
import RegisterPanel from './RegisterPanel';

// A 200 response with no access token means the backend answered something we
// don't understand — surface it instead of letting it look like a success.
const isNoSessionTokenError = (err) => err?.code === 'NO_SESSION_TOKEN';

const loginResponseErrorMessage = () =>
  'Sign-in did not return a session. Please try again.';

const HIGHLIGHTS = [
  { icon: Sparkles, label: 'Curated picks' },
  { icon: Truck, label: 'Fast delivery' },
  { icon: ShieldCheck, label: 'Secure checkout' },
];

const Login = () => {
  const [mode, setMode] = useState('login'); // 'login' | 'register'
  const [formData, setFormData] = useState({
    email: '',
    password: '',
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');
  const [oneTapDone, setOneTapDone] = useState(false);

  const navigate = useNavigate();
  const location = useLocation();
  const { login, isAuthenticated, userRole } = useAuth();

  // Check for success message from register or reset password
  useEffect(() => {
    if (location.state?.message) {
      setSuccessMessage(location.state.message);

      // Clear the state so message doesn't show on refresh
      window.history.replaceState({}, document.title);
    }
  }, [location]);

  // Redirect if already logged in - Role-based redirect
  useEffect(() => {
    if (isAuthenticated) {
      const redirectTo =
        localStorage.getItem('redirectAfterLogin') ||
        location.state?.from ||
        '/';

      localStorage.removeItem('redirectAfterLogin');

      // Redirect staff to products page
      let finalRedirect = redirectTo;

      if (userRole === 'staff' && redirectTo === '/') {
        finalRedirect = '/products';
      }

      navigate(finalRedirect);
    }
  }, [isAuthenticated, navigate, location, userRole]);

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    setLoading(true);
    setError('');
    setSuccessMessage('');

    try {
      const response = await authAPI.login(formData);
      login(response.data);
    } catch (err) {
      // Better error handling
      if (isNoSessionTokenError(err)) {
        setError(loginResponseErrorMessage(err));
      } else if (
        err.response?.status === 400 &&
        err.response?.data?.detail?.includes('Google')
      ) {
        setError(
          'This account was created with Google. Please sign in with Google.'
        );
      } else {
        setError(
          err.response?.data?.detail ||
            'Login failed. Please try again.'
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSuccess = async (credentialResponse) => {
    setLoading(true);
    setOneTapDone(true); // latch: never re-prompt while auth/redirect settles
    setError('');
    setSuccessMessage('');

    try {
      const response = await authAPI.googleLogin(
        credentialResponse.credential
      );

      login(response.data);
    } catch (err) {
      // Defensive: a malformed 200 response should not look like a success.
      setError(
        isNoSessionTokenError(err)
          ? loginResponseErrorMessage(err)
          : err.response?.data?.detail ||
              'Google login failed. Please try again.'
      );
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleError = () => {
    setError('Google login failed. Please try again.');
  };

  // One Tap — "Continue as ..." prompt for logged-out users.
  // Reuses the same ID-token → /auth/google flow as the Google button above.
  useGoogleOneTapLogin({
    onSuccess: handleGoogleSuccess,

    // Silent: dismissal / opt-out must not show an error banner
    onError: () => {},

    // Prompt moments are normal traffic, not problems: a `skipped: tap_outside`
    // just means the user touched the page before the prompt appeared, and GSI's
    // own FedCM/AbortError console noise is browser-side. Use console.debug so
    // these stay out of the default-visible console.
    promptMomentNotification: (notification) => {
      const type = notification?.getMomentType?.();

      if (type === 'skipped') {
        console.debug(
          '👤 One Tap skipped:',
          notification?.getSkippedReason?.()
        );
      } else if (type === 'dismissed') {
        console.debug(
          '👤 One Tap dismissed:',
          notification?.getDismissedReason?.()
        );
      } else if (type !== 'display') {
        console.debug('👤 One Tap moment:', type);
      }
    },

    cancel_on_tap_outside: true,
    use_fedcm_for_prompt: true,
    auto_select: false,
    disabled: isAuthenticated || loading || oneTapDone,
  });

  return (
    <div className="min-h-screen flex bg-background">

      {/* ── LEFT: Brand / Design Showcase ─────────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[46%] xl:w-1/2 relative overflow-hidden bg-primary-soft border-r border-border p-12 xl:p-16">

        {/* Decorative glows */}
        <div
          aria-hidden="true"
          className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-foreground/5 blur-3xl"
        />

        <div
          aria-hidden="true"
          className="absolute -bottom-40 -left-24 w-[28rem] h-[28rem] rounded-full bg-foreground/5 blur-3xl"
        />

        {/* Brand row */}
        <div className="relative flex items-center justify-between">

          <Link
            to="/"
            className="flex items-center gap-2.5 group"
          >
            <span className="w-10 h-10 rounded-2xl bg-primary text-primary-foreground flex items-center justify-center font-black text-xl tracking-tighter group-hover:scale-105 transition-transform">
              E
            </span>

            <span className="text-2xl font-extrabold tracking-tighter text-foreground">
              E-Shop.
            </span>
          </Link>

          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={14} />
            Back to store
          </Link>
        </div>

        {/* Headline */}
        <div className="relative max-w-md">

          <h1 className="text-4xl xl:text-[2.75rem] font-black leading-[1.1] tracking-tighter text-foreground">
            Discover & own
            <br />
            the designs
            <br />
            you deserve.
          </h1>

          <p className="mt-6 text-base text-muted-foreground leading-relaxed">
            Premium marketplace for curated products, fast delivery
            and secure checkout.
          </p>

          {/* Quick highlights */}
          <div className="mt-8 flex flex-wrap gap-3">

            {HIGHLIGHTS.map(({ icon: Icon, label }) => (
              <span
                key={label}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-card border border-border text-xs font-bold uppercase tracking-wider text-foreground"
              >
                <Icon size={14} />
                {label}
              </span>
            ))}

          </div>
        </div>

        {/* Stats + testimonial */}
        <div className="relative mt-12 flex flex-wrap items-center gap-x-10 gap-y-4">

          <div>
            <p className="text-2xl font-black tracking-tighter text-foreground">
              50K+
            </p>

            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mt-0.5">
              Happy shoppers
            </p>
          </div>

          <div>
            <p className="text-2xl font-black tracking-tighter text-foreground">
              4.9
              <span className="text-muted-foreground">
                ★
              </span>
            </p>

            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mt-0.5">
              Average rating
            </p>
          </div>

        </div>
      </div>

      {/* ── RIGHT: Login Options ──────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-4 py-12 sm:px-8">

        <div className="w-full max-w-md">

          {/* Mobile-only brand + back to store */}
          <div className="lg:hidden flex items-center justify-between gap-4 mb-8">

            <Link
              to="/"
              className="flex items-center gap-2 flex-shrink-0"
            >
              <span className="w-9 h-9 rounded-xl bg-primary text-primary-foreground flex items-center justify-center font-black text-lg">
                E
              </span>

              <span className="text-2xl font-extrabold tracking-tighter text-foreground">
                E-Shop.
              </span>
            </Link>

            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-primary border border-border rounded-full px-3 py-2 hover:bg-primary-soft transition-colors"
            >
              <ArrowLeft size={14} />
              Store
            </Link>

          </div>

          {mode === 'register' ? (
            <>
              <RegisterPanel
                onSwitchToLogin={(email) => {
                  setMode('login');

                  if (email) {
                    setFormData((prev) => ({
                      ...prev,
                      email,
                    }));
                  }

                  setSuccessMessage(
                    'Account created successfully! Please login.'
                  );
                }}
              />

              <p className="mt-6 text-center text-sm text-muted-foreground">
                Already have an account?{' '}

                <button
                  type="button"
                  onClick={() => setMode('login')}
                  className="font-semibold text-primary hover:text-primary-hover transition-colors cursor-pointer"
                >
                  Sign in
                </button>
              </p>
            </>
          ) : (
            <>
              {/* Login heading */}
              <div className="text-center">

                <h2 className="text-3xl font-extrabold tracking-tight text-foreground">
                  Welcome back
                </h2>

                <p className="mt-2 text-sm text-muted-foreground">
                  Sign in to continue to your account
                </p>

              </div>

              {/* Success message */}
              {successMessage && (
                <div className="mt-6 alert-success px-4 py-3 rounded-lg relative">
                  <span className="block sm:inline">
                    ✅ {successMessage}
                  </span>
                </div>
              )}

              {/* Error message */}
              {error && (
                <div className="mt-6 alert-danger px-4 py-3 rounded-lg relative">
                  <span className="block sm:inline">
                    ❌ {error}
                  </span>
                </div>
              )}

              {/* Social login */}
              <div className="mt-8">

                {/* 
                  Google requires the width to be specified in pixels.
                  Maximum supported width is 400px.

                  Previously:
                  width="100%"

                  That caused the personalized
                  "Sign in as Saraung" button to render much narrower.

                  Using 400px makes the Google button fill the
                  available desktop login width.
                */}
                <div className="w-full flex justify-center overflow-hidden">
                  <GoogleLogin
                    onSuccess={handleGoogleSuccess}
                    onError={handleGoogleError}
                    theme="filled_blue"
                    size="large"
                    shape="rectangular"
                    text="signin_with"
                    logo_alignment="left"
                    width={400}
                  />
                </div>

                {/* Divider */}
                <div className="relative mt-7">

                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-border" />
                  </div>

                  <div className="relative flex justify-center text-sm">
                    <span className="px-2 bg-background text-muted-foreground">
                      or with your email
                    </span>
                  </div>

                </div>
              </div>

              {/* Email/password login */}
              <form
                className="mt-7 space-y-5"
                onSubmit={handleSubmit}
              >

                {/* Email */}
                <div>

                  <label
                    htmlFor="email"
                    className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5"
                  >
                    Email address
                  </label>

                  <input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                    value={formData.email}
                    onChange={handleChange}
                    className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                    placeholder="you@example.com"
                  />

                </div>

                {/* Password */}
                <div>

                  <div className="flex items-center justify-between mb-1.5">

                    <label
                      htmlFor="password"
                      className="block text-xs font-bold uppercase tracking-widest text-foreground"
                    >
                      Password
                    </label>

                    <Link
                      to="/forgot-password"
                      className="text-xs font-semibold text-primary hover:text-primary-hover transition-colors"
                    >
                      Forgot password?
                    </Link>

                  </div>

                  <input
                    id="password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={formData.password}
                    onChange={handleChange}
                    className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                    placeholder="••••••••"
                    minLength={6}
                  />

                </div>

                {/* Sign in */}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full flex justify-center items-center py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300"
                >
                  {loading ? 'Signing in...' : 'Sign in'}
                </button>

              </form>

              {/* Register */}
              <p className="mt-7 text-center text-sm text-muted-foreground">
                New to E-Shop?{' '}

                <button
                  type="button"
                  onClick={() => setMode('register')}
                  className="font-semibold text-primary hover:text-primary-hover transition-colors cursor-pointer"
                >
                  Create an account
                </button>
              </p>

            </>
          )}

        </div>
      </div>
    </div>
  );
};

export default Login;
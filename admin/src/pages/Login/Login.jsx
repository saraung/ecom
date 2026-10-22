// src/pages/Login/Login.jsx
import React, { useState, useEffect, useRef } from 'react';
import { useNavigate, Navigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { Mail, Lock, Loader, Eye, EyeOff, LockKeyhole, TriangleAlert } from 'lucide-react';
import BrandPanel from '../../components/auth/BrandPanel';
import OtpChallenge from '../../components/auth/OtpChallenge';

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
// Optional storefront URL for the "Back to store" link (unset = hidden).
const STOREFRONT_URL = import.meta.env.VITE_STOREFRONT_URL;

const Login = () => {
  const navigate = useNavigate();
  const { login, verifyLoginOtp, resendLoginOtp, googleLogin, isAuthenticated } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockOn, setCapsLockOn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState('');
  // 'credentials' | 'otp'
  const [stage, setStage] = useState('credentials');
  const [challenge, setChallenge] = useState(null);
  const [otpLoading, setOtpLoading] = useState(false);
  const [otpError, setOtpError] = useState('');
  // 'pending' | 'ready' | 'unavailable' — tracks the Google GSI script.
  const [googleState, setGoogleState] = useState(
    GOOGLE_CLIENT_ID ? 'pending' : 'unavailable'
  );
  const googleButtonRef = useRef(null);
  // One Tap must fire exactly once per visit: GSI's FedCM
  // navigator.credentials.get crashes when two prompts overlap (notably
  // under StrictMode double-effects), so this flag + cancel-on-cleanup
  // keeps a single outstanding request at all times.
  const oneTapPromptedRef = useRef(false);
  // Tracks whether WE have handed the container to Google. The container
  // must never hold React-rendered children and must never be cleared with
  // innerHTML while React tracks children inside it — either one makes
  // React's removeChild blow up with NotFoundError (Google mutates that
  // subtree outside React's knowledge).
  const googleRenderedRef = useRef(false);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || isAuthenticated) return;

    let cancelled = false;
    let attempts = 0;
    let intervalId = null;

    const initGoogle = () => {
      if (cancelled || !window.google?.accounts?.id) return false;

      try {
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleCredential,
          auto_select: false,
          cancel_on_tap_outside: true,
        });

        const container = googleButtonRef.current;
        if (container && !googleRenderedRef.current) {
          googleRenderedRef.current = true;
          window.google.accounts.id.renderButton(container, {
            theme: 'outline',
            size: 'large',
            width: '100%',
            shape: 'rectangular',
            text: 'continue_with',
            logo_alignment: 'center',
          });
        }

        // NOTE: no google.accounts.id.prompt() here on purpose. One Tap's
        // FedCM navigator.credentials.get race ("Only one ... request may be
        // outstanding") crashes under StrictMode double-effects, and the
        // button flow doesn't need it.
        setGoogleState('ready');
        return true;
      } catch {
        setGoogleState('unavailable');
        return true; // stop retrying; config/origin error, not timing
      }
    };

    // The GSI <script> is async: it may arrive after React mounts, and the
    // window 'load' event may already have fired. Poll briefly instead of
    // trusting either one.
    if (initGoogle()) return undefined;
    intervalId = setInterval(() => {
      attempts += 1;
      if (initGoogle() || attempts >= 20) {
        clearInterval(intervalId);
        intervalId = null;
        if (attempts >= 20) setGoogleState('unavailable');
      }
    }, 500);

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
      // StrictMode unmounts/remounts: the container (with Google's iframe)
      // is destroyed by React, so allow a fresh renderButton on re-setup.
      googleRenderedRef.current = false;
      try {
        window.google?.accounts?.id?.cancel?.();
      } catch {
        // Non-fatal; the button flow owns no pending request.
      }
    };
  }, [isAuthenticated]);

  const enterOtpStage = (result) => {
    // Dismiss One Tap — the challenge screen owns auth now.
    try {
      window.google?.accounts?.id?.cancel?.();
    } catch {
      // Non-fatal.
    }
    setChallenge({
      token: result.challengeToken,
      emailMasked: result.emailMasked,
    });
    setOtpError('');
    setStage('otp');
  };

  const handleGoogleCredential = async (response) => {
    if (!response?.credential) return;
    setGoogleLoading(true);
    setError('');
    try {
      const result = await googleLogin(response.credential);
      if (result.success) {
        if (result.otpRequired) {
          enterOtpStage(result);
        } else {
          navigate('/');
        }
      } else {
        setError(result.error || 'Google login failed. Please try again.');
      }
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    const result = await login(email, password);

    if (result.success) {
      if (result.otpRequired) {
        enterOtpStage(result);
      } else {
        navigate('/');
      }
    } else {
      setError(result.error || 'Login failed. Please try again.');
    }
    setLoading(false);
  };

  const handleVerifyOtp = async (code) => {
    setOtpLoading(true);
    setOtpError('');
    const result = await verifyLoginOtp(challenge.token, code);
    if (result.success) {
      navigate('/');
    } else {
      // Backend detail carries "N attempt(s) remaining" / lockout state.
      setOtpError(result.error || 'Verification failed. Please try again.');
    }
    setOtpLoading(false);
  };

  const handleResendOtp = async () => {
    return resendLoginOtp(challenge.token);
  };

  // Google One Tap: fire exactly once, only on the credentials stage.
  // Runs after the button script is ready; never during OTP entry and
  // never twice (see oneTapPromptedRef — concurrent prompts crash FedCM).
  useEffect(() => {
    if (
      !GOOGLE_CLIENT_ID ||
      isAuthenticated ||
      stage !== 'credentials' ||
      googleState !== 'ready' ||
      oneTapPromptedRef.current
    ) {
      return undefined;
    }
    if (!window.google?.accounts?.id) return undefined;
    oneTapPromptedRef.current = true;
    try {
      window.google.accounts.id.prompt(() => {
        // Moment notifications ignored — the button + callback own the flow.
      });
    } catch {
      // One Tap unavailable (FedCM blocked, cookies off, ...) — the
      // Continue-with-Google button below still works.
    }
    return () => {
      try {
        window.google?.accounts?.id?.cancel?.();
      } catch {
        // Non-fatal.
      }
    };
  }, [googleState, isAuthenticated, stage]);

  const handleBackToCredentials = () => {
    setStage('credentials');
    setChallenge(null);
    setOtpError('');
    setPassword('');
  };

  // Active session (e.g. reloaded tab, back-button to /login): skip the
  // form entirely instead of flashing it before navigation.
  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="min-h-screen flex bg-background">
      <BrandPanel />

      <div className="flex-1 flex items-center justify-center px-4 py-8 sm:px-8">
        <div className="w-full max-w-md">
          {/* Mobile brand row (brand panel is desktop-only) */}
          <div className="lg:hidden flex items-center gap-2.5 mb-6">
            <div className="w-9 h-9 rounded-xl bg-primary text-primary-foreground flex items-center justify-center">
              <LockKeyhole size={18} />
            </div>
            <div>
              <p className="font-bold text-foreground leading-tight">Admin Panel</p>
              <p className="text-xs text-muted-foreground">Store management console</p>
            </div>
          </div>

          <div className="bg-card rounded-2xl shadow-xl border border-border p-6 sm:p-8">
            {stage === 'otp' && challenge ? (
              <OtpChallenge
                emailMasked={challenge.emailMasked}
                loading={otpLoading}
                serverError={otpError}
                onVerify={handleVerifyOtp}
                onResend={handleResendOtp}
                onBack={handleBackToCredentials}
              />
            ) : (
              <>
                <div className="mb-6">
                  <h1 className="text-2xl font-bold text-foreground">Welcome back</h1>
                  <p className="text-muted-foreground mt-1 text-sm">
                    Sign in to manage your store
                  </p>
                </div>

                {error && (
                  <div
                    role="alert"
                    aria-live="assertive"
                    className="bg-destructive/10 text-destructive p-3 rounded-lg mb-4 text-sm"
                  >
                    {error}
                  </div>
                )}

                {GOOGLE_CLIENT_ID && (
                  <>
                    <div className="mb-5">
                      {googleState === 'unavailable' && !googleLoading ? (
                        <p className="text-center text-xs text-muted-foreground border border-dashed border-input rounded-lg py-2.5 px-3">
                          Google sign-in unavailable (check connection or ad-blocker)
                          — continue with email below.
                        </p>
                      ) : (
                        <>
                          {(googleLoading || googleState === 'pending') && (
                            <div className="flex items-center justify-center py-2.5 w-full border border-input rounded-lg gap-2 text-muted-foreground text-sm mb-2">
                              <Loader className="animate-spin" size={18} />
                              {googleLoading ? 'Signing in with Google...' : 'Loading Google sign-in...'}
                            </div>
                          )}
                          {/* Google owns this subtree — React must never
                              render children inside it (see effect above). */}
                          <div ref={googleButtonRef} className="flex justify-center min-h-[40px]" />
                        </>
                      )}
                    </div>

                    <div className="flex items-center gap-3 my-5">
                      <div className="flex-1 h-px bg-border"></div>
                      <span className="text-xs text-muted-foreground uppercase tracking-wider">or</span>
                      <div className="flex-1 h-px bg-border"></div>
                    </div>
                  </>
                )}

                <form onSubmit={handleSubmit}>
                  <div className="mb-4">
                    <label htmlFor="login-email" className="block text-sm font-medium text-muted-foreground mb-1">
                      Email Address
                    </label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
                      <input
                        id="login-email"
                        type="email"
                        autoComplete="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border border-input rounded-lg bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="admin@example.com"
                        required
                      />
                    </div>
                  </div>

                  <div className="mb-2">
                    <label htmlFor="login-password" className="block text-sm font-medium text-muted-foreground mb-1">
                      Password
                    </label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
                      <input
                        id="login-password"
                        type={showPassword ? 'text' : 'password'}
                        autoComplete="current-password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        onKeyUp={(e) => setCapsLockOn(!!e.getModifierState?.('CapsLock'))}
                        className="w-full pl-10 pr-11 py-2 border border-input rounded-lg bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="••••••••"
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword((s) => !s)}
                        aria-label={showPassword ? 'Hide password' : 'Show password'}
                        className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
                  </div>

                  <div className="min-h-[1.5rem] mb-3" aria-live="polite">
                    {capsLockOn && (
                      <p className="text-xs text-warning flex items-center gap-1">
                        <TriangleAlert size={13} />
                        Caps Lock is on
                      </p>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full bg-primary text-primary-foreground py-2 rounded-lg font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
                  >
                    {loading ? (
                      <>
                        <Loader className="animate-spin mr-2" size={20} />
                        Signing in...
                      </>
                    ) : (
                      'Sign In'
                    )}
                  </button>
                </form>

                <p className="mt-5 text-center text-xs text-muted-foreground flex items-center justify-center gap-1.5">
                  <LockKeyhole size={13} />
                  Protected with two-step verification
                </p>
              </>
            )}
          </div>

          {STOREFRONT_URL && (
            <p className="mt-4 text-center text-xs text-muted-foreground">
              <a href={STOREFRONT_URL} className="hover:text-foreground">
                ← Back to store
              </a>
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Login;

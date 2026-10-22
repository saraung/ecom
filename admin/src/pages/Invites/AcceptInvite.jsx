// src/pages/Invites/AcceptInvite.jsx
/**
 * Public landing page for the emailed staff-invite link
 * (`{ADMIN_FRONTEND_URL}/accept-invite?token=...`).
 *
 * Two paths, mirroring POST /invites/accept:
 *  - New staffer  → username + password create a verified account holding the
 *    invited roles, and the returned tokens sign them straight in.
 *  - Existing account → when the invite email matches the signed-in user we
 *    only need to link the invited roles (no password).
 *
 * Lives OUTSIDE AdminLayout: the whole point is that the visitor has no
 * session yet, so it must render without the auth gate.
 */
import React, { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Loader,
  LockKeyhole,
  MailCheck,
  User as UserIcon,
  KeyRound,
  ShieldAlert,
  TriangleAlert,
} from 'lucide-react';
import toast from 'react-hot-toast';
import BrandPanel from '../../components/auth/BrandPanel';
import { acceptInvite, previewInvite } from '../../api/invites';
import { useAuth } from '../../context/AuthContext';

// Mirrors InviteAcceptRequest.password_strength on the backend.
const MIN_PASSWORD_LENGTH = 8;
const USERNAME_PATTERN = /^[A-Za-z0-9_]+$/;

const fieldClass =
  'w-full pl-10 pr-4 py-2 border border-input rounded-lg bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent';
const labelClass = 'block text-sm font-medium text-muted-foreground mb-1';
const iconClass =
  'absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground';

const AcceptInvite = () => {
  const [searchParams] = useSearchParams();
  const { user, isAuthenticated } = useAuth();
  const token = searchParams.get('token') || '';

  // `null` = still checking the link; `{ valid: false }` = dead link.
  // A URL with no token never needs a round-trip, so it resolves during
  // initial render instead of inside the effect.
  const [preview, setPreview] = useState(() => (
    token
      ? null
      : { valid: false, message: 'This link is missing its invitation token.' }
  ));
  const [checking, setChecking] = useState(!!token);
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  // Set once the invite is consumed — the link is single-use, so the form
  // stops rendering the moment it succeeds.
  const [accepted, setAccepted] = useState(null);

  useEffect(() => {
    let cancelled = false;

    if (!token) return undefined;

    previewInvite(token)
      .then((res) => {
        if (!cancelled) setPreview(res.data);
      })
      .catch(() => {
        if (!cancelled) {
          setPreview({
            valid: false,
            message: 'Could not verify this invitation link. Please try again later.',
          });
        }
      })
      .finally(() => {
        if (!cancelled) setChecking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [token]);

  // Signed in as the invited person → only the roles need linking.
  const canLinkExisting =
    isAuthenticated && !!preview?.valid && !!user?.email &&
    user.email === preview.email;

  const handleCreateAccount = async (e) => {
    e.preventDefault();
    const name = username.trim();
    const trimmedName = fullName.trim();

    if (!name) { setError('Choose a username to sign in with.'); return; }
    if (!USERNAME_PATTERN.test(name)) {
      setError('Username can contain only letters, numbers and underscores.');
      return;
    }
    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirmPassword) {
      setError('The two passwords do not match.');
      return;
    }

    setError('');
    setSubmitting(true);
    try {
      const res = await acceptInvite({
        token,
        username: name,
        password,
        full_name: trimmedName || null,
      });
      localStorage.setItem('access_token', res.data.access_token);
      localStorage.setItem('refresh_token', res.data.refresh_token);
      // Drop any stale cached profile so /auth/me rebuilds it with the new
      // permission set; the reload also re-initialises AuthContext.
      localStorage.removeItem('user');
      toast.success('Invitation accepted — signing you in');
      window.location.replace('/');
    } catch (err) {
      setError(
        err.response?.data?.detail ||
          'Could not accept the invitation. It may have expired.'
      );
      setSubmitting(false);
    }
  };

  const handleLinkRoles = async () => {
    setError('');
    setSubmitting(true);
    try {
      const res = await acceptInvite({ token });
      setAccepted({
        linked: true,
        email: res.data?.email || preview.email,
        roles: res.data?.roles || preview.role_slugs,
      });
      toast.success('Roles linked to your account');
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not accept the invitation.');
    } finally {
      setSubmitting(false);
    }
  };

  /** New-staffer form: creates the account, then signs them in. */
  const renderAccountForm = () => (
    <form onSubmit={handleCreateAccount}>
      <p className="text-sm text-muted-foreground mb-4">
        An account already uses this email?{' '}
        <Link to="/login" className="text-primary hover:underline">
          Sign in
        </Link>{' '}
        first, then open this link again to link the roles.
      </p>

      <div className="mb-4">
        <label htmlFor="invite-username" className={labelClass}>Username</label>
        <div className="relative">
          <UserIcon className={iconClass} size={18} />
          <input
            id="invite-username"
            type="text"
            autoComplete="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            className={fieldClass}
            placeholder="priya_staff"
            required
          />
        </div>
      </div>

      <div className="mb-4">
        <label htmlFor="invite-full-name" className={labelClass}>
          Full name <span className="text-xs">(optional)</span>
        </label>
        <div className="relative">
          <UserIcon className={iconClass} size={18} />
          <input
            id="invite-full-name"
            type="text"
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className={fieldClass}
            placeholder="Priya Sharma"
          />
        </div>
      </div>

      <div className="mb-4">
        <label htmlFor="invite-password" className={labelClass}>Password</label>
        <div className="relative">
          <LockKeyhole className={iconClass} size={18} />
          <input
            id="invite-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={fieldClass}
            placeholder={`At least ${MIN_PASSWORD_LENGTH} characters`}
            required
          />
        </div>
      </div>

      <div className="mb-5">
        <label htmlFor="invite-password-confirm" className={labelClass}>
          Confirm password
        </label>
        <div className="relative">
          <KeyRound className={iconClass} size={18} />
          <input
            id="invite-password-confirm"
            type="password"
            autoComplete="new-password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            className={fieldClass}
            placeholder="Repeat your password"
            required
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="w-full bg-primary text-primary-foreground rounded-lg py-2.5 font-medium hover:opacity-90 transition disabled:opacity-60 flex items-center justify-center gap-2"
      >
        {submitting ? <Loader className="animate-spin" size={16} /> : null}
        Create account &amp; join
      </button>
    </form>
  );

  const renderBody = () => {
    if (checking) {
      return (
        <div className="flex items-center gap-2 text-muted-foreground py-6 justify-center">
          <Loader className="animate-spin" size={18} />
          Checking your invitation…
        </div>
      );
    }

    if (!preview?.valid) {
      return (
        <div>
          <div className="flex items-center gap-2 mb-3 text-destructive">
            <TriangleAlert size={20} />
            <h1 className="text-xl font-bold text-foreground">
              Invitation not usable
            </h1>
          </div>
          <p className="text-sm text-muted-foreground">
            {preview?.message || 'This invitation link is invalid or expired.'}
          </p>
          <p className="text-sm text-muted-foreground mt-3">
            Ask an admin to resend it from <strong>Invites</strong>, or{' '}
            <Link to="/login" className="text-primary hover:underline">
              sign in
            </Link>{' '}
            if you already have an account.
          </p>
        </div>
      );
    }

    if (accepted) {
      return (
        <div>
          <div className="flex items-center gap-2 mb-3 text-primary">
            <MailCheck size={20} />
            <h1 className="text-xl font-bold text-foreground">
              Invitation accepted
            </h1>
          </div>
          <p className="text-sm text-muted-foreground">
            {accepted.email} now holds:{' '}
            <strong className="text-foreground">
              {accepted.roles.join(', ')}
            </strong>
          </p>
          <Link
            to="/"
            className="mt-5 inline-flex w-full justify-center bg-primary text-primary-foreground rounded-lg py-2.5 font-medium hover:opacity-90 transition"
          >
            Go to the dashboard
          </Link>
        </div>
      );
    }

    return (
      <div>
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-foreground">You&apos;re invited</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Join the store admin as{' '}
            <strong className="text-foreground">
              {preview.role_slugs.join(', ')}
            </strong>
          </p>
        </div>

        <div className="bg-muted rounded-lg p-3 mb-5 flex items-center gap-2 text-sm">
          <MailCheck size={16} className="text-primary shrink-0" />
          <span className="truncate text-muted-foreground">
            Invited email:{' '}
            <strong className="text-foreground">{preview.email}</strong>
          </span>
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

        {canLinkExisting ? (
          <>
            <p className="text-sm text-muted-foreground mb-4">
              You&apos;re signed in as this address — one click links the invited
              roles to your existing account.
            </p>
            <button
              type="button"
              onClick={handleLinkRoles}
              disabled={submitting}
              className="w-full bg-primary text-primary-foreground rounded-lg py-2.5 font-medium hover:opacity-90 transition disabled:opacity-60 flex items-center justify-center gap-2"
            >
              {submitting ? <Loader className="animate-spin" size={16} /> : null}
              Accept &amp; link roles
            </button>
          </>
        ) : (
          renderAccountForm()
        )}

        <p className="mt-5 flex items-start gap-2 text-xs text-muted-foreground">
          <ShieldAlert size={14} className="mt-0.5 shrink-0" />
          Signing in from this account still requires the emailed two-step code.
        </p>
      </div>
    );
  };

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
            {renderBody()}
          </div>

          <p className="text-center text-xs text-muted-foreground mt-6">
            <Link to="/login" className="hover:underline">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
};

export default AcceptInvite;


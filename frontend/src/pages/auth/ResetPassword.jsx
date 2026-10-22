// src/pages/auth/ResetPassword.jsx
import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import { RefreshCw, CheckCircle, AlertCircle, KeyRound, ArrowLeft } from 'lucide-react';
import { authAPI } from '../../api/auth';
import toast from 'react-hot-toast';

const ResetPassword = () => {
  const navigate = useNavigate();
  const location = useLocation();

  const queryParams = new URLSearchParams(location.search);
  const token = queryParams.get('token');

  const [loading, setLoading] = useState(false);
  const [resetSuccess, setResetSuccess] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [formData, setFormData] = useState({
    new_password: '',
    confirm_password: '',
  });

  useEffect(() => {
    if (!token) {
      setErrorMessage('No reset token found. Please request a new password reset link.');
    }
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setErrorMessage('');

    if (formData.new_password !== formData.confirm_password) {
      toast.error('Passwords do not match');
      return;
    }

    if (formData.new_password.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }

    if (!token) {
      toast.error('Invalid or missing reset token. Please request a new password reset link.');
      return;
    }

    try {
      setLoading(true);

      await authAPI.resetPassword({
        token: token,
        new_password: formData.new_password,
      });

      setResetSuccess(true);

      toast.success('✅ Password reset successfully! You can now login with your new password.', {
        duration: 5000,
      });

      setTimeout(() => {
        navigate('/login', {
          state: {
            message: 'Password reset successfully! Please login with your new password.',
          },
        });
      }, 3000);
    } catch (error) {
      let errorMsg = 'Failed to reset password. Please try again.';

      if (error.response?.status === 400) {
        const detail = error.response?.data?.detail || '';
        if (detail.includes('expired') || detail.includes('invalid')) {
          errorMsg = '🔒 This reset link has expired or has already been used. Please request a new password reset link.';
        } else {
          errorMsg = detail;
        }
      } else if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          errorMsg = error.response.data.detail.map((err) => err.msg || err.message).join(', ');
        } else {
          errorMsg = error.response.data.detail;
        }
      }

      setErrorMessage(errorMsg);
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  // Success state
  if (resetSuccess) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
        <div className="w-full max-w-md text-center">
          <div className="bg-card border border-border rounded-[2rem] shadow-sm p-8 sm:p-10">
            <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-success-soft text-success flex items-center justify-center">
              <CheckCircle size={28} />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
              Password Reset Successful! 🎉
            </h2>
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
              Your password has been reset. You will be redirected to the login page shortly.
            </p>
            <button
              onClick={() => navigate('/login', {
                state: { message: 'Password reset successfully! Please login with your new password.' },
              })}
              className="mt-8 w-full inline-flex items-center justify-center gap-2 py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover transition-all duration-300"
            >
              <ArrowLeft size={16} /> Go to Login
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-md">
        {/* Mobile-only brand + back to store */}
        <div className="lg:hidden flex items-center justify-between gap-4 mb-8">
          <Link to="/" className="flex items-center gap-2 flex-shrink-0">
            <span className="w-9 h-9 rounded-xl bg-primary text-primary-foreground flex items-center justify-center font-black text-lg">E</span>
            <span className="text-2xl font-extrabold tracking-tighter text-foreground">E-Shop.</span>
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-primary border border-border rounded-full px-3 py-2 hover:bg-primary-soft transition-colors"
          >
            <ArrowLeft size={14} /> Store
          </Link>
        </div>

        <div className="bg-card border border-border rounded-[2rem] shadow-sm p-8 sm:p-10">
          <div className="text-center">
            <div className="w-14 h-14 mx-auto mb-5 rounded-2xl bg-primary-soft flex items-center justify-center">
              <KeyRound size={22} className="text-foreground" />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
              Reset Password
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Enter your new password below
            </p>
          </div>

          {/* Error Message - Prominently Displayed */}
          {errorMessage && (
            <div className="mt-6 p-4 alert-danger rounded-xl flex items-start gap-3">
              <AlertCircle size={20} className="text-destructive flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium">Unable to reset password</p>
                <p className="text-sm">{errorMessage}</p>
                {errorMessage.includes('expired') || errorMessage.includes('already been used') ? (
                  <Link
                    to="/forgot-password"
                    className="mt-2 inline-block text-sm font-medium text-destructive hover:opacity-80 underline"
                  >
                    Request new reset link →
                  </Link>
                ) : null}
              </div>
            </div>
          )}

          {/* Token missing error */}
          {!token && !errorMessage && (
            <div className="mt-6 p-4 alert-warning rounded-xl flex items-start gap-3">
              <AlertCircle size={20} className="text-warning flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-medium">No reset token found</p>
                <p className="text-sm">
                  Please use the link from your email or request a new one.
                </p>
                <Link
                  to="/forgot-password"
                  className="mt-2 inline-block text-sm font-medium underline"
                >
                  Request new reset link →
                </Link>
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5">
                New Password
              </label>
              <input
                type="password"
                value={formData.new_password}
                onChange={(e) => setFormData({ ...formData, new_password: e.target.value })}
                className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                placeholder="Enter new password"
                required
                minLength={8}
                disabled={!token || loading}
              />
              <p className="text-[11px] text-muted-foreground mt-1.5">Must be at least 8 characters.</p>
            </div>

            <div>
              <label className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5">
                Confirm Password
              </label>
              <input
                type="password"
                value={formData.confirm_password}
                onChange={(e) => setFormData({ ...formData, confirm_password: e.target.value })}
                className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                placeholder="Confirm new password"
                required
                disabled={!token || loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading || !token}
              className="w-full flex items-center justify-center gap-2 py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300"
            >
              {loading ? (
                <>
                  <RefreshCw size={18} className="animate-spin" />
                  Resetting...
                </>
              ) : (
                'Reset Password'
              )}
            </button>
          </form>

          <button
            onClick={() => navigate('/login')}
            className="mt-6 w-full text-center text-sm font-semibold text-primary hover:text-primary-hover transition-colors"
          >
            Back to Login
          </button>
        </div>
      </div>
    </div>
  );
};

export default ResetPassword;
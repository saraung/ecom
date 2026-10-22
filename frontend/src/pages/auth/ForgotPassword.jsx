// src/pages/auth/ForgotPassword.jsx
import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Lock, ArrowLeft, MailCheck } from 'lucide-react';
import { authAPI } from '../../api/auth';
import toast from 'react-hot-toast';

const ForgotPassword = () => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await authAPI.forgotPassword(email);
      setSuccess(true);
      toast.success('Password reset link sent to your email!', {
        duration: 5000,
      });
    } catch {
      setError('Failed to send reset link. Please try again.');
      toast.error('Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-card border border-border rounded-[2rem] shadow-sm p-8 sm:p-10 text-center">
            <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-success-soft text-success flex items-center justify-center">
              <MailCheck size={28} />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
              Check Your Email
            </h2>
            <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
              We've sent a password reset link to{' '}
              <strong className="text-foreground">{email}</strong>.
            </p>
            <div className="mt-5 space-y-1 text-xs text-muted-foreground">
              <p>If you don't see the email, check your spam folder.</p>
              <p>The link will expire in <span className="font-bold text-foreground">1 hour</span>.</p>
            </div>
            <Link
              to="/login"
              className="mt-8 w-full inline-flex items-center justify-center gap-2 py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover transition-all duration-300"
            >
              <ArrowLeft size={16} /> Back to Login
            </Link>
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
              <Lock size={22} className="text-foreground" />
            </div>
            <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
              Forgot Password?
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Enter your email and we'll send you a link to reset your password.
            </p>
          </div>

          {error && (
            <div className="mt-6 alert-danger px-4 py-3 rounded-lg relative">
              <span className="block sm:inline">❌ {error}</span>
            </div>
          )}

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <div>
              <label htmlFor="email" className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5">
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                placeholder="you@example.com"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center gap-2 py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300"
            >
              {loading ? (
                <>
                  <svg className="animate-spin -ml-1 mr-2 h-5 w-5 text-primary-foreground" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Sending...
                </>
              ) : (
                'Send Reset Link'
              )}
            </button>
          </form>

          <Link
            to="/login"
            className="mt-6 block text-center text-sm font-semibold text-primary hover:text-primary-hover transition-colors"
          >
            Back to Login
          </Link>
        </div>
      </div>
    </div>
  );
};

export default ForgotPassword;
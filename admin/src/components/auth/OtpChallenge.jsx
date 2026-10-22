// src/components/auth/OtpChallenge.jsx
import React, { useState, useRef, useEffect } from 'react';
import { ShieldCheck, Loader, ArrowLeft, RefreshCw } from 'lucide-react';

const CODE_LENGTH = 6;
const RESEND_COOLDOWN = 60; // seconds — mirrors backend resend cooldown

/**
 * Second step of admin sign-in: 6-digit email code entry.
 *
 * Props:
 * - emailMasked: "a***@example.com" reassurance line
 * - loading: verify in flight
 * - serverError: error text from the last verify attempt (may carry
 *   "N attempt(s) remaining" / lockout messaging from the backend)
 * - onVerify(code): exchange code for session tokens
 * - onResend(): request a fresh code; returns {success, error}
 * - onBack(): return to the credentials screen
 */
const OtpChallenge = ({ emailMasked, loading, serverError, onVerify, onResend, onBack }) => {
  const [digits, setDigits] = useState(Array(CODE_LENGTH).fill(''));
  const [resendIn, setResendIn] = useState(RESEND_COOLDOWN);
  const [resendError, setResendError] = useState('');
  const [resendOk, setResendOk] = useState('');
  const inputsRef = useRef([]);

  useEffect(() => {
    inputsRef.current[0]?.focus();
  }, []);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = setTimeout(() => setResendIn((s) => s - 1), 1000);
    return () => clearTimeout(timer);
  }, [resendIn]);

  const setDigit = (index, value) => {
    const char = (value || '').replace(/\D/g, '').slice(-1);
    setDigits((prev) => {
      const next = [...prev];
      next[index] = char;
      return next;
    });
    if (char && index < CODE_LENGTH - 1) {
      inputsRef.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !digits[index] && index > 0) {
      inputsRef.current[index - 1]?.focus();
    }
    if (e.key === 'Enter') {
      handleSubmit(e);
    }
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const text = (e.clipboardData?.getData('text') || '').replace(/\D/g, '').slice(0, CODE_LENGTH);
    if (!text) return;
    setDigits((prev) => {
      const next = [...prev];
      for (let i = 0; i < text.length; i++) next[i] = text[i];
      return next;
    });
    inputsRef.current[Math.min(text.length, CODE_LENGTH - 1)]?.focus();
  };

  const code = digits.join('');
  const complete = code.length === CODE_LENGTH;

  const handleSubmit = (e) => {
    e?.preventDefault?.();
    if (!complete || loading) return;
    onVerify(code);
  };

  const handleResend = async () => {
    if (resendIn > 0 || loading) return;
    setResendError('');
    setResendOk('');
    const result = await onResend();
    if (result?.success) {
      setResendOk('A new code was sent to your email.');
      setResendIn(RESEND_COOLDOWN);
      setDigits(Array(CODE_LENGTH).fill(''));
      inputsRef.current[0]?.focus();
    } else {
      setResendError(result?.error || 'Could not resend the code.');
    }
  };

  return (
    <div>
      <div className="text-center mb-6">
        <div className="mx-auto w-12 h-12 rounded-2xl bg-primary-soft text-primary flex items-center justify-center mb-4">
          <ShieldCheck size={24} />
        </div>
        <h1 className="text-2xl font-bold text-foreground">Check your email</h1>
        <p className="text-muted-foreground mt-2 text-sm">
          We sent a 6-digit verification code to
          <br />
          <span className="font-semibold text-foreground">{emailMasked}</span>
        </p>
      </div>

      {(serverError || resendError) && (
        <div
          role="alert"
          aria-live="assertive"
          className="bg-destructive/10 text-destructive p-3 rounded-lg mb-4 text-sm"
        >
          {serverError || resendError}
        </div>
      )}
      {resendOk && (
        <div role="status" className="bg-success/15 text-success p-3 rounded-lg mb-4 text-sm">
          {resendOk}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="flex items-center justify-center gap-2 sm:gap-2.5 mb-6" onPaste={handlePaste}>
          {digits.map((digit, index) => (
            <input
              key={index}
              ref={(el) => { inputsRef.current[index] = el; }}
              type="text"
              inputMode="numeric"
              autoComplete={index === 0 ? 'one-time-code' : 'off'}
              maxLength={1}
              value={digit}
              onChange={(e) => setDigit(index, e.target.value)}
              onKeyDown={(e) => handleKeyDown(index, e)}
              aria-label={`Digit ${index + 1} of ${CODE_LENGTH}`}
              className="w-11 h-12 sm:w-12 sm:h-13 text-center text-xl font-bold border border-input rounded-lg bg-card text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-transparent transition-shadow"
            />
          ))}
        </div>

        <button
          type="submit"
          disabled={!complete || loading}
          className="w-full bg-primary text-primary-foreground py-2 rounded-lg font-medium hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
        >
          {loading ? (
            <>
              <Loader className="animate-spin mr-2" size={20} />
              Verifying...
            </>
          ) : (
            'Verify & Sign In'
          )}
        </button>
      </form>

      <div className="mt-5 text-center text-sm">
        {resendIn > 0 ? (
          <p className="text-muted-foreground">
            Didn&apos;t get the code? Resend in{' '}
            <span className="font-semibold text-foreground tabular-nums">{resendIn}s</span>
          </p>
        ) : (
          <button
            type="button"
            onClick={handleResend}
            disabled={loading}
            className="text-primary hover:text-primary-hover font-medium inline-flex items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw size={14} />
            Resend code
          </button>
        )}
      </div>

      <div className="mt-4 text-center">
        <button
          type="button"
          onClick={onBack}
          className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5"
        >
          <ArrowLeft size={14} />
          Use a different account
        </button>
      </div>
    </div>
  );
};

export default OtpChallenge;

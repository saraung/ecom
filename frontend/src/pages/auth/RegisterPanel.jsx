// src/pages/auth/RegisterPanel.jsx
import React, { useState } from 'react';
import { Mail, KeyRound, CheckCircle } from 'lucide-react';
import { authAPI } from '../../api/auth';

const RegisterPanel = ({ onSwitchToLogin }) => {
  const [step, setStep] = useState('email'); // 'email' | 'otp' | 'success'
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    full_name: '',
    phone: '',
  });
  const [otp, setOtp] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [timer, setTimer] = useState(0);

  const handleChange = (e) => {
    const { name, value } = e.target;
    // Phone accepts only digits, +, spaces, and dashes
    const nextValue = name === 'phone' ? value.replace(/[^\d+\s-]/g, '') : value;
    setFormData((prev) => ({ ...prev, [name]: nextValue }));
    setFieldErrors((prev) => (prev[name] ? { ...prev, [name]: '' } : prev));
  };

  const validateForm = () => {
    const errors = {};
    const emailRe = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!formData.email || !emailRe.test(formData.email)) {
      errors.email = 'Please enter a valid email address';
    }

    if (!formData.username) {
      errors.username = 'Username is required';
    } else if (!/^[a-zA-Z0-9_]{3,20}$/.test(formData.username)) {
      errors.username = 'Username must be 3-20 characters (letters, numbers, and underscores only)';
    }

    if (formData.full_name && !/^[A-Za-z\s'-]{2,}$/.test(formData.full_name.trim())) {
      errors.full_name = 'Full name must contain only letters (at least 2 characters)';
    }

    if (formData.phone && !/^\+?[\d\s-]{7,15}$/.test(formData.phone.trim())) {
      errors.phone = 'Please enter a valid phone number (digits only)';
    }

    if (!formData.password) {
      errors.password = 'Password is required';
    } else if (formData.password.length < 8) {
      errors.password = 'Password must be at least 8 characters';
    } else if (!/[A-Za-z]/.test(formData.password)) {
      errors.password = 'Password must contain at least one letter';
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const startCountdown = () => {
    const interval = setInterval(() => {
      setTimer((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  };

  // Step 1: Send OTP
  const sendOTP = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    if (!validateForm()) {
      setLoading(false);
      return;
    }

    try {
      await authAPI.initiateRegistration(formData);
      setStep('otp');
      setTimer(60);
      startCountdown();
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail === 'Username already taken') {
        setFieldErrors((prev) => ({ ...prev, username: detail }));
      } else if (detail === 'Email already registered') {
        setFieldErrors((prev) => ({ ...prev, email: 'This email is already registered' }));
      } else {
        setError(detail || 'Failed to send OTP. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Verify OTP and create account
  const verifyOTP = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    // Validate OTP
    if (otp.length !== 6) {
      setError('Please enter a valid 6-digit OTP');
      setLoading(false);
      return;
    }

    try {
      await authAPI.verifyRegistration({
        email: formData.email,
        otp_code: otp,
        username: formData.username,
        password: formData.password,
        full_name: formData.full_name,
        phone: formData.phone,
      });

      setStep('success');
      setTimeout(() => {
        onSwitchToLogin?.(formData.email);
      }, 2000);
    } catch (err) {
      const detail = err.response?.data?.detail;
      if (detail === 'Username already taken') {
        setStep('email');
        setFieldErrors({ username: detail });
        return;
      }
      if (detail === 'Email already registered') {
        setStep('email');
        setFieldErrors({ email: 'This email is already registered' });
        return;
      }
      let errMsg = 'Invalid OTP. Please try again.';
      if (typeof detail === 'string') errMsg = detail;
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  // Resend OTP
  const resendOTP = async () => {
    if (timer > 0) return;

    setLoading(true);
    setError('');

    try {
      await authAPI.resendOTP(formData.email);
      setTimer(60);
      startCountdown();
    } catch (err) {
      let errMsg = 'Failed to resend OTP. Please try again.';
      const detail = err.response?.data?.detail;
      if (typeof detail === 'string') errMsg = detail;
      setError(errMsg);
    } finally {
      setLoading(false);
    }
  };

  const FIELDS = [
    { id: 'username', label: 'Username', type: 'text', placeholder: 'janedoe', required: true },
    { id: 'full_name', label: 'Full Name', type: 'text', placeholder: 'Jane Doe (optional)', required: false },
    { id: 'phone', label: 'Phone', type: 'tel', placeholder: '+1 555 000 0000 (optional)', required: false },
  ];

  const inputBase =
    'w-full px-4 py-3 rounded-xl bg-card placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:border-primary transition-all sm:text-sm';
  const inputValid = `${inputBase} border border-border focus:ring-primary/40`;
  const inputInvalid = `${inputBase} border border-destructive focus:ring-destructive/40`;

  const labelCls = 'block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5';

  const btnPrimaryCls =
    'w-full flex items-center justify-center gap-2 py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300';
  const btnGhostCls =
    'w-full text-center text-sm font-semibold text-primary hover:text-primary-hover transition-colors';

  // Step 1: Email Form
  if (step === 'email') {
    return (
      <div className="bg-card border border-border rounded-[2rem] shadow-sm p-8 sm:p-10">
        <div className="text-center">
          <div className="w-14 h-14 mx-auto mb-5 rounded-2xl bg-primary-soft flex items-center justify-center">
            <Mail size={22} className="text-foreground" />
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
            Create your account
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign up with email verification.
          </p>
        </div>

        {error && (
          <div className="mt-6 alert-danger px-4 py-3 rounded-lg relative">
            <span className="block sm:inline">❌ {error}</span>
          </div>
        )}

        <form className="mt-8 space-y-5" onSubmit={sendOTP}>
          <div>
            <label htmlFor="reg-email" className={labelCls}>
              Email address
            </label>
            <input
              id="reg-email"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={formData.email}
              onChange={handleChange}
              className={fieldErrors.email ? inputInvalid : inputValid}
              placeholder="you@example.com"
            />
            {fieldErrors.email && (
              <p className="text-xs text-destructive mt-1.5">{fieldErrors.email}</p>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            {FIELDS.slice(0, 2).map(({ id, label, type, placeholder, required }) => (
              <div key={id}>
                <label htmlFor={`reg-${id}`} className={labelCls}>
                  {label}
                </label>
                <input
                  id={`reg-${id}`}
                  name={id}
                  type={type}
                  required={required}
                  value={formData[id]}
                  onChange={handleChange}
                  className={fieldErrors[id] ? inputInvalid : inputValid}
                  placeholder={placeholder}
                />
                {fieldErrors[id] && (
                  <p className="text-xs text-destructive mt-1.5">{fieldErrors[id]}</p>
                )}
              </div>
            ))}
          </div>

          {FIELDS.slice(2).map(({ id, label, type, placeholder, required }) => (
            <div key={id}>
              <label htmlFor={`reg-${id}`} className={labelCls}>
                {label}
              </label>
              <input
                id={`reg-${id}`}
                name={id}
                type={type}
                required={required}
                value={formData[id]}
                onChange={handleChange}
                className={fieldErrors[id] ? inputInvalid : inputValid}
                placeholder={placeholder}
              />
              {fieldErrors[id] && (
                <p className="text-xs text-destructive mt-1.5">{fieldErrors[id]}</p>
              )}
            </div>
          ))}

          <div>
            <label htmlFor="reg-password" className={labelCls}>
              Password
            </label>
            <input
              id="reg-password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={formData.password}
              onChange={handleChange}
              className={fieldErrors.password ? inputInvalid : inputValid}
              placeholder="••••••••"
            />
            <p className="text-[11px] text-muted-foreground mt-1.5">At least 8 characters.</p>
            {fieldErrors.password && (
              <p className="text-xs text-destructive mt-1.5">{fieldErrors.password}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading || !formData.email || !formData.username || !formData.password}
            className={btnPrimaryCls}
          >
            {loading ? 'Sending OTP...' : 'Send OTP'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-muted-foreground">
          Your email will only be used for account verification.
        </p>
      </div>
    );
  }

  // Step 2: OTP Verification
  if (step === 'otp') {
    return (
      <div className="bg-card border border-border rounded-[2rem] shadow-sm p-8 sm:p-10">
        <div className="text-center">
          <div className="w-14 h-14 mx-auto mb-5 rounded-2xl bg-primary-soft flex items-center justify-center">
            <KeyRound size={22} className="text-foreground" />
          </div>
          <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
            Verify Your Email
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            We sent a 6-digit code to{' '}
            <span className="font-bold text-foreground">{formData.email}</span>
          </p>
        </div>

        {error && (
          <div className="mt-6 alert-danger px-4 py-3 rounded-lg relative">
            <span className="block sm:inline">❌ {error}</span>
          </div>
        )}

        <form className="mt-8 space-y-6" onSubmit={verifyOTP}>
          <div>
            <label htmlFor="otp" className={labelCls}>
              Verification Code
            </label>
            <input
              id="otp"
              name="otp"
              type="text"
              inputMode="numeric"
              required
              maxLength={6}
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
              className="w-full px-4 py-4 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground text-center text-3xl tracking-[0.5em] focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
              placeholder="000000"
            />
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-muted-foreground">
              {timer > 0 ? `Resend in ${timer}s` : "Didn't receive the code?"}
            </span>
            <button
              type="button"
              onClick={resendOTP}
              disabled={timer > 0 || loading}
              className="text-sm font-bold text-primary hover:text-primary-hover disabled:text-muted-foreground disabled:cursor-not-allowed transition-colors"
            >
              Resend OTP
            </button>
          </div>

          <button
            type="submit"
            disabled={loading || otp.length !== 6}
            className={btnPrimaryCls}
          >
            {loading ? 'Verifying...' : 'Verify & Create Account'}
          </button>

          <button
            type="button"
            onClick={() => setStep('email')}
            className={btnGhostCls}
          >
            ← Back to email
          </button>
        </form>
      </div>
    );
  }

  // Step 3: Success
  return (
    <div className="bg-card border border-border rounded-[2rem] shadow-sm p-8 sm:p-10 text-center">
      <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-success-soft text-success flex items-center justify-center">
        <CheckCircle size={28} />
      </div>
      <h2 className="text-2xl font-extrabold tracking-tight text-foreground">
        Account Created!
      </h2>
      <p className="mt-2 text-sm text-muted-foreground">
        Redirecting you to login...
      </p>
    </div>
  );
};

export default RegisterPanel;
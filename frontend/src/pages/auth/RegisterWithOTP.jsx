// src/pages/auth/RegisterWithOTP.jsx
import React from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import RegisterPanel from './RegisterPanel';

const RegisterWithOTP = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-4 py-12 sm:px-8">
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

        <RegisterPanel
          onSwitchToLogin={() =>
            navigate('/login', {
              state: { message: 'Account created successfully! Please login.' },
            })
          }
        />

        <p className="mt-6 text-center text-sm text-muted-foreground">
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-primary hover:text-primary-hover transition-colors">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
};

export default RegisterWithOTP;
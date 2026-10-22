// src/pages/auth/Register.jsx
import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Sparkles, Truck, ShieldCheck, ArrowLeft } from 'lucide-react';
import { authAPI } from '../../api/auth';

const HIGHLIGHTS = [
  { icon: Sparkles, label: 'Curated picks' },
  { icon: Truck, label: 'Fast delivery' },
  { icon: ShieldCheck, label: 'Secure checkout' },
];

const Register = () => {
  const [formData, setFormData] = useState({
    email: '',
    username: '',
    password: '',
    full_name: '',
    phone: '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const navigate = useNavigate();

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

    try {
      await authAPI.register(formData);
      navigate('/login', { state: { message: 'Registration successful! Please login.' } });
    } catch (err) {
      setError(err.response?.data?.detail || 'Registration failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const FIELDS = [
    { id: 'full_name', label: 'Full Name', type: 'text', placeholder: 'Jane Doe', required: true },
    { id: 'username', label: 'Username', type: 'text', placeholder: 'janedoe', required: true },
    { id: 'email', label: 'Email address', type: 'email', placeholder: 'you@example.com', required: true },
    { id: 'phone', label: 'Phone', type: 'tel', placeholder: '+1 555 000 0000 (optional)', required: false },
  ];

  return (
    <div className="min-h-screen flex bg-background">
      
      {/* ── LEFT: Brand / Design Showcase ─────────────────────────────── */}
      <div className="hidden lg:flex flex-col justify-between w-[46%] xl:w-1/2 relative overflow-hidden bg-primary-soft border-r border-border p-12 xl:p-16">
        {/* Decorative glows */}
        <div aria-hidden="true" className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-foreground/5 blur-3xl" />
        <div aria-hidden="true" className="absolute -bottom-40 -left-24 w-[28rem] h-[28rem] rounded-full bg-foreground/5 blur-3xl" />

        {/* Brand row */}
        <div className="relative flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 group">
            <span className="w-10 h-10 rounded-2xl bg-primary text-primary-foreground flex items-center justify-center font-black text-xl tracking-tighter group-hover:scale-105 transition-transform">E</span>
            <span className="text-2xl font-extrabold tracking-tighter text-foreground">E-Shop.</span>
          </Link>
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft size={14} /> Back to store
          </Link>
        </div>

        {/* Headline */}
        <div className="relative max-w-md">
          <h1 className="text-4xl xl:text-[2.75rem] font-black leading-[1.1] tracking-tighter text-foreground">
            Join the
            <br />
            membership.
            <br />
            Shop smarter.
          </h1>
          <p className="mt-6 text-base text-muted-foreground leading-relaxed">
            Create a free account to track orders, save wishlists
            and get exclusive member-only deals.
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

        {/* Stats */}
        <div className="relative flex items-center gap-10">
          <div>
            <p className="text-2xl font-black tracking-tighter text-foreground">50K+</p>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mt-0.5">Happy shoppers</p>
          </div>
          <div>
            <p className="text-2xl font-black tracking-tighter text-foreground">4.9<span className="text-muted-foreground">★</span></p>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground font-bold mt-0.5">Average rating</p>
          </div>
        </div>
      </div>

      {/* ── RIGHT: Register Form ──────────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center px-4 py-12 sm:px-8 overflow-y-auto">
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

          <div className="text-center">
            <h2 className="text-3xl font-extrabold tracking-tight text-foreground">
              Create your account
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Already have an account?{' '}
              <Link to="/login" className="font-semibold text-primary hover:text-primary-hover transition-colors">
                Sign in
              </Link>
            </p>
          </div>

          {error && (
            <div className="mt-6 alert-danger px-4 py-3 rounded-lg relative">
              <span className="block sm:inline">❌ {error}</span>
            </div>
          )}

          <form className="mt-8 space-y-5" onSubmit={handleSubmit}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              {FIELDS.slice(0, 2).map(({ id, label, type, placeholder, required }) => (
                <div key={id}>
                  <label htmlFor={id} className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5">
                    {label}
                  </label>
                  <input
                    id={id}
                    name={id}
                    type={type}
                    autoComplete={id === 'email' ? 'email' : id === 'username' ? 'username' : 'name'}
                    required={required}
                    value={formData[id]}
                    onChange={handleChange}
                    className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                    placeholder={placeholder}
                  />
                </div>
              ))}
            </div>

            {FIELDS.slice(2).map(({ id, label, type, placeholder, required }) => (
              <div key={id}>
                <label htmlFor={id} className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5">
                  {label}
                </label>
                <input
                  id={id}
                  name={id}
                  type={type}
                  autoComplete="email"
                  required={required}
                  value={formData[id]}
                  onChange={handleChange}
                  className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                  placeholder={placeholder}
                />
              </div>
            ))}

            <div>
              <label htmlFor="password" className="block text-xs font-bold uppercase tracking-widest text-foreground mb-1.5">
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="new-password"
                required
                minLength={8}
                value={formData.password}
                onChange={handleChange}
                className="w-full px-4 py-3 rounded-xl bg-card border border-border placeholder:text-muted-foreground text-foreground focus:outline-none focus:ring-2 focus:ring-primary focus:border-primary transition-all sm:text-sm"
                placeholder="••••••••"
              />
              <p className="text-[11px] text-muted-foreground mt-1.5">At least 8 characters.</p>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full flex justify-center items-center py-3.5 rounded-xl text-sm font-bold tracking-widest uppercase text-primary-foreground bg-primary hover:bg-primary-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300"
            >
              {loading ? 'Creating account...' : 'Create account'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default Register;
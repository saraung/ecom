import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useWishlist } from '../../hooks/useWishlist';
import { orderAPI } from '../../api/orders';
import { addressAPI } from '../../api/addresses';
import Skeleton, { ProfileSkeleton } from '../../components/common/Skeleton';
import {
  User,
  AtSign,
  Mail,
  Phone,
  ShieldCheck,
  BadgeCheck,
  Settings,
  Package,
  MapPin,
  Heart,
  ArrowUpRight,
  ChevronRight,
} from 'lucide-react';

const Profile = () => {
  const { user, loading } = useAuth();
  const { getWishlistCount } = useWishlist();
  const [orderCount, setOrderCount] = useState(null);
  const [addressCount, setAddressCount] = useState(null);

  const initials =
    user?.full_name?.trim()?.charAt(0)?.toUpperCase() ||
    user?.username?.trim()?.charAt(0)?.toUpperCase() ||
    'U';

  const displayName = user?.full_name || user?.username || 'Unnamed user';

  const wishlistCount = getWishlistCount();

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    orderAPI
      .getOrders(0, 100)
      .then((res) => {
        if (!cancelled) {
          setOrderCount(Array.isArray(res.data) ? res.data.length : 0);
        }
      })
      .catch(() => {});
    addressAPI
      .getAddresses()
      .then((res) => {
        if (!cancelled) {
          setAddressCount(Array.isArray(res.data) ? res.data.length : 0);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [user]);

  const fields = [
    { label: 'Full name', value: user?.full_name, icon: User },
    { label: 'Username', value: user?.username, icon: AtSign },
    { label: 'Email', value: user?.email, icon: Mail },
    { label: 'Phone', value: user?.phone, icon: Phone },
  ];

  const stats = [
    {
      label: 'Total orders',
      value: orderCount,
      icon: Package,
      to: '/orders',
    },
    {
      label: 'Wishlist items',
      value: wishlistCount,
      icon: Heart,
      to: '/wishlist',
    },
    {
      label: 'Saved addresses',
      value: addressCount,
      icon: MapPin,
      to: '/addresses',
    },
  ];

  const quickActions = [
    {
      label: 'My orders',
      description: 'Track, manage and view your purchases',
      to: '/orders',
      icon: Package,
    },
    {
      label: 'Addresses',
      description: 'Add or update your shipping addresses',
      to: '/addresses',
      icon: MapPin,
    },
    {
      label: 'Wishlist',
      description: 'Browse the items you have saved',
      to: '/wishlist',
      icon: Heart,
    },
    {
      label: 'Account settings',
      description: 'Profile, security, preferences & more',
      to: '/settings',
      icon: Settings,
    },
  ];

  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        {/* Header */}
        <div className="mb-8 sm:mb-10 border-b border-border pb-6">
          <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-2">
            Account overview
          </p>
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">
            My Profile
          </h1>
          <p className="text-sm text-muted-foreground font-medium mt-2">
            Your account overview and personal information.
          </p>
        </div>

        {loading && !user ? (
          <ProfileSkeleton />
        ) : (
          <>
            {/* Identity hero */}
            <div className="bg-card border border-border rounded-[2rem] shadow-sm overflow-hidden">
              {/* Cover banner */}
              <div className="relative h-28 sm:h-36 bg-gradient-to-br from-primary via-primary to-primary-hover overflow-hidden">
                <div
                  aria-hidden="true"
                  className="absolute -top-20 -right-16 w-72 h-72 rounded-full bg-white/15 blur-3xl"
                />
                <div
                  aria-hidden="true"
                  className="absolute -bottom-24 left-10 w-64 h-64 rounded-full bg-black/20 blur-3xl"
                />
                <div
                  aria-hidden="true"
                  className="absolute inset-0 opacity-[0.06] bg-[radial-gradient(circle_at_20%_30%,white,transparent_55%)]"
                />
              </div>

              <div className="relative px-6 sm:px-10 pb-6 sm:pb-8 -mt-12 sm:-mt-14">
                <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-5 sm:gap-6">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
                    <div className="relative shrink-0">
                      <div className="w-24 h-24 sm:w-28 sm:h-28 rounded-[2rem] bg-gradient-to-br from-primary to-primary-hover text-primary-foreground flex items-center justify-center text-4xl sm:text-5xl font-black tracking-tighter shadow-xl ring-4 ring-card">
                        {initials}
                      </div>
                      <span
                        className="absolute -bottom-1.5 -right-1.5 w-7 h-7 rounded-full bg-success text-white flex items-center justify-center border-4 border-card"
                        title="Verified account"
                        aria-hidden="true"
                      >
                        <BadgeCheck size={14} strokeWidth={2.5} />
                      </span>
                    </div>

                    <div className="min-w-0 pt-2 sm:pt-0">
                      <h2 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-foreground truncate">
                        {displayName}
                      </h2>
                      <div className="flex flex-wrap items-center gap-2 mt-2.5">
                        {user?.role && (
                          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-primary-soft text-primary text-[11px] font-bold uppercase tracking-widest">
                            <ShieldCheck size={13} />
                            {user.role.charAt(0).toUpperCase() + user.role.slice(1)}
                          </span>
                        )}
                        {user?.email && (
                          <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-muted text-muted-foreground text-[11px] font-bold uppercase tracking-widest">
                            <Mail size={13} />
                            <span className="truncate max-w-[220px]">{user.email}</span>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <Link
                    to="/settings"
                    className="inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground px-5 sm:px-6 py-3 rounded-full text-xs font-bold uppercase tracking-widest shadow-lg hover:bg-primary-hover hover:-translate-y-0.5 transition-all duration-300 shrink-0"
                  >
                    <Settings size={15} />
                    Edit profile
                  </Link>
                </div>

                {/* Stats strip */}
                <div className="mt-7 grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
                  {stats.map(({ label, value, icon: Icon, to }) => (
                    <Link
                      key={label}
                      to={to}
                      className="group flex items-center gap-3 sm:gap-4 rounded-2xl border border-border bg-background px-4 sm:px-5 py-4 hover:border-primary/30 hover:bg-primary-soft/40 transition-all duration-300"
                    >
                      <span className="w-11 h-11 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center">
                        <Icon size={18} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-xl font-extrabold tracking-tight text-foreground leading-none">
                          {value === null ? <Skeleton inline className="h-6 w-10 rounded-md" /> : value}
                        </p>
                        <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground mt-1.5 truncate">
                          {label}
                        </p>
                      </div>
                      <ChevronRight
                        size={15}
                        className="shrink-0 text-muted-foreground opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300"
                      />
                    </Link>
                  ))}
                </div>
              </div>
            </div>

            {/* Details */}
            <div className="mt-6 sm:mt-8 bg-card border border-border rounded-[2rem] shadow-sm overflow-hidden">
              <div className="flex items-center justify-between px-6 sm:px-8 py-5 border-b border-border">
                <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground">
                  Account details
                </h3>
                <Link
                  to="/settings"
                  className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-primary hover:text-primary-hover transition-colors"
                >
                  Edit
                  <ArrowUpRight size={13} />
                </Link>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border">
                {fields.map(({ label, value, icon: Icon }) => (
                  <div
                    key={label}
                    className="flex items-center gap-4 px-6 sm:px-8 py-5 hover:bg-primary-soft/50 transition-colors duration-200"
                  >
                    <span className="w-11 h-11 shrink-0 rounded-2xl bg-primary-soft text-primary flex items-center justify-center">
                      <Icon size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <dt className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                        {label}
                      </dt>
                      <dd className="text-sm sm:text-base font-semibold text-foreground mt-1 break-words">
                        {value || (
                          <span className="font-medium text-muted-foreground">Not provided</span>
                        )}
                      </dd>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick actions */}
            <div className="mt-6 sm:mt-8">
              <div className="flex items-center justify-between mb-4 sm:mb-5">
                <h3 className="text-sm font-extrabold uppercase tracking-widest text-foreground">
                  Quick actions
                </h3>
                <Link
                  to="/settings"
                  className="text-xs font-bold uppercase tracking-widest text-primary hover:text-primary-hover transition-colors"
                >
                  View settings
                </Link>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 max-w-2xl">
                {quickActions.map(({ label, description, to, icon: Icon }) => (
                  <Link
                    key={label}
                    to={to}
                    className="group relative bg-card border border-border rounded-[2rem] shadow-sm p-5 sm:p-6 flex items-center gap-4 hover:shadow-md hover:border-primary/30 hover:-translate-y-1 transition-all duration-300"
                  >
                    <span className="w-12 h-12 shrink-0 rounded-2xl bg-gradient-to-br from-primary to-primary-hover text-primary-foreground flex items-center justify-center shadow-md group-hover:scale-105 transition-transform duration-300">
                      <Icon size={20} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="font-bold text-foreground tracking-tight">{label}</p>
                      <p className="text-xs text-muted-foreground font-medium mt-1 leading-relaxed">
                        {description}
                      </p>
                    </div>
                    <ArrowUpRight
                      size={17}
                      className="shrink-0 text-muted-foreground group-hover:text-primary group-hover:translate-x-1 group-hover:-translate-y-1 transition-all duration-300"
                    />
                  </Link>
                ))}
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default Profile;
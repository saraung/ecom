// src/pages/Settings/Settings.jsx
import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  User,
  Bell,
  Shield,
  Palette,
  Key,
  Save,
  RefreshCw,
  Smartphone,
  Sun,
  Moon,
  Monitor,
  ChevronRight,
  ArrowLeft
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { updateProfile, changePassword } from '../../api/auth';
import toast from 'react-hot-toast';

// Self-profile page — no permission gate by design: every tab (name/phone,
// password, theme, own notification toggles) calls the signed-in user's own
// `/auth/profile` or `/auth/change-password`, both of which only require
// authentication. Route access is therefore gated by the session alone
// (AdminLayout), so managers, staff and custom-role users all reach their
// own account page. See the `settings` route in routes/AppRoutes.jsx.
const Settings = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, updateUser } = useAuth();
  const { theme: currentTheme, setTheme } = useTheme();

  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') || 'profile');
  // Mobile drill-in navigation (Figma admin-kit / iOS Settings pattern): on
  // small screens the page is a hub menu; tapping a row pushes that one
  // section full-screen with a back button, so the tabs + whole panel are
  // never stacked into one long scroll. Desktop keeps the two-column layout.
  // A ?tab= param deep-links straight into a section (e.g. from the header).
  const [mobileOpen, setMobileOpen] = useState(() => !!searchParams.get('tab'));

  // Browser back/forward across ?tab=… stays in sync with the open panel.
  useEffect(() => {
    const t = searchParams.get('tab');
    if (t) {
      setActiveTab(t);
      setMobileOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);
  const [profile, setProfile] = useState({
    full_name: '',
    email: '',
    phone: '',
    username: ''
  });
  const [password, setPassword] = useState({
    current: '',
    new: '',
    confirm: ''
  });
  const [preferences, setPreferences] = useState({
    theme: currentTheme
  });
  const [pushEnabled, setPushEnabled] = useState(true);
  // NOTE: no Email Notifications toggle here by design. Promotional mail is
  // shopper-only (staff are never promo recipients in any channel), so the
  // `email_notifications_enabled` flag is consent UI for the storefront only.

  // Keep the displayed preference in sync when theme changes elsewhere (e.g. header toggle)
  useEffect(() => {
    setPreferences((prev) => ({ ...prev, theme: currentTheme }));
  }, [currentTheme]);

  useEffect(() => {
    if (user) {
      setProfile({
        full_name: user.full_name || '',
        email: user.email || '',
        phone: user.phone || '',
        username: user.username || ''
      });
    }
  }, [user]);

  // Keep notification toggles in sync with backend-persisted settings
  useEffect(() => {
    if (user) {
      setPushEnabled(user.push_notifications_enabled ?? true);
    }
  }, [user]);

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      // Backend PUT /auth/profile accepts full_name, phone and username only
      // (email changes go through a separate verification flow)
      const response = await updateProfile({
        full_name: profile.full_name,
        phone: profile.phone,
        username: profile.username,
      });
      // Reflect changes immediately in the header/sidebar
      updateUser(response.data);
      toast.success('Profile updated successfully');
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to update profile'));
    } finally {
      setSaving(false);
    }
  };

  // Extract a readable message from a FastAPI error response
  // (detail is a string for HTTPException, an array for 422 validation errors)
  const getApiErrorMessage = (error, fallback) => {
    const detail = error?.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : null;
      const msg = first.msg ? first.msg.replace(/^Value error,\s*/, '') : fallback;
      return field ? `${field}: ${msg}` : msg || fallback;
    }
    return fallback;
  };

  const handleUpdatePassword = async (e) => {
    e.preventDefault();
    if (password.new !== password.confirm) {
      toast.error('Passwords do not match');
      return;
    }
    if (password.new.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    try {
      setSaving(true);
      const response = await changePassword({
        current_password: password.current,
        new_password: password.new,
      });
      toast.success(response.data?.message || 'Password updated successfully');
      setPassword({ current: '', new: '', confirm: '' });
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to update password'));
    } finally {
      setSaving(false);
    }
  };

  const handleThemeChange = (value) => {
    setTheme(value);
    setPreferences((prev) => ({ ...prev, theme: value }));
  };

  const handleSavePreferences = async () => {
    try {
      setSaving(true);
      localStorage.setItem('ec-admin-preferences', JSON.stringify({
        theme: currentTheme,
      }));
      await new Promise(resolve => setTimeout(resolve, 500));
      toast.success('Preferences saved successfully');
    } catch {
      toast.error('Failed to save preferences');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveNotificationSettings = async () => {
    try {
      setSaving(true);
      const response = await updateProfile({
        push_notifications_enabled: pushEnabled,
      });
      // Reflect changes immediately in the header/sidebar
      updateUser(response.data);
      toast.success('Notification settings saved successfully');
    } catch (error) {
      toast.error(getApiErrorMessage(error, 'Failed to save notification settings'));
    } finally {
      setSaving(false);
    }
  };

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User, desc: 'Name, username, phone', tile: 'bg-primary-soft text-primary' },
    { id: 'security', label: 'Security', icon: Shield, desc: 'Password', tile: 'bg-success/15 text-success' },
    { id: 'preferences', label: 'Preferences', icon: Palette, desc: `Theme · ${currentTheme}`, tile: 'bg-purple-500/15 text-purple-600 dark:text-purple-300' },
    { id: 'notifications', label: 'Notifications', icon: Bell, desc: `Push ${pushEnabled ? 'on' : 'off'}`, tile: 'bg-warning/15 text-warning' },
  ];

  const selectTab = (id) => {
    setActiveTab(id);
    setSearchParams({ tab: id });
    setMobileOpen(true);
  };

  const activeTabMeta = tabs.find((t) => t.id === activeTab) || tabs[0];

  return (
    <div>
      {/* Desktop page header — mobile gets its own compact heading per view
          (hub menu / sub-screen nav bar) instead of stacking everything. */}
      <div className="mb-6 min-w-0 hidden lg:block">
        <h1 className="text-2xl font-bold text-foreground break-words">Settings</h1>
        <p className="text-sm text-muted-foreground mt-1">Manage your account and preferences</p>
      </div>

      {/* Mobile hub menu: identity card + drill-in rows (no panel stacked
          below, so the screen fits without scrolling). */}
      {!mobileOpen && (
        <div className="lg:hidden space-y-4">
          <div className="min-w-0">
            <h1 className="text-xl font-bold text-foreground break-words">Settings</h1>
            <p className="text-sm text-muted-foreground mt-0.5">Manage your account and preferences</p>
          </div>
          <div className="bg-card rounded-xl border border-border p-4 flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-primary flex items-center justify-center text-primary-foreground dark:text-black text-lg font-semibold shrink-0">
              {profile.full_name?.[0] || profile.username?.[0] || 'A'}
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground truncate">
                {profile.full_name || profile.username || 'Admin'}
              </p>
              <p className="text-xs text-muted-foreground truncate">{profile.email}</p>
            </div>
          </div>
          <div className="bg-card rounded-xl border border-border divide-y divide-border overflow-hidden">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => selectTab(tab.id)}
                  className="w-full flex items-center gap-3 p-4 text-left hover:bg-muted active:bg-muted transition-colors"
                >
                  <span className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${tab.tile}`}>
                    <Icon size={18} />
                  </span>
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-medium text-foreground">{tab.label}</span>
                    <span className="block text-xs text-muted-foreground truncate">{tab.desc}</span>
                  </span>
                  <ChevronRight size={18} className="text-muted-foreground shrink-0" />
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className={`grid grid-cols-1 lg:grid-cols-4 gap-4 lg:gap-6 ${mobileOpen ? '' : 'hidden lg:grid'}`}>
        {/* Sidebar (desktop only — mobile uses the hub menu above) */}
        <div className="hidden lg:block lg:col-span-1">
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 lg:sticky lg:top-6">
            <div className="flex flex-col gap-1 space-y-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => selectTab(tab.id)}
                    className={`w-full flex items-center gap-3 px-4 py-2.5 rounded-lg transition-colors ${
                      activeTab === tab.id
                        ? 'bg-primary-soft text-primary font-medium'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                    }`}
                  >
                    <Icon size={18} />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="lg:col-span-3 min-w-0">
          {/* Mobile sub-screen nav bar */}
          <button
            onClick={() => setMobileOpen(false)}
            className="lg:hidden flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground mb-3"
            aria-label="Back to settings"
          >
            <ArrowLeft size={16} />
            Settings
          </button>
          <p className="lg:hidden text-xs text-muted-foreground mb-2">
            {activeTabMeta.label} · {activeTabMeta.desc}
          </p>
          <div className="bg-card rounded-xl shadow-sm border border-border p-4 sm:p-6">
            {activeTab === 'profile' && (
              <form onSubmit={handleUpdateProfile}>
                <h2 className="text-lg font-semibold text-foreground mb-4">Profile Settings</h2>
                <p className="text-sm text-muted-foreground mb-6">Update your personal information</p>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      Full Name
                    </label>
                    <input
                      type="text"
                      value={profile.full_name}
                      onChange={(e) => setProfile({ ...profile, full_name: e.target.value })}
                      className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                      placeholder="Enter your full name"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      Username
                    </label>
                    <input
                      type="text"
                      value={profile.username}
                      onChange={(e) => setProfile({ ...profile, username: e.target.value })}
                      className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                      placeholder="Enter username"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      Email Address
                    </label>
                    <input
                      type="email"
                      value={profile.email}
                      readOnly
                      className="w-full px-4 py-2 border border-input rounded-lg bg-muted text-muted-foreground cursor-not-allowed"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Email cannot be changed from here
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      Phone Number
                    </label>
                    <input
                      type="tel"
                      value={profile.phone}
                      onChange={(e) => setProfile({ ...profile, phone: e.target.value })}
                      className="w-full px-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                      placeholder="Enter phone number"
                    />
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={saving}
                  className="mt-6 px-6 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <RefreshCw size={18} className="animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save size={18} />
                      Save Changes
                    </>
                  )}
                </button>
              </form>
            )}

            {activeTab === 'security' && (
              <form onSubmit={handleUpdatePassword}>
                <h2 className="text-lg font-semibold text-foreground mb-4">Change Password</h2>
                <p className="text-sm text-muted-foreground mb-6">Update your password to keep your account secure</p>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      Current Password
                    </label>
                    <div className="relative">
                      <Key className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
                      <input
                        type="password"
                        value={password.current}
                        onChange={(e) => setPassword({ ...password, current: e.target.value })}
                        className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="Enter current password"
                        required
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      New Password
                    </label>
                    <div className="relative">
                      <Key className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
                      <input
                        type="password"
                        value={password.new}
                        onChange={(e) => setPassword({ ...password, new: e.target.value })}
                        className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="Enter new password"
                        required
                        minLength={8}
                      />
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">Password must be at least 8 characters</p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      Confirm New Password
                    </label>
                    <div className="relative">
                      <Key className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" size={18} />
                      <input
                        type="password"
                        value={password.confirm}
                        onChange={(e) => setPassword({ ...password, confirm: e.target.value })}
                        className="w-full pl-10 pr-4 py-2 border border-input rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
                        placeholder="Confirm new password"
                        required
                      />
                    </div>
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={saving}
                  className="mt-6 px-6 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <RefreshCw size={18} className="animate-spin" />
                      Updating...
                    </>
                  ) : (
                    <>
                      <Key size={18} />
                      Update Password
                    </>
                  )}
                </button>
              </form>
            )}

            {activeTab === 'preferences' && (
              <div>
                <h2 className="text-lg font-semibold text-foreground mb-4">Preferences</h2>
                <p className="text-sm text-muted-foreground mb-6">Customize your experience</p>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-2">
                      Theme
                    </label>
                    <div className="grid grid-cols-3 gap-2 sm:gap-3">
                      {[
                        { value: 'light', label: 'Light', icon: Sun },
                        { value: 'dark', label: 'Dark', icon: Moon },
                        { value: 'system', label: 'System', icon: Monitor },
                      ].map((opt) => {
                        const ThemeIcon = opt.icon;
                        const isActive = currentTheme === opt.value;
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => handleThemeChange(opt.value)}
                            className={`flex flex-col items-center gap-1.5 sm:gap-2 p-3 sm:p-4 rounded-xl border-2 transition-colors ${
                              isActive
                                ? 'border-primary bg-primary-soft text-primary'
                                : 'border-border text-muted-foreground hover:bg-muted hover:text-foreground'
                            }`}
                          >
                            <ThemeIcon size={20} />
                            <span className="text-xs sm:text-sm font-medium">{opt.label}</span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Live preview of the active theme colors */}
                    <div className="mt-4 p-4 rounded-xl border border-border bg-background flex items-center gap-3">
                      <div className="w-14 h-14 rounded-lg border border-border bg-card shadow-sm flex items-center justify-center text-xs font-semibold text-foreground">
                        Aa
                      </div>
                      <div className="flex-1 space-y-2">
                        <div className="h-2.5 rounded-full bg-foreground/80 w-3/4" />
                        <div className="h-2.5 rounded-full bg-muted-foreground/60 w-1/2" />
                        <div className="h-2.5 rounded-full bg-muted w-2/3" />
                      </div>
                      <div className="w-8 h-8 rounded-full bg-primary shrink-0" />
                    </div>

                    <p className="text-xs text-muted-foreground mt-2">
                      Applies instantly everywhere. Want a different look? Change the colors in
                      <code className="text-primary mx-1">src/styles/theme.css</code> — that one file
                      controls the entire site's palette (light &amp; dark).
                    </p>
                  </div>
                </div>
                <button
                  onClick={handleSavePreferences}
                  disabled={saving}
                  className="mt-6 px-6 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <RefreshCw size={18} className="animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save size={18} />
                      Save Preferences
                    </>
                  )}
                </button>
              </div>
            )}

            {activeTab === 'notifications' && (
              <div>
                <h2 className="text-lg font-semibold text-foreground mb-4">Notification Settings</h2>
                <p className="text-sm text-muted-foreground mb-6">Manage how you receive notifications</p>
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-muted rounded-lg">
                    <div>
                      <div className="flex items-center gap-2">
                        <Smartphone size={18} className="text-muted-foreground" />
                        <p className="font-medium text-foreground">Push Notifications</p>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">Receive push notifications on your device</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={pushEnabled}
                        onChange={(e) => setPushEnabled(e.target.checked)}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-muted peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:border-input after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                  </div>
                </div>
                <button
                  onClick={handleSaveNotificationSettings}
                  disabled={saving}
                  className="mt-6 px-6 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <RefreshCw size={18} className="animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save size={18} />
                      Save Settings
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Settings;
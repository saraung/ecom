import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';
import { authAPI } from '../../api/auth';
import { addressAPI } from '../../api/addresses';
import toast from 'react-hot-toast';
import {
  User,
  MapPin,
  ShieldCheck,
  Palette,
  Bell,
  CheckCircle2,
  ChevronRight,
  Plus,
} from 'lucide-react';

const inputBase =
  'w-full px-4 py-3 rounded-xl border bg-card text-foreground text-sm placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-2 transition-all';
const inputValid = `${inputBase} border-border focus:ring-primary/40`;
const inputInvalid = `${inputBase} border-destructive focus:ring-destructive/40`;
const btnPrimary =
  'inline-flex items-center justify-center gap-2 bg-primary text-primary-foreground px-8 py-3.5 rounded-full font-bold uppercase tracking-widest text-xs sm:text-sm hover:scale-105 hover:-translate-y-0.5 hover:bg-primary-hover transition-all duration-300 ease-out shadow-xl disabled:opacity-60 disabled:pointer-events-none cursor-pointer';
const btnGhost =
  'inline-flex items-center justify-center gap-2 px-8 py-3.5 rounded-full border border-border bg-card text-foreground font-bold uppercase tracking-widest text-xs sm:text-sm hover:border-primary/30 hover:text-primary transition-all duration-300 cursor-pointer';
const labelCls = 'block text-xs font-bold uppercase tracking-widest text-muted-foreground mb-2';

const Settings = () => {
  const navigate = useNavigate();
  const { user, updateUser } = useAuth();
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('profile');

  const [profile, setProfile] = useState({
    full_name: '',
    email: '',
    phone: '',
    username: ''
  });
  const [profileErrors, setProfileErrors] = useState({});

  const [password, setPassword] = useState({
    current: '',
    new: '',
    confirm: ''
  });
  const [passwordErrors, setPasswordErrors] = useState({});
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const { theme, setTheme, resolvedTheme } = useTheme();
  const [preferences, setPreferences] = useState({
    language: 'en'
  });
  const [notifications, setNotifications] = useState(true);
  const [emailNotifications, setEmailNotifications] = useState(true);

  const [addresses, setAddresses] = useState([]);
  const [addressesLoading, setAddressesLoading] = useState(false);

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

  useEffect(() => {
    if (user) {
      setNotifications(user.push_notifications_enabled ?? true);
      setEmailNotifications(user.email_notifications_enabled ?? true);
    }
  }, [user]);

  useEffect(() => {
    if (activeTab === 'addresses') {
      fetchAddresses();
    }
  }, [activeTab]);

  const fetchAddresses = async () => {
    try {
      setAddressesLoading(true);
      const response = await addressAPI.getAddresses();
      setAddresses(response.data || []);
    } catch (error) {
      console.error('Error fetching addresses:', error);
      toast.error('Failed to load addresses');
    } finally {
      setAddressesLoading(false);
    }
  };

  const validateProfile = () => {
    const errors = {};
    if (!profile.full_name || profile.full_name.trim().length < 2) {
      errors.full_name = 'Full name must be at least 2 characters';
    }
    if (profile.phone && !/^\+?[\d\s-]{10,}$/.test(profile.phone)) {
      errors.phone = 'Please enter a valid phone number';
    }
    if (profile.username && profile.username.length < 3) {
      errors.username = 'Username must be at least 3 characters';
    }
    if (profile.username && !/^[a-zA-Z0-9_]+$/.test(profile.username)) {
      errors.username = 'Username can only contain letters, numbers, and underscores';
    }
    setProfileErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validatePassword = () => {
    const errors = {};
    if (!password.current) errors.current = 'Current password is required';
    if (!password.new || password.new.length < 8) errors.new = 'New password must be at least 8 characters';
    if (password.new && !/[A-Z]/.test(password.new)) errors.new = 'Password must contain at least one uppercase letter';
    if (password.new && !/[a-z]/.test(password.new)) errors.new = 'Password must contain at least one lowercase letter';
    if (password.new && !/[0-9]/.test(password.new)) errors.new = 'Password must contain at least one number';
    if (password.new !== password.confirm) errors.confirm = 'Passwords do not match';
    if (password.current && password.new && password.current === password.new) {
      errors.new = 'New password must be different from current password';
    }
    setPasswordErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleUpdateProfile = async (e) => {
    e.preventDefault();
    if (!validateProfile()) {
      toast.error('Please fix the errors in the form');
      return;
    }
    try {
      setSaving(true);
      const requestData = {
        full_name: profile.full_name.trim(),
        phone: profile.phone || null,
        username: profile.username || null,
      };
      const response = await authAPI.updateProfile(requestData);
      toast.success('✅ Profile updated successfully!');
      if (updateUser) updateUser(response.data);
      setProfile({
        full_name: response.data.full_name || '',
        email: response.data.email || '',
        phone: response.data.phone || '',
        username: response.data.username || ''
      });
    } catch (error) {
      let errorMessage = 'Failed to update profile';
      if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map(err => err.msg || err.message).join(', ');
        } else {
          errorMessage = error.response.data.detail;
        }
      }
      toast.error(errorMessage);
      if (error.response?.status === 400 && error.response?.data?.detail?.includes('username already taken')) {
        setProfileErrors({ ...profileErrors, username: 'Username already taken' });
      }
    } finally {
      setSaving(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    if (!validatePassword()) {
      toast.error('Please fix the errors in the form');
      return;
    }
    try {
      setSaving(true);
      setPasswordSuccess(false);
      await authAPI.changePassword({
        current_password: password.current,
        new_password: password.new,
      });
      toast.success('✅ Password changed successfully!');
      setPasswordSuccess(true);
      setPassword({ current: '', new: '', confirm: '' });
      setPasswordErrors({});
      setTimeout(() => setPasswordSuccess(false), 5000);
    } catch (error) {
      let errorMessage = 'Failed to change password';
      if (error.response?.status === 401) {
        errorMessage = 'Current password is incorrect. Please try again.';
        setPasswordErrors({ ...passwordErrors, current: 'Incorrect password' });
      } else if (error.response?.data?.detail) {
        if (Array.isArray(error.response.data.detail)) {
          errorMessage = error.response.data.detail.map(err => err.msg || err.message).join(', ');
        } else {
          errorMessage = error.response.data.detail;
        }
      }
      toast.error(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  const handleSavePreferences = async () => {
    try {
      setSaving(true);
      // Theme is applied instantly via ThemeContext; keep a legacy copy too
      localStorage.setItem('preferences', JSON.stringify({ language: preferences.language, theme }));
      localStorage.setItem('ec-theme', theme);
      await new Promise(resolve => setTimeout(resolve, 500));
      toast.success('✅ Preferences saved successfully!');
    } catch (error) {
      console.error('Error saving preferences:', error);
      toast.error('Failed to save preferences');
    } finally {
      setSaving(false);
    }
  };

  const handleSaveNotificationSettings = async () => {
    try {
      setSaving(true);
      const response = await authAPI.updateProfile({
        push_notifications_enabled: notifications,
        email_notifications_enabled: emailNotifications,
      });
      toast.success('✅ Notification settings saved successfully!');
      if (updateUser) updateUser(response.data);
    } catch (error) {
      console.error('Error saving notification settings:', error);
      let errorMessage = 'Failed to save notification settings';
      if (error.response?.data?.detail && typeof error.response.data.detail === 'string') {
        errorMessage = error.response.data.detail;
      }
      toast.error(errorMessage);
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const savedPrefs = localStorage.getItem('preferences');
    if (savedPrefs) {
      try {
        const parsed = JSON.parse(savedPrefs);
        setPreferences(prev => ({ ...prev, language: parsed.language ?? prev.language }));
        // Migrate a stored theme from the old dummy select into the live switcher
        if (parsed.theme === 'light' || parsed.theme === 'dark' || parsed.theme === 'system') {
          setTheme(parsed.theme);
        }
      } catch (e) { /* ignore */ }
    }
  }, [setTheme]);

  const tabs = [
    { id: 'profile', label: 'Profile', icon: User },
    { id: 'addresses', label: 'Addresses', icon: MapPin },
    { id: 'security', label: 'Security', icon: ShieldCheck },
    { id: 'preferences', label: 'Preferences', icon: Palette },
    { id: 'notifications', label: 'Notifications', icon: Bell }
  ];

  const sectionTitle = (title, subtitle) => (
    <header className="mb-6">
      <h2 className="text-xl font-extrabold tracking-tight text-foreground">{title}</h2>
      <p className="text-sm text-muted-foreground font-medium mt-1">{subtitle}</p>
    </header>
  );

  return (
    <div className="bg-background min-h-screen transition-colors duration-700 pb-24">
      <div className="max-w-6xl mx-auto px-4 lg:px-8 pt-8 sm:pt-12">
        {/* Header */}
        <div className="mb-8 sm:mb-10 border-b border-border pb-6">
          <h1 className="text-3xl md:text-4xl font-extrabold tracking-tighter text-foreground">
            Settings
          </h1>
          <p className="text-sm text-muted-foreground font-medium mt-2">
            Manage your account, addresses, security and preferences.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 lg:gap-8">
          {/* Sidebar nav */}
          <aside className="lg:col-span-1">
            <nav className="flex lg:flex-col gap-2 overflow-x-auto lg:overflow-visible pb-2 lg:pb-0" aria-label="Settings sections">
              {tabs.map(({ id, label, icon: Icon }) => (
                <button
                  key={id}
                  onClick={() => setActiveTab(id)}
                  className={`inline-flex items-center gap-3 px-4 sm:px-5 py-3 rounded-2xl text-sm font-bold whitespace-nowrap transition-all duration-200 cursor-pointer ${
                    activeTab === id
                      ? 'bg-primary text-primary-foreground shadow-lg'
                      : 'text-muted-foreground hover:bg-primary-soft hover:text-foreground'
                  }`}
                >
                  <Icon size={17} />
                  {label}
                </button>
              ))}
            </nav>
          </aside>

          {/* Content */}
          <section className="lg:col-span-3">
            <div className="bg-card border border-border rounded-[2rem] shadow-sm p-6 sm:p-8">
              {/* PROFILE */}
              {activeTab === 'profile' && (
                <form onSubmit={handleUpdateProfile}>
                  {sectionTitle('Profile Settings', 'Update your personal information')}

                  <div className="space-y-5">
                    <div>
                      <label className={labelCls}>Full Name *</label>
                      <input
                        type="text"
                        value={profile.full_name}
                        onChange={(e) => {
                          setProfile({ ...profile, full_name: e.target.value });
                          if (profileErrors.full_name) setProfileErrors({ ...profileErrors, full_name: '' });
                        }}
                        className={profileErrors.full_name ? inputInvalid : inputValid}
                        placeholder="e.g. Priya Sharma"
                        required
                      />
                      {profileErrors.full_name && <p className="text-xs text-destructive mt-1.5">{profileErrors.full_name}</p>}
                    </div>

                    <div>
                      <label className={labelCls}>Username</label>
                      <input
                        type="text"
                        value={profile.username}
                        onChange={(e) => {
                          setProfile({ ...profile, username: e.target.value });
                          if (profileErrors.username) setProfileErrors({ ...profileErrors, username: '' });
                        }}
                        className={profileErrors.username ? inputInvalid : inputValid}
                        placeholder="@username"
                      />
                      {profileErrors.username && <p className="text-xs text-destructive mt-1.5">{profileErrors.username}</p>}
                      <p className="text-xs text-muted-foreground mt-1.5">Letters, numbers, and underscores only</p>
                    </div>

                    <div>
                      <label className={labelCls}>Email Address</label>
                      <input
                        type="email"
                        value={profile.email}
                        disabled
                        className="w-full px-4 py-3 rounded-xl border border-border bg-muted text-muted-foreground text-sm"
                      />
                      <p className="text-xs text-muted-foreground mt-1.5">Email cannot be changed. Contact support.</p>
                    </div>

                    <div>
                      <label className={labelCls}>Phone Number</label>
                      <input
                        type="tel"
                        value={profile.phone}
                        onChange={(e) => {
                          setProfile({ ...profile, phone: e.target.value });
                          if (profileErrors.phone) setProfileErrors({ ...profileErrors, phone: '' });
                        }}
                        className={profileErrors.phone ? inputInvalid : inputValid}
                        placeholder="+91 00000 00000"
                      />
                      {profileErrors.phone && <p className="text-xs text-destructive mt-1.5">{profileErrors.phone}</p>}
                    </div>
                  </div>

                  <div className="mt-8 flex justify-end">
                    <button type="submit" disabled={saving} className={btnPrimary}>
                      {saving ? 'Saving...' : 'Save Changes'}
                    </button>
                  </div>
                </form>
              )}

              {/* ADDRESSES */}
              {activeTab === 'addresses' && (
                <div>
                  <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
                    <header>
                      <h2 className="text-xl font-extrabold tracking-tight text-foreground">Addresses</h2>
                      <p className="text-sm text-muted-foreground font-medium mt-1">Manage your saved addresses</p>
                    </header>
                    <button onClick={() => navigate('/addresses')} className={btnGhost}>
                      <Plus size={15} />
                      Manage Addresses
                    </button>
                  </div>

                  {addressesLoading ? (
                    <div className="flex items-center justify-center py-12">
                      <div className="w-8 h-8 rounded-full bg-primary-soft animate-pulse" aria-hidden="true" />
                    </div>
                  ) : addresses.length === 0 ? (
                    <div className="text-center py-12 rounded-2xl border-2 border-dashed border-border bg-background">
                      <div className="text-4xl mb-3" aria-hidden="true">📍</div>
                      <p className="text-sm font-semibold text-foreground">No addresses saved</p>
                      <p className="text-sm text-muted-foreground mt-1 mb-5">Add your first address for faster checkout</p>
                      <button onClick={() => navigate('/addresses')} className={btnPrimary}>
                        <Plus size={15} />
                        Add Address
                      </button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {addresses.slice(0, 3).map((address) => (
                        <div
                          key={address.id}
                          className="flex items-center gap-4 p-4 rounded-2xl border border-border bg-background"
                        >
                          <span className="w-10 h-10 shrink-0 rounded-xl bg-primary-soft text-primary flex items-center justify-center">
                            <MapPin size={17} />
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-bold text-foreground truncate">
                                {address.label || 'Address'}
                              </span>
                              {address.is_default && (
                                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full bg-primary-soft text-primary text-[10px] font-bold uppercase tracking-widest">
                                  Default
                                </span>
                              )}
                            </div>
                            <p className="text-xs text-muted-foreground truncate mt-0.5">
                              {address.line1}
                              {address.line2 ? `, ${address.line2}` : ''} · {address.city}
                            </p>
                          </div>
                          <button
                            onClick={() => navigate('/addresses')}
                            className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-widest text-muted-foreground hover:text-primary transition-colors cursor-pointer bg-transparent border-none"
                          >
                            Edit
                            <ChevronRight size={14} />
                          </button>
                        </div>
                      ))}
                      {addresses.length > 3 && (
                        <button
                          onClick={() => navigate('/addresses')}
                          className="w-full text-center text-sm font-bold uppercase tracking-widest text-primary hover:text-primary-hover underline underline-offset-4 transition-colors cursor-pointer bg-transparent border-none py-2"
                        >
                          View all {addresses.length} addresses →
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* SECURITY */}
              {activeTab === 'security' && (
                <form onSubmit={handleChangePassword}>
                  {sectionTitle('Change Password', 'Update your password to keep your account secure')}

                  {passwordSuccess && (
                    <div className="mb-5 p-4 rounded-2xl bg-success-soft text-success-soft-foreground text-sm font-semibold flex items-center gap-2">
                      <CheckCircle2 size={18} className="shrink-0" />
                      Password changed successfully!
                    </div>
                  )}

                  <div className="space-y-5">
                    <div>
                      <label className={labelCls}>Current Password *</label>
                      <input
                        type="password"
                        value={password.current}
                        onChange={(e) => {
                          setPassword({ ...password, current: e.target.value });
                          if (passwordErrors.current) setPasswordErrors({ ...passwordErrors, current: '' });
                        }}
                        className={passwordErrors.current ? inputInvalid : inputValid}
                        placeholder="Enter your current password"
                        required
                      />
                      {passwordErrors.current && <p className="text-xs text-destructive mt-1.5">{passwordErrors.current}</p>}
                    </div>

                    <div>
                      <label className={labelCls}>New Password *</label>
                      <input
                        type="password"
                        value={password.new}
                        onChange={(e) => {
                          setPassword({ ...password, new: e.target.value });
                          if (passwordErrors.new) setPasswordErrors({ ...passwordErrors, new: '' });
                        }}
                        className={passwordErrors.new ? inputInvalid : inputValid}
                        placeholder="Enter a new password"
                        required
                        minLength={8}
                      />
                      {passwordErrors.new && <p className="text-xs text-destructive mt-1.5">{passwordErrors.new}</p>}
                      <p className="text-xs text-muted-foreground mt-1.5">
                        Must be at least 8 characters, include uppercase, lowercase, and number
                      </p>
                    </div>

                    <div>
                      <label className={labelCls}>Confirm New Password *</label>
                      <input
                        type="password"
                        value={password.confirm}
                        onChange={(e) => {
                          setPassword({ ...password, confirm: e.target.value });
                          if (passwordErrors.confirm) setPasswordErrors({ ...passwordErrors, confirm: '' });
                        }}
                        className={passwordErrors.confirm ? inputInvalid : inputValid}
                        placeholder="Re-enter the new password"
                        required
                      />
                      {passwordErrors.confirm && <p className="text-xs text-destructive mt-1.5">{passwordErrors.confirm}</p>}
                      {password.confirm && password.new === password.confirm && password.new.length >= 8 && (
                        <p className="text-xs text-success mt-1.5 font-semibold flex items-center gap-1">
                          <CheckCircle2 size={13} /> Passwords match
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="mt-8 flex justify-end">
                    <button type="submit" disabled={saving} className={btnPrimary}>
                      {saving ? 'Updating...' : 'Update Password'}
                    </button>
                  </div>
                </form>
              )}

              {/* PREFERENCES */}
              {activeTab === 'preferences' && (
                <div>
                  {sectionTitle('Appearance & Preferences', 'Customize your experience (theme applies instantly)')}

                  <div className="space-y-6">
                    <div>
                      <label className={labelCls}>Theme</label>
                      <div className="grid grid-cols-3 gap-1.5 rounded-xl border border-border bg-muted p-1.5" role="radiogroup" aria-label="Theme">
                        {[
                          { value: 'light', label: 'Light' },
                          { value: 'dark', label: 'Dark' },
                          { value: 'system', label: 'System' },
                        ].map((opt) => (
                          <button
                            key={opt.value}
                            type="button"
                            role="radio"
                            aria-checked={theme === opt.value}
                            onClick={() => setTheme(opt.value)}
                            className={`rounded-lg px-2 py-2.5 text-sm font-bold tracking-wide transition-colors cursor-pointer ${
                              theme === opt.value
                                ? 'bg-card text-foreground shadow-sm border border-border'
                                : 'text-muted-foreground hover:text-foreground border border-transparent'
                            }`}
                          >
                            {opt.label}
                          </button>
                        ))}
                      </div>
                      <p className="mt-2 text-xs text-muted-foreground">
                        Currently showing {resolvedTheme === 'dark' ? 'Dark' : 'Light'}
                        {theme === 'system' ? ' (following system)' : ''}
                      </p>
                    </div>

                    <div>
                      <label className={labelCls}>Language</label>
                      <select
                        value={preferences.language}
                        onChange={(e) => setPreferences({ ...preferences, language: e.target.value })}
                        className="w-full px-4 py-3 rounded-xl border border-border bg-card text-foreground text-sm"
                      >
                        <option value="en">English (UK)</option>
                        <option value="hi">Hindi</option>
                        <option value="es">Spanish</option>
                        <option value="fr">French</option>
                      </select>
                    </div>
                  </div>

                  <div className="mt-8 flex justify-end">
                    <button onClick={handleSavePreferences} disabled={saving} className={btnPrimary}>
                      {saving ? 'Saving...' : 'Save Preferences'}
                    </button>
                  </div>
                </div>
              )}

              {/* NOTIFICATIONS */}
              {activeTab === 'notifications' && (
                <div>
                  {sectionTitle('Notification Settings', 'Manage how you receive notifications')}

                  <div className="space-y-3">
                    {[
                      {
                        key: 'push',
                        checked: notifications,
                        setter: setNotifications,
                        title: 'Push Notifications',
                        desc: 'Receive push notifications on your device',
                      },
                      {
                        key: 'email',
                        checked: emailNotifications,
                        setter: setEmailNotifications,
                        title: 'Email Notifications',
                        desc: 'Receive email updates and announcements',
                      },
                    ].map(({ key, checked, setter, title, desc }) => {
                      return (
                        <div
                          key={key}
                          className="flex items-center justify-between gap-4 p-5 rounded-2xl border border-border bg-background"
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-bold text-foreground">{title}</p>
                            <p className="text-sm text-muted-foreground mt-0.5">{desc}</p>
                          </div>
                          <label className="relative inline-flex items-center cursor-pointer shrink-0">
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => setter(!checked)}
                              className="sr-only peer"
                            />
                            <div className="w-11 h-6 bg-muted peer-focus:ring-2 peer-focus:ring-primary rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:border-input after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                          </label>
                        </div>
                      );
                    })}
                  </div>

                  <div className="mt-8 flex justify-end">
                    <button onClick={handleSaveNotificationSettings} disabled={saving} className={btnPrimary}>
                      {saving ? 'Saving...' : 'Save Settings'}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
};

export default Settings;
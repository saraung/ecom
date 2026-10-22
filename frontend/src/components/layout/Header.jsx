import React, { useState, useEffect, useRef } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { Bell, Heart, Search, ShoppingBag, Menu, X, User } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { useCart } from '../../hooks/useCart';
import { useWishlist } from '../../hooks/useWishlist';
import notificationService from '../../services/notificationService';
import { useNotifications } from '../../contexts/NotificationContext';
import SearchSuggestions from '../common/SearchSuggestions';

const Header = () => {
  const { user, logout } = useAuth();
  const { subscribe } = useNotifications();
  const { itemCount } = useCart();
  const { getWishlistCount } = useWishlist();
  const navigate = useNavigate();
  const location = useLocation();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  
  const searchRef = useRef(null);
  const userMenuRef = useRef(null);
  const notificationRef = useRef(null);
  const desktopSearchInputRef = useRef(null);
  const mobileSearchInputRef = useRef(null);

  const wishlistCount = getWishlistCount();

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) setIsSearchOpen(false);
      if (userMenuRef.current && !userMenuRef.current.contains(e.target)) setIsUserMenuOpen(false);
      if (notificationRef.current && !notificationRef.current.contains(e.target)) setIsNotificationOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Subscribe to live push
  useEffect(() => {
    if (user) {
      loadNotifications();
      return subscribe((notification) => {
        setNotifications(prev => {
          const exists = prev.some(n => n.id === notification.id);
          if (exists) return prev;
          return [notification, ...prev];
        });
        if (!notification.is_read) {
          setUnreadCount(prev => prev + 1);
        }
      });
    }
    setNotifications([]);
    setUnreadCount(0);
  }, [user, subscribe]);

  const loadNotifications = async () => {
    try {
      const [feed, count] = await Promise.allSettled([
        notificationService.getFeed(0, 20),
        notificationService.getUnreadCount(),
      ]);

      if (feed.status === 'fulfilled') {
        setNotifications(feed.value);
        if (count.status !== 'fulfilled') {
          setUnreadCount(feed.value.filter(n => !n.is_read).length);
        }
      }
      if (count.status === 'fulfilled') {
        setUnreadCount(count.value);
      }
    } catch (error) {
      console.error('Failed to load notifications:', error);
    }
  };

  // Polling fallback
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState === 'visible') loadNotifications();
    };
    const interval = setInterval(refresh, 12000);
    document.addEventListener('visibilitychange', refresh);
    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', refresh);
    };
  }, []);

  useEffect(() => {
    setIsMobileMenuOpen(false);
    setIsUserMenuOpen(false);
    setIsSearchOpen(false);
    setIsNotificationOpen(false);
  }, [location]);

  // Close the mobile sheet when rotating/resizing up to desktop —
  // otherwise the hidden overlay keeps body scroll locked.
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 768) {
        setIsMobileMenuOpen(false);
        setIsNotificationOpen(false);
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = isMobileMenuOpen ? 'hidden' : prevOverflow;
    return () => { document.body.style.overflow = prevOverflow; };
  }, [isMobileMenuOpen]);

  const handleLogout = async () => {
    await logout();
    navigate('/');
    setIsUserMenuOpen(false);
    setIsNotificationOpen(false);
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      navigate(`/products?search=${encodeURIComponent(searchQuery.trim())}`);
      setSearchQuery('');
      setIsSearchOpen(false);
      setIsMobileMenuOpen(false);
    }
  };

  const closeSearch = () => {
    setSearchQuery('');
    setIsSearchOpen(false);
    setIsMobileMenuOpen(false);
  };

  const handleSelectProduct = (product) => {
    navigate(`/products/${product.slug || product.id}`);
    closeSearch();
  };

  const handleSelectCategory = (category) => {
    navigate(`/products?category=${category.id}`);
    closeSearch();
  };

  const handleSubmitSearch = () => {
    if (searchQuery.trim()) {
      navigate(`/products?search=${encodeURIComponent(searchQuery.trim())}`);
    }
    closeSearch();
  };

  const handleNotificationClick = async (notification) => {
    if (!notification.is_read) {
      try {
        await notificationService.markAsRead(notification.id);
        setUnreadCount(prev => Math.max(0, prev - 1));
        setNotifications(prev =>
          prev.map(n => n.id === notification.id ? { ...n, is_read: true } : n)
        );
      } catch (error) {
        console.error('Failed to mark notification as read:', error);
      }
    }

    setIsNotificationOpen(false);
    setIsMobileMenuOpen(false);

    if (notification.link) {
      const link = notification.link.startsWith('/') || /^(https?:|mailto:|tel:|#|\?)/i.test(notification.link)
        ? notification.link
        : `/${notification.link}`;
      navigate(link);
      return;
    }

    switch (notification.type) {
      case 'order_placed':
      case 'order_cancelled':
      case 'order_status':
        navigate(notification.order_id ? `/orders/${notification.order_id}` : '/orders');
        break;
      case 'promotion':
        navigate('/products');
        break;
      default:
        navigate('/orders');
    }
  };

  const markAllAsRead = async () => {
    try {
      await notificationService.markAllAsRead();
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch (error) {
      console.error('Failed to mark all as read:', error);
    }
  };

  const handleDeleteNotification = async (notificationId) => {
    try {
      await notificationService.deleteNotification(notificationId);
      const removed = notifications.find(n => n.id === notificationId);
      setNotifications(prev => prev.filter(n => n.id !== notificationId));
      if (removed && !removed.is_read) {
        setUnreadCount(u => Math.max(0, u - 1));
      }
    } catch (error) {
      console.error('Failed to delete notification:', error);
    }
  };

  const navLinks = [
    { name: 'Home', path: '/' },
    { name: 'Catalog', path: '/products' },
    { name: 'Orders', path: '/orders' },
  ];

  const initials = user?.full_name?.charAt(0) || user?.username?.charAt(0) || 'U';

  return (
    <header className="fixed top-0 inset-x-0 z-50 border-b border-border transition-colors duration-700">
      {/* Blurred bar background lives on its own layer — never on <header> itself.
          backdrop-filter on an ancestor turns it into the containing block for
          fixed-position descendants, which shrank the mobile menu + notification
          dropdown to a cut-off sliver under the bar on mobile. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-background/70 backdrop-blur-2xl" />
      <div className="relative max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-20">
          
          {/* Logo */}
          <Link to="/" className="text-lg sm:text-2xl font-extrabold tracking-tighter text-foreground hover:opacity-70 transition-opacity flex-shrink-0">
            E-Shop.
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-8">
            {navLinks.map((link) => {
              const active = location.pathname === link.path;
              return (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`text-[11px] font-bold uppercase tracking-widest transition-all duration-300 ${
                    active
                      ? 'text-foreground border-b-2 border-primary py-1'
                      : 'text-muted-foreground hover:text-foreground py-1 border-b-2 border-transparent'
                  }`}
                >
                  {link.name}
                </Link>
              );
            })}
          </nav>

          {/* Right Icons Section */}
          <div className="flex items-center gap-1 sm:gap-3 text-foreground">
            
            {/* Search */}
            <div ref={searchRef} className="relative hidden md:block">
              <button
                onClick={() => setIsSearchOpen(!isSearchOpen)}
                className="w-10 h-10 rounded-full flex items-center justify-center hover:bg-primary-soft transition-colors hover:scale-105 active:scale-95"
                aria-label="Search"
              >
                <Search size={20} strokeWidth={2} />
              </button>

              {isSearchOpen && (
                <div className="absolute top-[120%] right-0 w-[300px] sm:w-[340px] p-2 bg-card border border-border rounded-3xl shadow-xl transform origin-top-right animate-[popUp_0.2s_ease-out]">
                  <form onSubmit={handleSearch}>
                    <input
                      ref={desktopSearchInputRef}
                      type="text"
                      placeholder="Search collection..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      autoFocus
                      className="w-full bg-primary-soft border-none rounded-2xl px-5 py-3 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all placeholder:text-muted-foreground outline-none"
                    />
                  </form>
                  <SearchSuggestions
                    query={searchQuery}
                    inputRef={desktopSearchInputRef}
                    onSelectProduct={handleSelectProduct}
                    onSelectCategory={handleSelectCategory}
                    onSearch={handleSubmitSearch}
                  />
                </div>
              )}
            </div>

            {/* Notifications */}
            {user && (
              <div ref={notificationRef} className="relative">
                <button
                  onClick={() => setIsNotificationOpen(!isNotificationOpen)}
                  className="relative w-10 h-10 rounded-full flex items-center justify-center hover:bg-primary-soft transition-colors hover:scale-105 active:scale-95"
                  aria-label="Notifications"
                >
                  <Bell size={20} strokeWidth={2} />
                  {unreadCount > 0 && (
                    <span className="absolute top-1.5 right-2 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-destructive ring-2 ring-background">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-destructive opacity-75"></span>
                    </span>
                  )}
                </button>

                {isNotificationOpen && (
                  <div className="fixed top-[84px] right-4 left-4 sm:absolute sm:top-[120%] sm:left-auto sm:right-0 sm:w-[340px] bg-card border border-border rounded-3xl shadow-xl transform origin-top-right animate-[popUp_0.2s_ease-out] overflow-hidden flex flex-col">
                    <div className="flex items-center justify-between p-5 border-b border-border bg-primary-soft/50">
                      <h3 className="text-xs font-bold uppercase tracking-widest text-foreground m-0">
                        Updates {unreadCount > 0 && <span className="text-muted-foreground">({unreadCount})</span>}
                      </h3>
                      {unreadCount > 0 && (
                        <button onClick={markAllAsRead} className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors">
                          Clear All
                        </button>
                      )}
                    </div>
                    
                    <div className="max-h-[min(350px,55vh)] overflow-y-auto custom-scrollbar">
                      {notifications.length === 0 ? (
                        <div className="py-12 text-center flex flex-col items-center">
                          <Bell size={32} strokeWidth={1} className="text-muted-foreground mb-3" />
                          <p className="text-sm font-medium text-muted-foreground">You're all caught up.</p>
                        </div>
                      ) : (
                        notifications.map((notification) => (
                          <div
                            key={notification.id}
                            onClick={() => handleNotificationClick(notification)}
                            className={`group relative p-5 border-b border-border cursor-pointer transition-colors ${notification.is_read ? 'hover:bg-primary-soft/50' : 'bg-primary-soft/30'}`}
                          >
                            <div className="flex items-start gap-3">
                              {!notification.is_read && <div className="w-1.5 h-1.5 rounded-full bg-success mt-2 shrink-0 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />}
                              <div className="flex-1 min-w-0 pr-4">
                                <p className={`text-sm truncate m-0 ${notification.is_read ? 'font-medium text-foreground/80' : 'font-bold text-foreground'}`}>
                                  {notification.title}
                                </p>
                                <p className="text-xs text-muted-foreground mt-1 line-clamp-2 leading-relaxed">
                                  {notification.message}
                                </p>
                                <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground mt-2">
                                  {notification.created_at ? new Date(notification.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}
                                </p>
                              </div>
                              <button
                                onClick={(e) => { e.stopPropagation(); handleDeleteNotification(notification.id); }}
                                className="absolute top-4 right-4 text-muted-foreground hover:text-destructive transition-colors opacity-100 sm:opacity-0 sm:group-hover:opacity-100"
                              >
                                <X size={14} strokeWidth={3} />
                              </button>
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                    {notifications.length > 0 && (
                      <Link
                        to="/notifications"
                        onClick={() => setIsNotificationOpen(false)}
                        className="block p-4 text-center text-xs font-bold uppercase tracking-widest text-foreground hover:bg-primary-soft transition-colors"
                      >
                        View Archive
                      </Link>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Wishlist */}
            <Link
              to="/wishlist"
              className="relative w-10 h-10 rounded-full flex items-center justify-center hover:bg-primary-soft transition-colors hover:scale-105 active:scale-95"
              aria-label="Wishlist"
            >
              <Heart size={20} strokeWidth={2} />
              {wishlistCount > 0 && (
                <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground shadow-sm ring-2 ring-background">
                  {wishlistCount > 99 ? '99+' : wishlistCount}
                </span>
              )}
            </Link>

            {/* Cart */}
            <Link
              to="/cart"
              className="relative w-10 h-10 rounded-full flex items-center justify-center hover:bg-primary-soft transition-colors hover:scale-105 active:scale-95 mr-1 sm:mr-2"
              aria-label="Cart"
            >
              <ShoppingBag size={20} strokeWidth={2} />
              {itemCount > 0 && (
                <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground shadow-sm ring-2 ring-background">
                  {itemCount > 99 ? '99+' : itemCount}
                </span>
              )}
            </Link>

            {/* User Menu */}
            <div ref={userMenuRef} className="relative hidden sm:block">
              {user ? (
                <>
                  <button
                    onClick={() => setIsUserMenuOpen(!isUserMenuOpen)}
                    className="flex items-center gap-2 pl-2 pr-4 py-1.5 rounded-full bg-primary-soft hover:bg-primary-soft transition-colors border border-border hover:scale-105 active:scale-95"
                  >
                    <span className="flex items-center justify-center w-7 h-7 rounded-full bg-primary text-primary-foreground text-xs font-bold uppercase shadow-sm">
                      {initials}
                    </span>
                    <span className="text-xs font-bold text-foreground max-w-[100px] truncate tracking-wide">
                      {user.full_name || user.username}
                    </span>
                  </button>

                  {isUserMenuOpen && (
                    <div className="absolute top-[130%] right-0 w-[240px] bg-card border border-border rounded-3xl shadow-xl transform origin-top-right animate-[popUp_0.2s_ease-out] overflow-hidden p-2 flex flex-col gap-1">
                      <div className="px-4 py-3 mb-1 bg-primary-soft/50 rounded-2xl">
                        <p className="text-sm font-bold text-foreground m-0 truncate">{user.full_name || user.username}</p>
                        <p className="text-xs font-medium text-muted-foreground m-0 truncate mt-0.5">{user.email}</p>
                      </div>
                      <Link to="/profile" onClick={() => setIsUserMenuOpen(false)} className="px-4 py-2.5 text-sm font-medium text-foreground/80 rounded-xl hover:bg-primary-soft transition-colors">Profile</Link>
                      <Link to="/orders" onClick={() => setIsUserMenuOpen(false)} className="px-4 py-2.5 text-sm font-medium text-foreground/80 rounded-xl hover:bg-primary-soft transition-colors">Order History</Link>
                      <Link to="/settings" onClick={() => setIsUserMenuOpen(false)} className="px-4 py-2.5 text-sm font-medium text-foreground/80 rounded-xl hover:bg-primary-soft transition-colors">Settings</Link>
                      <div className="h-px bg-border my-1 mx-2" />
                      <button onClick={handleLogout} className="text-left px-4 py-2.5 text-sm font-bold text-destructive rounded-xl hover:bg-destructive-soft transition-colors">Sign Out</button>
                    </div>
                  )}
                </>
              ) : (
                <div className="flex items-center gap-3">
                  <Link
                    to="/login"
                    className="inline-flex items-center h-10 px-5 rounded-full bg-primary-soft border border-border text-xs font-bold uppercase tracking-widest text-foreground hover:bg-primary-soft hover:scale-105 active:scale-95 transition-all"
                  >
                    Sign In
                  </Link>
                </div>
              )}
            </div>

            {/* Mobile Menu Button */}
            <button
              onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
              className="md:hidden w-10 h-10 rounded-full flex items-center justify-center hover:bg-primary-soft transition-colors"
              aria-label="Toggle menu"
            >
              {isMobileMenuOpen ? <X size={24} strokeWidth={2} /> : <Menu size={24} strokeWidth={2} />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile menu sheet — fixed to the viewport, opening below the 80px bar.
          Keep it viewport-fixed: never put backdrop-blur/filter/transform on
          <header>, or this collapses into a sliver again. */}
      <div className={`md:hidden fixed inset-x-0 top-20 bottom-0 z-40 bg-background transition-all duration-500 ease-[cubic-bezier(0.4,0,0.2,1)] ${isMobileMenuOpen ? 'opacity-100 visible translate-y-0' : 'opacity-0 invisible -translate-y-4 pointer-events-none'}`}>
        <div className="flex flex-col h-full overflow-y-auto p-6 space-y-8">
          
          {/* Mobile Search */}
          <form onSubmit={handleSearch}>
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" size={18} strokeWidth={2} />
              <input
                ref={mobileSearchInputRef}
                type="text"
                placeholder="Search products…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-primary-soft border-none rounded-2xl pl-12 pr-4 py-4 text-sm text-foreground font-medium focus:ring-2 focus:ring-primary transition-all outline-none"
              />
            </div>
          </form>
          <SearchSuggestions
            query={searchQuery}
            inputRef={mobileSearchInputRef}
            onSelectProduct={handleSelectProduct}
            onSelectCategory={handleSelectCategory}
            onSearch={handleSubmitSearch}
          />

          {/* Mobile Navigation */}
          <nav className="flex flex-col space-y-2">
            {navLinks.map((link) => (
              <Link
                key={link.path}
                to={link.path}
                className="text-2xl font-extrabold tracking-tight text-foreground py-3 border-b border-border"
              >
                {link.name}
              </Link>
            ))}
          </nav>

          <div className="mt-auto pt-8 border-t border-border">
            {user ? (
              <div className="flex flex-col gap-4">
                <div className="flex items-center gap-4 p-4 bg-primary-soft rounded-3xl">
                  <div className="w-12 h-12 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-lg font-bold uppercase shadow-md">
                    {initials}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-base font-bold text-foreground truncate">{user.full_name || user.username}</p>
                    <p className="text-xs font-medium text-muted-foreground truncate mt-1">{user.email}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Link to="/profile" className="p-3 text-center rounded-2xl bg-primary-soft text-sm font-bold text-foreground">Profile</Link>
                  <Link to="/settings" className="p-3 text-center rounded-2xl bg-primary-soft text-sm font-bold text-foreground">Settings</Link>
                </div>
                <button onClick={handleLogout} className="w-full py-4 text-center rounded-2xl bg-destructive-soft text-sm font-bold text-destructive mt-2">
                  Sign Out
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <Link to="/login" className="w-full py-4 text-center rounded-2xl bg-primary-soft text-sm font-bold uppercase tracking-widest text-foreground">Sign In</Link>
                <Link to="/register" className="w-full py-4 text-center rounded-2xl bg-primary text-primary-foreground text-sm font-bold uppercase tracking-widest shadow-xl">Create Account</Link>
              </div>
            )}
          </div>
        </div>
      </div>

    </header>
  );
};

export default Header;
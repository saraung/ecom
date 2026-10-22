// src/components/layout/Sidebar.jsx
import React, { useEffect, useRef, useState } from 'react';
import { NavLink, useNavigate, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Package,
  ShoppingBag,
  Users,
  Tag,
  BarChart3,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
  FolderTree,
  Megaphone,
  Truck,
  Banknote,
  RefreshCw,
  ScrollText,
  MailPlus,
  Star,
  SlidersHorizontal,
  Images,
  X,
  Bot
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { canDo } from '../../utils/permissions';
import { hasReturnPermission } from '../../utils/returns';
import { ShieldCheck } from 'lucide-react';
import eLogo from '../../assets/elogo.png';

const Sidebar = ({ isOpen, setIsOpen }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { logout, user } = useAuth();
  const navRef = useRef(null);

  // Auto-close the drawer on navigation (mobile only — desktop keeps its
  // collapsed/expanded state across route changes).
  useEffect(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      setIsOpen(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const closeOnMobileNav = () => {
    if (typeof window !== 'undefined' && window.innerWidth < 1024) {
      setIsOpen(false);
    }
  };

  const menuItems = [
    {
      path: '/',
      icon: LayoutDashboard,
      label: 'Dashboard',
      minRole: 'manager', // 👈 legacy fallback
      perm: 'dashboard.view',
      group: 'Overview',
    },
    {
      path: '/products',
      icon: Package,
      label: 'Products',
      minRole: 'staff',
      perm: 'products.view',
      group: 'Catalog',
    },
    {
      path: '/categories',
      icon: FolderTree,
      label: 'Categories',
      minRole: 'manager',
      perm: 'categories.view',
      group: 'Catalog',
    },
    {
      path: '/content',
      icon: Images,
      label: 'Banners',
      minRole: 'manager',
      perm: 'content.manage',
      group: 'Catalog',
    },
    {
      path: '/reviews',
      icon: Star,
      label: 'Reviews',
      minRole: 'admin',
      perm: 'reviews.moderate',
      group: 'Catalog',
    },
    {
      path: '/orders',
      icon: ShoppingBag,
      label: 'Orders',
      minRole: 'manager',
      perm: 'orders.view',
      group: 'Sales',
    },
    ...(hasReturnPermission(user, 'orders.view') ? [{ path: '/returns', icon: Package, label: 'Product Returns', minRole: 'manager', perm: 'orders.view', group: 'Sales' }] : []),
    {
      path: '/refunds',
      icon: RefreshCw,
      label: 'Refunds',
      minRole: 'manager',
      perm: 'orders.refund',
      group: 'Sales',
    },
    {
      path: '/cod',
      icon: Banknote,
      label: 'COD Reconciliation',
      minRole: 'manager',
      perm: 'cod.view',
      group: 'Sales',
    },
    {
      path: '/shipping-simulator',
      icon: Truck,
      label: 'Shiprocket Simulator',
      minRole: 'manager',
      perm: 'shipping.manage',
      group: 'Sales',
    },
    {
      path: '/users',
      icon: Users,
      label: 'Users',
      minRole: 'admin',
      perm: 'users.view',
      group: 'Customers',
    },
    {
      path: '/coupons',
      icon: Tag,
      label: 'Coupons',
      minRole: 'manager',
      perm: 'coupons.view',
      group: 'Marketing',
    },
    {
      path: '/promotions',
      icon: Megaphone,
      label: 'Promotions',
      minRole: 'manager',
      perm: 'promotions.send',
      group: 'Marketing',
    },
    {
      path: '/roles',
      icon: ShieldCheck,
      label: 'Roles',
      minRole: 'admin',
      perm: 'roles.manage',
      group: 'Administration',
    },
    {
      path: '/invites',
      icon: MailPlus,
      label: 'Invites',
      minRole: 'admin',
      perm: 'users.manage_roles',
      group: 'Administration',
    },
    {
      path: '/audit-log',
      icon: ScrollText,
      label: 'Audit Log',
      minRole: 'manager',
      perm: 'reports.view',
      group: 'Administration',
    },
    {
      path: '/reports',
      icon: BarChart3,
      label: 'Reports',
      minRole: 'manager',
      perm: 'reports.view',
      group: 'Administration',
    },
    {
      path: '/store-settings',
      icon: SlidersHorizontal,
      label: 'Store Settings',
      minRole: 'admin',
      perm: 'settings.manage',
      group: 'Administration',
    },
    {
      path: '/mcp-agent',
      icon: Bot,
      label: 'MCP Agent',
      group: 'Administration',
      // No perm/minRole: UI-preview page, session-gated like Settings.
      // Every signed-in user sees it; no new auth system.
    },
    {
      path: '/settings',
      icon: Settings,
      label: 'Settings',
      group: 'Administration',
      // No perm/minRole: self-profile page, every signed-in user has one.
    },
  ];

  const visibleMenuItems = menuItems.filter(item => {
    if (!item.perm && !item.minRole) return true;
    return canDo(user, item.perm, item.minRole || 'admin');
  });

  // Group consecutive visible items by their section. Permission filtering
  // runs first, so groups with zero visible items never render a heading.
  const visibleGroups = [];
  for (const item of visibleMenuItems) {
    const name = item.group || 'Other';
    const last = visibleGroups[visibleGroups.length - 1];
    if (last && last.name === name) {
      last.items.push(item);
    } else {
      visibleGroups.push({ name, items: [item] });
    }
  }

  // Figma-standard scrollable nav: comfortable fixed sizes, the list
  // scrolls independently while brand + logout stay pinned. On every
  // route change the active tab scrolls into view (nearest, no page jump).
  // A bottom fade hints that more tabs (e.g. Settings) sit below the fold.
  const [showMoreBelow, setShowMoreBelow] = useState(false);
  const updateMoreBelow = () => {
    const nav = navRef.current;
    if (!nav) return;
    setShowMoreBelow(nav.scrollHeight - nav.scrollTop - nav.clientHeight > 8);
  };
  useEffect(() => {
    const nav = navRef.current;
    if (!nav) return;
    const active = nav.querySelector('[aria-current="page"]');
    active?.scrollIntoView({ block: 'nearest' });
    updateMoreBelow();
    const observer = new ResizeObserver(updateMoreBelow);
    observer.observe(nav);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, visibleMenuItems.length, visibleGroups.length, isOpen]);

  const tabFontSize = 14;
  const tabPadY = 8;
  const tabIconSize = 18;
  // Section headings: compact muted labels.
  const groupFontSize = 11;
  const groupPadY = 4;

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <div className={`
      fixed inset-y-0 left-0 z-40 w-64
      ${isOpen ? 'translate-x-0' : '-translate-x-full'}
      lg:translate-x-0 lg:static
      ${isOpen ? 'lg:w-64' : 'lg:w-20'}
      bg-card border-r border-border transition-all duration-300
      flex flex-col flex-shrink-0
    `}>
      <div className="h-16 flex items-center justify-between px-4 border-b border-border shrink-0">
        {isOpen ? (
          <button
            type="button"
            onClick={() => { navigate('/'); closeOnMobileNav(); }}
            title="Go to home"
            className="flex items-center gap-2 min-w-0 rounded-lg hover:opacity-80 transition-opacity text-left"
          >
            <img src={eLogo} alt="E-shop logo" className="h-9 w-9 object-contain flex-shrink-0" />
            <div className="flex flex-col leading-tight min-w-0">
              <span className="text-xl font-bold text-primary truncate">E-shop</span>
              <span className="text-[11px] font-medium text-muted-foreground truncate">Admin Dashboard</span>
            </div>
          </button>
        ) : (
          <button
            type="button"
            onClick={() => { navigate('/'); closeOnMobileNav(); }}
            title="Go to home"
            className="rounded-lg hover:opacity-80 transition-opacity"
          >
            <img src={eLogo} alt="E-shop logo" className="h-8 w-8 object-contain flex-shrink-0" />
          </button>
        )}
        <div className="flex items-center gap-1 shrink-0">
          {/* Explicit close affordance on mobile (drawer mode) */}
          <button
            onClick={() => setIsOpen(false)}
            className="lg:hidden p-1.5 -mr-1 text-muted-foreground hover:text-foreground rounded-lg hover:bg-muted"
            aria-label="Close menu"
          >
            <X size={20} />
          </button>
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="hidden lg:block p-1 text-muted-foreground hover:text-foreground"
            aria-label={isOpen ? 'Collapse sidebar' : 'Expand sidebar'}
          >
            {isOpen ? <ChevronLeft size={20} /> : <ChevronRight size={20} />}
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 relative">
      <nav
        ref={navRef}
        onScroll={updateMoreBelow}
        className="absolute inset-0 overflow-y-auto overscroll-contain py-2"
        aria-label="Admin sections"
      >
        {visibleGroups.map((group, gi) => (
          <div key={group.name}>
            {isOpen && (
              <p
                className="px-4 mx-2 text-muted-foreground uppercase tracking-wider font-semibold truncate"
                style={{
                  fontSize: groupFontSize,
                  paddingTop: groupPadY,
                  paddingBottom: 3,
                  marginTop: gi === 0 ? 0 : 6,
                }}
              >
                {group.name}
              </p>
            )}
            {group.items.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={closeOnMobileNav}
                style={{ fontSize: tabFontSize, paddingTop: tabPadY, paddingBottom: tabPadY }}
                className={({ isActive }) =>
                  `flex items-center px-4 mx-2 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-primary-soft text-primary'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`
                }
              >
                <item.icon size={tabIconSize} className="shrink-0" />
                {isOpen && <span className="truncate ml-3">{item.label}</span>}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      {showMoreBelow && (
        <div
          aria-hidden="true"
          className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-card to-transparent pointer-events-none"
        />
      )}
      </div>

      <div className="border-t border-border p-4">
        <button 
          onClick={handleLogout}
          className="flex items-center px-4 py-2.5 w-full rounded-lg text-[15px] text-destructive hover:bg-destructive/10 transition-colors"
        >
          <LogOut size={19} className="shrink-0" />
          {isOpen && <span className="ml-3">Logout</span>}
        </button>
      </div>
    </div>
  );
};

export default Sidebar;

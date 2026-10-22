// src/utils/permissions.js

/**
 * Role hierarchy levels (legacy fallback).
 * Higher number = more permissions.
 *
 * The backend is now the source of truth: /auth/me returns `permissions`
 * (e.g. "orders.view") from the dynamic role grants. The helpers below
 * prefer the permission list when available and fall back to the legacy
 * role string for old sessions / pre-RBAC backends.
 */
export const ROLE_LEVELS = {
  customer: 0,
  staff: 1,
  manager: 2,
  admin: 3,
};

/**
 * Check if user has at least the minimum required role
 * @param {string} userRole - The user's current role
 * @param {string} minRole - The minimum role required (e.g., 'staff', 'manager', 'admin')
 * @returns {boolean}
 */
export const hasMinRole = (userRole, minRole) => {
  if (!userRole) return false;
  const userLevel = ROLE_LEVELS[userRole] ?? -1;
  const requiredLevel = ROLE_LEVELS[minRole] ?? -1;
  return userLevel >= requiredLevel;
};

/**
 * Check if the user (object with `permissions`, or raw array) holds a
 * dynamic permission key. Returns null when no permission list is
 * available so callers can fall back to legacy role checks.
 * @param {object|string[]} userOrPerms
 * @param {string} key - e.g. 'orders.view'
 * @returns {boolean|null}
 */
export const hasPerm = (userOrPerms, key) => {
  const perms = Array.isArray(userOrPerms)
    ? userOrPerms
    : userOrPerms?.permissions;
  if (!Array.isArray(perms) || perms.length === 0) return null;
  return perms.includes(key);
};

/**
 * Preferred gate: permission key when the session carries permissions,
 * otherwise the legacy minimum-role equivalent.
 * @param {object} user - full user object ({ role, permissions })
 * @param {string} key - permission key, e.g. 'orders.view'
 * @param {string} legacyMinRole - fallback role floor, e.g. 'manager'
 * @returns {boolean}
 */
export const can = (user, key, legacyMinRole) => {
  const result = hasPerm(user, key);
  if (result !== null) return result;
  return hasMinRole(user?.role, legacyMinRole);
};

/**
 * Check if user has exactly a specific role
 * @param {string} userRole - The user's current role
 * @param {string} role - The role to check
 * @returns {boolean}
 */
export const hasRole = (userRole, role) => {
  return userRole === role;
};

/**
 * Check if user is admin
 * @param {string} userRole - The user's current role
 * @returns {boolean}
 */
export const isAdmin = (userRole) => userRole === 'admin';

/**
 * Check if user is manager or above (manager or admin)
 * @param {string} userRole - The user's current role
 * @returns {boolean}
 */
export const isManagerOrAbove = (userRole) => {
  return hasMinRole(userRole, 'manager');
};

/**
 * Check if user is staff or above (staff, manager, or admin)
 * @param {string} userRole - The user's current role
 * @returns {boolean}
 */
export const isStaffOrAbove = (userRole) => {
  return hasMinRole(userRole, 'staff');
};

/**
 * Check if user is customer only (not staff/manager/admin)
 * @param {string} userRole - The user's current role
 * @returns {boolean}
 */
export const isCustomerOnly = (userRole) => {
  return userRole === 'customer';
};

/**
 * Legacy role floor per permission key — used ONLY when the session has no
 * permission list (old backend / cached session). Mirrors the pre-RBAC
 * `minRole` guards in AppRoutes.
 */
export const PERMISSION_LEGACY_FLOOR = {
  'dashboard.view': 'manager',
  'reports.view': 'manager',
  'products.view': 'staff',
  'products.create': 'staff',
  'products.update': 'staff',
  'products.delete': 'admin',
  'products.export': 'admin',
  'product_images.manage': 'staff',
  'categories.view': 'staff',
  'categories.manage': 'manager',
  'orders.view': 'manager',
  'orders.update': 'manager',
  'orders.refund': 'manager',
  'shipping.manage': 'manager',
  'cod.view': 'manager',
  'cod.reconcile': 'manager',
  'coupons.view': 'manager',
  'coupons.manage': 'manager',
  'promotions.send': 'manager',
  'users.view': 'admin',
  'users.manage': 'admin',
  'users.manage_roles': 'admin',
  'roles.manage': 'admin',
  'reviews.moderate': 'manager',
  'payments.view': 'manager',
  'notifications.manage': 'manager',
  'settings.manage': 'admin',
};

/**
 * Single-call gate for components: permission key when available,
 * legacy role floor otherwise.
 * @param {object} user - full user object ({ role, permissions })
 * @param {string} key - permission key
 * @param {string} [fallbackRole] - explicit legacy floor for this call site
 *   (e.g. the route's minRole). Defaults to PERMISSION_LEGACY_FLOOR.
 * @returns {boolean}
 */
export const canDo = (user, key, fallbackRole) => {
  const result = hasPerm(user, key);
  if (result !== null) return result;
  return hasMinRole(user?.role, fallbackRole || PERMISSION_LEGACY_FLOOR[key] || 'admin');
};

/**
 * Highest-privilege legacy role slug among `slugs`. Mirrors the backend's
 * `set_user_roles` so the single `role` field never downgrades when a
 * read-only role (e.g. `customer`) is stacked on top of `manager`.
 * @param {string[]} slugs
 * @returns {string|undefined}
 */
export const highestLegacyRole = (slugs) => {
  if (!Array.isArray(slugs) || slugs.length === 0) return undefined;
  return slugs.reduce((best, slug) =>
    (ROLE_LEVELS[slug] ?? -1) > (ROLE_LEVELS[best] ?? -1) ? slug : best
  );
};

/**
 * Human-readable module labels for the Roles builder UI.
 */
export const PERMISSION_MODULE_LABELS = {
  dashboard: 'Dashboard',
  reports: 'Reports',
  products: 'Products',
  categories: 'Categories',
  orders: 'Orders',
  shipping: 'Shipping',
  cod: 'COD Reconciliation',
  coupons: 'Coupons',
  promotions: 'Promotions',
  users: 'Users',
  roles: 'Roles & Permissions',
  reviews: 'Reviews',
  payments: 'Payments',
  notifications: 'Notifications',
  settings: 'Settings',
};

/**
 * Ordered sidebar tabs with their permission keys and legacy floors.
 * Mirrors Sidebar.jsx menu order + AppRoutes guards. Used by
 * firstAllowedPath() so redirects/landing pages agree with the tab list
 * for every role — including custom slugs no role-string check can name.
 * `key: null` = visible to every authenticated user (self-profile page).
 */
export const ORDERED_TABS = [
  { path: '/', key: 'dashboard.view', fallback: 'manager' },
  { path: '/products', key: 'products.view', fallback: 'staff' },
  { path: '/categories', key: 'categories.view', fallback: 'manager' },
  { path: '/orders', key: 'orders.view', fallback: 'manager' },
  { path: '/returns', key: 'orders.view', fallback: 'manager' },
  { path: '/shipping-simulator', key: 'shipping.manage', fallback: 'manager' },
  { path: '/users', key: 'users.view', fallback: 'admin' },
  { path: '/roles', key: 'roles.manage', fallback: 'admin' },
  { path: '/coupons', key: 'coupons.view', fallback: 'manager' },
  { path: '/promotions', key: 'promotions.send', fallback: 'manager' },
  { path: '/refunds', key: 'orders.refund', fallback: 'manager' },
  { path: '/cod', key: 'cod.view', fallback: 'manager' },
  { path: '/audit-log', key: 'reports.view', fallback: 'manager' },
  { path: '/invites', key: 'users.manage_roles', fallback: 'admin' },
  { path: '/reviews', key: 'reviews.moderate', fallback: 'admin' },
  { path: '/store-settings', key: 'settings.manage', fallback: 'admin' },
  { path: '/content', key: 'content.manage', fallback: 'manager' },
  { path: '/reports', key: 'reports.view', fallback: 'manager' },
  { path: '/settings', key: null, fallback: null },
];

/**
 * First tab the user may open (sidebar order). Falls through to the
 * self-profile Settings page, which every session can reach.
 * @param {object} user - full user object ({ role, permissions })
 * @returns {string} path
 */
export const firstAllowedPath = (user) => {
  for (const tab of ORDERED_TABS) {
    if (!tab.key || canDo(user, tab.key, tab.fallback)) return tab.path;
  }
  return '/unauthorized';
};

/**
 * Group a flat permission list [{key,label,module}] by module for the UI.
 * @param {Array} permissions
 * @returns {Array<{module:string,label:string,items:Array}>}
 */
export const groupPermissionsByModule = (permissions = []) => {
  const groups = {};
  for (const perm of permissions) {
    const module = perm.module || 'other';
    if (!groups[module]) groups[module] = [];
    groups[module].push(perm);
  }
  return Object.entries(groups)
    .map(([module, items]) => ({
      module,
      label: PERMISSION_MODULE_LABELS[module] || module,
      items: items.sort((a, b) => a.key.localeCompare(b.key)),
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
};

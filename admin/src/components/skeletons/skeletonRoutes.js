// src/components/skeletons/skeletonRoutes.js
// Central route → skeleton map shared by AdminLayout (chunk-load fallback)
// and RoleBasedRoute (no-cache auth wait). Props carry per-route titles
// (form titles differ between create/edit for the same skeleton type).
export const SKELETON_BY_ROUTE = [
  { test: /^\/$/, type: 'dashboard' },                              // Dashboard
  { test: /^\/products\/new$/, type: 'product-form', props: { title: 'Create New Product', mode: 'create' } },
  { test: /^\/products\/.+\/edit$/, type: 'product-form', props: { title: 'Edit Product', mode: 'edit' } },
  { test: /^\/products\/.+$/, type: 'product-detail' },              // ProductDetail
  { test: /^\/products/, type: 'products' },                         // ProductList
  { test: /^\/categories\/new$/, type: 'category-form', props: { title: 'Create New Category' } },
  { test: /^\/categories\/.+\/edit$/, type: 'category-form', props: { title: 'Edit Category' } },
  { test: /^\/categories\/.+\/products/, type: 'category-products' },// CategoryProducts
  { test: /^\/categories/, type: 'categories' },                     // CategoryList
  { test: /^\/orders\/.+$/, type: 'order-detail' },                  // OrderDetail
  { test: /^\/orders/, type: 'orders' },                             // OrderList
  { test: /^\/returns\/.+$/, type: 'return-detail' },               // ReturnDetail
  { test: /^\/returns/, type: 'returns' },                           // ReturnList
  { test: /^\/users\/.+$/, type: 'user-detail' },                    // UserDetail
  { test: /^\/users/, type: 'users' },                               // UserList
  { test: /^\/roles\/new$/, type: 'role-form', props: { title: 'Create New Role' } },
  { test: /^\/roles\/.+\/edit$/, type: 'role-form', props: { title: 'Edit Role' } },
  { test: /^\/roles/, type: 'roles' },                               // RoleList
  { test: /^\/coupons\/new$/, type: 'coupon-form', props: { title: 'Create New Coupon', submitLabel: 'Create Coupon', mode: 'create' } },
  { test: /^\/coupons\/.+\/edit$/, type: 'coupon-form', props: { title: 'Edit Coupon', submitLabel: 'Update Coupon', mode: 'edit' } },
  { test: /^\/coupons/, type: 'coupons' },                           // CouponList
  { test: /^\/reports/, type: 'reports' },                           // Reports
  { test: /^\/settings/, type: 'settings' },                         // Settings
  { test: /^\/promotions/, type: 'promotions' },                     // Promotions
  { test: /^\/refunds/, type: 'refunds' },                           // Refunds
  { test: /^\/cod\/import$/, type: 'cod-import' },                    // COD CSV import
  { test: /^\/cod\/new$/, type: 'cod-manual' },                       // COD manual batch
  { test: /^\/cod\/.+$/, type: 'cod-detail' },                         // COD remittance detail
  { test: /^\/cod/, type: 'cod' },                                    // COD reconciliation
  { test: /^\/audit-log/, type: 'audit-log' },                       // AuditLog
  { test: /^\/invites/, type: 'invites' },                           // Invites
  { test: /^\/reviews/, type: 'reviews' },                             // Reviews
  { test: /^\/store-settings/, type: 'store-settings' },              // StoreSettings
  { test: /^\/content\/new$/, type: 'content-form', props: { title: 'New Banner' } },
  { test: /^\/content\/.+\/edit$/, type: 'content-form', props: { title: 'Edit Banner' } },
  { test: /^\/content/, type: 'banners' },                            // Content (Banners list)
  { test: /^\/shipping-simulator/, type: 'shipping-simulator' },     // ShiprocketSimulator
  { test: /^\/mcp-agent/, type: 'mcp-agent' },                             // McpAgent
];

export const skeletonForPath = (pathname) => {
  const match = SKELETON_BY_ROUTE.find((r) => r.test.test(pathname || ''));
  return match || { type: 'products', props: {} };
};

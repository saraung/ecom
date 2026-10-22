# Admin Dashboard

> React 19 + Vite 8 operations console for staff.
> Directory: `admin/` · Dev port: **3001** · API: `/api/v1`

---

## 1. Overview

The admin app is where staff run the store: catalog, inventory, orders,
fulfilment, refunds, returns, COD reconciliation, customers, promotions, content,
roles and reporting.

Its defining characteristic is **defence in depth on authorization**: every route
is gated twice, the sidebar hides what the session cannot use, and the backend
re-checks permissions on every request. The UI is a convenience layer, never the
security boundary.

| Property | Value |
|---|---|
| Entry | `src/main.jsx` → `src/App.jsx` → `src/routes/AppRoutes.jsx` |
| Route loading | `React.lazy` for every page except `Login` |
| Styling | Tailwind 4 + CSS variables |
| Data | axios + `useState`/`useEffect` (React Query is configured but not yet used by pages) |
| Auth | JWT with **admin audience** + email OTP step-up |
| Real time | `NotificationsContext` (bell + toasts) |
| Documents | jsPDF + autotable, `react-to-print` for invoice/packing slip |
| Charts | Recharts 3 |

---

## 2. Structure

```
admin/src/
├── App.jsx                     Theme → QueryClient → Auth → Notifications
├── api/                        20 modules (client.js configures @ecom/shared)
├── components/
│   ├── auth/                   BrandPanel, OtpChallenge
│   ├── cards/                  StatCard, InfoCard
│   ├── charts/                 Revenue, SalesTrend, OrderStatus,
│   │                           TopProducts, SalesByCategory
│   ├── cod/                    CodShared
│   ├── common/                 ImageLightbox
│   ├── invoice/                OrderInvoice, PackingSlip
│   ├── layout/                 AdminLayout, Header, Sidebar, NotificationBell
│   ├── orders/                 AdminCancelDialog, RefundDialog, FulfilmentStage,
│   │                           ShiprocketDispatchModal, TrackingModal
│   ├── returns/                ReturnEvidence
│   ├── skeletons/              one per page + skeletonRoutes.js mapping
│   └── ui/                     ConfirmDialog, PageLoader, PageSkeleton, Skeleton
├── context/                    AuthContext, NotificationsContext, ThemeContext
├── pages/                      23 feature folders
├── routes/AppRoutes.jsx
└── utils/                      permissions, returns, format (→ @ecom/shared), reportLoader
```

---

## 3. Authentication and Session

### 3.1 Sign-in

`pages/Login/Login.jsx` → `context/AuthContext.jsx`.

1. `POST /auth/login` with `audience: "admin"` (default).
2. If the account is privileged, the API returns
   `{otp_required, challenge_token, email_masked}` and the UI swaps to
   `components/auth/OtpChallenge.jsx`.
3. `POST /auth/login/verify-otp` exchanges the challenge + emailed code for
   tokens.
4. `POST /auth/login/resend-otp` is rate-limited with a 60-second cooldown shown
   in the UI.
5. Google sign-in (`POST /auth/google`) follows the same challenge path for
   privileged accounts.

Tokens and the cached user live in `localStorage`:

| Key | Content |
|---|---|
| `access_token` | JWT (admin audience) |
| `refresh_token` | Opaque, rotated on use |
| `user` | Cached profile incl. `role` and `permissions[]` |

The cached profile is hydrated **synchronously** on boot so the sidebar and
header render with the right shape immediately; `fetchUser()` then refreshes it
in the background. A network failure keeps the cache (no spurious logout); a
401/403 clears everything and redirects to `/login`.

### 3.2 Refresh

`api/client.js` configures `createSession()` from `@ecom/shared/session` and
`createApiClient()` from `@ecom/shared/http`; the implementation is **shared
with the storefront**. It performs **single-flight refresh**: all concurrent
401s await one `/auth/refresh` call and then retry with the token it produced.
Without this, N simultaneous 401s would rotate the refresh token N times and
revoke the session.

Admin-specific options: redirect to `/login?reason=session_expired` with
`location.replace`, a re-entry guard, and clearing the cached `user` key.

`API_BASE_URL` comes from `VITE_API_URL` (default
`http://localhost:8001/api/v1`). There is no Vite proxy: the admin talks to the
backend origin directly, so `CORS_ORIGINS` must include
`http://localhost:3001`.

### 3.3 Logout

`POST /auth/logout` with the refresh token, then clear storage. The backend
revokes the session id, which invalidates outstanding access tokens too.

---

## 4. Authorization

Three cooperating layers, all derived from the same permission catalog.

### 4.1 Layer 1 — route guard (`RoleBasedRoute`)

```jsx
<RoleBasedRoute minRole="manager" requirePerm="orders.view">
  <OrderList />
</RoleBasedRoute>
```

- Waits only when there is **no** cached user (avoids an auth skeleton on every
  refresh); otherwise renders from cache.
- Unauthenticated → `/login`.
- Visiting `/` without `dashboard.view` → redirect to `firstAllowedPath(user)`.
- Fails the permission check → `/unauthorized`.

### 4.2 Layer 2 — navigation (`Sidebar.jsx`)

`menuItems` carry both `minRole` (legacy fallback) and `perm` (preferred key).
Items are filtered with `canDo(user, perm, minRole)`, and empty groups render no
heading. Groups, in order:

| Group | Tabs |
|---|---|
| Overview | Dashboard |
| Catalog | Products, Categories, Banners, Reviews |
| Sales | Orders, Product Returns, Refunds, COD Reconciliation, Shiprocket Simulator |
| Customers | Users |
| Marketing | Coupons, Promotions |
| Administration | Roles, Invites, Audit Log, Reports, Store Settings, MCP Agent, Settings |

### 4.3 Layer 3 — backend

Every admin endpoint uses `require_perm(...)`. Even if a user guesses a URL or
tampers with the client, the API returns `403`. See `backend-api.md` §2.7.

### 4.4 Permission resolution

`utils/permissions.js`:

```js
hasPerm(user, key)   // true/false, or null when the session has no list
canDo(user, key, fallbackRole)
                     // permission list when present, else legacy role floor
```

`PERMISSION_LEGACY_FLOOR` maps every key to a minimum legacy role so pre-RBAC
sessions still behave. `ORDERED_TABS` mirrors the sidebar and is used by
`firstAllowedPath()`, guaranteeing the landing page and the visible tabs can
never disagree.

`highestLegacyRole(slugs)` mirrors the backend's role-collapse rule: stacking a
read-only role onto `manager` must not downgrade the single legacy `role` field.

---

## 5. Route Map and Gates

| Path | Page | Gate (perm · legacy floor) |
|---|---|---|
| `/login` | Login | public |
| `/accept-invite` | AcceptInvite | public (emailed link) |
| `/unauthorized` | Unauthorized | public |
| `/` | Dashboard | `dashboard.view` · manager |
| `/products` | ProductList | `products.view` · staff |
| `/products/new` | ProductForm | `products.create` · staff |
| `/products/:slug` | ProductDetail | `products.view` · staff |
| `/products/:slug/edit` | ProductForm | `products.update` · staff |
| `/categories` | CategoryList | `categories.view` · manager |
| `/categories/new`, `/:id/edit` | CategoryForm | `categories.manage` · manager |
| `/categories/:categoryId/products` | CategoryProducts | `categories.view` · manager |
| `/orders` | OrderList | `orders.view` · manager |
| `/orders/:id` | OrderDetail | `orders.view` · manager |
| `/returns`, `/returns/:id` | ReturnList / ReturnDetail | `orders.view` · manager |
| `/users`, `/users/:id` | UserList / UserDetail | `users.view` · admin |
| `/roles`, `/roles/new`, `/:id/edit` | RoleList / RoleForm | `roles.manage` · admin |
| `/coupons`, `/new`, `/:id/edit` | CouponList / CouponForm | `coupons.view` / `coupons.manage` · manager |
| `/promotions` | Promotions | `promotions.send` · manager |
| `/reports` | Reports | `reports.view` · manager |
| `/refunds` | Refunds | `orders.refund` · manager |
| `/cod` | CodReconciliation | `cod.view` · manager |
| `/cod/import` | CodImport | `cod.reconcile` · manager |
| `/cod/new` | CodManualBatch | `cod.reconcile` · manager |
| `/cod/:id` | CodRemittanceDetail | `cod.view` · manager |
| `/audit-log` | AuditLog | `reports.view` · manager |
| `/invites` | Invites | `users.manage_roles` · admin |
| `/reviews` | Reviews | `reviews.moderate` · admin |
| `/store-settings` | StoreSettings | `settings.manage` · admin |
| `/content`, `/new`, `/:id/edit` | Content / ContentForm | `content.manage` · manager |
| `/shipping-simulator` | ShiprocketSimulator | `shipping.manage` · manager |
| `/mcp-agent` | McpAgent | any authenticated session |
| `/settings` | Settings | any authenticated session (self-profile) |

Every page is wrapped in `ErrorBoundary` and rendered under `AdminLayout`, which
owns the auth gate — so the sidebar and header stay mounted while a lazy chunk
loads. A route-matched skeleton (`skeletonForPath`) prevents layout shift.

---

## 6. Permission Catalog

30 keys, seeded from `backend/app/core/rbac_catalog.py`, grouped by module:

| Module | Keys |
|---|---|
| Dashboard | `dashboard.view` |
| Reports | `reports.view` |
| Products | `products.view`, `.create`, `.update`, `.delete`, `.export`, `.manage_prices`, `product_images.manage` |
| Inventory | `inventory.adjust` |
| Categories | `categories.view`, `categories.manage` |
| Orders | `orders.view`, `.update`, `.refund` |
| Shipping | `shipping.manage` |
| COD | `cod.view`, `cod.reconcile` |
| Coupons | `coupons.view`, `coupons.manage` |
| Promotions | `promotions.send` |
| Users | `users.view`, `users.manage`, `users.manage_roles` |
| Roles | `roles.manage` |
| Reviews | `reviews.moderate` |
| Content | `content.manage` |
| Payments | `payments.view` (reserved) |
| Notifications | `notifications.manage` (reserved) |
| Settings | `settings.manage` |

### System roles

| Role | Summary | Refund ceiling |
|---|---|---|
| `admin` | All 30 permissions | unlimited |
| `manager` | Catalog, orders, refunds, shipping, COD, coupons, content, reports; no user/role/settings admin | 5,000 |
| `staff` | Products + categories view + orders view + images | 0 (cannot refund alone) |
| `customer` | none | — |

Custom roles are built in **Roles** from the same catalog; the picker never
invents keys. The refund ceiling (`roles.max_refund_amount`) is enforced
server-side: a refund above it requires a second approver, and the approver must
differ from the requester.

---

## 7. Dashboard

`pages/Dashboard/Dashboard.jsx` combines `/analytics/dashboard`,
`/analytics/top-products`, `/categories`, and `/products` into:

- **KPI cards** — revenue, orders, customers, pending/processing counts
  (`StatCard`, `InfoCard`).
- **Charts** — revenue over time, sales trend, order status mix, top products,
  sales by category (Recharts, responsive containers).
- **Quick actions** — jump to orders, products, reports, filtered by state.
- Prices are locale-aware (`formatPrice`, `formatShort`) and collapse to compact
  notation on small screens.

Loading uses the dashboard skeleton; each card fails independently so one bad
series does not blank the page.

---

## 8. Product and Inventory Management

### Product list (`pages/Products/ProductList.jsx`)
- Server-side pagination/search/filter, including inactive products.
- Row actions: view, edit, activate/deactivate, delete.
- Bulk selection → `POST /admin/products/bulk-update-status` or
  `POST /admin/products/bulk-delete`.
- CSV export via `GET /admin/products/export` (permission `products.export`).

### Product form (`ProductForm.jsx`)
- Create/edit name, slug, description, category, price, compare-at price.
- **Variants**: SKU, attributes (size/colour/etc. as JSON), stock,
  `price_override`. Effective price and discount are server-computed.
- **Images**: multipart upload to Cloudinary, reorder, alt text, delete.
- Validation mirrors the backend schema (slug format, non-negative prices,
  integer stock) but the server remains authoritative.

### Product detail (`ProductDetail.jsx`)
Read-only summary plus quick links to edit, image management, and the storefront
page.

### Categories (`CategoryList`, `CategoryForm`, `CategoryProducts`)
Hierarchy (parent/child), slug, sort order, active flag, thumbnail upload, and a
per-category product listing.

### Inventory
Stock is per variant (`product_variants.stock`). It is decremented at checkout,
restored on cancellation, and restored on RTO/received-return exactly once
(guarded by `orders.rto_stock_restored` / `stock_released`). The admin can adjust
stock directly (backend permission `inventory.adjust`, also exposed to the MCP
agent behind a preview token).

---

## 9. Order Management

### List (`pages/Orders/OrderList.jsx`)
- Filters: status, payment status, date range, free-text search, page/limit.
- Uses `GET /admin/orders` and `/admin/orders/stats` for tab counters.
- Status badges and fulfilment stage share `utils`/component mappings so list and
  detail cannot disagree.

### Detail (`pages/Orders/OrderDetail.jsx`) — the operations hub

| Area | Capabilities |
|---|---|
| Summary | Order number, placed date, customer, payment state, totals incl. COD fee |
| Items | Line snapshots (name, SKU, attributes, qty, unit price, line total) |
| Addresses | Shipping/billing, with customer snapshot fallback |
| Items/stock | Link to product/variant |
| Status | Legal transitions via `PUT /admin/orders/{id}/status` |
| Fulfilment | Create Shiprocket order → assign AWB → request pickup → label/manifest/tracking |
| Tracking | Timeline + milestone scans; simulator can inject events |
| Money | Refund dialog, reconcile refund, admin cancel with explicit outcome |
| Documents | Invoice (jsPDF) and packing slip (`react-to-print`) |
| History | Audit entries for the order |

Legal statuses: `pending, confirmed, processing, shipped, out_for_delivery,
delivered, cancelled, rto, refunded`.

`FulfilmentStage` derives a coarse stage from shipment status/scans, with a
fallback for orders that have no shipment record.

### Cancellation
`AdminCancelDialog` collects a reason and shows the restocking fee implied by the
current status (store policy: pending/confirmed/processing tiers). The backend
computes the money outcome and restores stock; the dialog never calculates the
final refund.

### Refunds (`pages/Refunds/Refunds.jsx`)
- Ledger with status filter (`pending_approval`, `executed`, `rejected`,
  `failed`).
- **Attention queue** (`/admin/refunds/attention`): cancelled orders that were
  paid online and still hold captured money.
- Approve/reject pending refunds. The UI hides approve when
  `my-authority` says the amount exceeds the actor's ceiling — the API enforces
  it anyway.
- Manual transfers can carry a reference for offline settlements.

---

## 10. Product Returns

`ReturnList` → `ReturnDetail` implements the reverse-logistics workflow:

```
requested → approved → return_shipped → received → inspection → refund_pending → refunded
                 ↘ rejected                                  ↘ cancelled
```

- Evidence photos are retrieved through an authenticated download endpoint (files
  live in `private_storage`, never publicly served).
- Approve/reject with a note; both write `return_events` + audit rows.
- Attach manual tracking or create a Shiprocket reverse shipment.
- Receive → inspect (pass/fail + note) → refund.
- Refund requires `orders.refund`; the amount is recomputed server-side from the
  return lines, restocking fee and store policy.

---

## 11. COD Reconciliation

Two panels, deliberately separate:

1. **Collection** — cash handed over by the customer at delivery. Bulk-mark
   orders collected (`orders.update`).
2. **Remittance** — the courier's payout batch (CSV import or manual batch).

`CodImport` runs a **dry-run preview first**; every row is classified
(`matched`, `amount_mismatch`, `order_not_found`, `not_cod`, `not_delivered`,
`cash_not_collected`, `already_remitted`, `duplicate`, `adjustment`) before
anything is written. `CodRemittanceDetail` allows line resolution, bank-credit
confirmation (UTR, amount, date), CSV export and voiding.

A non-zero `difference` (net expected vs bank credit) requires an explicit
`accept_difference` and a reason. The simulator batch is available outside
production, or with `COD_REMITTANCE_SIMULATOR_ENABLED=true`.

---

## 12. Customers, Roles and Invites

### Users (`UserList`, `UserDetail`)
- Search + pagination; totals and growth stats.
- Detail: profile, activation, legacy role, dynamic role set, addresses, lifetime
  order stats, orders.
- Deactivate/delete requires `users.manage`; changing the legacy role requires
  `users.manage_roles`.

### Roles (`RoleList`, `RoleForm`)
- Lists system + custom roles with permission counts and user counts.
- Builder groups the catalog by module (`groupPermissionsByModule`) with
  select-all per module.
- System roles are immutable; roles in use cannot be deleted.
- Setting a user's roles replaces the set and updates the legacy `role` to the
  highest-privilege slug so old guards keep working.

### Invites (`Invites`, `AcceptInvite`)
- Invite by email + role slugs; token is hashed, expiring, resendable, revocable.
- `AcceptInvite` is a public route matching the emailed link; the token is the
  proof of inbox control. Acceptance creates/activates the account and assigns
  roles.

### Audit log (`AuditLog`)
- Newest-first, filterable by action/entity/actor.
- Records before/after JSON for money and permission changes, plus IP.

---

## 13. Marketing and Content

### Coupons (`CouponList`, `CouponForm`)
- Manual and automatic coupons; percentage or fixed.
- Automatic triggers: min cart value, min item count, category spend, first order.
- Caps: total uses, per-user uses, validity window, minimum order value,
  internal-only flag.
- **Risky coupons** report flags live codes with no expiry/cap or over-use.

### Promotions (`Promotions`)
- Compose a broadcast to all active customers (in-app feed + optional email).
- Live audience estimate before sending (counts only, no PII).
- History and retraction (removes the message from every recipient's feed).

### Content / Banners (`Content`, `ContentForm`)
- Slot-keyed blocks (e.g. `announcement.bar`, hero) with title/body, link, CTA
  label, sort order, active flag and start/end window.
- Desktop + mobile images, art-direction `layout_mode`, focal `image_position`,
  alt text — uploaded to Cloudinary.
- Public counterpart: `GET /content/blocks` returns only live blocks; the
  storefront falls back to hardcoded defaults when a slot is empty.

### Reviews (`Reviews`)
- Moderation queue including hidden rows.
- Hide/unhide (abuse) or hard delete (spam). Storefront reflects changes
  immediately.

---

## 14. Reports and Store Settings

### Reports (`Reports`)
- Sales for a date range, top products, order-status distribution, revenue trend,
  customer summary.
- PDF/CSV export via jsPDF + autotable (`utils/reportLoader.js` handles lazy
  loading of the heavy generators).

### Store Settings (`StoreSettings`)
Edits the single DB policy row that drives pricing everywhere:

| Field | Effect |
|---|---|
| `tax_rate` | Applied to taxable subtotal |
| `free_shipping_threshold`, `shipping_cost` | Delivery pricing |
| `cod_fee`, `cod_min_order_value`, `cod_max_order_value` | COD eligibility and fee |
| `restocking_fee_pending/confirmed/processing` | Cancellation deduction tiers |
| `refund_processing_days` | Customer-facing SLA |
| `pending_order_expiry_minutes` | Abandoned-order timeout |

Every save is audited; the history panel can restore a previous snapshot.
Changes take effect immediately — no redeploy.

---

## 15. Shiprocket Simulator

`/shipping-simulator` (permission `shipping.manage`) exercises the full
fulfilment lifecycle without a courier account:

- Lists orders that have shipments.
- Injects tracking events (picked up, in transit, out for delivery, delivered,
  RTO, exception) into the same handler the real webhook uses.
- Renders printable mock label and manifest documents.

This is a first-class feature, not a hidden dev tool — `SHIPPING_PROVIDER=simulator`
is a valid deployment mode.

---

## 16. MCP Agent

`pages/McpAgent/McpAgent.jsx` + `api/mcp.js`:

- Chat UI with Markdown rendering (`react-markdown` + `remark-gfm`).
- `POST /mcp/chat` or `/mcp/chat/stream` (SSE) for responses.
- Tool previews render as cards; **destructive actions need explicit button
  confirmation**, which posts the `preview_token` to
  `/mcp/cancel`, `/mcp/refund`, `/mcp/products/*`, or `/mcp/inventory/adjust`.
- The agent inherits the operator's RBAC, so it cannot do anything the user
  cannot do directly.
- Every write is audited like a normal admin action.

The route has no permission key (session-gated) — the *tools* enforce authority.
The inline comment in `AppRoutes.jsx` saying "backend wiring lands later" is
stale; the endpoints exist and are used.

---

## 17. Cross-Cutting UI

| Concern | Implementation |
|---|---|
| Layout | Fixed sidebar (collapsible, mobile drawer) + sticky header |
| Loading | Per-route skeletons (`components/skeletons/*`, `skeletonRoutes.js`) |
| Errors | `ErrorBoundary` per route + toast for API failures |
| Confirmation | `ConfirmDialog` for destructive actions |
| Toasts | `react-hot-toast`, theme-aware |
| Tables | Client-side sort on fetched pages; server-side paging |
| Money | `formatPrice` (locale-aware) — never raw floats |
| Currency | Deployment-wide; switched by backend env, not by UI |
| Theming | `ThemeContext` toggles light/dark CSS variables |
| Accessibility | Focus-visible rings, labelled controls, keyboard dialogs |

---

## 18. Build and Run

```bash
cd admin
npm install           # also links ../packages/shared as @ecom/shared
npm run dev           # http://localhost:3001, proxies /api → :8001
npm run build         # dist/ (self-contained; shared code is bundled)
npm run preview
npm run lint          # oxlint (all)
npm run lint:release  # oxlint on the release-critical file list
npm test              # node --test src/utils/*.test.js
npm run check:release # test + lint:release + build
```

`@ecom/shared` is a `file:../packages/shared` dependency: the `packages/`
sibling directory must exist when installing or building, but the built `dist/`
does not need it at runtime.

`.env`:

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | `http://localhost:8001/api/v1` in dev; absolute API origin for deployed builds |
| `VITE_GOOGLE_CLIENT_ID` | Google sign-in |

The dev server calls the backend directly (no Vite proxy), so
`CORS_ORIGINS` must include `http://localhost:3001`.

---

## 19. Conventions for New Admin Features

1. **Add the permission key first** in `backend/app/core/rbac_catalog.py` + a
   migration; never invent a key only in the frontend.
2. **Guard the route** with `requirePerm` and a `minRole` fallback.
3. **Add the sidebar entry** with the same `perm`/`minRole` and a group.
4. **Add to `ORDERED_TABS`** so landing redirects stay consistent.
5. **Add a skeleton** and register it in `skeletonRoutes.js`.
6. **Put API calls in `src/api/<domain>.js`**, not inline.
7. **Destructive actions** need `ConfirmDialog` + a server-side audit row.
8. **Money actions** must display the server-computed amount, never a local
   estimate.

---

## 20. Known Gaps

- React Query is installed and `QueryClientProvider` is mounted, but no admin
  page uses `useQuery`/`useMutation` yet — fetching is still manual
  `useEffect` + `useState`. The storefront has already migrated its catalog
  pages, so the pattern to copy exists.
- ~~Auth logic is duplicated with the storefront~~ — the transport/session layer
  now comes from `@ecom/shared` (`session.js`, `http.js`); only the React
  contexts remain app-specific.
- ~~The `McpAgent` route comment contradicts the implemented wiring~~ — the
  comment now describes the streaming backend it actually uses.
- Several admin lists have bespoke response-envelope handling (some
  `{items,total}`, some `{orders,total}`) — a shared table abstraction would
  remove that drift.

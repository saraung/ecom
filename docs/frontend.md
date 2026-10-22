# Storefront (Customer Frontend)

> React 19 + Vite 8 single-page application for shoppers.
> Directory: `frontend/` · Dev port: **5175** · API: `/api/v1`

---

## 1. Overview

The storefront is the public shopping experience: browsing, search, cart,
checkout, orders, returns, account management, notifications and an AI chat
assistant.

| Property | Value |
|---|---|
| Entry | `src/main.jsx` → `src/App.jsx` → `src/routes/index.jsx` |
| Rendering | Client-side SPA, no SSR |
| Styling | Tailwind CSS 4 + CSS variables (`styles/theme.css`, `index.css`) |
| State | React Context (5 providers) + local component state |
| HTTP | axios instance with single-flight refresh |
| Real-time | Native WebSocket for notifications |
| Payments | Razorpay Checkout.js + Stripe.js (whichever the backend provider returns) |

There is no global data cache (no TanStack Query in this app). Pages fetch on
mount and after mutations; `CartContext` is the only long-lived data source.

---

## 2. Directory Structure

```
frontend/src/
├── App.jsx                 provider nesting + region gate + toaster
├── main.jsx                React root
├── index.css               Tailwind entry + base tokens
├── styles/theme.css        light/dark CSS variable palette
├── api/                    14 modules — one per backend domain
│   ├── axios.js            thin wrapper: @ecom/shared/http + local session
│   ├── session.js          single-flight refresh / hard logout (@ecom/shared/session)
│   ├── auth.js              authAPI
│   ├── category.js          categoryAPI
│   ├── orders.js            orderAPI
│   ├── checkout.js          checkoutAPI
│   ├── payments.js          paymentAPI
│   ├── returns.js           returnAPI
│   ├── review.js            reviewAPI
│   ├── wishlist.js          wishlistAPI
│   ├── coupons.js           couponAPI
│   ├── addresses.js         addressAPI
│   ├── chat.js              chatAPI
│   └── content.js           getContentBlocks
├── contexts/               Auth, Cart, Wishlist, Notification, Theme
├── hooks/                  useAuth, useCart, useWishlist, useTheme, useModalA11y
├── components/
│   ├── common/             AnnouncementBar, Chatbot, ErrorBoundary, ImageLightbox,
│   │                       NotificationBell, ProductCard, SearchSuggestions,
│   │                       Skeleton, WishlistButton
│   ├── layout/             Header, Footer, Layout
│   └── orders/             AddressCard, CancelOrderModal, CancellationPolicyNotice,
│                           OrderCard, OrderItemsList, OrderReturns, OrderStatusBadge,
│                           OrderTotals, OrderTrackingCard, RefundBadge
├── pages/
│   ├── auth/               Login, Register, RegisterPanel, RegisterWithOTP,
│   │                       ForgotPassword, ResetPassword
│   ├── home/               Home
│   ├── product/            ProductList, ProductDetail
│   ├── checkout/           Cart, Checkout
│   ├── customer/           Orders, OrderDetail, Profile, Addresses, Wishlist,
│   │                       Notifications, Settings
│   └── ChangePassword/     ChangePassword
│   └── NotFound.jsx        catch-all 404 page
├── routes/                 index.jsx (lazy route table), PrivateRoute, PublicRoute
├── services/               notificationService.js (WebSocket owner)
└── utils/                  catalog.js, chatSession.js, guestCartMerge.js,
                            returns.js, region.js, format.js (+ 4 test files)
```

Formatting and the HTTP/session plumbing are **not** in this tree: they live in
`../packages/shared/` and are installed as the `@ecom/shared` file dependency.
See `architecture.md` §3.1.

---

## 3. Routing

`src/routes/index.jsx` defines all routes. Two guards wrap protected/public areas:

| Guard | Behaviour |
|---|---|
| `PrivateRoute` | Shows a spinner while auth resolves; redirects to `/login` if not authenticated |
| `PublicRoute` | Redirects authenticated users to `/` (login/register pages) |

| Path | Component | Guard | Notes |
|---|---|---|---|
| `/` | `Home` | public | Hero banners from `/content/blocks`, featured products |
| `/products` | `ProductList` | public | Search/category/sort/pagination via query string |
| `/products/:slug` | `ProductDetail` | public | Variants, gallery, reviews, wishlist |
| `/cart` | `Cart` | public | Guest cart lives in `localStorage` |
| `/wishlist` | `Wishlist` | public | Guests see a sign-in prompt |
| `/login` | `Login` | `PublicRoute` | Email/password + Google |
| `/register` | `RegisterWithOTP` | `PublicRoute` | Two-step email OTP registration |
| `/forgot-password` | `ForgotPassword` | `PublicRoute` | Sends reset link |
| `/reset-password` | `ResetPassword` | `PublicRoute` | Consumes token from email |
| `/checkout` | `Checkout` | `PrivateRoute` | Address + payment + order creation |
| `/orders` | `Orders` | `PrivateRoute` | Order history |
| `/orders/:id` | `OrderDetail` | `PrivateRoute` | Timeline, cancel, return, invoice print |
| `/notifications` | `Notifications` | `PrivateRoute` | Feed + mark read |
| `/profile` | `Profile` | `PrivateRoute` | Name, phone, email |
| `/settings` | `Settings` | `PrivateRoute` | Password + notification prefs |
| `/addresses` | `Addresses` | `PrivateRoute` | CRUD + default |
| `*` | `NotFound` | public | Catch-all 404 inside `Layout`, with links home and to the catalog |

A `ScrollToTop` component resets scroll on every pathname change.

**Code splitting:** only `Home` and `Login` are imported eagerly. Every other
page is a `React.lazy` chunk behind one `<Suspense>` boundary in
`routes/index.jsx`, with a centred spinner fallback. The initial JS payload is
~373 kB (110 kB gzipped); individual pages and the Chatbot widget load on
first use and are then served from cache. Adding a page means adding a
`lazy()` import and a `<Route>`, not a static import.

---

## 4. Provider Composition

`App.jsx` nests providers deliberately — cart must exist before auth (guest
merge), and notifications need an authenticated user:

```jsx
<ErrorBoundary>
  <QueryClientProvider>     {/* catalog cache; defaults: 60s stale, no focus refetch */}
    <RegionGate>            {/* loads currency/locale/tax label once */}
      <CartProvider>
        <WishlistProvider>
          <AuthProvider>
            <NotificationProvider>
              <ThemedToaster />
              <AppRoutes />
            </NotificationProvider>
          </AuthProvider>
        </WishlistProvider>
      </CartProvider>
    </RegionGate>
  </QueryClientProvider>
</ErrorBoundary>
```

| Provider | Owns | Persistence |
|---|---|---|
| `CartProvider` | Cart lines, totals, coupon, guest merge | Server cart + `localStorage` guest cart |
| `WishlistProvider` | Wishlist ids | Server |
| `AuthProvider` | User, tokens, login/logout | `localStorage` (`access_token`, `refresh_token`, `user`) |
| `NotificationProvider` | WebSocket connection status + listener fan-out | Server + socket |
| `ThemeContext` | Light/dark preference | `localStorage` |
| `RegionGate` (in App) | `{currency, locale, taxLabel, country}` | Fetched from `/checkout/config` |

### 4.1 AuthContext

```js
const { user, loading, isAuthenticated, login, logout,
        updateUser, fetchUser } = useAuth();
```

- On boot: if `access_token` exists, call `GET /auth/me`.
- 401/403 → clear tokens and drop to guest.
- Network failure → keep the cached `user` from `localStorage` rather than
  logging the shopper out for a transient error.
- `login()` stores both tokens and the user object.

### 4.2 CartContext

The most complex provider. Responsibilities:

| Concern | Implementation |
|---|---|
| Guest cart | `localStorage` array of `{variant_id, quantity, merge_key}` |
| Server sync | `GET /cart` on login; `POST/PUT/DELETE /cart/items` |
| Guest → user merge | `createGuestCartMerger()` replays items once per `merge_key` |
| Coupon | `POST/DELETE /cart/coupon` |
| Automatic coupons | Displayed from `cart.automatic_coupon` (server-selected) |
| Totals | Always taken from the server response (`subtotal`, `discount_total`, `tax_total`, `shipping_total`, `total`) |
| Auth switching | Listens for an `auth-change` event and re-syncs |

**Guest merge idempotency** — `src/utils/guestCartMerge.js` generates a stable
`merge_key` per guest cart and sends it with every add. The backend records
`cart_merge_receipts`, so a duplicate replay is a no-op. This unit is covered by
`guestCartMerge.test.js`.

### 4.3 NotificationContext + service

`notificationService.js` owns exactly **one** WebSocket per logged-in user:

```
ws(s)://<host>/api/v1/notifications/ws?token=<access_token>
```

- Dedupes connections if React re-renders.
- Reconnects with backoff on unexpected close.
- On close code **4401** (token expired) it refreshes the token first, then
  reconnects.
- Fans messages out to any number of subscribers via `subscribe(cb)`.
- Normalises legacy payload shapes so older notification rows still render.

`GET /notifications` remains the source of truth after a reconnect; the socket
is a latency optimisation, not the store.

---

## 5. API Integration

`src/api/axios.js` is now a five-line wrapper:

```js
baseURL = '/api/v1'
createApiClient({ axios, baseURL, session })   // from @ecom/shared/http
```

The bearer header, the 401 → refresh → retry-once interceptor and the
`NO_REFRESH_PATHS` list all live in `packages/shared/src/http.js`, because the
admin panel needs exactly the same behaviour. `src/api/session.js` configures
one `createSession()` instance (refresh URL `/api/v1/auth/refresh`, redirect
`/login`) from `@ecom/shared/session`; the axios client and the notification
WebSocket share that instance so both queue onto the **same single-flight**
refresh. Refresh tokens are parsed tolerantly (flat, camelCase or wrapped
bodies) and a rotated token is persisted.

Paths excluded from refresh-and-retry: `/auth/login`, `/auth/refresh`,
`/auth/register`, `/auth/google`, `/auth/logout`.

### API module → backend mapping

| Module | Backend area |
|---|---|
| `authAPI` | `/auth/*` (incl. OTP registration, Google, password reset) |
| `categoryAPI` | `/categories` |
| `orderAPI` | `/orders`, `/orders/{id}/cancel`, `/orders/number/{n}` |
| `checkoutAPI` | `/checkout`, `/checkout/config` |
| `paymentAPI` | `/payments/create-intent`, `/payments/confirm` |
| `returnAPI` | `/orders/{id}/returns`, `/returns/*` |
| `reviewAPI` | `/reviews/*` |
| `wishlistAPI` | `/wishlist/*` |
| `couponAPI` | `/coupons/validate` |
| `addressAPI` | `/addresses/*` |
| `chatAPI` | `/chat/*` |
| `getContentBlocks` | `/content/blocks` |

Product/catalog calls live inside `utils/catalog.js` and page components rather
than a dedicated module.

---

## 6. Page Behaviour

### Home (`pages/home/Home.jsx`)
- Loads live content blocks (announcement bar, hero, promos) with a hardcoded
  fallback when a slot is empty.
- Featured/newest products from the catalog API.
- Both feed a TanStack Query cache (`['products','featured']`,
  `['content','home.hero']`), so returning to `/` does not refetch or re-flash
  skeletons.
- Region-aware currency formatting from `RegionGate`.

### Product list (`pages/product/ProductList.jsx`)
- URL is the state: `?search=`, `?category=`, `?page=` via `useSearchParams`.
- Category tree is cached for ten minutes (`['categories']`).
- One cache entry per filter combination
  (`['catalog',{search,category,sort,page}]`); `keepPreviousData` keeps the
  current grid on screen while a new page loads instead of collapsing to a
  skeleton.
- Sort options map to backend `sort` values; pagination reads
  `total_pages` from the response and clamps out-of-range pages.
- Superseded requests are aborted by React Query, so a slow page can no longer
  overwrite a newer one. Revisiting a filter renders instantly from cache.
- Skeleton grid on first load, empty state with a "clear filters" action.

### Product detail (`pages/product/ProductDetail.jsx`)
- Slug-based query (`['product',slug]`), cached; 404s are not retried.
- Reviews are a child query (`['reviews',productId]`) and review
  create/delete update that cache entry in place.
- Variant selector updates price/stock/`sku`.
- Gallery with lightbox; wishlist toggle; review list + rating summary.
- Verified-purchase reviews can include customer photos.

### Cart (`pages/checkout/Cart.jsx`)
- Works signed-out (local cart) and signed-in (server cart).
- Quantity changes are optimistic on the client but reconciled with the server
  response — the server total always wins.
- Shows automatic coupon and applied manual coupon separately.

### Checkout (`pages/checkout/Checkout.jsx`)
A single page that:

1. Picks or creates a shipping address.
2. Chooses `online` or `cod`, disabling COD outside the configured min/max.
3. Recomputes the payable total locally for display, but submits to
   `POST /checkout` and trusts the returned order.
4. For **online**: `POST /payments/create-intent` →
   - Razorpay: loads `checkout.razorpay.com/v1/checkout.js`, opens the widget.
   - Stripe: `loadStripe(VITE_STRIPE_PUBLISHABLE_KEY)`, mounts Payment Element in
     a modal, confirms, then `POST /payments/confirm`.
5. Shows an order confirmation; the webhook is authoritative if the client
   callback is lost.

Duplicate submission is guarded with a busy flag plus an idempotent backend
checkout path.

### Orders (`pages/customer/Orders.jsx`, `OrderDetail.jsx`)
- Status badges share one mapping (`OrderStatusBadge`).
- Detail shows items, totals, addresses, payment state, shipment tracking
  (`OrderTrackingCard`), and refund state.
- Cancel is gated by `CancellationPolicyNotice` (restocking fee depends on
  status).
- Returns are created from `OrderReturns` once
  `GET /orders/{id}/return-eligibility` allows it.
- Invoice/receipt printing uses `react-to-print`.

### Auth pages
- `RegisterWithOTP` implements the two-step flow: initiate → 6-digit code →
  verify, with resend cooldown and inline error copy.
- `Login` supports password and Google; it posts `audience: "storefront"` so
  staff accounts are not forced through the admin OTP step-up while shopping.
- Password reset uses the token from the email link.

### Chatbot (`components/common/Chatbot.jsx`)
- Floating assistant backed by `/chat`.
- Session id persisted in `sessionStorage` via `utils/chatSession.js`.
- Renders Markdown (`react-markdown` + `remark-gfm`) for structured answers.
- Rate-limit (`429`) and offline states are surfaced as toast/inline messages.

---

## 7. Shared Components

| Component | Role |
|---|---|
| `Layout` | Header + `<Outlet>` + Footer + announcement bar |
| `Header` | Nav, search, cart badge, wishlist, notification bell, account menu |
| `Footer` | Static links + support info |
| `ProductCard` | Image, name, price/sale price, rating, wishlist heart |
| `SearchSuggestions` | Debounced typeahead against the catalog |
| `WishlistButton` | Optimistic toggle; prompts sign-in for guests |
| `NotificationBell` | Unread badge driven by context/socket |
| `ImageLightbox` | Keyboard-accessible full-screen gallery |
| `Skeleton` | Layout-preserving loading placeholders |
| `ErrorBoundary` | Catches render errors per page; offers reload |
| `useModalA11y` | Escape-to-close, focus trap, scroll lock for dialogs |

---

## 8. Regionalisation and Formatting

`utils/region.js` loads `/checkout/config` once at boot and caches:

```js
{ currency, locale, taxLabel, country, supportPhone }
```

`utils/format.js` re-exports the formatters built by
`createFormatters(getRegion)` from `@ecom/shared/format` — the same
implementation the admin panel uses, so money and dates cannot drift between
the two apps. Locally it adds only the storefront-specific `supportPhone()` and
the order/payment display maps.

Available: `formatPrice`, `formatShort`, `formatNumber`, `currencySymbol`,
`formatDate`, `formatDateTime`, `formatDay`, `taxLabel`, `storeCountry`.
`en-IN` produces lakh/crore grouping (`₹1,23,456.00`). **Never hardcode a
currency symbol in a component.**

---

## 9. Styling

- Tailwind 4 via `@tailwindcss/vite` (no `tailwind.config.js`; theme lives in CSS).
- Design tokens are CSS variables in `styles/theme.css` — `--background`,
  `--card`, `--foreground`, `--border`, `--primary`, `--ring`, `--success`,
  `--destructive`, etc.
- Dark mode is a class/attribute toggle managed by `ThemeContext`; components use
  token classes (`bg-card`, `text-foreground`) rather than literal colours.
- Toasts use the same tokens so they follow the theme.

---

## 10. Build, Run, Test

```bash
cd frontend
npm install          # also links ../packages/shared as @ecom/shared
npm run dev          # http://localhost:5175, proxies /api → :8001
npm run build        # dist/ (single self-contained bundle set)
npm run preview      # serve dist on 5175
npm run lint         # oxlint
npm test             # node --test src/utils/*.test.js
npm run check:release # test + targeted lint + build
```

`@ecom/shared` is a `file:../packages/shared` dependency, so **the
`packages/` sibling directory must be present when installing or building**.
The Vite config allows the dev server to read `..` for that reason. The built
`dist/` has no runtime dependency on `packages/` — shared code is bundled in.

Environment (`.env`):

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | `/api/v1` in dev; absolute API origin for deployed builds |
| `VITE_GOOGLE_CLIENT_ID` | Google sign-in button |
| `VITE_RAZORPAY_KEY_ID` | Razorpay checkout widget |
| `VITE_STRIPE_PUBLISHABLE_KEY` | Stripe Payment Element |

Unit tests cover pure logic only: `catalog.test.js`, `chatSession.test.js`,
`guestCartMerge.test.js`, `returns.test.js`.

---

## 11. Extending the App — Conventions

1. **New API call** → add to the matching `api/*.js`, not inline in a component.
2. **New page** → `pages/<area>/<Name>.jsx`, register in `routes/index.jsx`,
   wrap in `Layout` and (if personal) `PrivateRoute`.
3. **New shared UI** → `components/common/`; keep it prop-driven and
   theme-token based.
4. **New global state** → only if it must survive navigation; otherwise local
   state or URL params.
5. **Money** → render with `formatPrice`, derive from server responses.
6. **Auth** → never read tokens directly in components; use `useAuth()`.

---

## 12. Previously Known Gaps — Status

All four gaps listed in the first draft of this document have been resolved.

| Gap | Resolution |
|---|---|
| No catch-all route (empty layout on unknown URLs) | `pages/NotFound.jsx` registered as the last route inside `Layout` |
| `console.log` noise in `CartContext` | 47 debug statements removed across `CartContext`, `WishlistContext` and `notificationService`; genuine `console.error`/`warn` paths kept. (`Checkout.jsx` never had debug logs — its 10 calls are all error reporting.) |
| Auth/notification logic duplicated in `admin/` | Transport and session logic extracted to `packages/shared` (`@ecom/shared`); both apps now share one implementation of refresh, retry and regionalised formatting |
| No query cache (list pages always refetch) | TanStack Query adopted for `Home`, `ProductList` and `ProductDetail`; cart and checkout deliberately stay imperative/uncached |

Deliberately **not** shared: the React contexts themselves (`AuthContext`,
`NotificationContext`, `CartContext`). They look similar but encode different
session rules (customer vs staff roles, cart merge events, notification
routing), and a forced merge would be riskier than the duplication it removes.
Only the framework-agnostic layer below them is shared.

Remaining watch-items (not defects):

- The admin panel mounts a `QueryClientProvider` but its pages still fetch in
  effects; migrating admin lists is a separate, mechanical follow-up.
- Bundle size: the initial storefront chunk is ~373 kB (110 kB gzipped).
  Route splitting and the on-demand Chatbot already removed ~390 kB from the
  original single bundle; lazy-loading the checkout's payment SDKs would be the
  next step.

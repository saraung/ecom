# Backend API Reference

> FastAPI · Python 3.12 · 212 endpoints across 34 router modules.
> Source of truth: `backend/app/api/v1/**`. Interactive docs at `/docs`
> (Swagger) and `/redoc` when the server is running.

---

## 1. Conventions

| Item | Value |
|---|---|
| Base URL (dev) | `http://localhost:8001` |
| API prefix | `/api/v1` |
| Content type | `application/json` (except uploads: `multipart/form-data`) |
| Auth header | `Authorization: Bearer <access_token>` |
| Currency | `Decimal`; serialised as JSON string/number (never float math) |
| Timestamps | ISO-8601 UTC with offset |
| IDs | UUID v4 |

### Public entry points outside `/api/v1`

| Path | Purpose |
|---|---|
| `GET /` | Liveness payload: name, environment, payment provider |
| `GET /docs`, `/redoc`, `/openapi.json` | Generated API docs |
| `GET /uploads/{file}` | Content/hero images served from disk |
| `/mcp` | MCP protocol mount (JSON-RPC for the agent) |
| `/api/v1/notifications/ws` | WebSocket upgrade |

---

## 2. Authentication

### 2.1 Token pair

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "9f2c...",
  "token_type": "bearer"
}
```

Access tokens are short-lived (default 15 min) and carry:

| Claim | Meaning |
|---|---|
| `sub` | user email |
| `role` | legacy role string (`customer` … `admin`) |
| `permissions` | dynamic permission keys |
| `aud` | `admin` or `storefront` |
| `ver` | `users.token_version` — bump to revoke all sessions |
| `sid` | refresh-session id — revoking the session kills the access token |
| `exp`, `type` | expiry, `"access"` |

Refresh tokens are opaque, hashed at rest (`refresh_tokens.token_hash`), rotated
on every use, scoped to the audience they were issued for, and expire after
`REFRESH_TOKEN_EXPIRE_DAYS` (default 30).

### 2.2 Registration (OTP, two steps)

```http
POST /api/v1/auth/register/initiate
Content-Type: application/json

{ "email": "asha@example.com", "password": "S3cure!pass",
  "username": "asha", "full_name": "Asha Rao", "phone": "+9198..." }
```

```json
{ "message": "OTP sent to your email", "email": "asha@example.com",
  "expires_in": "10 minutes" }
```

```http
POST /api/v1/auth/register/verify

{ "email": "asha@example.com", "otp_code": "418302",
  "username": "asha", "password": "S3cure!pass",
  "full_name": "Asha Rao", "phone": "+9198..." }
```

```json
{ "access_token": "...", "refresh_token": "...", "token_type": "bearer" }
```

`POST /auth/register/resend-otp` re-sends (cooldown enforced). If the email
provider rejects the message the endpoint returns **503**, never a silent
success.

### 2.3 Login — shopper vs privileged

```http
POST /api/v1/auth/login
{ "email": "asha@example.com", "password": "S3cure!pass",
  "audience": "storefront" }
```

`200` with `TokenPair`.

The same call with `audience: "admin"` (the default) returns a **challenge**
when the account holds any admin permission:

```json
{ "otp_required": true,
  "challenge_token": "eyJ...",
  "email_masked": "a***@example.com",
  "expires_in": "10 minutes" }
```

Complete it with:

```http
POST /api/v1/auth/login/verify-otp
{ "challenge_token": "eyJ...", "otp_code": "517240" }
```

`POST /auth/login/resend-otp` re-issues a code for a live challenge
(60 s cooldown, `429` while cooling down).

The challenge token is a 5-minute JWT with `type:"challenge"`; it is rejected
anywhere except `/login/verify-otp`.

### 2.4 Refresh and logout

```http
POST /api/v1/auth/refresh
{ "refresh_token": "..." }
```

Returns a **new** token pair. The refresh token is rotated and the old one
revoked. Re-issues with the session's original audience — a storefront session
cannot upgrade to admin.

```http
POST /api/v1/auth/logout
{ "refresh_token": "..." }
```

`204 No Content`. Revokes the whole session (`sid`), so outstanding access
tokens for it fail immediately.

### 2.5 Current user

```http
GET /api/v1/auth/me
Authorization: Bearer <token>
```

```json
{
  "id": "6f1c...",
  "email": "asha@example.com",
  "username": "asha",
  "role": "manager",
  "roles": ["manager", "support-lead"],
  "permissions": ["dashboard.view", "orders.view", "orders.update", "..."],
  "full_name": "Asha Rao",
  "phone": "+9198...",
  "is_active": true,
  "email_verified": true,
  "auth_provider": "email",
  "push_notifications_enabled": true,
  "email_notifications_enabled": true,
  "created_at": "2026-08-20T11:02:44Z",
  "updated_at": "2026-10-01T09:14:03Z"
}
```

Clients should gate UI on `permissions`; `role` is the legacy fallback.

### 2.6 Google

```http
POST /api/v1/auth/google
{ "id_token": "<Google ID token>" }
```

Same `TokenPair` / challenge duality as password login. Google-created accounts
have a null `password_hash` and can add one via `POST /auth/set-password`.

### 2.7 Authorization guards

| Guard | Behaviour |
|---|---|
| *(none)* | Public |
| `user` / `CurrentUser` | Valid access token, active account, live session |
| `require_perm("x")` | `x` in the caller's DB permission union **and** `aud=admin` |
| `require_perm("x","y", require_all=False)` | Any of the listed keys |
| `require_role("admin")` | Legacy enum hierarchy **and** `aud=admin` |

A storefront token receives **403** on any admin route regardless of permissions:

```json
{ "detail": "This session is not authorized for the admin panel" }
```

---

## 3. Errors

All errors use FastAPI's shape:

```json
{ "detail": "Incorrect email or password" }
```

Validation errors (`422`) return the standard Pydantic array in `detail`.

| Status | When |
|---|---|
| `400` | Business-rule violation (wrong OTP, bad coupon, invalid state) |
| `401` | Missing/expired/invalid token, wrong password, dead challenge |
| `403` | Authenticated but not allowed (permission, audience, disabled account) |
| `404` | Resource not found or not owned by the caller |
| `409` | Conflicts (duplicate key/slug, already-processed state) |
| `422` | Request body/query validation |
| `429` | Rate limit or OTP cooldown |
| `500` | Unhandled (`{"detail": "Internal server error"}`) |
| `503` | Email provider unavailable when an OTP must be sent |

### Rate limits (slowapi, per client IP)

| Route | Limit |
|---|---|
| `POST /auth/login` | 10/min |
| `POST /auth/login/verify-otp` | 10/min |
| `POST /auth/login/resend-otp` | 3/min |
| `POST /auth/google` | 10/min |
| `POST /coupons/validate` | 30/min |
| Chat / MCP | `CHAT_MESSAGES_PER_MINUTE` (10), `CHAT_SESSIONS_PER_MINUTE` (5), global 100/min |

Exceeding returns `429` with `{"error": "Rate limit exceeded: ..."}` from the
slowapi handler.

### Pagination

List endpoints accept `page` (1-based) and `limit`, and return paged envelopes
where implemented:

```json
{ "products": [...], "total": 137, "page": 2, "limit": 20, "total_pages": 7 }
```

Admin lists that predate the envelope use `{items, total, page, limit}` or
`{orders, total}`; check the endpoint row below.

---

## 4. Endpoint Reference

Legend — **Auth**: `PUBLIC`, `user` (any authenticated), `perm:key`.

### 4.1 Authentication — `/auth`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/register/initiate` | PUBLIC | Send signup OTP |
| POST | `/auth/register/verify` | PUBLIC | Verify OTP, create account, issue tokens |
| POST | `/auth/register/resend-otp` | PUBLIC | Resend signup OTP |
| POST | `/auth/login` | PUBLIC | Password login (OTP step-up for admins) |
| POST | `/auth/login/verify-otp` | PUBLIC | Exchange challenge + OTP for tokens |
| POST | `/auth/login/resend-otp` | PUBLIC | Resend admin-login OTP |
| POST | `/auth/refresh` | PUBLIC | Rotate refresh token, new pair |
| POST | `/auth/logout` | PUBLIC | Revoke session (needs refresh token) |
| GET | `/auth/me` | user | Current profile + roles + permissions |
| PUT | `/auth/profile` | user | Update name, phone, username, notification prefs |
| POST | `/auth/google` | PUBLIC | Google ID-token sign-in |
| POST | `/auth/set-password` | user | Add a password to a Google-only account |
| POST | `/auth/forgot-password` | PUBLIC | Email a reset link |
| POST | `/auth/reset-password` | PUBLIC | Consume reset token |
| POST | `/auth/change-password` | user | Change password while signed in |

### 4.2 Products — `/products`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/products/` | PUBLIC | Active catalog; `page,limit,search,category_id,sort` |
| GET | `/products/{slug}` | PUBLIC | Product detail by slug |
| POST | `/products/` | perm:`products.create` | Create product (+ optional variants) |
| PUT | `/products/{product_id}` | perm:`products.update` | Partial update |
| DELETE | `/products/{product_id}` | perm:`products.delete` | Deactivate (soft delete) |
| GET | `/products/{product_id}/variants` | PUBLIC | Variants for a product |
| POST | `/products/{product_id}/variants` | perm:`products.create` | Add variant |
| PUT | `/products/{product_id}/variants/{variant_id}` | perm:`products.update` | Update variant (SKU, stock, price override, attributes) |
| DELETE | `/products/{product_id}/variants/{variant_id}` | perm:`products.update` | Delete variant |

Product response includes computed sale fields on variants:
`effective_price`, `discount_percentage`, `savings_amount`, `is_on_sale`.

### 4.3 Product images — `/products/{product_id}/images`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `` | PUBLIC | List images |
| POST | `` | perm:`product_images.manage` | Add image by URL |
| POST | `/upload` | perm:`product_images.manage` | Multipart upload to Cloudinary |
| PUT | `/{image_id}` | perm:`product_images.manage` | Update alt/sort |
| DELETE | `/{image_id}` | perm:`product_images.manage` | Remove image |
| POST | `/reorder` | perm:`product_images.manage` | Set explicit order |

### 4.4 Categories — `/categories`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/categories` | PUBLIC | All categories with direct product counts |
| GET | `/categories/{category_id}` | PUBLIC | Single category |
| POST | `/categories` | perm:`categories.manage` | Create |
| PUT | `/categories/{category_id}` | perm:`categories.manage` | Update |
| POST | `/categories/{category_id}/image/upload` | perm:`categories.manage` | Thumbnail upload |
| DELETE | `/categories/{category_id}` | perm:`categories.manage` | Delete |

### 4.5 Cart — `/cart`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/cart` | user | Cart + computed totals + automatic coupon |
| POST | `/cart/items` | user | Add `{variant_id, quantity, merge_key?}` |
| PUT | `/cart/items/{item_id}` | user | Set quantity (1–999) |
| DELETE | `/cart/items/{item_id}` | user | Remove line |
| DELETE | `/cart` | user | Clear cart |
| POST | `/cart/coupon` | user | Apply `{coupon_code}` |
| DELETE | `/cart/coupon` | user | Remove coupon |

Cart response:

```json
{
  "id": "…",
  "items": [{
    "id": "…", "variant_id": "…", "quantity": 2,
    "price_at_add": "1499.00", "variant_sku": "TSHIRT-M-BLK",
    "variant_attributes": {"size": "M", "color": "Black"},
    "product_name": "Everyday Tee", "product_slug": "everyday-tee",
    "product_image": "https://res.cloudinary.com/…"
  }],
  "subtotal": "2998.00",
  "coupon_code": "WELCOME10",
  "automatic_coupon": {
    "code": "AUTO200", "discount_type": "fixed", "value": "200.00",
    "discount_amount": "200.00", "trigger_type": "min_cart_value",
    "description": "₹200 off orders above ₹2,000"
  },
  "discount_total": "200.00",
  "tax_total": "503.64",
  "shipping_total": "0.00",
  "total": "3301.64",
  "item_count": 2
}
```

### 4.6 Checkout — `/checkout`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/checkout/config` | PUBLIC | Display-only pricing policy + currency/locale |
| POST | `/checkout` | user | Place an order atomically |

```http
POST /api/v1/checkout
{ "shipping_address_id": "…", "billing_address_id": "…",
  "payment_method": "online" }
```

`payment_method` ∈ `online` | `cod`. Returns the created order:

```json
{
  "id": "…", "order_number": "ORD-20261022-8F3K2",
  "user_id": "…",
  "subtotal": "2998.00", "discount_total": "200.00",
  "tax_total": "503.64", "shipping_total": "0.00",
  "cod_fee": "0.00", "grand_total": "3301.64",
  "status": "pending", "payment_status": "pending",
  "payment_method": "online", "placed_at": "2026-10-22T09:41:12Z"
}
```

`GET /checkout/config`:

```json
{ "cod_enabled": true, "cod_fee": 50.0,
  "cod_min_order_value": 0.0, "cod_max_order_value": 10000.0,
  "free_shipping_threshold": 1000.0, "shipping_cost": 50.0,
  "tax_rate": 0.18, "currency": "INR", "locale": "en-IN",
  "tax_label": "GST", "country": "India", "support_phone": "…" }
```

### 4.7 Addresses — `/addresses`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/addresses` | user | List own addresses |
| POST | `/addresses` | user | Create |
| PUT | `/addresses/{address_id}` | user | Update |
| DELETE | `/addresses/{address_id}` | user | Delete |
| POST | `/addresses/default/{address_id}` | user | Mark default |

### 4.8 Orders (customer) — `/orders`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/orders` | user | Own orders (`status`, `page`, `limit`) |
| GET | `/orders/{order_id}` | user | Own order detail |
| GET | `/orders/number/{order_number}` | user | Lookup by human order number |
| POST | `/orders/{order_id}/cancel` | user | Cancel if policy allows |
| GET | `/orders/{order_id}/refund-status` | user | Refund state for the order |

Cancellation returns the restocking fee that applies for the order's current
status (`pending` < `confirmed` < `processing`), taken from store policy.

### 4.9 Returns (customer) — `/orders/{id}/returns`, `/returns`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/orders/{order_id}/return-eligibility` | user | Item-level eligibility + window |
| POST | `/orders/{order_id}/returns` | user | Create return request |
| GET | `/returns` | user | Own returns |
| GET | `/returns/{return_id}` | user | Detail + events |
| POST | `/returns/{return_id}/cancel` | user | Cancel while allowed |
| POST | `/returns/{return_id}/tracking` | user | Attach return tracking |
| POST | `/returns/{return_id}/evidence` | user | Multipart photo upload |
| GET | `/returns/{return_id}/evidence/{evidence_id}` | user | Download evidence |

```http
POST /api/v1/orders/{order_id}/returns
{
  "idempotency_key": "0f0a6c1e-…",
  "reason": "damaged",
  "description": "Box arrived crushed",
  "items": [{ "order_item_id": "…", "quantity": 1 }]
}
```

`reason` ∈ `damaged | wrong_product | defective | missing_accessory |
wrong_variant | changed_mind | other`. Reusing an idempotency key with a
different payload is rejected.

### 4.10 Payments — `/payments`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/payments/create-intent` | user | Create provider intent for an order |
| POST | `/payments/confirm` | user | Confirm/settle after client SDK callback |

```json
// create-intent response
{ "client_secret": "pi_…_secret_…", "payment_intent_id": "pi_…",
  "order_id": "…", "amount": "3301.64", "currency": "INR",
  "provider": "stripe", "is_dummy": false }
```

### 4.11 Webhooks — `/webhooks`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/webhooks/payment` | signature | Razorpay/Stripe payment + refund events |
| POST | `/webhooks/shiprocket` | token | Tracking scans, RTO, delivery |

These are public routes guarded by provider signatures/secrets, **not** JWTs.
The payment webhook is the authoritative settlement path; the client confirm
endpoint is a fast path.

### 4.12 Reviews — `/reviews`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/reviews/{product_id}` | user | Review (verified purchase required) |
| POST | `/reviews/{product_id}/with-images` | user | Review + up to 6 photos |
| GET | `/reviews/products/{product_id}` | PUBLIC | Paginated product reviews |
| GET | `/reviews/product/{product_id}/rating` | PUBLIC | Average + count |
| GET | `/reviews/my-reviews` | user | Own reviews |
| PUT | `/reviews/{review_id}` | user | Edit own review |
| DELETE | `/reviews/{review_id}` | user | Delete own review |

### 4.13 Wishlist — `/wishlist`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/wishlist` | user | List |
| POST | `/wishlist/{product_id}` | user | Add |
| DELETE | `/wishlist/{product_id}` | user | Remove |
| GET | `/wishlist/check/{product_id}` | user | Membership boolean |

### 4.14 Coupons — `/coupons`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/coupons/validate` | PUBLIC | Validate a code against the live cart |
| GET | `/coupons` | perm:`coupons.view` | List (paged, filters) |
| GET | `/coupons/risky` | perm:`coupons.view` | Hygiene report (no expiry/cap, over-used) |
| GET | `/coupons/{coupon_id}` | perm:`coupons.view` | Detail |
| POST | `/coupons` | perm:`coupons.manage` | Create manual or automatic coupon |
| PUT | `/coupons/{coupon_id}` | perm:`coupons.manage` | Update |
| DELETE | `/coupons/{coupon_id}` | perm:`coupons.manage` | Delete |
| POST | `/coupons/generate` | perm:`coupons.manage` | Random code generator |

Coupon model supports `discount_type: percentage|fixed`,
`coupon_type: manual|automatic`, and triggers `none|min_cart_value|
min_item_count|category_spend|first_order`.

### 4.15 Content (public) — `/content`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/content/blocks` | PUBLIC | Live blocks grouped by slot |

Slots include `announcement.bar`, hero banners and other merchandising areas.
Inactive, draft and out-of-window blocks are omitted; the client falls back to
hardcoded defaults when a slot is absent.

### 4.16 Chat (customer assistant) — `/chat`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/chat/session` | PUBLIC | Create/attach a chat session |
| POST | `/chat` | PUBLIC | Send a message (RAG + tools) |
| GET | `/chat/history` | PUBLIC | Session history |
| DELETE | `/chat/history` | PUBLIC | Clear history |

Sessions are owner-scoped by session id/owner and TTL-bound
(`CHAT_SESSION_TTL_HOURS`). Per-minute limits apply (see §3).

### 4.17 Notifications — `/notifications`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| WS | `/notifications/ws` | token | Real-time push channel |
| GET | `/notifications` | user | Feed, newest first |
| GET | `/notifications/unread-count` | user | Badge count |
| PUT | `/notifications/mark-all-read` | user | Bulk read (optionally by audience) |
| PUT | `/notifications/{notification_id}/read` | user | Mark one |
| DELETE | `/notifications/{notification_id}` | user | Delete one |

Types: `order_placed`, `order_cancelled`, `order_status`, `promotion`,
`refund_approval`.

The WebSocket is authenticated with the session token (query/header per client
implementation); the HTTP feed remains the recovery path after a dropped socket.

### 4.18 Public analytics — `/analytics`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/analytics/dashboard` | perm:`dashboard.view` | Aggregate KPIs |
| GET | `/analytics/sales` | perm:`reports.view` | Sales for a date range |
| GET | `/analytics/top-products` | perm:`reports.view` | Best sellers |
| GET | `/analytics/orders` | perm:`reports.view` | Counts by status |
| GET | `/analytics/revenue` | perm:`reports.view` | Revenue over time |
| GET | `/analytics/customers` | perm:`reports.view` | Customer summary |

Despite the unprefixed path these are **admin** data and are permission-gated.

### 4.19 Staff invites — `/admin/invites`, `/invites`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/admin/invites` | perm:`users.manage_roles` | Invite by email + roles |
| GET | `/admin/invites` | perm:`users.manage_roles` | List invites |
| POST | `/admin/invites/{invite_id}/resend` | perm:`users.manage_roles` | Rotate token + resend |
| DELETE | `/admin/invites/{invite_id}` | perm:`users.manage_roles` | Revoke |
| GET | `/invites/accept` | PUBLIC | Preview invite (email + roles only) |
| POST | `/invites/accept` | PUBLIC | Accept (token is the email proof) |

### 4.20 MCP agent — `/mcp`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/mcp/chat` | user | Chat turn (tool-calling agent) |
| POST | `/mcp/chat/stream` | user | SSE streaming twin |
| POST | `/mcp/cancel` | user | Execute confirmed cancellation |
| POST | `/mcp/refund` | user | Execute confirmed refund |
| POST | `/mcp/products/update` | user | Execute confirmed product edit |
| POST | `/mcp/products/price` | user | Execute confirmed price change |
| POST | `/mcp/products/delete` | user | Execute confirmed deactivation |
| POST | `/mcp/inventory/adjust` | user | Execute confirmed stock adjustment |

Write endpoints require a `preview_token` produced by the preceding preview
tool call. The agent runs as the calling user and cannot exceed their RBAC.

---

## 5. Admin Endpoints

### 5.1 Dashboard — `/admin/dashboard`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/dashboard` | perm:`dashboard.view` | Revenue, orders, users, low stock, recent activity |

### 5.2 Orders — `/admin/orders`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/orders` | perm:`orders.view` | Filter: status, payment_status, search, dates, page |
| GET | `/admin/orders/stats` | perm:`orders.view` | Counters per status |
| GET | `/admin/orders/{order_id}` | perm:`orders.view` | Full detail incl. items, addresses, payments |
| PUT | `/admin/orders/{order_id}/status` | perm:`orders.update` | `{status}` transition |
| GET | `/admin/orders/{order_id}/shipping/serviceability` | perm:`shipping.manage` | Courier rates for destination |
| POST | `/admin/orders/{order_id}/shipping/create` | perm:`shipping.manage` | Push to Shiprocket (or simulator) |
| POST | `/admin/orders/{order_id}/shipping/assign-awb` | perm:`shipping.manage` | Assign courier + AWB |
| POST | `/admin/orders/{order_id}/shipping/request-pickup` | perm:`shipping.manage` | Schedule pickup |
| GET | `/admin/orders/{order_id}/shipping/label` | perm:`shipping.manage` | Label URL |
| GET | `/admin/orders/{order_id}/shipping/manifest` | perm:`shipping.manage` | Manifest URL |
| GET | `/admin/orders/{order_id}/shipping/tracking` | perm:`shipping.manage` | Timeline + scans |
| GET | `/admin/orders/shipping/simulated-label/{shipment_id}` | perm:`shipping.manage` | Printable mock label |
| GET | `/admin/orders/shipping/simulated-manifest/{shipment_id}` | perm:`shipping.manage` | Printable mock manifest |
| GET | `/admin/orders/shipping/simulator/shipments` | perm:`shipping.manage` | Simulator inventory |
| POST | `/admin/orders/{order_id}/shipping/simulator/trigger-event` | perm:`shipping.manage` | Inject a tracking event |

Valid statuses: `pending, confirmed, processing, shipped, out_for_delivery,
delivered, cancelled, rto, refunded`.

### 5.3 Refunds and cancellation — `/admin/refunds`, `/admin/orders/{id}/...`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/refunds/my-authority` | perm:`orders.refund` | Caller's max single-refund amount |
| GET | `/admin/refunds/attention` | perm:`orders.refund` | Queue: cancelled, paid, money still held |
| GET | `/admin/refunds` | perm:`orders.refund` | Refund ledger |
| POST | `/admin/refunds/{refund_id}/approve` | perm:`orders.refund` | Execute pending refund (approver ≠ requester) |
| POST | `/admin/refunds/{refund_id}/reject` | perm:`orders.refund` | Reject, no money moves |
| POST | `/admin/orders/{order_id}/refund` | perm:`orders.refund` | Refund without cancelling |
| POST | `/admin/orders/{order_id}/reconcile-refund` | perm:`orders.refund` | Reconcile provider state |
| POST | `/admin/orders/{order_id}/cancel` | perm:`orders.update` | Cancel with explicit money outcome |

Refunds above the actor's `max_refund_amount` require a second approver. Every
money action writes `admin_audit_log` before/after JSON.

### 5.4 Returns — `/admin/returns`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/returns` | perm:`orders.view` | Queue + filters |
| GET | `/admin/returns/{return_id}` | perm:`orders.view` | Detail + events |
| GET | `/admin/returns/{return_id}/evidence/{evidence_id}` | perm:`orders.view` | Download photo |
| POST | `/admin/returns/{return_id}/decision` | perm:`orders.update` | `{decision: approve\|reject, note}` |
| POST | `/admin/returns/{return_id}/cancel` | perm:`orders.update` | Cancel request |
| POST | `/admin/returns/{return_id}/tracking` | perm:`orders.update` + `shipping.manage` | Attach tracking |
| POST | `/admin/returns/{return_id}/shipping/shiprocket` | perm:`orders.update` + `shipping.manage` | Create reverse shipment |
| POST | `/admin/returns/{return_id}/tracking/sync` | perm:`orders.update` + `shipping.manage` | Pull latest scans |
| POST | `/admin/returns/{return_id}/receive` | perm:`orders.update` | Mark received (restores stock) |
| POST | `/admin/returns/{return_id}/inspection` | perm:`orders.update` | `{passed, note}` |
| POST | `/admin/returns/{return_id}/refund` | perm:`orders.refund` | Issue refund |
| GET | `/admin/returns/shipping/simulator/shipments` | perm:`orders.view` + `shipping.manage` | Simulator list |
| POST | `/admin/returns/{return_id}/shipping/simulator/trigger-event` | perm:`orders.update` + `shipping.manage` | Simulate scan |

Return states: `requested → approved → return_shipped → received →
inspection → refund_pending → refunded`, with `rejected` and `cancelled`
terminal branches.

### 5.5 Products — `/admin/products`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/products` | perm:`products.view` | Paged, includes inactive |
| GET | `/admin/products/export` | perm:`products.export` | CSV export |
| GET | `/admin/products/by-slug/{slug}` | perm:`products.view` | Lookup by slug |
| GET | `/admin/products/{product_id}` | perm:`products.view` | Detail |
| POST | `/admin/products/bulk-delete` | perm:`products.delete` | `{product_ids[]}` |
| POST | `/admin/products/bulk-update-status` | perm:`products.update` | `{product_ids[], is_active}` |

### 5.6 Users — `/admin/users`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/users` | perm:`users.view` | Paged list + search |
| GET | `/admin/users/stats` | perm:`users.view` | Totals, growth |
| GET | `/admin/users/{user_id}/stats` | perm:`users.view` | Lifetime order stats |
| GET | `/admin/users/{user_id}/addresses` | perm:`users.view` | Saved addresses |
| GET | `/admin/users/{user_id}` | perm:`users.view` | Detail |
| PUT | `/admin/users/{user_id}/role` | perm:`users.manage_roles` | Set legacy role |
| PUT | `/admin/users/{user_id}/status` | perm:`users.manage` | Activate/deactivate |
| DELETE | `/admin/users/{user_id}` | perm:`users.manage` | Delete |

### 5.7 Roles and permissions — `/admin`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/permissions` | perm:`roles.manage` or `users.manage_roles` | Catalog grouped by module |
| GET | `/admin/roles` | same (any) | Roles + granted keys + user counts |
| POST | `/admin/roles` | perm:`roles.manage` | Create custom role |
| GET | `/admin/roles/{role_id}` | either | Detail |
| PUT | `/admin/roles/{role_id}` | perm:`roles.manage` | Rename / replace permission set |
| DELETE | `/admin/roles/{role_id}` | perm:`roles.manage` | Delete (system/in-use protected) |
| GET | `/admin/users/{user_id}/roles` | perm:`users.view` | Role slugs |
| PUT | `/admin/users/{user_id}/roles` | perm:`users.manage_roles` | Replace role set |

### 5.8 COD reconciliation — `/admin/cod`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/cod/pending` | perm:`orders.update` | COD orders awaiting cash collection |
| POST | `/admin/cod/orders/{order_id}/collect` | perm:`orders.update` | Mark cash collected |
| POST | `/admin/cod/collect-bulk` | perm:`orders.update` | `{order_ids[]}` |
| GET | `/admin/cod/summary` | perm:`cod.view` | Collection vs remittance totals |
| GET | `/admin/cod/awaiting-remittance` | perm:`cod.view` | Delivered + cash in hand |
| GET | `/admin/cod/remittances` | perm:`cod.view` | Batch list |
| GET | `/admin/cod/remittances/sample-template` | perm:`cod.view` | CSV template |
| GET | `/admin/cod/remittances/sample-fixture` | perm:`cod.view` | Sample import file |
| POST | `/admin/cod/remittances/import/preview` | perm:`cod.reconcile` | Dry-run row matching |
| POST | `/admin/cod/remittances/import` | perm:`cod.reconcile` | Persist batch |
| POST | `/admin/cod/remittances` | perm:`cod.reconcile` | Manual batch |
| POST | `/admin/cod/remittances/simulate` | perm:`cod.reconcile` | Synthetic batch (dev; prod needs flag) |
| GET | `/admin/cod/remittances/{remittance_id}` | perm:`cod.view` | Batch detail + lines |
| GET | `/admin/cod/remittances/{remittance_id}/export` | perm:`cod.view` | CSV export |
| POST | `/admin/cod/remittances/{remittance_id}/resolve` | perm:`cod.reconcile` | Accept/exclude a disputed line |
| POST | `/admin/cod/remittances/{remittance_id}/confirm` | perm:`cod.reconcile` | Record bank credit (UTR) |
| POST | `/admin/cod/remittances/{remittance_id}/void` | perm:`cod.reconcile` | Void batch |

Line match statuses: `matched, amount_mismatch, order_not_found, not_cod,
not_delivered, cash_not_collected, already_remitted, duplicate, adjustment`.

```json
// POST /admin/cod/remittances/{id}/confirm
{ "utr": "HDFC0001234567",
  "bank_credit_amount": "48500.00",
  "bank_credit_date": "2026-10-20",
  "notes": "Oct week 3 payout",
  "accept_difference": true,
  "difference_reason": "Courier weight dispute credit" }
```

### 5.9 Coupons — see §4.14 (same routes, permission-gated)

### 5.10 Promotions and notifications — `/admin/notifications`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/admin/notifications/promotional` | perm:`promotions.send` | Broadcast to all active customers |
| GET | `/admin/notifications/promotional/audience-estimate` | perm:`promotions.send` | Live recipient counts (no PII) |
| GET | `/admin/notifications/promotional` | perm:`promotions.send` | Broadcast history |
| DELETE | `/admin/notifications/promotional/{broadcast_id}` | perm:`promotions.send` | Retract from every feed |

### 5.11 Content management — `/admin/content`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/content/blocks` | perm:`content.manage` | All blocks incl. drafts/expired |
| POST | `/admin/content/blocks` | perm:`content.manage` | Create |
| GET | `/admin/content/blocks/{block_id}` | perm:`content.manage` | Edit payload |
| PUT | `/admin/content/blocks/{block_id}` | perm:`content.manage` | Partial update |
| DELETE | `/admin/content/blocks/{block_id}` | perm:`content.manage` | Delete |
| POST | `/admin/content/images` | perm:`content.manage` | Multipart image upload |

### 5.12 Reviews moderation — `/admin/reviews`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/reviews` | perm:`reviews.moderate` | Queue incl. hidden |
| PUT | `/admin/reviews/{review_id}/visibility` | perm:`reviews.moderate` | Hide/unhide |
| DELETE | `/admin/reviews/{review_id}` | perm:`reviews.moderate` | Hard delete |

### 5.13 Store settings — `/admin/settings`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/settings/store` | perm:`settings.manage` | Current policy + source (DB vs env) |
| PUT | `/admin/settings/store` | perm:`settings.manage` | Partial update (audited) |
| GET | `/admin/settings/store/history` | perm:`settings.manage` | Save/restore history |
| POST | `/admin/settings/store/restore` | perm:`settings.manage` | Re-apply a previous snapshot |

Policy fields: `tax_rate`, `free_shipping_threshold`, `shipping_cost`, `cod_fee`,
`cod_min_order_value`, `cod_max_order_value`, restocking fees per status,
`refund_processing_days`, `pending_order_expiry_minutes`.

### 5.14 Audit log — `/admin/audit-log`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/admin/audit-log` | perm:`reports.view` | Newest first; filter by actor/entity/action |

### 5.15 Email — `/email`

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/email/test` | perm:`promotions.send` | Send a test message |

---

## 6. Request/Response Examples

### 6.1 Product listing

```http
GET /api/v1/products/?page=2&limit=20&search=tee&category_id=3f2a...
```

```json
{
  "products": [{
    "id": "…", "name": "Everyday Tee", "slug": "everyday-tee",
    "description": "Heavyweight cotton",
    "price": "1499.00", "compare_at_price": "1999.00",
    "is_active": true,
    "category": {"id": "3f2a…", "name": "T-Shirts", "slug": "t-shirts"},
    "variants": [{
      "id": "…", "sku": "TSHIRT-M-BLK",
      "attributes": {"size": "M", "color": "Black"},
      "stock": 12, "effective_price": "1499.00",
      "discount_percentage": 25, "savings_amount": "500.00",
      "is_on_sale": true
    }],
    "average_rating": 4.4, "review_count": 87
  }],
  "total": 137, "page": 2, "limit": 20, "total_pages": 7
}
```

### 6.2 Admin status transition

```http
PUT /api/v1/admin/orders/{order_id}/status
Authorization: Bearer <admin-token>
{ "status": "shipped" }
```

```json
{ "id": "…", "order_number": "ORD-20261022-8F3K2",
  "status": "shipped", "payment_status": "paid",
  "shipped_at": "2026-10-22T12:03:11Z" }
```

Invalid transitions and side effects (stock, refund windows, notifications) are
enforced server-side; the admin UI only offers legal moves.

### 6.3 Coupon validation

```http
POST /api/v1/coupons/validate
{ "coupon_code": "WELCOME10" }
```

```json
{ "valid": true, "code": "WELCOME10",
  "discount_type": "percentage", "value": "10.00",
  "discount_amount": "299.80",
  "message": "Coupon applied" }
```

Invalid codes return `200` with `valid:false` and a human message, so the
storefront can show inline feedback without treating it as an error.

---

## 7. Client Integration Notes

1. **Always send the access token** as `Authorization: Bearer`.
2. **On 401, try refresh once**, then hard-logout. Both SPAs implement
   single-flight refresh so concurrent 401s do not rotate the token multiple
   times and self-revoke.
3. **Never cache money values client-side** — recompute from `/cart` or
   `/checkout/config` after mutations.
4. **`/auth/me` is the permission source**; do not derive permissions locally.
5. **Polling is unnecessary** for notifications — use the WebSocket and fall
   back to `GET /notifications` after reconnect.
6. **Uploads** are multipart to the dedicated `.../upload` endpoints; JSON
   endpoints accept an existing URL instead.

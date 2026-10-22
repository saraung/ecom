# System Architecture

> Full-stack e-commerce platform — three applications, one API.
> Generated from source: `backend/`, `admin/`, `frontend/` (October 2026).

---

## 1. System Overview

The platform is a **decoupled three-application system**. A single FastAPI
backend owns all state and business rules; two independent React single-page
applications consume it over HTTP.

```
                        ┌──────────────────────────────────┐
                        │            Browser               │
                        └───────────┬──────────┬───────────┘
                                    │          │
                    ┌───────────────▼──┐   ┌───▼────────────────┐
                    │  frontend/       │   │  admin/            │
                    │  Customer store  │   │  Staff dashboard   │
                    │  :5175           │   │  :3001             │
                    └───────────────┬──┘   └───┬────────────────┘
                                    │          │
                         /api/v1    │          │    /api/v1
                         (Vite dev proxy → localhost:8001)
                                    │          │
                        ┌───────────▼──────────▼───────────┐
                        │        backend/  :8001            │
                        │        FastAPI application        │
                        └───┬───────────┬───────────┬──────┘
                            │           │           │
                   ┌────────▼──┐  ┌─────▼─────┐ ┌───▼──────────┐
                   │PostgreSQL │  │ Cloudinary│ │ 3rd-party    │
                   │  (SQLModel│  │  (media)  │ │ APIs         │
                   │  +Alembic)│  └───────────┘ │ Razorpay     │
                   └───────────┘                │ Stripe       │
                                                │ Shiprocket   │
                                                │ Gmail/SendGrid│
                                                │ Groq / Gemini│
                                                └──────────────┘
```

| Application | Directory | Role | Dev port |
|---|---|---|---|
| Storefront | `frontend/` | Public shopping experience | 5175 |
| Admin | `admin/` | Staff operations console | 3001 |
| API | `backend/` | All business logic and persistence | 8001 |

Cross-cutting code is shared through `packages/shared` (`@ecom/shared`):
session refresh, the axios 401 interceptor and regionalised formatting are
installed into both SPAs as a local dependency (see §3.1). Feature code, React
contexts and page components remain app-specific. Any change to an API contract
still has to be applied to both consumers.

---

## 2. Technology Stack

### Backend

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.12 | pinned `>=3.12,<3.13` |
| Framework | FastAPI ≥0.141 | ASGI, automatic OpenAPI |
| ORM | SQLModel ≥0.0.39 | SQLAlchemy 2 + Pydantic in one model |
| Database | PostgreSQL | `psycopg2-binary` driver |
| Migrations | Alembic ≥1.19 | 61 revisions, one head |
| Package manager | **uv** | `pyproject.toml` + `uv.lock` |
| Auth | `python-jose` JWT, `passlib`/bcrypt | access + refresh rotation |
| Rate limiting | `slowapi` | in-process, per-route decorators |
| Scheduler | APScheduler (background) | 2 interval jobs |
| Validation | Pydantic v2 | `pydantic-settings` for config |
| Payments | Razorpay + Stripe SDKs | one active provider per deployment |
| Shipping | Shiprocket HTTP API | plus a first-class simulator |
| Media | Cloudinary | product/category/review/content images |
| Email | Gmail SMTP or SendGrid | transactional outbox pattern |
| AI | Groq / Gemini + ChromaDB + fastembed | customer chatbot + admin MCP agent |

### Frontend (both apps)

| Concern | Choice |
|---|---|
| Framework | React 19 |
| Build | Vite 8 |
| Styling | Tailwind CSS 4 (`@tailwindcss/vite`) |
| Routing | React Router 7 |
| HTTP | axios with interceptors |
| Icons | lucide-react |
| Toasts | react-hot-toast |
| Lint | oxlint |
| Tests | `node --test` on pure utilities |

Admin adds **TanStack Query 5**, Recharts 3, jsPDF + autotable, react-markdown.
Storefront adds **Stripe.js**, `jwt-decode`, `react-to-print`, `@react-oauth/google`.

---

## 3. Repository Layout

```
ecom/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app, middleware, scheduler, mounts
│   │   ├── api/
│   │   │   ├── deps.py        CurrentUser / require_perm / require_role
│   │   │   └── v1/            34 routers (public + admin/)
│   │   ├── core/              config, security, RBAC catalog, rate limit,
│   │   │                      region/currency, store settings, release gates
│   │   ├── db/                engine + get_session
│   │   ├── models/            27 SQLModel modules → 40 tables
│   │   ├── schemas/           26 Pydantic request/response modules
│   │   ├── repositories/      19 data-access modules
│   │   ├── services/          24 integration/domain services
│   │   ├── utils/             cart, coupon, pricing, order helpers
│   │   └── mcp/               MCP server, 23 tools, agent loop, guards
│   ├── alembic/               61 migration revisions
│   ├── tests/                 62 pytest modules
│   ├── scripts/               release_check.py, seed_rbac.py, backfill
│   ├── chroma_db/             local vector store (RAG)
│   ├── uploads/               content images served at /uploads
│   ├── private_storage/       return evidence (not web-served)
│   └── pyproject.toml, uv.lock, alembic.ini, .env
├── admin/
│   └── src/
│       ├── api/               20 axios modules
│       ├── components/        layout, charts, cards, dialogs, skeletons, invoice
│       ├── context/           Auth, Notifications, Theme
│       ├── pages/             23 feature folders
│       ├── routes/            AppRoutes.jsx (lazy + permission-gated)
│       └── utils/             permissions, returns, format, reportLoader
├── frontend/
│   └── src/
│       ├── api/               14 axios modules
│       ├── components/        common, layout, orders
│       ├── contexts/          Auth, Cart, Wishlist, Notification, Theme
│       ├── hooks/             thin consumers of each context
│       ├── pages/             auth, home, product, checkout, customer + NotFound
│       ├── routes/            index (lazy route table), PrivateRoute, PublicRoute
│       └── utils/             catalog, chatSession, guestCartMerge, returns, region
├── packages/
│   └── shared/                @ecom/shared — code used by BOTH SPAs
│       └── src/
│           ├── session.js     single-flight refresh + hard logout
│           ├── http.js        axios factory: bearer header + 401 retry
│           └── format.js      createFormatters(getRegion) money/date helpers
└── docs/
```

### 3.1 `packages/shared` (`@ecom/shared`)

The storefront and admin panel are separate Vite apps, but they must agree on
three things: how a 401 is refreshed, when a session is dead, and how money and
dates are rendered. Those used to be copy-pasted. They now live in one package
consumed through a local dependency:

```json
"@ecom/shared": "file:../packages/shared"
```

- **No build step.** The package ships ESM sources and an `exports` map
  (`./session`, `./http`, `./format`); Vite bundles it like app code.
- **No runtime dependency.** Code is compiled into each app's `dist/`, so
  deployment artifacts are unchanged. The `packages/` directory is only needed
  at install/build time.
- **Deliberately dependency-free at runtime.** It cannot resolve the apps'
  `node_modules`, so `http.js` receives `axios` as an injected argument and
  `session.js` uses `fetch` for the refresh call.
- **Reusable but not over-abstracted.** React contexts stay app-specific; only
  framework-agnostic logic is shared.

Both apps install the package with their normal `npm install`; the Vite configs
add `server.fs.allow: ['..']` so the dev server can read the sibling folder.

**Backend layering** is strictly one-directional:

```
api  →  services  →  repositories  →  models  →  PostgreSQL
 └────────→ schemas ┘
```

Routers never import models for writes directly when a repository exists; they
own transaction boundaries (`session.commit()` lives in the route or service).

---

## 4. Application Communication

### 4.1 Development: one origin per app

Both Vite configs proxy `/api` to the backend so the page and the API share the
browser origin:

| App | Page origin | Proxy target | API base used by code |
|---|---|---|---|
| `frontend/` | `http://localhost:5175` | `http://localhost:8001` | `/api/v1` |
| `admin/` | `http://localhost:3001` | `http://localhost:8001` | `/api/v1` |

This is not cosmetic. When either app is exposed through an ngrok tunnel
(`https://*.ngrok-free.dev`), an absolute `http://localhost:8001` call is blocked
by **Chrome Private Network Access** before CORS is ever evaluated. Routing
through the proxy avoids the block entirely, which is why
`VITE_API_URL=/api/v1` is relative. `server.allowedHosts: true` and conditional
`wss` HMR are configured for the same tunnel workflow.

### 4.2 Production

The two SPAs are static builds. They must be served from origins listed in the
backend `CORS_ORIGINS`, and `VITE_API_URL` must be set to the absolute API
origin at build time (see `deployment.md`).

### 4.3 CORS and credentials

`app/main.py` configures:

```python
CORSMiddleware(
    allow_origins=settings.cors_origins_list,   # "*" or explicit comma list
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

A custom `CatchAllExceptionsMiddleware` sits **inside** CORS so unhandled 500s
still carry CORS headers — otherwise the browser reports a misleading CORS
error instead of the real server failure.

`*` is accepted in development but rejected in production by
`validate_production_settings()`.

---

## 5. Request Lifecycle

A typical authenticated admin request:

```
1. Browser            axios interceptor attaches Authorization: Bearer <access>
2. Vite dev server    /api/v1/... → http://localhost:8001 (changeOrigin)
3. FastAPI            CatchAllExceptions → CORS → router match (/api/v1 prefix)
4. slowapi            rate-limit decorator (only on selected routes)
5. Dependency chain   oauth2_scheme → decode_access_token → load User
                      → session_is_valid (sid + token_version)
                      → require_perm("products.update")
6. Route handler      validates with a Pydantic schema
7. Service            business rules, external calls, orchestration
8. Repository         SQLModel/SQLAlchemy queries
9. PostgreSQL         transaction commit / rollback
10. Response          response_model serialisation (Decimal → JSON number/str)
```

Failure points return a uniform body:

```json
{ "detail": "Insufficient permissions" }
```

### Dependency chain (`app/api/deps.py`)

| Dependency | Guarantees |
|---|---|
| `oauth2_scheme` | Extracts `Bearer` token |
| `get_current_user` / `CurrentUser` | Valid token, active user, live session |
| `require_role(*roles)` | Legacy enum hierarchy + admin audience |
| `require_perm(*keys, require_all=True)` | Dynamic DB permission union + admin audience |
| `SessionDep` | One SQLModel session per request |

`require_perm` first calls `_assert_admin_audience()`: a **storefront-scoped
token can never reach an admin route**, even with matching permissions, because
the `aud` claim is checked before the permission union. Tokens with no `aud`
claim (pre-audience legacy sessions) are treated as admin for compatibility.

---

## 6. Authentication Model

### 6.1 Two audiences

| Audience | Issued by | Reach |
|---|---|---|
| `admin` | `POST /auth/login` (after OTP) | Admin routes + everything a customer can do |
| `storefront` | `POST /auth/login` with `audience="storefront"` | Customer routes only |

Refresh tokens store their original `scope`; `POST /auth/refresh` re-issues with
the **stored** scope, so a storefront session cannot upgrade itself to admin by
refreshing.

### 6.2 Login flows

**Shopper (storefront audience)**

```
POST /auth/login {email, password, audience:"storefront"}
  → 200 {access_token, refresh_token, token_type}
```

**Privileged (admin audience)** — password alone is not enough:

```
POST /auth/login {email, password, audience:"admin"}
  → 200 {otp_required:true, challenge_token, email_masked, expires_in}
POST /auth/login/verify-otp {challenge_token, otp_code}
  → 200 {access_token, refresh_token, token_type}
```

The challenge token is a 5-minute JWT with `type:"challenge"` — it can only be
exchanged at `/login/verify-otp`, never used as an API credential.

**Google sign-in** is supported for both; privileged Google accounts still hit
the OTP step-up, because a compromised Google account alone must not grant
admin access.

### 6.3 Session invalidation

`users.token_version` and `refresh_tokens.session_id` are both embedded in the
access token and checked by `session_is_valid()`. Rotating either invalidates
every outstanding access token for that session — used for logout-everywhere,
password change, and role changes.

---

## 7. Authorization Model

Three layers, all enforced server-side; the UI mirrors them for usability only.

1. **Legacy role enum** — `users.role ∈ {customer, staff, manager, admin}`.
2. **Dynamic RBAC** — `roles` / `permissions` / `role_permissions` / `user_roles`.
3. **API guards** — `require_perm("orders.refund")` on each route.

`GET /auth/me` returns both `role` (legacy) and `permissions[]` (union of the
user's roles). Clients prefer the permission list and fall back to the role
floor when the list is empty.

System roles are seeded from `app/core/rbac_catalog.py`:

| Role | Scope |
|---|---|
| `admin` | Every permission; unlimited refund authority |
| `manager` | Catalog, orders, refunds, COD, coupons, content, reports — no user/role/settings admin |
| `staff` | Products, categories (view), orders (view), images |
| `customer` | No admin permissions |

Custom roles are created from the same catalog in Admin → Roles.

---

## 8. Core Data Flows

### 8.1 Storefront browse (public, cache-hinted)

```
Home/PLP → GET /content/blocks            (banners, announcement)
         → GET /products?page&limit&search&category_id&sort
         → GET /reviews/products/{id}     (ratings for the page, batch-joined)
```

Product listing returns `{products, total, page, limit, total_pages}`. Rating
stats for the whole page are fetched in one extra query, not N+1.

### 8.2 Cart and guest merge

```
Guest:  localStorage cart  →  POST /cart/items {variant_id, quantity, merge_key}
Login:  createGuestCartMerger() replays local items once per merge_key
        → backend records cart_merge_receipts to stay idempotent
```

`cart_merge_receipts` makes a replayed merge a no-op, so a refresh or a second
tab cannot double-add quantities.

### 8.3 Checkout (single transaction)

```
POST /checkout {shipping_address_id, billing_address_id, payment_method}
  1. load cart + validate items / stock / active products
  2. resolve_cart_pricing()  → subtotal, coupon discount, tax, shipping, COD fee
  3. re-read store_settings (authoritative; client config is display-only)
  4. create Order + OrderItems with product/variant snapshots
  5. decrement variant stock
  6. snapshot customer + shipping + billing addresses (JSON)
  7. enqueue confirmation email (email_outbox, delivered async)
  8. create notification row
  → commit
```

Failures roll back everything; there is no partially-created order.

### 8.4 Payment

```
POST /payments/create-intent {order_id}
  → provider intent (Razorpay order / Stripe PaymentIntent) + client_secret
Client SDK confirms
POST /payments/confirm {payment_intent_id | transaction_id}
POST /webhooks/payment   (authoritative, provider-signed)
  → mark Payment succeeded → order payment_status → notify + email
```

`payment_creations` records each attempt before the provider call, so a
provider timeout can be reconciled rather than guessed at.

### 8.5 Abandoned order expiry (background)

APScheduler sweeps every `PENDING_ORDER_EXPIRY_JOB_MINUTES` (default 2):

```
orders WHERE status=pending AND payment_status=pending
       AND placed_at < now - pending_order_expiry_minutes (default 10)
  → cancel, restore stock, cancel provider intent, notify + email
```

The timeout is **store policy** (DB-overridable); the sweep cadence is an ops
env var.

### 8.6 Shipping / fulfilment

```
POST /admin/orders/{id}/shipping/create      push order to Shiprocket
POST /admin/orders/{id}/shipping/assign-awb  courier + AWB
POST /admin/orders/{id}/shipping/request-pickup
GET  /admin/orders/{id}/shipping/label|manifest|tracking
POST /webhooks/shiprocket                    tracking scans → status updates
```

`SHIPPING_PROVIDER=simulator` swaps in a local fake that still exercises the
same order fields and emits printable label/manifest HTML — used for demos and
tests. RTO scans restore stock exactly once (`orders.rto_stock_restored`).

### 8.7 Product return

```
Customer: GET  /orders/{id}/return-eligibility
          POST /orders/{id}/returns  {idempotency_key, reason, items[], description}
          POST /returns/{id}/evidence (multipart, stored privately)
Admin:    POST /admin/returns/{id}/decision  approve|reject
          POST /admin/returns/{id}/shipping/shiprocket | tracking
          POST /admin/returns/{id}/receive → inspection → refund
```

Every transition writes `return_events` (from_status, to_status, actor, note) and
`admin_audit_log` for money actions. Stock is restored only on `received` with
inspection passing.

### 8.8 COD remittance reconciliation

Two distinct concepts that are deliberately separated:

1. **Collection** — cash taken from the customer at delivery
   (`orders.cod_remittance_status`, `POST /admin/cod/orders/{id}/collect`).
2. **Remittance** — the courier's bank payout batch
   (`cod_remittances` + `cod_remittance_items`).

```
Import CSV → POST /admin/cod/remittances/import/preview  (no writes, row-by-row status)
           → POST /admin/cod/remittances/import          (persist + match)
Match statuses: matched | amount_mismatch | order_not_found | not_cod
                not_delivered | cash_not_collected | already_remitted | duplicate | adjustment
Resolve    → POST /admin/cod/remittances/{id}/resolve
Confirm    → POST /admin/cod/remittances/{id}/confirm  {utr, bank_credit_amount, ...}
Void       → POST /admin/cod/remittances/{id}/void
```

`line_hash` makes re-importing the same file idempotent. Confirmation stores the
bank UTR and computes `difference = net_expected − bank_credit_amount`; a
non-zero difference requires an explicit `accept_difference` + reason.

### 8.9 MCP agent (admin AI)

```
Admin UI → POST /mcp/chat | /mcp/chat/stream (SSE)
         → app/mcp/agent.py → LLM (Groq default, Gemini optional)
         → 23 MCP tools (read-only by default)
Writes are two-step:
  preview tool → returns preview_token
  POST /mcp/cancel | /refund | /products/update | /products/price
       | /products/delete | /inventory/adjust   with that token
```

The agent calls back into the same API over loopback
(`MCP_LOOPBACK_URL`, auto-derived from the request origin). Guards in
`app/mcp/guards.py` enforce RBAC for the calling user, so the chatbot can never
exceed the operator's own permissions.

---

## 9. Background Processing

| Job | Trigger | Work |
|---|---|---|
| `expire_pending_orders` | APScheduler interval (2 min default) | Auto-cancel unpaid online orders, restore stock |
| `deliver_email_outbox` | APScheduler interval (30 s) | Drain `email_outbox`, retry with backoff |

Both are skipped when `ENVIRONMENT=test` or the DB URL is SQLite.

> **Deployment constraint:** APScheduler runs **in-process**, so every uvicorn
> worker starts a scheduler. Each tick takes a PostgreSQL transaction-scoped
> advisory lock (`pg_try_advisory_xact_lock`); only the first worker runs the
> job and the rest skip it, so N workers no longer mean N scans or N provider
> calls. The lock releases when the job's session closes, so a crashed leader
> cannot wedge the schedule. See `deployment.md` §8.3. An external queue is
> still the right choice if jobs need retries, priorities or independent
> scaling.

Email is transactional-queue based rather than fire-and-forget: the outbox row
is committed with the business transaction, then delivered asynchronously with
`attempts`, `next_attempt_at`, `last_error`, and `expires_at` columns. An email
provider outage delays mail; it never fails an order.

---

## 10. Third-Party Integrations

| Integration | Used for | Failure mode |
|---|---|---|
| Razorpay / Stripe | Online payments, refunds | Order stays `pending`, sweeper cancels; webhook is authoritative |
| Shiprocket | Fulfilment, AWB, pickup, tracking | Admin sees the error per action; simulator available |
| Cloudinary | All public images | Upload fails loudly; existing URLs unaffected |
| Gmail SMTP / SendGrid | OTP, order, refund email | Outbox retries; OTP endpoints return 503 rather than pretend |
| Groq / Gemini | Chatbot + MCP agent | Assistant degrades; storefront still works |
| ChromaDB + fastembed | RAG context for the customer chatbot | Falls back to non-RAG answers |

All integration credentials are optional at import time and validated only when
`ENVIRONMENT=production` (`app/core/release.py`).

---

## 11. Regionalisation

One deployment serves one currency/locale, switched by configuration rather than
code:

| Setting | Effect |
|---|---|
| `PAYMENT_CURRENCY` | `INR` → Razorpay/GST/en-IN; anything else → Stripe/VAT |
| `DISPLAY_LOCALE` | Number/date grouping (derived from currency when unset) |
| `TAX_LABEL` | `GST`, `VAT`, `Sales Tax` |
| `DEFAULT_COUNTRY` | Address defaults |

`app/core/region.py` is the single formatter; `GET /checkout/config` exposes the
resolved values to clients so nothing is hardcoded in the SPAs. The storefront
loads it once at boot (`RegionGate`) before first paint settles.

---

## 12. Design Decisions Worth Knowing

| Decision | Rationale |
|---|---|
| **Money as `Decimal`** | No float drift in totals, refunds, remittances |
| **Store settings in DB** | Tax/shipping/COD/return rules change without a redeploy; env values only seed a fresh DB |
| **Snapshots on orders** | Product name/price/address are copied onto the order, so later catalog edits never rewrite history |
| **Idempotency keys** | Returns (`idempotency_key`), refunds (`idempotency_key`), COD lines (`line_hash`), cart merges (`merge_key`) |
| **Audit everything financial** | `admin_audit_log` before/after JSON on refunds, cancellations, settings, role changes |
| **Two-step AI writes** | Every destructive MCP action requires a preview token, so an LLM cannot silently mutate data |
| **Soft delete by default** | Products deactivate (`is_active`), users deactivate; hard delete is explicit and permission-gated |
| **Optimistic UI where safe** | Admin keeps cached rows and skeletons; money paths always refetch |
| **Simulators as first-class** | `PAYMENT_PROVIDER=dummy` and `SHIPPING_PROVIDER=simulator` allow full-flow demos without credentials |

---

## 13. Known Constraints

1. **In-process scheduler** — APScheduler still lives inside the API process. A
   PostgreSQL advisory lock elects one worker per tick, so jobs do not run N
   times, but there is no external queue and a stuck job occupies a worker
   thread. Move to Celery/RQ if jobs need retries, priorities or independent
   scaling.
2. **Rate limiting defaults to per-process memory** — set
   `RATE_LIMIT_STORAGE_URI=redis://…` and `REQUIRE_SHARED_RATE_LIMIT=true` when
   running more than one API process. Chat throttles are still database-backed.
3. **Local ChromaDB** — the vector index lives on disk at `CHROMA_DB_PATH` and
   is not shared between replicas; each replica needs the volume or its own
   rebuild from the product catalog.
4. **Local file storage** — public banner uploads use `UPLOADS_DIR` and return
   evidence uses `RETURN_STORAGE_DIR`; both need a shared volume with more than
   one host. Product/category/review imagery already goes to Cloudinary.
5. **Two independent frontend repos' history collapsed** into one commit each; the backend retains its 25-commit history in the original repo.

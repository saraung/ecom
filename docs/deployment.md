# Deployment and Operations

> Configuration, build, hosting and release procedure for all three applications.
> Source of truth: `backend/app/core/config.py`, `backend/app/core/release.py`,
> `backend/app/main.py`, `backend/scripts/release_check.py`, both `vite.config.js`.

---

## 1. Topology

Three deployable artifacts:

| Artifact | Type | Runtime | Scales by |
|---|---|---|---|
| `backend/` | ASGI application | Python 3.12 + uvicorn | Vertical; careful with workers (see §8.3) |
| `admin/` | Static SPA (`dist/`) | Any static host / CDN | CDN |
| `frontend/` | Static SPA (`dist/`) | Any static host / CDN | CDN |

Both SPAs must be served over **HTTPS** from origins listed in
`backend CORS_ORIGINS`, and each must have `/api/v1/*` reachable on its own
origin (reverse proxy) or via an absolute `VITE_API_URL`.

```
Internet
   │
   ├── https://shop.example.com      → static frontend/dist
   │        └── /api/*  ─┐
   ├── https://admin.example.com     → static admin/dist
   │        └── /api/*  ─┤
   │                     ▼
   └── https://api.example.com  →  uvicorn backend:8001
                                     ├── PostgreSQL
                                     ├── /uploads (disk)
                                     ├── private_storage/ (disk)
                                     └── chroma_db/ (disk)
```

A same-origin reverse proxy for `/api` is strongly recommended: it avoids CORS
entirely and keeps cookies/credentials simple. The SPAs already default to the
relative base `/api/v1`.

---

## 2. Runtime Versions (enforced)

| Tool | Requirement | Where enforced |
|---|---|---|
| Python | `3.12.x` | `pyproject.toml`, `release_check.py` |
| uv | `0.12.0` (lockfile format) | `uv lock --check` |
| Node | `>=24.18.1 <25` | `package.json` engines, `release_check.py` |
| npm | `11.x` | `package.json` engines, `release_check.py` |
| PostgreSQL | supported by psycopg2 (13+) | runtime |

`.nvmrc` in each frontend pins `24`.

---

## 3. Environment Variables — Backend

All variables are read by `app/core/config.py` (`pydantic-settings`, `.env`
supported). Unknown keys are ignored (`extra="ignore"`).

### 3.1 Required always

| Variable | Example | Notes |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@host:5432/ecom` | SQLite only for tests |
| `JWT_SECRET_KEY` | 48+ random chars | production requires ≥32 |
| `ENVIRONMENT` | `production` \| `development` \| `test` | gates validation and jobs |

### 3.2 Application

| Variable | Default | Purpose |
|---|---|---|
| `PROJECT_NAME` | `E-Commerce API` | OpenAPI title |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `15` | access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `30` | refresh token TTL |
| `CORS_ORIGINS` | `*` | comma-separated origins; `*` rejected in production |
| `FRONTEND_URL` | `http://localhost:5173` | reset/return links; must be HTTPS in production |
| `ADMIN_FRONTEND_URL` | `http://localhost:3001` | staff invite links; HTTPS in production |
| `RESET_TOKEN_EXPIRE_HOURS` | `1` | password reset validity |
| `UPLOADS_DIR` | `uploads` | relative to `backend/`; use a shared volume with >1 replica |
| `CHROMA_DB_PATH` | `./chroma_db` | MCP product index; shared volume or per-replica rebuild |
| `RATE_LIMIT_STORAGE_URI` | `memory://` | `redis://host:6379/0` when >1 API process |
| `REQUIRE_SHARED_RATE_LIMIT` | `false` | `true` makes production boot fail if the limiter is in-memory |

### 3.3 Regionalisation

| Variable | Default | Purpose |
|---|---|---|
| `PAYMENT_CURRENCY` | `INR` | single currency for the deployment |
| `DISPLAY_LOCALE` | derived | number/date grouping (`en-IN`, `en-US`) |
| `TAX_LABEL` | derived | `GST` for INR, `VAT` otherwise |
| `DEFAULT_COUNTRY` | `India` | address defaults |
| `STORE_SUPPORT_PHONE` | placeholder | shown in chat/receipts |

Stripe is expected for non-INR; Razorpay for INR. The pairing is validated in
production only by provider credentials, not by currency.

### 3.4 Payments

| Variable | Notes |
|---|---|
| `PAYMENT_PROVIDER` | `dummy` \| `razorpay` \| `stripe`; production allows only razorpay/stripe |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `RAZORPAY_WEBHOOK_SECRET` | required when Razorpay |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | required when Stripe |

Keep the previous provider's credentials until all historical attempts/refunds
are resolved — provider API calls need them.

### 3.5 Shipping

| Variable | Default | Notes |
|---|---|---|
| `SHIPPING_PROVIDER` | `simulator` | production requires `shiprocket` |
| `SHIPROCKET_EMAIL`, `SHIPROCKET_PASSWORD` | — | API login |
| `SHIPROCKET_PICKUP_LOCATION` | `Primary` | warehouse nickname |
| `SHIPROCKET_PICKUP_PINCODE` | `110001` | must match the provider account |
| `SHIPROCKET_WEBHOOK_TOKEN` | — | must match the value configured at Shiprocket |

### 3.6 Email

| Variable | Notes |
|---|---|
| `EMAIL_PROVIDER` | `gmail` \| `sendgrid`; unset = auto-detect (Gmail wins if configured) |
| `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD` | Gmail SMTP (App Password, not the account password) |
| `SENDGRID_API_KEY` | when using SendGrid |
| `FROM_EMAIL` | verified sender |

If the email provider fails while an OTP must be sent, the API returns **503**.
Transactional mail is queued in `email_outbox` and retried, so an outage delays
mail but never blocks an order.

### 3.7 Media

| Variable | Notes |
|---|---|
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | required in production |
| `CLOUDINARY_SECURE` | default `true` |

`uploads/` serves content images; `private_storage/returns/` holds return
evidence and is **never** publicly served.

### 3.8 Store policy (seeded defaults)

These affect only a fresh database (startup seed) or the DB-outage fallback. Once
`store_settings` has a row, the DB wins and Admin → Store Settings is the control
surface.

| Variable | Default |
|---|---|
| `TAX_RATE` | `0.18` |
| `FREE_SHIPPING_THRESHOLD` | `1000.00` |
| `SHIPPING_COST` | `50.00` |
| `COD_FEE` | `50.00` |
| `COD_MIN_ORDER_VALUE` | `0.00` |
| `COD_MAX_ORDER_VALUE` | `10000.00` |
| `RESTOCKING_FEE_PENDING` | `0.0` |
| `RESTOCKING_FEE_CONFIRMED` | `5.0` |
| `RESTOCKING_FEE_PROCESSING` | `15.0` |
| `REFUND_PROCESSING_DAYS` | `5` |
| `PENDING_ORDER_EXPIRY_MINUTES` | `10` |

### 3.9 Background jobs

| Variable | Default | Notes |
|---|---|---|
| `PENDING_ORDER_EXPIRY_JOB_MINUTES` | `2` | sweep cadence (ops concern, not store policy) |
| `COD_REMITTANCE_SIMULATOR_ENABLED` | `false` | must be explicit in production |

### 3.10 Returns

| Variable | Default | Notes |
|---|---|---|
| `RETURNS_ENABLED` | `true` | global switch |
| `RETURN_WINDOW_DAYS` | unset | days after delivery; unset = no window enforced |
| `RETURN_EXCLUDED_VARIANT_IDS` | `[]` | JSON/comma list |
| `RETURN_REQUIRED_PHOTO_REASONS` | `[]` | reasons requiring evidence |
| `RETURN_FEE_PERCENT` | `0` | restocking percentage |
| `RETURN_MAX_IMAGES` | `6` | |
| `RETURN_IMAGE_MAX_BYTES` | `5242880` | 5 MB |
| `RETURN_STORAGE_DIR` | `private_storage/returns` | disk path |

### 3.11 AI / chat

| Variable | Default | Notes |
|---|---|---|
| `GROQ_API_KEY` | — | required in production (default provider) |
| `GEMINI_API_KEY` | — | if `MCP_LLM_PROVIDER=gemini` |
| `MCP_LLM_PROVIDER` | `groq` | `groq` \| `gemini` |
| `MCP_LLM_MODEL` | provider default | override model id |
| `CHAT_MESSAGES_PER_MINUTE` | `10` | per principal |
| `CHAT_SESSIONS_PER_MINUTE` | `5` | per principal |
| `CHAT_GLOBAL_MESSAGES_PER_MINUTE` | `100` | instance-wide |
| `CHAT_SESSION_TTL_HOURS` | `24` | |
| `MCP_LOOPBACK_URL` | auto | force the internal loopback origin behind proxies |

### 3.12 Google OAuth

| Variable | Notes |
|---|---|
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | server-side token verification; the same client id is used by both SPAs |

---

## 4. Environment Variables — Frontends

Build-time only (Vite inlines `VITE_*` at build; changing them requires a
rebuild).

### `frontend/`

| Variable | Dev | Production |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8001/api/v1` | absolute API origin (no proxy required) |
| `VITE_GOOGLE_CLIENT_ID` | client id | same |
| `VITE_RAZORPAY_KEY_ID` | test key | live key matching backend |
| `VITE_STRIPE_PUBLISHABLE_KEY` | `pk_test_…` | `pk_live_…` matching backend |

### `admin/`

| Variable | Notes |
|---|---|
| `VITE_API_URL` | `http://localhost:8001/api/v1` (direct; no Vite proxy) |
| `VITE_GOOGLE_CLIENT_ID` | same client id |

Optional: `NGROK_HOST` is no longer used; the dev server runs without proxy or
host-header exceptions.

> **Never put a secret in a `VITE_*` variable.** Everything prefixed `VITE_` is
> embedded in the public bundle. Only publishable keys belong there.

---

## 5. Production Configuration Gates

`app/core/release.py → validate_production_settings()` runs at startup when
`ENVIRONMENT=production` and refuses to boot on any of:

| Check | Requirement |
|---|---|
| DB engine | PostgreSQL (not SQLite) |
| `JWT_SECRET_KEY` | ≥ 32 characters |
| `CORS_ORIGINS` | explicit list, no `*` |
| `PAYMENT_PROVIDER` | `stripe` or `razorpay` (not `dummy`) |
| Provider credentials | all three keys for the chosen provider |
| `SHIPPING_PROVIDER` | `shiprocket` (not `simulator`) |
| Shiprocket | email, password, webhook token |
| `GROQ_API_KEY` | present |
| Cloudinary | cloud name, key, secret |
| Email | Gmail pair or SendGrid key |
| `FRONTEND_URL`, `ADMIN_FRONTEND_URL` | must start with `https://` |
| `REQUIRE_SHARED_RATE_LIMIT` | optional: if `true`, `RATE_LIMIT_STORAGE_URI` must not be `memory://` |

Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are disabled
automatically when `ENVIRONMENT=production`; they remain available in
development. Security headers (`nosniff`, `DENY` framing, referrer policy,
permissions policy, HSTS) are added by `SecurityHeadersMiddleware`.

Failure is fatal:

```
RuntimeError: Production configuration invalid: CORS_ORIGINS must list explicit
browser origins; SHIPPING_PROVIDER must be shiprocket in production; ...
```

`assert_database_ready(engine)` then verifies `SELECT 1` **and** that the applied
Alembic revision set exactly equals the single expected head:

```
RuntimeError: Database migration revision does not match this release
```

The application **never auto-migrates** and never stamps a revision.

---

## 6. Build

### Backend

```bash
cd backend
uv sync --locked                 # exact lockfile install
uv run alembic upgrade head      # run in the deploy job, not at startup
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Artifacts to ship: the source tree (or a wheel), `pyproject.toml`, `uv.lock`,
`alembic.ini`, `alembic/`. Runtime state (`uploads/`, `private_storage/`,
`chroma_db/`) lives outside the artifact.

### Admin and storefront

```bash
cd admin && npm ci --include=dev && npm run build       # → admin/dist
cd frontend && npm ci --include=dev && npm run build    # → frontend/dist
```

Both apps depend on the local package `@ecom/shared`
(`file:../packages/shared`), so:

- the `packages/` directory must be present next to `admin/` and `frontend/`
  **when installing and building**;
- `package-lock.json` must be regenerated (`npm install`) whenever the shared
  package's `package.json` or `exports` change — otherwise `npm ci` fails with
  a lockfile mismatch;
- the built `dist/` is self-contained: shared code is bundled at build time, so
  the static host does not need `packages/`.

Serve `dist/` as static files. Both are true SPAs: unknown paths must rewrite to
`index.html`.

Verify a bundle was built with the right API origin:

```bash
grep -ro "https://api\.example\.com" admin/dist | head
```

### Full release pre-check

```bash
cd backend
.venv/bin/python -m scripts.release_check \
  --storefront ../frontend \
  --admin ../admin
```

It verifies the runtime versions, `uv lock --check`, locked install,
`uv pip check`, the full pytest suite, one Alembic head, whitespace
(`git diff --check`), then `npm ci` + `check:release` (test → scoped lint →
build) for both frontends.

---

## 7. Hosting Configurations

### 7.1 Reverse proxy (nginx)

```nginx
server {
  listen 443 ssl http2;
  server_name api.example.com;

  client_max_body_size 12m;          # image uploads (return evidence ≤ 5 MB default)

  location / {
    proxy_pass         http://127.0.0.1:8001;
    proxy_http_version 1.1;
    proxy_set_header   Host              $host;
    proxy_set_header   X-Real-IP         $remote_addr;
    proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
  }

  # WebSocket: notifications
  location /api/v1/notifications/ws {
    proxy_pass         http://127.0.0.1:8001;
    proxy_http_version 1.1;
    proxy_set_header   Upgrade    $http_upgrade;
    proxy_set_header   Connection "upgrade";
    proxy_read_timeout 3600s;
  }

  # SSE: MCP streaming
  location /api/v1/mcp/chat/stream {
    proxy_pass         http://127.0.0.1:8001;
    proxy_http_version 1.1;
    proxy_buffering    off;
    proxy_read_timeout 600s;
  }
}
```

### 7.2 Same-origin SPA hosting

```nginx
server {
  listen 443 ssl http2;
  server_name shop.example.com;

  root /var/www/ecom/frontend;
  index index.html;

  location /api/ { proxy_pass http://127.0.0.1:8001; }   # same-origin API
  location /     { try_files $uri /index.html; }         # SPA fallback
}
```

Repeat for `admin.example.com` with `root /var/www/ecom/admin`.

With this setup, `CORS_ORIGINS` is not exercised at all for same-origin calls,
but it must still list both origins because absolute links and tooling use them.

### 7.3 Persistent volumes

| Path | Contents | Notes |
|---|---|---|
| `backend/uploads/` | Content/banner images | Must survive deploys; served at `/uploads` |
| `backend/private_storage/` | Return evidence | **Never** expose via the proxy; authenticate downloads |
| `backend/chroma_db/` | Vector store for RAG | Rebuildable, but slow to rebuild |

Cloudinary holds the public product/category/review media, so `uploads/` only
covers content blocks.

---

## 8. Runtime Behaviour and Constraints

### 8.1 Startup sequence

1. Load settings (`config.py`).
2. If production: validate configuration.
3. If production: assert DB connectivity + exact Alembic head.
4. Start the MCP session manager (`/mcp` mount).
5. Seed `store_settings` singleton (non-fatal outside production).
6. Start APScheduler (skipped for `test`/SQLite).
7. Serve.

### 8.2 Health endpoints

| Path | Meaning |
|---|---|
| `GET /health/live` | Process is alive → `{"status":"alive"}` |
| `GET /health/ready` | Config valid, DB reachable, migrations match, scheduler jobs registered (production) → `200 {"status":"ready"}`; otherwise `503 {"status":"not_ready"}` |

Readiness deliberately leaks no detail. Use it for load-balancer gating and for
smoke tests after a deploy. It does **not** prove provider credentials are
accepted or that email is being delivered.

### 8.3 Workers and background jobs

APScheduler runs **inside the application process**, and every uvicorn worker
starts its own scheduler. To stop N workers from each scanning (and each calling
the payment provider), both jobs run through a **PostgreSQL transaction-scoped
advisory lock** (`_run_as_scheduler_leader` in `app/main.py`):

- the first worker to acquire the lock for a tick runs the job;
- every other worker skips that tick immediately;
- the lock is released when the job's session commits/closes, so a crashed
  leader never blocks the next tick;
- SQLite (tests/local) bypasses the lock and runs in-process as before.

The job bodies are also individually idempotent (`FOR UPDATE SKIP LOCKED` for
the email outbox, row locks for order expiry), so the lock is defence in depth,
not the only protection.

**Recommended:** any number of API workers is now safe. Keep the sweep cadence
(`PENDING_ORDER_EXPIRY_JOB_MINUTES`) low enough that a skipped tick is harmless.
Monitor job failures; readiness reports missing jobs in production.

### 8.4 Signals and graceful shutdown

The lifespan context stops the scheduler with `shutdown(wait=False)` on exit.
Give the process a termination grace period longer than the 30-second outbox
interval so in-flight deliveries complete.

---

## 9. Release Procedure

1. **Freeze artifacts.** Backend source + `uv.lock`, both frontend `dist/`
   bundles + lockfiles, and the migration head must come from the same commit.
2. **Back up.** PostgreSQL dump **and** `uploads/` + `private_storage/`.
   Rehearse the restore on an isolated clone — a backup you have not restored is
   a hypothesis.
3. **Rehearse migrations** on the clone:
   ```bash
   uv run --locked alembic upgrade head
   uv run --locked alembic heads          # exactly one
   ```
4. **Migrate production** as a separate step, before starting new workers:
   ```bash
   uv run --locked alembic upgrade head
   ```
   Do not stamp to bypass a failure. Prefer roll-forward.
5. **Deploy.** Start the backend, wait for `/health/ready` → `200`.
6. **Deploy SPAs.** Publish `dist/` with the correct `VITE_API_URL`.
7. **Smoke test** (see §10).
8. **Monitor** for 30 minutes: error rate, 401/403 spikes, outbox age, stuck
   `payment_creations.submitting`, pending refunds, readiness flaps.

### Rollback

- **Application**: redeploy the previous bundle. If the old code is incompatible
  with the new schema, roll forward instead.
- **Schema**: avoid downgrades once new money movements exist. Restoring a DB
  backup after payments requires provider reconciliation, not a blind restore.
- **Feature kill-switches** (no redeploy needed): `COD_REMITTANCE_SIMULATOR_ENABLED`,
  `RETURNS_ENABLED`, `SHIPPING_PROVIDER`, `PAYMENT_PROVIDER` (with credentials),
  and all store policy values via Admin → Store Settings.

---

## 10. Post-Deploy Smoke Checklist

- [ ] `GET /health/ready` → 200
- [ ] `GET /api/v1/checkout/config` returns the expected currency/locale
- [ ] Storefront home loads with live banners (or documented fallback)
- [ ] Product list pagination and search return results
- [ ] Add to cart → totals match the server
- [ ] Guest cart survives login and is not duplicated
- [ ] Checkout with the test provider creates an order and a payment row
- [ ] Signed payment webhook is accepted; order becomes `paid`
- [ ] Admin login triggers the OTP challenge; wrong code is rejected
- [ ] Admin order status transition works and is audited
- [ ] Shipping simulator (or Shiprocket sandbox) produces a label
- [ ] Return request + evidence upload + admin decision round-trips
- [ ] COD import preview classifies rows without writing
- [ ] Notification WebSocket connects; bell updates
- [ ] Chat/MCP answers, and a destructive tool requires confirmation
- [ ] `uploads/` images render after a redeploy (volume persisted)
- [ ] Return evidence download requires auth (direct URL returns 404)

---

## 11. Monitoring and Alerts

| Signal | Why | Suggested alert |
|---|---|---|
| `/health/ready` non-200 | Config/DB/migration/scheduler failure | 2 consecutive failures |
| 5xx rate | Unhandled errors | >1% for 5 min |
| 401/403 rate | Token/audience or permission regressions | 3× baseline |
| `email_outbox` due age | Mail outage | oldest unsent > 15 min |
| `email_outbox.attempts` | Poison messages | any row > 5 attempts |
| `payment_creations.state='submitting'` | Provider timeouts needing reconciliation | any older than 10 min |
| Refunds `pending_approval` | Money waiting on a human | oldest > 24 h |
| Refunds `failed` | Provider rejection | any new |
| COD `awaiting_remittance` age | Cash in hand too long | oldest > 14 days |
| Scheduler job absence | Jobs stopped | readiness flap or log error |
| Chat 429/503 rate | Limits or LLM outage | sustained >5 min |
| Disk on `uploads/`, `private_storage/`, `chroma_db/` | Silent write failures | >80% |

Log hygiene: never log `Authorization`, cookies, capability tokens, reset/invite
links, or raw chat session ids.

---

## 12. Security Checklist

- [ ] `JWT_SECRET_KEY` ≥ 32 random chars, unique per environment, rotated on
      compromise (rotation invalidates all sessions).
- [ ] `CORS_ORIGINS` explicit; no `*` in production.
- [ ] HTTPS on all three hosts; HSTS at the proxy.
- [ ] `.env` not in the artifact and not readable by the static host.
- [ ] Only publishable keys in `VITE_*`.
- [ ] Webhook endpoints reachable but verified by provider signature/token.
- [ ] `private_storage/` blocked at the proxy (only the authenticated download
      endpoint serves evidence).
- [ ] Database least-privilege user; migrations run by a separate role if
      possible.
- [ ] Backups encrypted and restore-tested.
- [ ] Client secrets and personal data retention reviewed
      (`admin_audit_log.ip_address`, chat history, reset tokens).

---

## 13. Local Development Reference

```bash
# backend
cd backend
uv sync
cp .env.example .env 2>/dev/null || true   # or restore your .env
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8001

# admin
cd admin && npm install && npm run dev     # :3001

# storefront
cd frontend && npm install && npm run dev  # :5175
```

Both frontends call the backend directly at `http://localhost:8001/api/v1`.
`backend/.env` must list both dev origins in
`CORS_ORIGINS=http://localhost:5175,http://localhost:3001`.

---

## 14. Known Deployment Risks

1. **In-process scheduler** — see §8.3.
2. **Local disk state** — `uploads/`, `private_storage/`, `chroma_db/` are not
   shared across replicas; run a single backend instance or mount shared storage.
3. **`/uploads` is unauthenticated** — it serves content images only; keep
   private files out of that directory.
4. **No automated rollback of migrations** — roll-forward is the supported path.
5. **Provider sandbox ≠ production** — signature verification, refund recovery
   and webhook retries must be tested against real sandboxes before go-live.

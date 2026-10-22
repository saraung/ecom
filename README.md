# ecom

Full-stack e-commerce platform: a FastAPI backend serving a customer storefront
and a staff admin dashboard.

```
ecom/
├── backend/    FastAPI API, business logic, DB models, MCP agent
├── admin/      Staff/admin dashboard (React)
├── frontend/   Customer storefront (React)
├── packages/   shared code used by both SPAs (@ecom/shared)
└── docs/       API specifications and architecture notes
```

## Layout

| Folder | Stack | Dev port | Purpose |
|---|---|---|---|
| `backend/` | FastAPI · SQLModel · PostgreSQL · Alembic | `8001` | API, auth, catalog, carts, orders, payments, inventory, returns, COD, MCP agent |
| `admin/` | React 19 · Vite · TanStack Query · Tailwind | `3001` | Products, inventory, orders, users, refunds, analytics, RBAC |
| `frontend/` | React 19 · Vite · TanStack Query · Tailwind | `5175` | Product listings, search, cart, checkout, orders, profile |
| `packages/shared/` | ESM, no build step | — | Session refresh, axios client factory, regionalised formatters |

Both frontends call the backend directly at `http://localhost:8001/api/v1`
(configured via `VITE_API_URL`); the backend allows the two dev origins through
`CORS_ORIGINS`.

## Setup

`backend/` uses [uv](https://docs.astral.sh/uv/) (Python 3.12):

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8001
```

`admin/` and `frontend/` use Node 24. Install from inside each app; `npm`
links the sibling `packages/shared` package automatically:

```bash
cd admin     # or frontend
npm install
npm run dev
```

Each app reads configuration from its own `.env` (not committed). Copy from
your existing environment or ask a teammate for the keys.

## Checks

```bash
cd backend && uv run --group test pytest   # test suite
cd admin && npm run check:release    # test + lint + build
cd frontend && npm run check:release
```

## Documentation

| Document | Contents |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | System architecture, communication, tech stack, data flows |
| [`docs/backend-api.md`](docs/backend-api.md) | All 212 endpoints, auth, examples, error codes |
| [`docs/frontend.md`](docs/frontend.md) | Storefront pages, components, routing, state, API layer |
| [`docs/admin.md`](docs/admin.md) | Admin pages, permissions, dashboard, product/order management |
| [`docs/database.md`](docs/database.md) | Tables, relationships, indexes, migrations |
| [`docs/deployment.md`](docs/deployment.md) | Environment variables, hosting, build and release steps |

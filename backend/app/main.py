from contextlib import AsyncExitStack, asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text as sql_text
from sqlmodel import Session
from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.core.release import validate_production_settings, assert_database_ready
from app.core.rate_limit import limiter
from app.api.v1.router import api_router
from app.db.database import engine
from app.services.order_expiry import expire_stale_pending_orders
from app.services.email_outbox import deliver_pending_emails
from app.mcp.server import mcp, mcp_app


def _deliver_email_outbox_once():
    try:
        with Session(engine) as session:
            deliver_pending_emails(session)
    except Exception as exc:
        print(f"Email outbox delivery failed: {exc}")


def _sweep_expired_orders_once() -> None:
    """Auto-cancel abandoned unpaid online orders."""
    try:
        with Session(engine) as session:
            result = expire_stale_pending_orders(session)

        if result["cancelled"]:
            print(
                f"🧹 Auto-cancelled {result['cancelled']} abandoned order(s): "
                f"{', '.join(result['order_numbers']) or '-'}"
            )

    except Exception as e:
        print(f"❌ Order-expiry sweep failed: {e}")


#: Arbitrary but stable int64 key for the scheduler advisory lock.
_SCHEDULER_LOCK_KEY = 0x45434F4D  # "ECOM"


def _run_as_scheduler_leader(job, label: str):
    """
    Run an APScheduler job on exactly one process.

    BackgroundScheduler lives inside the API process, so every uvicorn worker
    starts its own copy. The jobs are individually idempotent, but N workers
    still mean N scans (and N provider calls). A PostgreSQL transaction-scoped
    advisory lock makes the job a cluster-wide singleton per tick: the first
    worker to acquire it runs the job, everyone else skips immediately. The
    lock is released when the session commits/closes, so a crashed leader does
    not block the next tick.

    SQLite (tests/local) has no advisory locks and runs a single process, so
    the job runs directly.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        return job()

    try:
        with Session(engine) as lock_session:
            acquired = lock_session.execute(
                sql_text("SELECT pg_try_advisory_xact_lock(:key)"),
                {"key": _SCHEDULER_LOCK_KEY},
            ).scalar()

            if not acquired:
                return None

            return job()

    except Exception as exc:
        # A transient DB outage must not kill the scheduler thread; the next
        # tick retries. Never let this raise into APScheduler.
        print(f"⚠️ Scheduler lock for {label} failed: {exc}")
        return None


def _deliver_email_outbox():
    _run_as_scheduler_leader(_deliver_email_outbox_once, "email outbox")


def _sweep_expired_orders():
    _run_as_scheduler_leader(_sweep_expired_orders_once, "order expiry")


_scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    production = settings.ENVIRONMENT.lower() == "production"

    if production:
        validate_production_settings(settings)
        assert_database_ready(engine)

    # ---------------------------------------------------------
    # MCP SESSION MANAGER
    # ---------------------------------------------------------
    #
    # Because the MCP application is mounted inside this FastAPI
    # application, the MCP application's own lifespan does not
    # automatically run.
    #
    # Therefore the host FastAPI lifespan must explicitly start
    # the MCP session manager.
    #
    async with AsyncExitStack() as stack:
        # The session manager is one-shot per process. Tests build many
        # TestClient instances against the same module-level MCP server and
        # never exercise the /mcp HTTP mount, so they skip it; every real
        # run (development, production) starts it exactly once.
        if settings.ENVIRONMENT != "test":
            await stack.enter_async_context(mcp.session_manager.run())

        # Disabled during tests (or when a sqlite test DB is in use)
        # so a stray interval job never touches the database.
        started = False

        uses_test_db = settings.DATABASE_URL.startswith("sqlite")

        if settings.ENVIRONMENT == "test" or uses_test_db:
            yield
            return

        # Guarantee the store_settings singleton exists before serving,
        # so request handlers (notably GET) never have to write.
        # A failed seed never crashes boot — reads degrade to env defaults.
        try:
            from app.core.store_settings import seed_store_settings

            with Session(engine) as session:
                seed_store_settings(session)

        except Exception as exc:
            if production:
                raise RuntimeError(
                    "Production store-policy initialization failed"
                ) from exc

            print(
                f"⚠️ store_settings startup seed failed "
                f"({type(exc).__name__}: {exc})"
            )

        # ---------------------------------------------------------
        # BACKGROUND JOBS
        # ---------------------------------------------------------

        _scheduler.add_job(
            _sweep_expired_orders,
            "interval",
            minutes=settings.PENDING_ORDER_EXPIRY_JOB_MINUTES,
            id="expire_pending_orders",
            replace_existing=True,
        )

        _scheduler.add_job(
            _deliver_email_outbox,
            "interval",
            seconds=30,
            id="deliver_email_outbox",
            replace_existing=True,
            max_instances=1,
        )

        _scheduler.start()
        started = True

        print(
            f"🧹 Order-expiry sweep started: every "
            f"{settings.PENDING_ORDER_EXPIRY_JOB_MINUTES} min "
            f"(auto-cancel after "
            f"{settings.PENDING_ORDER_EXPIRY_MINUTES} min)"
        )

        try:
            yield

        finally:
            if started:
                _scheduler.shutdown(wait=False)


#: Interactive docs/OpenAPI are a development convenience; exposing the full
#: schema in production is an unnecessary information leak.
_expose_docs = settings.ENVIRONMENT.lower() != "production"

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan,
    docs_url="/docs" if _expose_docs else None,
    redoc_url="/redoc" if _expose_docs else None,
    openapi_url="/openapi.json" if _expose_docs else None,
)

app.state.limiter = limiter

app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)


class CatchAllExceptionsMiddleware:
    """
    Converts unhandled exceptions into a JSON 500 response.

    Without this, an unhandled 500 is sent by Starlette's OUTERMOST
    error middleware — bypassing CORSMiddleware — so the response has
    no CORS headers and the browser reports a misleading CORS error
    instead of the real 500.

    Registered INNER to CORSMiddleware (added before it), so its
    responses still get CORS headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)

        except Exception as exc:
            print(
                f"❌ Unhandled error on "
                f"{scope.get('method')} "
                f"{scope.get('path')}: "
                f"{type(exc).__name__}: {exc}"
            )

            try:
                response = JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Internal server error"
                    },
                )

                await response(
                    scope,
                    receive,
                    send,
                )

            except Exception:
                # Response already started — nothing more we can do.
                pass


class SecurityHeadersMiddleware:
    """Baseline headers every production response should carry.

    HSTS is only emitted in production: sending it from a local HTTP dev
    server would pin `http://localhost` in the browser. CSP is deliberately
    not set here — the SPAs load Stripe, Razorpay and Google scripts, so a
    meaningful policy needs to be authored per deployment.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
                headers.setdefault(
                    "Permissions-Policy",
                    "camera=(), microphone=(), geolocation=()",
                )
                if settings.ENVIRONMENT.lower() == "production":
                    headers.setdefault(
                        "Strict-Transport-Security",
                        "max-age=31536000; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_with_headers)


# ---------------------------------------------------------
# MIDDLEWARE
# ---------------------------------------------------------

# Inner middleware first...
app.add_middleware(
    CatchAllExceptionsMiddleware
)

app.add_middleware(
    SecurityHeadersMiddleware
)

# ...then CORS (added last = outermost after Starlette's
# error middleware, so it stamps CORS headers on every response,
# including our JSON 500s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Debug: Print CORS settings
print(
    f"CORS_ORIGINS: {settings.CORS_ORIGINS}"
)

print(
    f"CORS_ORIGINS_LIST: "
    f"{settings.cors_origins_list}"
)

print(
    f"MCP_LOOPBACK_URL: "
    f"{settings.MCP_LOOPBACK_URL or '(auto: request origin)'}"
)


# ---------------------------------------------------------
# EXISTING API ROUTES
# ---------------------------------------------------------

app.include_router(
    api_router,
    prefix="/api/v1",
)


# ---------------------------------------------------------
# MCP
# ---------------------------------------------------------
#
# The MCP server is now part of the same FastAPI application.
#
# Client endpoint:
#
#     http://127.0.0.1:8000/mcp
#
# The MCP session manager is started inside the FastAPI
# lifespan above.
#
app.mount(
    "/mcp",
    mcp_app,
)


# ---------------------------------------------------------
# USER UPLOADS
# ---------------------------------------------------------

# User-uploaded content (banner/hero images).
# Served straight from disk; back up the uploads/ dir —
# it is user content, not code.
#
# The directory is created on boot so a fresh clone serves
# (empty) instead of 500ing.

from pathlib import Path as _Path  # noqa: E402

from fastapi.staticfiles import StaticFiles  # noqa: E402


_UPLOADS_DIR = _Path(settings.UPLOADS_DIR)
if not _UPLOADS_DIR.is_absolute():
    # Relative paths are resolved against the backend root, not the process
    # CWD, so the same .env works under systemd/uvicorn/docker.
    _UPLOADS_DIR = _Path(__file__).resolve().parent.parent / _UPLOADS_DIR

_UPLOADS_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


app.mount(
    "/uploads",
    StaticFiles(
        directory=str(_UPLOADS_DIR)
    ),
    name="uploads",
)


# ---------------------------------------------------------
# ROOT
# ---------------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "E-Commerce API",
        "environment": settings.ENVIRONMENT,
        "payment_provider": settings.PAYMENT_PROVIDER,
    }


# ---------------------------------------------------------
# HEALTH CHECKS
# ---------------------------------------------------------

@app.get("/health/live")
def liveness():
    return {
        "status": "alive"
    }


@app.get("/health/ready")
def readiness():
    try:
        validate_production_settings(settings)
        assert_database_ready(engine)

        if settings.ENVIRONMENT.lower() == "production":

            if (
                not _scheduler.running
                or any(
                    _scheduler.get_job(key) is None
                    for key in (
                        "expire_pending_orders",
                        "deliver_email_outbox",
                    )
                )
            ):
                raise RuntimeError(
                    "Commerce background jobs unavailable"
                )

        return {
            "status": "ready"
        }

    except Exception:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not_ready"
            },
        )


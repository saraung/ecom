"""Read-only production configuration and migration readiness gates."""
from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


def validate_production_settings(config):
    if config.ENVIRONMENT.lower() != "production":
        return
    errors = []
    if make_url(config.DATABASE_URL).get_backend_name() != "postgresql":
        errors.append("DATABASE_URL must use PostgreSQL")
    if len(config.JWT_SECRET_KEY.strip()) < 32:
        errors.append("JWT_SECRET_KEY must be a deployment secret of at least 32 characters")
    if not config.cors_origins_list or "*" in config.cors_origins_list:
        errors.append("CORS_ORIGINS must list explicit browser origins")
    if config.REQUIRE_SHARED_RATE_LIMIT and config.RATE_LIMIT_STORAGE_URI.startswith("memory://"):
        errors.append(
            "RATE_LIMIT_STORAGE_URI must use shared storage (e.g. redis://) "
            "when REQUIRE_SHARED_RATE_LIMIT is true"
        )
    provider = config.PAYMENT_PROVIDER.lower()
    required = {"stripe": ("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "STRIPE_WEBHOOK_SECRET"),
                "razorpay": ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET", "RAZORPAY_WEBHOOK_SECRET")}
    if provider not in required:
        errors.append("PAYMENT_PROVIDER must be stripe or razorpay in production")
    else:
        errors.extend(f"{key} is required" for key in required[provider] if not str(getattr(config, key) or "").strip())
    if config.SHIPPING_PROVIDER.lower() != "shiprocket":
        errors.append("SHIPPING_PROVIDER must be shiprocket in production")
    for key in ("SHIPROCKET_EMAIL", "SHIPROCKET_PASSWORD", "SHIPROCKET_WEBHOOK_TOKEN", "GROQ_API_KEY"):
        if not str(getattr(config, key) or "").strip():
            errors.append(f"{key} is required")
    for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        if not str(getattr(config, key) or "").strip():
            errors.append(f"{key} is required")
    email = (config.EMAIL_PROVIDER or ("gmail" if config.GMAIL_ADDRESS and config.GMAIL_APP_PASSWORD else "sendgrid")).lower()
    if email == "gmail":
        if not str(config.GMAIL_ADDRESS or "").strip() or not str(config.GMAIL_APP_PASSWORD or "").strip():
            errors.append("Gmail address and app password are required")
    elif email != "sendgrid" or not str(config.SENDGRID_API_KEY or "").strip():
        errors.append("A configured Gmail or SendGrid email provider is required")
    for key in ("FRONTEND_URL", "ADMIN_FRONTEND_URL"):
        if not getattr(config, key).startswith("https://"):
            errors.append(f"{key} must be the HTTPS production frontend URL")
    if errors:
        raise RuntimeError("Production configuration invalid: " + "; ".join(errors))


def migration_heads():
    heads = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads()
    if len(heads) != 1:
        raise RuntimeError("Release requires exactly one Alembic head")
    return tuple(heads)


def assert_database_ready(engine):
    expected = migration_heads()
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        applied = MigrationContext.configure(connection).get_current_heads()
    if set(applied) != set(expected):
        raise RuntimeError("Database migration revision does not match this release")

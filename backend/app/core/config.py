from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


#: Canonical store-policy defaults — the SINGLE source of truth for every
#: other default in the system (pydantic fields below, SQLModel field
#: defaults, the snapshot fallback, fresh-DB seeds). Values match the live
#: production row (verified 2026-10-01, incl. the 10-minute unpaid-order
#: expiry the old code default of 30 had drifted from). Change a default
#: here, not in four places. Runtime values still come from the
#: `store_settings` DB row once it exists — these only seed fresh
#: databases and back the DB-outage fallback.
STORE_DEFAULTS: dict = {
    "tax_rate": 0.18,
    "free_shipping_threshold": 1000.00,
    "shipping_cost": 50.00,
    "cod_fee": 50.00,
    "cod_min_order_value": 0.00,
    "cod_max_order_value": 10000.00,
    "restocking_fee_pending": 0.0,
    "restocking_fee_confirmed": 5.0,
    "restocking_fee_processing": 15.0,
    "refund_processing_days": 5,
    "pending_order_expiry_minutes": 10,
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # App
    PROJECT_NAME: str = "E-Commerce API"
    ENVIRONMENT: str = "development"

    # DB
    DATABASE_URL: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: str = "*"

    # ========== Operations / horizontal scaling ==========
    # Public banner uploads. Point at a shared volume when running more than
    # one API replica; otherwise only the replica that received an upload can
    # serve it.
    UPLOADS_DIR: str = "uploads"
    # ChromaDB persistence directory for the MCP product index. Point at a
    # shared volume (or rebuild per replica) when scaling out.
    CHROMA_DB_PATH: str = "./chroma_db"
    # slowapi storage. "memory://" is per-process; use
    # "redis://host:6379/0" when more than one API process serves traffic so
    # that rate limits and login throttles are shared.
    RATE_LIMIT_STORAGE_URI: str = "memory://"
    # When true, production boot refuses an in-memory rate limiter. Enable it
    # for any deployment with more than one API process/replica.
    REQUIRE_SHARED_RATE_LIMIT: bool = False

    # Payment
    PAYMENT_PROVIDER: str = "dummy"
    # THE currency switch for the whole deployment (INR | EUR | USD …).
    # Providers charge in this currency and every display layer formats
    # from it — see app/core/region.py. Pair with PAYMENT_PROVIDER:
    # razorpay for INR, stripe for anything else.
    PAYMENT_CURRENCY: str = "INR"

    # ========== Regionalization (one currency/locale per deployment) ==========
    # BCP-47 locale for number/date grouping. Unset = derived from currency
    # (en-IN for INR with lakh/crore grouping, en-US otherwise).
    DISPLAY_LOCALE: str | None = None
    # Customer-facing tax name. Unset = derived (GST for INR, VAT otherwise);
    # set explicitly for cases like US "Sales Tax".
    TAX_LABEL: str | None = None
    # Store home country: address defaults and country fallbacks.
    DEFAULT_COUNTRY: str = "India"
    # Public support phone shown in chat prompts and receipts.
    STORE_SUPPORT_PHONE: str = "+91-00000-00000"
    RAZORPAY_KEY_ID: str | None = None
    RAZORPAY_KEY_SECRET: str | None = None
    RAZORPAY_WEBHOOK_SECRET: str | None = None
    STRIPE_SECRET_KEY: str | None = None
    STRIPE_PUBLISHABLE_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None

    # Email provider: "gmail" (free SMTP, recommended) or "sendgrid".
    # Unset = auto-detect (Gmail creds win when present).
    EMAIL_PROVIDER: str | None = None
    # Gmail SMTP (free, 500/day): address + 16-char App Password
    # (Google Account → Security → 2-Step Verification → App passwords).
    # Never use the real Gmail password here.
    GMAIL_ADDRESS: str | None = None
    GMAIL_APP_PASSWORD: str | None = None

    # Email (SendGrid)
    SENDGRID_API_KEY: str | None = None
    FROM_EMAIL: str = "noreply@yourstore.com"

    # Google OAuth
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None

    # Password Reset Settings
    FRONTEND_URL: str = "http://localhost:5173"
    # Admin panel URL (staff invite accept links point here).
    ADMIN_FRONTEND_URL: str = "http://localhost:3001"
    RESET_TOKEN_EXPIRE_HOURS: int = 1

    # ========== Store policy (tax, shipping, COD, refunds, expiry) ==========
    # NOTE: boot defaults only. Live values live in the `store_settings`
    # DB row, editable (audited) in Admin → Store Settings. These fields
    # (and the .env keys of the same name) affect fresh databases
    # (startup seed) and the DB-outage fallback — never a running server
    # whose row already exists. Canonical values live in STORE_DEFAULTS
    # below; the fields just expose them as env-overridable settings.
    # See app/core/store_settings.py.
    TAX_RATE: float = STORE_DEFAULTS["tax_rate"]  # 18% GST
    FREE_SHIPPING_THRESHOLD: float = STORE_DEFAULTS["free_shipping_threshold"]
    SHIPPING_COST: float = STORE_DEFAULTS["shipping_cost"]

    # ========== COD (Cash on Delivery) Settings ==========
    # Same note as above: DB-overridable boot defaults.
    COD_FEE: float = STORE_DEFAULTS["cod_fee"]                 # flat fee added to COD orders
    COD_MIN_ORDER_VALUE: float = STORE_DEFAULTS["cod_min_order_value"]      # grand_total must be >= this for COD
    COD_MAX_ORDER_VALUE: float = STORE_DEFAULTS["cod_max_order_value"]  # grand_total must be <= this for COD

    # ========== Cancellation & Refund Settings ==========
    # Same note as above: DB-overridable boot defaults.
    REFUND_PROCESSING_DAYS: int = STORE_DEFAULTS["refund_processing_days"]           # days for refund to reflect in account
    RESTOCKING_FEE_PENDING: float = STORE_DEFAULTS["restocking_fee_pending"]       # % fee when cancelling a PENDING order
    RESTOCKING_FEE_CONFIRMED: float = STORE_DEFAULTS["restocking_fee_confirmed"]     # % fee when cancelling a CONFIRMED order
    RESTOCKING_FEE_PROCESSING: float = STORE_DEFAULTS["restocking_fee_processing"]   # % fee when cancelling a PROCESSING order

    # ========== Abandoned unpaid online orders ==========
    # Same note as above for PENDING_ORDER_EXPIRY_MINUTES (DB-overridable).
    # PENDING_ORDER_EXPIRY_JOB_MINUTES stays env-only: sweep cadence is an
    # ops concern, not store policy.
    # Online orders that are still PENDING/payment_status "pending" longer than
    # PENDING_ORDER_EXPIRY_MINUTES get auto-cancelled by the sweep job (stock
    # restored, provider PaymentIntent cancelled, customer emailed).
    PENDING_ORDER_EXPIRY_MINUTES: int = STORE_DEFAULTS["pending_order_expiry_minutes"]
    # How often the sweep job runs (seconds between runs via APScheduler)
    PENDING_ORDER_EXPIRY_JOB_MINUTES: int = 2

    # ========== Shiprocket / Shipping Provider Settings ==========
    SHIPPING_PROVIDER: str = "simulator"  # "simulator" or "shiprocket"
    SHIPROCKET_EMAIL: str | None = None
    SHIPROCKET_PASSWORD: str | None = None
    SHIPROCKET_PICKUP_LOCATION: str = "Primary"
    SHIPROCKET_PICKUP_PINCODE: str = "110001"
    SHIPROCKET_WEBHOOK_TOKEN: str | None = None
    # Synthetic COD remittance batches are a development aid only. They are
    # always allowed outside production and must be explicitly enabled in
    # production; they never call Shiprocket and are labelled in the UI.
    COD_REMITTANCE_SIMULATOR_ENABLED: bool = False

    # ========== Cloudinary media storage ==========
    CLOUDINARY_CLOUD_NAME: str | None = None
    CLOUDINARY_API_KEY: str | None = None
    CLOUDINARY_API_SECRET: str | None = None
    CLOUDINARY_SECURE: bool = True

    # Delivered-product returns: isolated from pre-shipping cancellation policy.
    RETURNS_ENABLED: bool = True
    RETURN_WINDOW_DAYS: int | None = Field(default=None, ge=1, le=3650)
    RETURN_EXCLUDED_VARIANT_IDS: List[str] = []
    RETURN_REQUIRED_PHOTO_REASONS: List[str] = []
    RETURN_FEE_PERCENT: float = Field(default=0, ge=0, lt=100)
    RETURN_MAX_IMAGES: int = Field(default=6, ge=1, le=12)
    RETURN_IMAGE_MAX_BYTES: int = Field(default=5 * 1024 * 1024, ge=1024, le=20 * 1024 * 1024)
    RETURN_STORAGE_DIR: str = "private_storage/returns"

    GROQ_API_KEY:str|None=None
    GEMINI_API_KEY:str|None=None
    # MCP chatbot LLM provider: "groq" (default) or "gemini". Switching
    # providers requires only changing env vars and restarting the backend.
    MCP_LLM_PROVIDER: str = "groq"
    # Model override; when empty, the provider default is used
    # (groq: openai/gpt-oss-120b, gemini: gemini-3.1-flash-lite).
    MCP_LLM_MODEL: str | None = None
    CHAT_MESSAGES_PER_MINUTE: int = Field(default=10, ge=1, le=1000)
    CHAT_SESSIONS_PER_MINUTE: int = Field(default=5, ge=1, le=100)
    CHAT_GLOBAL_MESSAGES_PER_MINUTE: int = Field(default=100, ge=1, le=10000)
    CHAT_SESSION_TTL_HOURS: int = Field(default=24, ge=1, le=168)

    # MCP self-call loopback. Unset = derive from the request origin
    # (correct on localhost). Behind tunnels/proxies that rewrite or
    # expose a public Host (ngrok etc.), set this to the local origin,
    # e.g. MCP_LOOPBACK_URL=http://127.0.0.1:8001/mcp/, so the agent's
    # internal HTTP hop never leaves the machine.
    MCP_LOOPBACK_URL: str | None = None

    @property
    def cors_origins_list(self) -> List[str]:
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]


settings = Settings()

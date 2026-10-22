import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import create_engine

from app.core.config import Settings
from app.core.release import validate_production_settings, assert_database_ready, migration_heads
from scripts.release_check import isolated_environment


def production(**overrides):
    values = dict(ENVIRONMENT="production", DATABASE_URL="postgresql://test:test@localhost/release",
                  JWT_SECRET_KEY="a-unique-release-secret-at-least-32-characters", CORS_ORIGINS="https://shop.example.com,https://admin.example.com",
                  PAYMENT_PROVIDER="stripe", STRIPE_SECRET_KEY="secret", STRIPE_PUBLISHABLE_KEY="public", STRIPE_WEBHOOK_SECRET="webhook",
                   SHIPPING_PROVIDER="shiprocket", SHIPROCKET_EMAIL="shipping@example.com", SHIPROCKET_PASSWORD="password", SHIPROCKET_WEBHOOK_TOKEN="shipping-token",
                   CLOUDINARY_CLOUD_NAME="test-cloud", CLOUDINARY_API_KEY="test-key", CLOUDINARY_API_SECRET="test-secret",
                   EMAIL_PROVIDER="gmail", GMAIL_ADDRESS="mail@example.com", GMAIL_APP_PASSWORD="app-password",
                  GROQ_API_KEY="chat-key", FRONTEND_URL="https://shop.example.com", ADMIN_FRONTEND_URL="https://admin.example.com")
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize("overrides,expected", [
    ({"DATABASE_URL": "sqlite:///:memory:"}, "PostgreSQL"),
    ({"JWT_SECRET_KEY": "short"}, "JWT_SECRET_KEY"),
    ({"CORS_ORIGINS": "*"}, "CORS_ORIGINS"),
    ({"PAYMENT_PROVIDER": "dummy"}, "PAYMENT_PROVIDER"),
    ({"STRIPE_WEBHOOK_SECRET": ""}, "STRIPE_WEBHOOK_SECRET"),
    ({"SHIPPING_PROVIDER": "simulator"}, "SHIPPING_PROVIDER"),
    ({"SHIPROCKET_WEBHOOK_TOKEN": " "}, "SHIPROCKET_WEBHOOK_TOKEN"),
    ({"GMAIL_APP_PASSWORD": " "}, "Gmail"),
    ({"GROQ_API_KEY": ""}, "GROQ_API_KEY"),
    ({"CLOUDINARY_API_SECRET": ""}, "CLOUDINARY_API_SECRET"),
    ({"FRONTEND_URL": "http://localhost:3000"}, "FRONTEND_URL"),
])
def test_missing_production_configuration_fails_closed(overrides, expected):
    with pytest.raises(RuntimeError, match=expected):
        validate_production_settings(production(**overrides))


def test_supported_production_provider_configurations_pass():
    validate_production_settings(production())
    validate_production_settings(production(PAYMENT_PROVIDER="razorpay", RAZORPAY_KEY_ID="key",
                                            RAZORPAY_KEY_SECRET="secret", RAZORPAY_WEBHOOK_SECRET="hook",
                                            EMAIL_PROVIDER="sendgrid", SENDGRID_API_KEY="mail-key"))


def test_schema_readiness_is_read_only_and_requires_matching_head():
    engine = create_engine("sqlite:///:memory:")
    with pytest.raises(RuntimeError, match="migration revision"):
        assert_database_ready(engine)
    assert inspect(engine).get_table_names() == []
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        connection.execute(text("INSERT INTO alembic_version VALUES ('old-revision')"))
    with pytest.raises(RuntimeError):
        assert_database_ready(engine)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": migration_heads()[0]})
    assert_database_ready(engine)
    engine.dispose()


def test_release_script_overrides_live_database_and_credentials():
    env = isolated_environment({"DATABASE_URL": "postgresql://user:secret@example/live", "ENVIRONMENT": "production",
                                "STRIPE_SECRET_KEY": "live-secret", "GMAIL_APP_PASSWORD": "real", "NODE_ENV": "production"})
    assert env["DATABASE_URL"] == "sqlite:///:memory:" and env["ENVIRONMENT"] == "test"
    assert env["PAYMENT_PROVIDER"] == "dummy" and env["STRIPE_SECRET_KEY"] == env["GMAIL_APP_PASSWORD"] == ""
    assert "NODE_ENV" not in env
    with pytest.raises(ValueError, match="disposable"):
        isolated_environment({"REMEDIATION_TEST_DATABASE_URL": "postgresql://user:secret@example/live"})


def test_production_startup_rejects_unmigrated_database_before_jobs(monkeypatch):
    from app import main
    from unittest.mock import Mock
    engine = create_engine("sqlite:///:memory:")
    scheduler = Mock()
    monkeypatch.setattr(main, "settings", production())
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "_scheduler", scheduler)
    with pytest.raises(RuntimeError, match="migration revision"):
        with TestClient(main.app):
            pass
    scheduler.start.assert_not_called()
    assert inspect(engine).get_table_names() == []
    engine.dispose()


def test_health_distinguishes_liveness_from_readiness_without_error_leak(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "settings", production(ENVIRONMENT="test"))
    def down(engine):
        raise RuntimeError("sensitive database details")
    monkeypatch.setattr(main, "assert_database_ready", down)
    with TestClient(main.app) as client:
        assert client.get("/health/live").json() == {"status": "alive"}
        response = client.get("/health/ready")
        assert response.status_code == 503 and response.json() == {"status": "not_ready"}


def test_new_migrations_form_one_ordered_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from app.core.release import ROOT
    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    heads = migration_heads()

    # Exactly one head: no competing tips.
    assert len(heads) == 1
    assert heads == ("b2c3d4e5f6a7",)

    # Every revision must be reachable from the head. A merge revision
    # (down_revision is a tuple) is legitimate; an orphan branch is not.
    reachable = set()
    stack = list(heads)
    while stack:
        revision = stack.pop()
        if revision in reachable:
            continue
        reachable.add(revision)
        down = scripts.get_revision(revision).down_revision
        if down is None:
            continue
        stack.extend(down if isinstance(down, tuple) else (down,))

    all_revisions = {script.revision for script in scripts.walk_revisions()}
    assert reachable == all_revisions

"""Locked installs and local release checks across the three existing repos.

Run with Python 3.12; never consumes the live DATABASE_URL for test commands.
"""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def isolated_environment(source=None):
    env = dict(os.environ if source is None else source)
    env.update(ENVIRONMENT="test", DATABASE_URL="sqlite:///:memory:",
               JWT_SECRET_KEY="remediation-test-secret", GROQ_API_KEY="remediation-test-key",
               PAYMENT_PROVIDER="dummy", PAYMENT_CURRENCY="INR", SHIPPING_PROVIDER="simulator",
               SENDGRID_API_KEY="", GMAIL_ADDRESS="", GMAIL_APP_PASSWORD="",
               RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="", STRIPE_SECRET_KEY="",
               SHIPROCKET_WEBHOOK_TOKEN="remediation-test-webhook", PYTHONPATH=str(ROOT))
    for key in ("NODE_ENV", "NPM_CONFIG_PRODUCTION"):
        env.pop(key, None)
    if env.get("REMEDIATION_TEST_DATABASE_URL"):
        from sqlalchemy.engine import make_url
        url = make_url(env["REMEDIATION_TEST_DATABASE_URL"])
        if url.get_backend_name() != "postgresql" or not (url.database or "").startswith("remediation_test"):
            raise ValueError("PostgreSQL tests require a disposable database named remediation_test*")
    return env


def run(args, cwd, env):
    print(f"Running {' '.join(args)} in {cwd}", flush=True)
    subprocess.run(args, cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storefront", type=Path, required=True)
    parser.add_argument("--admin", type=Path, required=True)
    parser.add_argument("--require-postgres", action="store_true")
    options = parser.parse_args()
    if sys.version_info[:2] != (3, 12):
        parser.error("Release runtime is Python 3.12")
    env = isolated_environment()
    node = tuple(map(int, subprocess.check_output(["node", "--version"], text=True).strip().removeprefix("v").split(".")))
    npm = subprocess.check_output(["npm", "--version"], text=True).strip().split(".")[0]
    if node[0] != 24 or node < (24, 18, 1) or npm != "11":
        parser.error("Release runtime requires Node >=24.18.1,<25 and npm 11")
    if options.require_postgres and not env.get("REMEDIATION_TEST_DATABASE_URL"):
        parser.error("Set isolated REMEDIATION_TEST_DATABASE_URL to require PostgreSQL races")
    frontends = [options.storefront.resolve(), options.admin.resolve()]
    for path in frontends:
        if not (path / "package.json").is_file() or not (path / "package-lock.json").is_file():
            parser.error(f"Frontend manifests/lockfile missing in {path}")
    run(["uv", "lock", "--check"], ROOT, env)
    run(["uv", "sync", "--locked", "--group", "test"], ROOT, env)
    python = str(ROOT / ".venv/bin/python")
    run(["uv", "pip", "check", "--python", python], ROOT, env)
    run([python, "-m", "pytest", "-q", "--tb=short"], ROOT, env)
    run([python, "-m", "alembic", "heads"], ROOT, env)
    from app.core.release import migration_heads
    migration_heads()
    run(["git", "diff", "--check"], ROOT, env)
    for path in frontends:
        run(["npm", "ci", "--include=dev", "--no-audit", "--no-fund"], path, env)
        run(["npm", "run", "check:release"], path, env)
    print("Release checks passed; production migrations/provider/browser/restore rehearsal are separate deployment checks.")


if __name__ == "__main__":
    main()

"""Opt-in concurrency checks use only explicitly named disposable test DBs."""
import os
from uuid import uuid4

import pytest
from sqlalchemy.engine import make_url
from sqlmodel import SQLModel, create_engine


@pytest.fixture
def postgres_engine():
    raw = os.environ.get("REMEDIATION_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Set REMEDIATION_TEST_DATABASE_URL for isolated PostgreSQL concurrency checks")
    url = make_url(raw)
    if url.get_backend_name() != "postgresql" or not (url.database or "").startswith("remediation_test"):
        pytest.fail("PostgreSQL checks require a database named remediation_test*; never use the live DB")
    schema = f"remediation_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        SQLModel.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()

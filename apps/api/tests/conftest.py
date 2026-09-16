"""Shared test fixtures.

The database fixture points at ``repolens_test`` and recreates the schema per
session, so tests never touch a development database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://repolens:repolens@127.0.0.1:5432/repolens_test"
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-not-used-in-production-abcdefghijklmnop")
os.environ.setdefault("ENCRYPTION_KEY", "test-encryption-key-not-used-in-production-abcdef")
os.environ.setdefault("ALLOW_INLINE_WORKER", "false")


@pytest.fixture(scope="session")
def database_available() -> bool:
    from sqlalchemy import text

    from app.db.session import engine

    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def db_engine(database_available: bool):
    if not database_available:
        pytest.skip("PostgreSQL is not reachable; database tests are skipped")
    from app.db.session import engine
    from app.models import Base

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(db_engine) -> Iterator:
    """A session wrapped in a transaction that is rolled back after each test."""
    from sqlalchemy.orm import Session

    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client(db_engine, db):
    """A TestClient whose requests share the test transaction."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def student_token(client) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "student@example.com",
            "password": "TestPassw0rd!x",
            "full_name": "Test Student",
            "role": "STUDENT",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["tokens"]["access_token"]


@pytest.fixture
def interviewer_token(client) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "interviewer@example.com",
            "password": "TestPassw0rd!x",
            "full_name": "Test Interviewer",
            "role": "INTERVIEWER",
            "organization_name": "Test Org",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["tokens"]["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}

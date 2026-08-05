"""Tests for the authentication system: JWT login, invalid PIN, lockout."""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth.jwt import create_access_token, decode_access_token
from app.auth.rate_limiter import rate_limiter
from app.models.database import Base, get_db
# Import Employee so its table is registered on Base.metadata
from app.models.employee import Employee  # noqa: F401
from app.routers.auth import router, get_current_user, require_manager


# ── test data ───────────────────────────────────────────────────────

TEST_EMPLOYEES = [
    {
        "employee_id": "emp_1",
        "name": "Alice Manager",
        "pin": "1234",
        "status": "in",
        "email": "alice@example.com",
        "primary_department": "Management",
        "primary_department_id": "dept_1",
        "custom_employee_id": "c001",
        "title": "Manager",
    },
    {
        "employee_id": "emp_2",
        "name": "Bob Employee",
        "pin": "5678",
        "status": "out",
        "email": "bob@example.com",
        "primary_department": "Engineering",
        "primary_department_id": "dept_2",
        "custom_employee_id": "c002",
        "title": "Developer",
    },
]


# ── fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Clear rate-limiter state before each test (singleton shared with router)."""
    rate_limiter._pin_attempts.clear()
    rate_limiter._ip_attempts.clear()


@pytest.fixture
def app():
    """Minimal FastAPI app with the auth router and an in-memory SQLite DB."""
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(app):
    return TestClient(app)


def _mock_employees():
    """Context manager that patches timestation.get_employees with test data."""
    return patch(
        "app.routers.auth.timestation.get_employees",
        new_callable=AsyncMock,
        return_value=TEST_EMPLOYEES,
    )


# ── JWT unit tests ──────────────────────────────────────────────────

def test_create_and_decode_access_token():
    """JWT round-trips correctly and contains the original claims."""
    data = {"sub": "emp_1", "name": "Alice", "role": "manager", "email": "a@b.com"}
    token = create_access_token(data)
    payload = decode_access_token(token)
    assert payload["sub"] == "emp_1"
    assert payload["name"] == "Alice"
    assert payload["role"] == "manager"
    assert payload["email"] == "a@b.com"
    assert "exp" in payload


def test_decode_invalid_token_returns_empty():
    """Garbage tokens decode to an empty dict (no exception)."""
    assert decode_access_token("not.a.valid.token") == {}


# ── login endpoint tests ────────────────────────────────────────────

def test_login_valid_pin(client):
    """Valid PIN returns 200 with access_token and employee info."""
    with _mock_employees():
        resp = client.post("/auth/login", json={"pin": "1234"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # JWT should decode back to the right subject
    payload = decode_access_token(body["access_token"])
    assert payload["sub"] == "emp_1"
    assert payload["name"] == "Alice Manager"
    # Employee info in response
    emp = body["employee"]
    assert emp["name"] == "Alice Manager"
    assert emp["role"] == "employee"  # default role for new DB record
    assert emp["department"] == "Management"
    assert emp["email"] == "alice@example.com"


def test_login_invalid_pin_returns_401(client):
    """Unknown PIN returns 401."""
    with _mock_employees():
        resp = client.post("/auth/login", json={"pin": "0000"})

    assert resp.status_code == 401
    assert "Invalid PIN" in resp.json()["detail"]


def test_login_lockout_after_5_failures(client):
    """After 5 failed attempts the PIN is locked → 6th attempt returns 429."""
    with _mock_employees():
        # First 5 attempts all fail with 401
        for i in range(5):
            resp = client.post("/auth/login", json={"pin": "0000"})
            assert resp.status_code == 401, f"attempt {i + 1} should be 401"

        # 6th attempt → locked out
        resp = client.post("/auth/login", json={"pin": "0000"})
        assert resp.status_code == 429
        assert "pin" in resp.json()["detail"].lower()


def test_login_successful_clears_pin_attempts(client):
    """A successful login resets the failed-attempt counter for that PIN."""
    with _mock_employees():
        # Two failures
        for _ in range(2):
            client.post("/auth/login", json={"pin": "0000"})
        # Successful login
        resp = client.post("/auth/login", json={"pin": "1234"})
        assert resp.status_code == 200
        # Subsequent wrong-PIN attempt should be 401, not 429
        resp2 = client.post("/auth/login", json={"pin": "0000"})
        assert resp2.status_code == 401


# ── dependency tests ────────────────────────────────────────────────

def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_get_current_user_missing_token(app, client):
    """No Authorization header → 401."""

    @app.get("/_test_me")
    def _me(user: dict = Depends(get_current_user)):
        return user

    resp = client.get("/_test_me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Not authenticated"


def test_get_current_user_valid_token(app, client):
    """Valid Bearer token → returns user dict."""

    @app.get("/_test_me")
    def _me(user: dict = Depends(get_current_user)):
        return user

    token = create_access_token(
        {"sub": "emp_1", "name": "Alice", "role": "manager", "email": "a@b.com"}
    )
    resp = client.get("/_test_me", headers=_auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["timestation_id"] == "emp_1"
    assert body["name"] == "Alice"
    assert body["role"] == "manager"
    assert body["email"] == "a@b.com"


def test_get_current_user_invalid_token(app, client):
    """Garbage token → 401."""

    @app.get("/_test_me")
    def _me(user: dict = Depends(get_current_user)):
        return user

    resp = client.get("/_test_me", headers=_auth_header("garbage.token.here"))
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


def test_require_manager_allows_manager(app, client):
    """Manager role passes the require_manager gate."""

    @app.get("/_test_mgr")
    def _mgr(user: dict = Depends(require_manager)):
        return user

    token = create_access_token(
        {"sub": "emp_1", "name": "Alice", "role": "manager", "email": "a@b.com"}
    )
    resp = client.get("/_test_mgr", headers=_auth_header(token))
    assert resp.status_code == 200


def test_require_manager_blocks_employee(app, client):
    """Non-manager role → 403."""

    @app.get("/_test_mgr")
    def _mgr(user: dict = Depends(require_manager)):
        return user

    token = create_access_token(
        {"sub": "emp_2", "name": "Bob", "role": "employee", "email": "b@b.com"}
    )
    resp = client.get("/_test_mgr", headers=_auth_header(token))
    assert resp.status_code == 403

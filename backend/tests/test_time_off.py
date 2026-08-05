"""Tests for the time-off request API.

Uses fastapi.testclient.TestClient against a minimal FastAPI app that only
includes the time_off router. Auth dependencies are mocked via
``dependency_overrides``. An in-memory SQLite database is created per test to
keep tests isolated.
"""

from datetime import date
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee
from app.models.time_off import TimeOffRequest
from app.routers.auth import get_current_user, require_manager
from app.routers.time_off import router as time_off_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_app():
    """Build a fresh FastAPI app with an in-memory SQLite DB wired up."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(time_off_router)
    app.dependency_overrides[get_db] = override_get_db
    return app, TestingSessionLocal


def _seed_employees(session_local):
    """Seed one employee and one manager into the DB."""
    with session_local() as db:
        db.add(Employee(timestation_id="EMP001", name="Alice", email="alice@example.com", role="employee", pin="1111"))
        db.add(Employee(timestation_id="MGR001", name="Bob", email="bob@example.com", role="manager", pin="2222"))
        db.commit()


def _user_employee():
    return {"timestation_id": "EMP001", "name": "Alice", "role": "employee", "email": "alice@example.com"}


def _user_manager():
    return {"timestation_id": "MGR001", "name": "Bob", "role": "manager", "email": "bob@example.com"}


@pytest.fixture
def client():
    """TestClient wired up as an employee by default."""
    app, session_local = _make_app()
    _seed_employees(session_local)
    app.dependency_overrides[get_current_user] = lambda: _user_employee()
    app.dependency_overrides[require_manager] = lambda: _user_manager()
    yield TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_create_time_off_request(client):
    """POST /api/time-off/ creates a pending request for the logged-in employee."""
    resp = client.post(
        "/api/time-off/",
        json={
            "request_type": "vacation",
            "start_date": "2026-08-10",
            "end_date": "2026-08-14",
            "reason": "Family trip",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["request_type"] == "vacation"
    assert body["employee_id"] == "EMP001"
    assert body["employee_name"] == "Alice"
    assert body["reason"] == "Family trip"
    assert body["start_date"] == "2026-08-10"
    assert body["end_date"] == "2026-08-14"
    assert body["reviewed_by"] is None
    assert body["reviewed_at"] is None


def test_create_request_invalid_type(client):
    resp = client.post(
        "/api/time-off/",
        json={"request_type": "birthday", "start_date": "2026-08-10", "end_date": "2026-08-14"},
    )
    assert resp.status_code == 400


def test_create_request_bad_date_range(client):
    resp = client.post(
        "/api/time-off/",
        json={"request_type": "sick", "start_date": "2026-08-14", "end_date": "2026-08-10"},
    )
    assert resp.status_code == 400


def test_list_my_requests(client):
    """GET /api/time-off/ returns only the logged-in employee's requests, newest first."""
    # create two requests
    client.post("/api/time-off/", json={"request_type": "vacation", "start_date": "2026-08-10", "end_date": "2026-08-12"})
    client.post("/api/time-off/", json={"request_type": "sick", "start_date": "2026-09-01", "end_date": "2026-09-02"})

    resp = client.get("/api/time-off/")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    # newest first -> sick (created second) should come first
    assert body[0]["request_type"] == "sick"
    assert body[1]["request_type"] == "vacation"
    # all belong to the employee
    assert all(r["employee_id"] == "EMP001" for r in body)


def test_list_all_requests_manager(client):
    """GET /api/time-off/all returns all requests with employee names (manager only)."""
    client.post("/api/time-off/", json={"request_type": "vacation", "start_date": "2026-08-10", "end_date": "2026-08-12"})

    resp = client.get("/api/time-off/all")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["employee_name"] == "Alice"
    assert body[0]["request_type"] == "vacation"


def test_list_all_requests_with_status_filter(client):
    client.post("/api/time-off/", json={"request_type": "vacation", "start_date": "2026-08-10", "end_date": "2026-08-12"})
    client.post("/api/time-off/", json={"request_type": "sick", "start_date": "2026-09-01", "end_date": "2026-09-02"})

    # only pending (both should match)
    resp = client.get("/api/time-off/all?status_filter=pending")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    # none approved yet
    resp = client.get("/api/time-off/all?status_filter=approved")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_manager_review_approve(client):
    """PUT /api/time-off/{id}/review updates status and fires email notification."""
    create = client.post("/api/time-off/", json={"request_type": "personal", "start_date": "2026-08-15", "end_date": "2026-08-16"})
    request_id = create.json()["id"]

    with patch("app.routers.time_off.send_time_off_notification") as mock_send:
        resp = client.put(f"/api/time-off/{request_id}/review", json={"status": "approved"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] == "MGR001"
    assert body["reviewed_at"] is not None

    # email notification was called for the employee (who has an email)
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["to_email"] == "alice@example.com"
    assert call_kwargs["employee_name"] == "Alice"
    assert call_kwargs["status"] == "approved"
    assert call_kwargs["request_type"] == "personal"


def test_manager_review_deny(client):
    create = client.post("/api/time-off/", json={"request_type": "sick", "start_date": "2026-08-20", "end_date": "2026-08-21"})
    request_id = create.json()["id"]

    with patch("app.routers.time_off.send_time_off_notification") as mock_send:
        resp = client.put(f"/api/time-off/{request_id}/review", json={"status": "denied"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "denied"
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["status"] == "denied"


def test_review_nonexistent_request(client):
    resp = client.put("/api/time-off/9999/review", json={"status": "approved"})
    assert resp.status_code == 404


def test_review_already_reviewed(client):
    create = client.post("/api/time-off/", json={"request_type": "vacation", "start_date": "2026-08-10", "end_date": "2026-08-12"})
    request_id = create.json()["id"]

    with patch("app.routers.time_off.send_time_off_notification"):
        client.put(f"/api/time-off/{request_id}/review", json={"status": "approved"})

    # second review should fail
    resp = client.put(f"/api/time-off/{request_id}/review", json={"status": "denied"})
    assert resp.status_code == 400


def test_review_invalid_status(client):
    create = client.post("/api/time-off/", json={"request_type": "vacation", "start_date": "2026-08-10", "end_date": "2026-08-12"})
    request_id = create.json()["id"]
    resp = client.put(f"/api/time-off/{request_id}/review", json={"status": "maybe"})
    assert resp.status_code == 400


def test_review_no_email_skips_notification(client):
    """If the employee has no email, no notification is sent (no crash)."""
    # Build a fresh app with an employee that has no email.
    app, session_local = _make_app()
    with session_local() as db:
        db.add(Employee(timestation_id="EMP002", name="No Email", email=None, role="employee", pin="3333"))
        db.add(Employee(timestation_id="MGR002", name="Mgr2", email="m2@example.com", role="manager", pin="4444"))
        db.commit()

    app.dependency_overrides[get_current_user] = lambda: {"timestation_id": "EMP002", "name": "No Email", "role": "employee", "email": None}
    app.dependency_overrides[require_manager] = lambda: {"timestation_id": "MGR002", "name": "Mgr2", "role": "manager", "email": "m2@example.com"}
    c = TestClient(app)

    create = c.post("/api/time-off/", json={"request_type": "vacation", "start_date": "2026-08-10", "end_date": "2026-08-12"})
    request_id = create.json()["id"]

    with patch("app.routers.time_off.send_time_off_notification") as mock_send:
        resp = c.put(f"/api/time-off/{request_id}/review", json={"status": "approved"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "approved"
    mock_send.assert_not_called()

"""Company workflow security/idempotency contracts (disposable DB only)."""
from datetime import datetime, timedelta, timezone
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee
from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.routers.auth import get_current_user
from app.routers import tasks, company_calendar, notifications, vault


@pytest.fixture
def workflow_harness(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        company_one = ComplianceCompany(legal_name="Allied", is_active=True)
        company_two = ComplianceCompany(legal_name="Restricted", is_active=True)
        db.add_all([
            company_one,
            company_two,
            Employee(timestation_id="local_f2a5804ba2e5", name="Marc", pin="1", role="super_admin", email="marc@example.test"),
            Employee(timestation_id="local_262a0ca4abea", name="Nicole", pin="2", role="employee", email="nicole@example.test"),
            Employee(timestation_id="OTHER", name="Marc", pin="3", role="super_admin", email="marc@example.test"),
        ])
        db.flush()
        db.add_all([
            CompanyPermission(employee_id="OTHER", company_id=company_one.id, can_edit=True),
            CompanyPermission(employee_id="local_262a0ca4abea", company_id=company_one.id, can_edit=True),
        ])
        db.commit()
    current = {"user": {"timestation_id": "local_f2a5804ba2e5", "name": "Marc", "role": "super_admin"}}
    app = FastAPI()
    for router in (tasks.router, notifications.router, company_calendar.router, vault.router):
        app.include_router(router)
    def override_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    monkeypatch.setenv("PASSWORD_VAULT_KEY", base64.urlsafe_b64encode(b"x" * 32).decode())
    return TestClient(app), current, Session


def create_task(client, **extra):
    payload = {"company_id": 1, "title": "File report", "assigned_employee_ids": ["local_262a0ca4abea"]}
    payload.update(extra)
    response = client.post("/api/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_assignment_and_completion_notifications_are_idempotent(workflow_harness):
    client, _, Session = workflow_harness
    task = create_task(client)
    assert client.put(f"/api/tasks/{task['id']}", json={"status": "Completed"}).status_code == 200
    assert client.put(f"/api/tasks/{task['id']}", json={"status": "Completed"}).status_code == 200
    rows = client.get("/api/notifications").json()["notifications"]
    assert [n["event_type"] for n in rows].count("task_completed") == 1
    with Session() as db:
        from app.models.company_workflow import NotificationDelivery
        keys = [row.idempotency_key for row in db.query(NotificationDelivery).all()]
        assert len(keys) == len(set(keys))


def test_due_scheduler_is_idempotent_and_marks_daily_overdue(workflow_harness):
    client, _, _ = workflow_harness
    task = create_task(client, due_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    first = client.post("/api/notifications/run-due", json={"as_of": datetime.now(timezone.utc).isoformat()}).json()
    second = client.post("/api/notifications/run-due", json={"as_of": datetime.now(timezone.utc).isoformat()}).json()
    assert first["created"] == 1 and second["created"] == 0
    detail = client.get(f"/api/tasks/{task['id']}").json()
    assert detail["status"] == "Overdue"


def test_calendar_task_edit_updates_source_and_event_audit(workflow_harness):
    client, _, _ = workflow_harness
    task = create_task(client, due_at="2030-01-02T15:00:00Z")
    events = client.get("/api/company-calendar", params={"company_id": 1, "start": "2030-01-01T00:00:00Z", "end": "2030-02-01T00:00:00Z"}).json()["events"]
    task_event = next(e for e in events if e["source_type"] == "task")
    assert client.put(f"/api/company-calendar/{task_event['id']}", json={"start_at": "2030-01-03T16:00:00Z", "color": "#123456"}).status_code == 200
    assert client.get(f"/api/tasks/{task['id']}").json()["due_at"].startswith("2030-01-03T16:00:00")
    event = client.post("/api/company-calendar", json={"company_id": 1, "title": "Board meeting", "start_at": "2030-01-04T12:00:00Z", "attendee_ids": ["local_262a0ca4abea"], "reminder_minutes": 30}).json()
    assert event["color"]
    detail = client.get(f"/api/company-calendar/events/{event['id']}").json()
    assert detail["attendee_ids"] == ["local_262a0ca4abea"] and detail["audit"]


def test_vault_authorization_uses_only_immutable_ids_and_requires_unlock(workflow_harness):
    client, current, _ = workflow_harness
    current["user"] = {"timestation_id": "OTHER", "name": "Marc Mancuso", "role": "super_admin"}
    assert client.post("/api/password-vault/unlock", json={"password": "correct horse battery staple"}).status_code == 404
    current["user"] = {"timestation_id": "local_262a0ca4abea", "name": "Anything", "role": "super_admin"}
    assert client.post("/api/password-vault/configure", json={"password": "correct horse battery staple"}).status_code == 204
    unlocked = client.post("/api/password-vault/unlock", json={"password": "correct horse battery staple"})
    assert unlocked.status_code == 200
    token = unlocked.json()["vault_token"]
    headers = {"X-Vault-Token": token}
    created = client.post("/api/password-vault/entries", headers=headers, json={"company_id": 1, "name": "Bank", "username": "user", "password": "top-secret", "url": "https://example.test"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert "top-secret" not in created.text
    reveal = client.post(f"/api/password-vault/entries/{body['id']}/reveal", headers=headers)
    assert reveal.json()["password"] == "top-secret"
    for response in (created, reveal):
        assert "no-store" in response.headers["cache-control"]
        assert response.headers["pragma"] == "no-cache"
    assert client.post("/api/password-vault/lock", headers=headers).status_code == 204
    assert client.post(f"/api/password-vault/entries/{body['id']}/reveal", headers=headers).status_code == 423


def test_task_attachment_duplicate_content_is_rejected_and_summary_is_pdf(workflow_harness):
    client, _, _ = workflow_harness
    task = create_task(client)
    files = {"file": ("one.pdf", b"%PDF-1.4 same", "application/pdf")}
    assert client.post(f"/api/tasks/{task['id']}/attachments", files=files).status_code == 200
    duplicate = client.post(f"/api/tasks/{task['id']}/attachments", files={"file": ("two.pdf", b"%PDF-1.4 same", "application/pdf")})
    assert duplicate.status_code == 409
    pdf = client.get(f"/api/tasks/{task['id']}/summary.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"].startswith("application/pdf") and pdf.content.startswith(b"%PDF")


def test_task_and_calendar_routes_enforce_company_permissions(workflow_harness):
    client, current, _ = workflow_harness
    allowed = create_task(client, due_at="2030-01-05T12:00:00Z")
    restricted = create_task(client, company_id=2, due_at="2030-01-06T12:00:00Z")
    restricted_event = client.post("/api/company-calendar", json={"company_id": 2, "title": "Private", "start_at": "2030-01-04T12:00:00Z"}).json()

    current["user"] = {"timestation_id": "OTHER", "name": "Admin", "role": "admin"}
    assert client.get(f"/api/tasks/{allowed['id']}").status_code == 200
    assert client.get(f"/api/tasks/{restricted['id']}").status_code == 403
    assert client.put(f"/api/tasks/{restricted['id']}", json={"title": "No"}).status_code == 403
    listed = client.get("/api/tasks").json()["tasks"]
    assert {row["id"] for row in listed} == {allowed["id"]}
    task_calendar = client.get("/api/tasks/calendar/events", params={"start": "2030-01-01T00:00:00Z", "end": "2030-02-01T00:00:00Z"}).json()["events"]
    assert {row["task_id"] for row in task_calendar} == {allowed["id"]}
    assert client.get("/api/company-calendar", params={"company_id": 2, "start": "2030-01-01T00:00:00Z", "end": "2030-02-01T00:00:00Z"}).status_code == 403
    assert client.get(f"/api/company-calendar/events/{restricted_event['id']}").status_code == 403
    assert client.put(f"/api/company-calendar/{restricted_event['id']}", json={"title": "No"}).status_code == 403


def test_every_workflow_route_has_unique_method_and_path(workflow_harness):
    client, _, _ = workflow_harness
    pairs = [(method, route.path) for route in client.app.routes for method in (route.methods or ())]
    duplicates = {pair for pair in pairs if pairs.count(pair) > 1}
    assert not duplicates


def test_calendar_update_validates_attendees_and_attachment_lifecycle(workflow_harness):
    client, _, _ = workflow_harness
    event = client.post("/api/company-calendar", json={"company_id": 1, "title": "Review", "start_at": "2030-01-04T12:00:00Z"}).json()
    rejected = client.put(f"/api/company-calendar/{event['id']}", json={"attendee_ids": ["MISSING"]})
    assert rejected.status_code == 400
    bad = client.post(f"/api/company-calendar/events/{event['id']}/attachments", files={"file": ("bad.exe", b"bad", "application/octet-stream")})
    assert bad.status_code == 400
    uploaded = client.post(f"/api/company-calendar/events/{event['id']}/attachments", files={"file": ("agenda.pdf", b"%PDF-1.4 agenda", "application/pdf")})
    assert uploaded.status_code == 200
    attachment_id = uploaded.json()["id"]
    download = client.get(f"/api/company-calendar/events/{event['id']}/attachments/{attachment_id}")
    assert download.content == b"%PDF-1.4 agenda" and "no-store" in download.headers["cache-control"]
    assert client.delete(f"/api/company-calendar/events/{event['id']}/attachments/{attachment_id}").status_code == 204
    assert client.get(f"/api/company-calendar/events/{event['id']}/attachments/{attachment_id}").status_code == 404
    assert client.delete(f"/api/company-calendar/events/{event['id']}").status_code == 204
    assert client.get(f"/api/company-calendar/events/{event['id']}").status_code == 404


def test_vault_company_scope_and_safe_configuration(workflow_harness):
    client, current, _ = workflow_harness
    current["user"] = {"timestation_id": "local_262a0ca4abea", "name": "Nicole", "role": "admin"}
    password = "correct horse battery staple"
    assert client.post("/api/password-vault/configure", json={"password": password}).status_code == 204
    assert client.post("/api/password-vault/configure", json={"password": "different password phrase"}).status_code == 409
    token = client.post("/api/password-vault/unlock", json={"password": password}).json()["vault_token"]
    headers = {"X-Vault-Token": token}
    assert client.get("/api/password-vault/entries", headers=headers).status_code == 422
    assert client.get("/api/password-vault/entries", params={"company_id": 2}, headers=headers).status_code == 403
    assert client.post("/api/password-vault/entries", headers=headers, json={"company_id": 9999, "name": "No", "password": "secret"}).status_code in {403, 404}

"""Document distribution, templates, mandatory signing, and void tests."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee
from app.routers.auth import get_current_user, require_manager
from app.routers import documents as documents_router


def _manager():
    return {"timestation_id": "MGR", "name": "Brandon", "role": "manager", "email": "brandon@example.com"}


def _employee(employee_id="E1"):
    return {"timestation_id": employee_id, "name": employee_id, "role": "employee", "email": f"{employee_id.lower()}@example.com"}


@pytest.fixture
def harness(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        db.add_all([
            Employee(timestation_id="MGR", name="Brandon", pin="1000", email="brandon@example.com", role="manager"),
            Employee(timestation_id="E1", name="Alice", pin="1001", email="alice@example.com", role="employee"),
            Employee(timestation_id="E2", name="Evan", pin="1002", email="evan@example.com", role="employee"),
        ])
        db.commit()

    current = {"user": _manager()}

    def override_db():
        with Session() as db:
            yield db

    app = FastAPI()
    app.include_router(documents_router.router)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[require_manager] = lambda: current["user"]
    monkeypatch.setattr(documents_router, "STORAGE_DIR", Path(tmp_path))
    return TestClient(app), current


def _upload(client, recipients=("E1",), signature=True):
    return client.post(
        "/api/documents",
        data={
            "title": "Updated Handbook",
            "version": "2.0",
            "requires_signature": str(signature).lower(),
            "employee_ids": "[" + ",".join(f'\"{item}\"' for item in recipients) + "]",
        },
        files={"file": ("handbook.txt", b"company rules", "text/plain")},
    )


def test_upload_assigns_only_selected_employees_and_sends_email(harness):
    client, current = harness
    with patch("app.routers.documents.send_document_notification", new=AsyncMock()) as send:
        response = _upload(client, recipients=("E1",))
    assert response.status_code == 201, response.text
    assert response.json()["recipient_count"] == 1
    send.assert_awaited_once()
    assert send.await_args.kwargs["to_email"] == "alice@example.com"

    current["user"] = _employee("E1")
    assert len(client.get("/api/documents").json()["documents"]) == 1
    current["user"] = _employee("E2")
    assert client.get("/api/documents").json()["documents"] == []


def test_recipient_template_can_be_saved_and_loaded(harness):
    client, _ = harness
    create = client.post("/api/documents/templates", json={"name": "Monthly handbook", "employee_ids": ["E1", "E2"]})
    assert create.status_code == 201, create.text
    template_id = create.json()["id"]
    listed = client.get("/api/documents/templates").json()["templates"]
    assert listed == [{"id": template_id, "name": "Monthly handbook", "employee_ids": ["E1", "E2"], "employee_names": ["Alice", "Evan"]}]


def test_required_document_blocks_until_reviewed_and_signed(harness):
    client, current = harness
    with patch("app.routers.documents.send_document_notification", new=AsyncMock()):
        doc_id = _upload(client).json()["id"]
    current["user"] = _employee("E1")

    status = client.get("/api/documents/requirements").json()
    assert status["has_blocking_documents"] is True
    assert status["blocking_documents"][0]["viewed"] is False

    not_reviewed = client.post(f"/api/documents/{doc_id}/sign")
    assert not_reviewed.status_code == 400
    assert "review" in not_reviewed.json()["detail"].lower()

    reviewed = client.post(f"/api/documents/{doc_id}/review")
    assert reviewed.status_code == 200
    signed = client.post(f"/api/documents/{doc_id}/sign")
    assert signed.status_code == 200
    assert client.get("/api/documents/requirements").json()["has_blocking_documents"] is False


def test_void_removes_access_and_sends_void_email(harness):
    client, current = harness
    with patch("app.routers.documents.send_document_notification", new=AsyncMock()):
        doc_id = _upload(client, recipients=("E1", "E2")).json()["id"]

    with patch("app.routers.documents.send_document_void_notification", new=AsyncMock()) as send_void:
        response = client.put(f"/api/documents/{doc_id}/void")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "voided"
    assert send_void.await_count == 2

    current["user"] = _employee("E1")
    assert client.get("/api/documents").json()["documents"] == []
    assert client.get(f"/api/documents/{doc_id}/download").status_code == 404
    assert client.post(f"/api/documents/{doc_id}/sign").status_code == 404

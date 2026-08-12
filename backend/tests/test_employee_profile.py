"""Employee profile onboarding and directory privacy tests."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee
from app.routers.auth import get_current_user, require_manager
from app.routers.employee import router as employee_router


@pytest.fixture
def harness():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        db.add_all([
            Employee(timestation_id="E1", name="Alice", pin="1001", role="employee"),
            Employee(timestation_id="E2", name="Evan", pin="1002", role="employee"),
            Employee(timestation_id="M1", name="Brandon", pin="1003", role="manager"),
            Employee(timestation_id="A1", name="Marc", pin="1004", role="super_admin"),
        ])
        db.commit()

    current = {"user": {"timestation_id": "E1", "name": "Alice", "role": "employee", "email": None}}
    app = FastAPI()
    app.include_router(employee_router)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    app.dependency_overrides[require_manager] = lambda: current["user"]
    return TestClient(app), current


def test_profile_completion_is_required_until_all_contact_fields_are_saved(harness):
    client, _ = harness
    before = client.get("/api/me/profile-status")
    assert before.status_code == 200
    assert before.json()["is_complete"] is False

    saved = client.put("/api/me/profile", json={
        "name": "Alice Jones", "address": "10 Main Street", "email": "alice@example.com",
        "phone": "555-0100", "show_in_directory": True,
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["is_complete"] is True
    assert saved.json()["profile"]["phone"] == "555-0100"


def test_employee_directory_only_shows_opted_in_name_and_phone(harness):
    client, current = harness
    client.put("/api/me/profile", json={
        "name": "Alice Jones", "address": "10 Main Street", "email": "alice@example.com",
        "phone": "555-0100", "show_in_directory": True,
    })
    current["user"] = {"timestation_id": "E2", "name": "Evan", "role": "employee", "email": None}
    client.put("/api/me/profile", json={
        "name": "Evan Smith", "address": "20 Main Street", "email": "evan@example.com",
        "phone": "555-0200", "show_in_directory": False,
    })

    directory = client.get("/api/me/directory")
    assert directory.status_code == 200
    assert directory.json()["employees"] == [{"name": "Alice Jones", "phone": "555-0100", "role": "employee"}]


def test_employee_directory_always_includes_management_and_opted_in_employees(harness):
    client, current = harness
    profiles = [
        ("E1", "Alice Jones", "10 Main Street", "alice@example.com", "555-0100", True),
        ("E2", "Evan Smith", "20 Main Street", "evan@example.com", "555-0200", False),
        ("M1", "Brandon Manager", "30 Main Street", "brandon@example.com", "555-0300", False),
        ("A1", "Marc Admin", "40 Main Street", "marc@example.com", "555-0400", False),
    ]
    for employee_id, name, address, email, phone, show in profiles:
        current["user"] = {"timestation_id": employee_id, "name": name, "role": "employee", "email": email}
        client.put("/api/me/profile", json={"name": name, "address": address, "email": email, "phone": phone, "show_in_directory": show})

    current["user"] = {"timestation_id": "E1", "name": "Alice", "role": "employee", "email": "alice@example.com"}
    directory = client.get("/api/me/directory")
    assert directory.status_code == 200
    assert directory.json()["employees"] == [
        {"name": "Marc Admin", "phone": "555-0400", "role": "super_admin"},
        {"name": "Brandon Manager", "phone": "555-0300", "role": "manager"},
        {"name": "Alice Jones", "phone": "555-0100", "role": "employee"},
    ]


def test_management_directory_shows_all_employee_contact_information(harness):
    client, current = harness
    for employee_id, name, address, email, phone, show in [
        ("E1", "Alice Jones", "10 Main Street", "alice@example.com", "555-0100", True),
        ("E2", "Evan Smith", "20 Main Street", "evan@example.com", "555-0200", False),
    ]:
        current["user"] = {"timestation_id": employee_id, "name": name, "role": "employee", "email": email}
        client.put("/api/me/profile", json={"name": name, "address": address, "email": email, "phone": phone, "show_in_directory": show})

    current["user"] = {"timestation_id": "M1", "name": "Brandon", "role": "manager", "email": None}
    directory = client.get("/api/me/directory")
    assert directory.status_code == 200
    assert directory.json()["is_management_view"] is True
    assert directory.json()["employees"] == [
        {"employee_id": "E1", "name": "Alice Jones", "address": "10 Main Street", "email": "alice@example.com", "phone": "555-0100", "show_in_directory": True, "role": "employee"},
        {"employee_id": "E2", "name": "Evan Smith", "address": "20 Main Street", "email": "evan@example.com", "phone": "555-0200", "show_in_directory": False, "role": "employee"},
    ]

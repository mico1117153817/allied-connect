"""Compliance register tests."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee
from app.routers.auth import get_current_user, require_super_admin
from app.routers import compliance as compliance_router


@pytest.fixture
def harness():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        db.add_all([
            Employee(timestation_id="ADMIN", name="Marc", pin="1001", role="super_admin"),
            Employee(timestation_id="MGR", name="Brandon", pin="7111", role="manager"),
        ])
        db.commit()
    current = {"user": {"timestation_id": "ADMIN", "name": "Marc", "role": "super_admin"}}
    app = FastAPI()
    app.include_router(compliance_router.router)
    def override_db():
        with Session() as db:
            yield db
    app.dependency_overrides[get_db] = override_db
    def override_super_admin():
        if current["user"].get("role") != "super_admin":
            raise HTTPException(403, "Super admin access required")
        return current["user"]
    app.dependency_overrides[require_super_admin] = override_super_admin
    return TestClient(app), current


def test_compliance_register_starts_with_all_50_states(harness):
    client, _ = harness
    response = client.get("/api/compliance")
    assert response.status_code == 200
    states = response.json()["states"]
    assert len(states) == 50
    assert states[0]["state"] == "Alabama"
    assert states[-1]["state"] == "Wyoming"
    assert states[0]["license_status"] == "Not Held"
    assert states[0]["bond_status"] == "Expired"


def test_super_admin_can_update_state_compliance(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "certificate_of_authority": True,
        "license_status": "Active",
        "license_number": "AL-123",
        "license_expiration": "2027-12-31",
        "bond_status": "Active",
        "bond_amount": 25000,
    })
    assert response.status_code == 200
    row = response.json()
    assert row["license_number"] == "AL-123"
    assert row["bond_amount"] == 25000


def test_manager_is_forbidden_from_compliance(harness):
    client, current = harness
    current["user"] = {"timestation_id": "MGR", "name": "Brandon", "role": "manager"}
    assert client.get("/api/compliance").status_code == 403

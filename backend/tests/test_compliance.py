"""Compliance register tests."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee
from app.models.state_compliance import ensure_state_compliance_schema
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


def test_schema_upgrade_adds_new_fields_to_existing_compliance_table():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE state_compliance (id INTEGER PRIMARY KEY, state VARCHAR UNIQUE NOT NULL, license_status VARCHAR)")
    ensure_state_compliance_schema(engine)
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(state_compliance)")}
    assert "collection_license_requirement" in columns
    assert "coa_number" in columns
    assert "bond_expiration" in columns
    assert "source_urls_json" in columns


def test_matrix_seed_populates_known_company_records(harness):
    client, _ = harness
    response = client.get("/api/compliance")
    rows = {row["state"]: row for row in response.json()["states"]}
    assert rows["Delaware"]["coa_number"] == "3338836"
    assert rows["Delaware"]["license_number"] == "2020706824"
    assert rows["Delaware"]["license_expiration"] == "2026-12-31"
    assert rows["Minnesota"]["bond_number"] == "7752151287"
    assert rows["Minnesota"]["bond_amount"] == 50000
    assert rows["New York"]["notes"] is not None
    assert "2127071-DCWP" in rows["New York"]["notes"]


def test_user_edits_are_not_overwritten_by_seed_data(harness):
    client, _ = harness
    updated = client.put("/api/compliance/Delaware", json={
        "collection_license_requirement": "Not Required",
        "license_status": "Active",
        "license_number": "MANUAL-123",
        "coa_requirement": "Conditional",
        "coa_status": "Perpetual",
        "bond_requirement": "Unknown",
        "bond_status": "Unknown",
        "data_confidence": "Verified",
    })
    assert updated.status_code == 200, updated.text
    rows = {row["state"]: row for row in client.get("/api/compliance").json()["states"]}
    assert rows["Delaware"]["license_number"] == "MANUAL-123"


def test_compliance_register_starts_with_all_50_states(harness):
    client, _ = harness
    response = client.get("/api/compliance")
    assert response.status_code == 200
    states = response.json()["states"]
    assert len(states) == 50
    assert states[0]["state"] == "Alabama"
    assert states[-1]["state"] == "Wyoming"
    assert states[0]["license_status"] == "Not Required"
    assert states[0]["bond_status"] == "Unknown"


def test_compliance_register_exposes_requirement_and_indicator_fields(harness):
    client, _ = harness
    response = client.get("/api/compliance")
    assert response.status_code == 200
    row = response.json()["states"][0]
    assert row["collection_license_requirement"] == "Not Required"
    assert row["coa_requirement"] == "Conditional"
    assert row["coa_status"] == "Perpetual"
    assert row["overall_status"] == "Needs Review"
    assert row["source_urls"]
    assert row["document_paths"]


def test_active_indicator_requires_all_known_requirements_to_be_satisfied(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Required",
        "coa_status": "Active",
        "coa_number": "001-164-821",
        "license_status": "Not Required",
        "bond_requirement": "Not Required",
        "bond_status": "Not Required",
        "data_confidence": "Verified",
        "source_urls": ["https://example.gov/alabama"],
        "document_paths": ["Licensing/Alabama/SOSBusinessServiceDocument-20241202000017960.pdf"],
    })
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["overall_status"] == "Active"
    assert row["indicator"] == "green"


def test_missing_required_license_is_not_authorized(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Required",
        "coa_requirement": "Required",
        "coa_status": "Active",
        "license_status": "Not Held",
        "bond_requirement": "Unknown",
        "bond_status": "Unknown",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200, response.text
    assert response.json()["overall_status"] == "Not Authorized"
    assert response.json()["indicator"] == "red"


def test_required_items_reject_not_required_status(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Required",
        "license_status": "Not Required",
        "coa_requirement": "Required",
        "coa_status": "Not Required",
        "bond_requirement": "Required",
        "bond_status": "Not Required",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200, response.text
    assert response.json()["overall_status"] == "Not Authorized"
    assert response.json()["indicator"] == "red"


def test_seed_preserves_populated_legacy_values_without_audit_marker(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Delaware").one()
        row.updated_by = None
        row.data_confidence = "Unverified"
        row.license_number = "LEGACY-KEEP"
        db.commit()
    rows = {row["state"]: row for row in client.get("/api/compliance").json()["states"]}
    assert rows["Delaware"]["license_number"] == "LEGACY-KEEP"


def test_seed_preserves_legacy_status_values_without_numbers(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Delaware").one()
        for field in (
            "license_number", "license_issue_date", "license_expiration", "license_renewal_due",
            "coa_number", "coa_issue_date", "bond_number", "bond_amount", "bond_expiration",
            "regulator", "notes", "source_urls_json", "document_paths_json",
        ):
            setattr(row, field, None)
        row.updated_by = None
        row.data_confidence = "Unverified"
        row.license_status = "Active"
        row.certificate_of_authority = True
        row.bond_status = "Active"
        db.commit()
    rows = {row["state"]: row for row in client.get("/api/compliance").json()["states"]}
    assert rows["Delaware"]["license_status"] == "Active"
    assert rows["Delaware"]["certificate_of_authority"] is True
    assert rows["Delaware"]["bond_status"] == "Active"


def test_postgresql_upgrade_ddl_is_idempotent():
    from app.models.state_compliance import _upgrade_statement
    statement = _upgrade_statement("coa_number", "VARCHAR", "postgresql")
    assert statement == "ALTER TABLE state_compliance ADD COLUMN IF NOT EXISTS coa_number VARCHAR"


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

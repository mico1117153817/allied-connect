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
from app.routers.auth import get_current_user, require_compliance_access
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
    def override_compliance_access():
        if current["user"].get("role") not in ("admin", "super_admin"):
            raise HTTPException(403, "Compliance access required")
        return current["user"]
    app.dependency_overrides[require_compliance_access] = override_compliance_access
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


def test_matrix_seed_includes_all_three_workbook_tabs(harness):
    client, _ = harness
    rows = {row["state"]: row for row in client.get("/api/compliance").json()["states"]}
    assert rows["Colorado"]["coa_number"] == "20258078187"
    assert rows["Colorado"]["coa_issue_date"] == "2025-09-29"
    assert rows["Colorado"]["license_number"] == "CAR-L-00212101"
    assert rows["Colorado"]["license_issue_date"] == "2025-10-30"
    assert rows["Colorado"]["bond_number"] == "7752031014"
    assert rows["Colorado"]["bond_amount"] == 12000
    assert rows["Colorado"]["bond_expiration"] == "2026-07-01"
    assert "Licensing/Allied_Licensing_Matrix.xlsx" in rows["Colorado"]["document_paths"]
    assert rows["District of Columbia"]["license_number"] == "400325810346"
    assert rows["District of Columbia"]["coa_number"] == "C00008494896"
    assert "Licensing/Allied_Licensing_Matrix.xlsx" in rows["Louisiana"]["document_paths"]


def test_matrix_seed_preserves_multiple_and_local_records(harness):
    client, _ = harness
    rows = {row["state"]: row for row in client.get("/api/compliance").json()["states"]}
    assert "7752202154" in rows["North Carolina"]["bond_number"]
    assert "7752202155" in rows["North Carolina"]["bond_number"]
    assert "Chicago license 3051982" in rows["Illinois"]["notes"]
    assert "Yonkers, NY license 10948" in rows["New York"]["notes"]


def test_matrix_merge_fills_existing_legacy_rows_without_overwriting_manual_fields(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Colorado").one()
        row.document_paths_json = None
        row.bond_number = None
        row.bond_amount = None
        row.license_number = "MANUAL-COLORADO"
        row.updated_by = None
        db.commit()
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Colorado"]
    assert row["bond_number"] == "7752031014"
    assert row["bond_amount"] == 12000
    assert row["license_number"] == "MANUAL-COLORADO"
    assert "Licensing/Allied_Licensing_Matrix.xlsx" in row["document_paths"]


def test_matrix_merge_preserves_legacy_statuses_and_identifiers(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Colorado").one()
        row.document_paths_json = None
        row.license_status = "Expired"
        row.license_number = "LEGACY-OLD"
        row.license_expiration = compliance_router.date(2027, 1, 1)
        row.updated_by = None
        db.commit()
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Colorado"]
    assert row["license_status"] == "Expired"
    assert row["license_number"] == "LEGACY-OLD"
    assert row["license_expiration"] == "2027-01-01"


def test_matrix_merge_keeps_coa_boolean_consistent(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Colorado").one()
        row.document_paths_json = None
        row.coa_status = "Unknown"
        row.coa_number = None
        row.coa_issue_date = None
        row.certificate_of_authority = False
        row.updated_by = None
        db.commit()
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Colorado"]
    assert row["coa_status"] == "Perpetual"
    assert row["coa_number"] == "20258078187"
    assert row["certificate_of_authority"] is True


def test_user_edits_are_not_overwritten_by_seed_data(harness):
    client, _ = harness
    updated = client.put("/api/compliance/Delaware", json={
        "collection_license_requirement": "Required",
        "license_status": "Active",
        "license_number": "MANUAL-123",
        "coa_requirement": "Required",
        "coa_status": "Active",
        "bond_requirement": "Not Required",
        "bond_status": "Not Held",
        "data_confidence": "Verified",
    })
    assert updated.status_code == 200, updated.text
    rows = {row["state"]: row for row in client.get("/api/compliance").json()["states"]}
    assert rows["Delaware"]["license_number"] == "MANUAL-123"


def test_update_rejects_removed_requirement_and_status_options(harness):
    client, _ = harness
    base = {
        "collection_license_requirement": "Required",
        "license_status": "Active",
        "coa_requirement": "Required",
        "coa_status": "Active",
        "bond_requirement": "Required",
        "bond_status": "Active",
        "data_confidence": "Verified",
    }
    for field, invalid in (
        ("collection_license_requirement", "Conditional"),
        ("coa_requirement", "Unknown"),
        ("bond_requirement", "Local Only"),
        ("license_status", "Expired"),
        ("coa_status", "Perpetual"),
        ("bond_status", "Unknown"),
    ):
        response = client.put("/api/compliance/Alabama", json={**base, field: invalid})
        assert response.status_code == 400, (field, response.text)


def test_expired_license_and_bond_need_review_with_issue_summary(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Required",
        "license_status": "Active",
        "license_expiration": "2020-01-01",
        "coa_requirement": "Not Required",
        "bond_requirement": "Required",
        "bond_status": "Active",
        "bond_expiration": "2021-01-01",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["overall_status"] == "Needs Review"
    assert row["indicator"] == "yellow"
    assert any("License expired" in issue for issue in row["issues"])
    assert any("Bond expired" in issue for issue in row["issues"])


def test_not_required_items_accept_no_status_or_detail_fields(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Not Required",
        "bond_requirement": "Not Required",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["overall_status"] == "Active"
    assert row["license_number"] is None
    assert row["coa_number"] is None
    assert row["bond_number"] is None


def test_state_portal_credentials_are_stored_without_returning_password(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Not Required",
        "bond_requirement": "Not Required",
        "state_portal_url": "https://alabama.gov/portal",
        "portal_username": "allied-user",
        "portal_password": "secret-value",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["state_portal_url"] == "https://alabama.gov/portal"
    assert row["portal_username"] == "allied-user"
    assert row["has_portal_password"] is True
    assert "portal_password" not in row
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        stored = db.query(compliance_router.StateCompliance).filter_by(state="Alabama").one()
        assert stored.portal_password_encrypted != "secret-value"
        assert stored.portal_password_encrypted


def test_portal_credentials_can_be_retrieved_by_compliance_user(harness):
    client, _ = harness
    saved = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Not Required",
        "bond_requirement": "Not Required",
        "portal_username": "allied-user",
        "portal_password": "secret-value",
        "data_confidence": "Verified",
    })
    assert saved.status_code == 200
    response = client.get("/api/compliance/Alabama/portal-credentials")
    assert response.status_code == 200
    assert "no-store" in response.headers["cache-control"]
    assert response.headers["pragma"] == "no-cache"
    assert response.json() == {"username": "allied-user", "password": "secret-value"}


def test_existing_source_url_is_migrated_even_after_manual_update(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Alabama").one()
        row.state_portal_url = None
        row.state_portal_url_migrated = False
        row.source_urls_json = '["https://legacy.alabama.gov"]'
        row.updated_by = "ADMIN"
        db.commit()
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Alabama"]
    assert row["state_portal_url"] == "https://legacy.alabama.gov"


def test_state_portal_url_can_be_explicitly_cleared_after_migration(harness):
    client, _ = harness
    client.get("/api/compliance")
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Not Required",
        "bond_requirement": "Not Required",
        "state_portal_url": None,
        "source_urls": ["https://legacy.alabama.gov"],
        "data_confidence": "Verified",
    })
    assert response.status_code == 200
    assert response.json()["state_portal_url"] is None
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Alabama"]
    assert row["state_portal_url"] is None


def test_explicit_password_removal_wins_over_autofilled_password(harness):
    client, _ = harness
    saved = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Not Required",
        "bond_requirement": "Not Required",
        "portal_password": "initial-secret",
        "data_confidence": "Verified",
    })
    assert saved.status_code == 200
    removed = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "coa_requirement": "Not Required",
        "bond_requirement": "Not Required",
        "portal_password": "autofilled-secret",
        "clear_portal_password": True,
        "data_confidence": "Verified",
    })
    assert removed.status_code == 200
    credentials = client.get("/api/compliance/Alabama/portal-credentials")
    assert credentials.json()["password"] is None


def test_legacy_secret_encrypted_password_remains_retrievable(harness, monkeypatch):
    client, _ = harness
    legacy = compliance_router._legacy_fernet().encrypt(b"legacy-secret").decode("ascii")
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Alabama").one()
        row.portal_username = "legacy-user"
        row.portal_password_encrypted = legacy
        db.commit()
    response = client.get("/api/compliance/Alabama/portal-credentials")
    assert response.status_code == 200
    assert response.json()["password"] == "legacy-secret"


def test_compliance_attachments_filter_by_item_type_and_preserve_pdf_metadata(harness):
    client, current = harness
    response = client.get("/api/compliance/Alabama/attachments?item_type=license")
    assert response.status_code == 200
    assert response.json()["attachments"] == []

    upload = client.post(
        "/api/compliance/Alabama/attachments",
        files={"file": ("license.pdf", b"%PDF-1.4 fake pdf", "application/pdf")},
        data={"item_type": "license"},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()["attachment"]
    assert attachment["item_type"] == "license"
    assert attachment["filename"] == "license.pdf"
    assert attachment["content_type"] == "application/pdf"

    assert client.get("/api/compliance/Alabama/attachments?item_type=license").json()["attachments"]
    assert client.get("/api/compliance/Alabama/attachments?item_type=bond").json()["attachments"] == []


def test_compliance_attachment_rejects_non_pdf_and_invalid_item_type(harness):
    client, _ = harness
    for item_type in ("other", "", "license/bond"):
        response = client.post(
            "/api/compliance/Alabama/attachments",
            files={"file": ("document.pdf", b"%PDF-1.4 fake pdf", "application/pdf")},
            data={"item_type": item_type},
        )
        assert response.status_code == 400

    response = client.post(
        "/api/compliance/Alabama/attachments",
        files={"file": ("document.txt", b"not pdf", "text/plain")},
        data={"item_type": "license"},
    )
    assert response.status_code == 400


def test_compliance_attachments_are_returned_in_state_register(harness):
    client, _ = harness
    upload = client.post(
        "/api/compliance/Alabama/attachments",
        files={"file": ("coa.pdf", b"%PDF-1.4 fake pdf", "application/pdf")},
        data={"item_type": "certificate_of_authority"},
    )
    assert upload.status_code == 201
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Alabama"]
    assert row["attachments"]["certificate_of_authority"][0]["filename"] == "coa.pdf"


def test_annual_report_pdf_can_be_uploaded_viewed_and_deleted(harness):
    client, _ = harness
    upload = client.post(
        "/api/compliance/Alabama/attachments",
        files={"file": ("annual-report.pdf", b"%PDF-1.4 annual report", "application/pdf")},
        data={"item_type": "annual_report"},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()["attachment"]
    assert attachment["item_type"] == "annual_report"
    assert attachment["label"] == "Annual Report"

    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Alabama"]
    assert row["attachments"]["annual_report"][0]["filename"] == "annual-report.pdf"
    assert client.get(attachment["view_url"]).status_code == 200

    deleted = client.delete(f"/api/compliance/Alabama/attachments/{attachment['id']}")
    assert deleted.status_code == 204, deleted.text
    assert client.get(attachment["view_url"]).status_code == 404
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Alabama"]
    assert row["attachments"]["annual_report"] == []


def test_attachment_delete_requires_matching_state(harness):
    client, _ = harness
    attachment = client.post(
        "/api/compliance/Alabama/attachments",
        files={"file": ("license.pdf", b"%PDF-1.4 license", "application/pdf")},
        data={"item_type": "license"},
    ).json()["attachment"]
    assert client.delete(f"/api/compliance/Alaska/attachments/{attachment['id']}").status_code == 404
    assert client.get(attachment["view_url"]).status_code == 200


def test_filing_receipt_pdf_can_be_uploaded_and_returned_in_register(harness):
    client, _ = harness
    upload = client.post(
        "/api/compliance/Alabama/attachments",
        files={"file": ("filing-receipt.pdf", b"%PDF-1.4 filing receipt", "application/pdf")},
        data={"item_type": "filing_receipt"},
    )
    assert upload.status_code == 201, upload.text
    attachment = upload.json()["attachment"]
    assert attachment["item_type"] == "filing_receipt"
    assert attachment["label"] == "Filing Receipt"
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Alabama"]
    assert row["attachments"]["filing_receipt"][0]["filename"] == "filing-receipt.pdf"

def test_compliance_register_starts_with_all_supported_jurisdictions(harness):
    client, _ = harness
    response = client.get("/api/compliance")
    assert response.status_code == 200
    states = response.json()["states"]
    assert len(states) == 51
    assert states[0]["state"] == "Alabama"
    assert any(row["state"] == "District of Columbia" for row in states)
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
        "license_status": "Not Held",
        "bond_requirement": "Not Required",
        "bond_status": "Not Held",
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
        "bond_requirement": "Not Required",
        "bond_status": "Not Held",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200, response.text
    assert response.json()["overall_status"] == "Not Authorized"
    assert response.json()["indicator"] == "red"


def test_required_items_reject_not_required_status(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Required",
        "license_status": "Not Held",
        "coa_requirement": "Required",
        "coa_status": "Not Held",
        "bond_requirement": "Required",
        "bond_status": "Not Held",
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


def test_seed_preserves_legacy_expired_bond_status(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Colorado").one()
        for field in (
            "license_number", "license_issue_date", "license_expiration", "license_renewal_due",
            "coa_number", "coa_issue_date", "bond_number", "bond_amount", "bond_expiration",
            "regulator", "notes", "source_urls_json", "document_paths_json",
        ):
            setattr(row, field, None)
        row.updated_by = None
        row.data_confidence = "Unverified"
        row.license_status = "Not Held"
        row.certificate_of_authority = False
        row.bond_status = "Expired"
        db.commit()
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Colorado"]
    assert row["bond_status"] == "Expired"


def test_seed_preserves_legacy_revoked_coa_status(harness):
    client, _ = harness
    client.get("/api/compliance")
    dependency = client.app.dependency_overrides[get_db]
    with next(dependency()) as db:
        row = db.query(compliance_router.StateCompliance).filter_by(state="Colorado").one()
        for field in (
            "license_number", "license_issue_date", "license_expiration", "license_renewal_due",
            "coa_number", "coa_issue_date", "bond_number", "bond_amount", "bond_expiration",
            "regulator", "notes", "source_urls_json", "document_paths_json",
        ):
            setattr(row, field, None)
        row.updated_by = None
        row.data_confidence = "Unverified"
        row.license_status = "Not Held"
        row.coa_status = "Revoked"
        row.certificate_of_authority = False
        row.bond_status = "Unknown"
        db.commit()
    row = {item["state"]: item for item in client.get("/api/compliance").json()["states"]}["Colorado"]
    assert row["coa_status"] == "Revoked"


def test_postgresql_upgrade_ddl_is_idempotent():
    from app.models.state_compliance import _upgrade_statement
    statement = _upgrade_statement("coa_number", "VARCHAR", "postgresql")
    assert statement == "ALTER TABLE state_compliance ADD COLUMN IF NOT EXISTS coa_number VARCHAR"


def test_super_admin_can_update_state_compliance(harness):
    client, _ = harness
    response = client.put("/api/compliance/Alabama", json={
        "certificate_of_authority": True,
        "collection_license_requirement": "Required",
        "license_status": "Active",
        "license_number": "AL-123",
        "license_expiration": "2027-12-31",
        "coa_requirement": "Required",
        "coa_status": "Active",
        "bond_requirement": "Required",
        "bond_status": "Active",
        "bond_amount": 25000,
    })
    assert response.status_code == 200
    row = response.json()
    assert row["license_number"] == "AL-123"
    assert row["bond_amount"] == 25000


def test_admin_can_view_and_update_compliance(harness):
    client, current = harness
    current["user"] = {"timestation_id": "ADMIN_ROLE", "name": "Compliance Admin", "role": "admin"}
    assert client.get("/api/compliance").status_code == 200
    response = client.put("/api/compliance/Alabama", json={
        "collection_license_requirement": "Not Required",
        "license_status": "Not Held",
        "coa_requirement": "Not Required",
        "coa_status": "Not Held",
        "bond_requirement": "Not Required",
        "bond_status": "Not Held",
        "data_confidence": "Verified",
    })
    assert response.status_code == 200


def test_manager_is_forbidden_from_compliance(harness):
    client, current = harness
    current["user"] = {"timestation_id": "MGR", "name": "Brandon", "role": "manager"}
    assert client.get("/api/compliance").status_code == 403
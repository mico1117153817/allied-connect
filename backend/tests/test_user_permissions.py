from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.database import Base, get_db
from app.models.employee import Employee, EmployeePermissionAudit, ensure_employee_schema
from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.routers.auth import get_current_user
from app.routers import manager, tasks, company_calendar, vault

MARC_ID = "local_f2a5804ba2e5"
NICOLE_ID = "local_262a0ca4abea"


def _employee(employee_id, name, role="employee", **permissions):
    return Employee(timestation_id=employee_id, name=name, pin=employee_id[-4:], role=role, **permissions)


def test_employee_schema_upgrade_is_idempotent_and_backfills_safe_defaults():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE employees (id INTEGER PRIMARY KEY, timestation_id VARCHAR NOT NULL, name VARCHAR NOT NULL, pin VARCHAR NOT NULL, role VARCHAR)"))
        connection.execute(text("INSERT INTO employees (timestation_id,name,pin,role) VALUES (:id,'Marc','1','employee'), (:other,'Other Admin','2','admin'), ('worker','Worker','3','employee')"), {"id": MARC_ID, "other": "other-admin"})
    ensure_employee_schema(engine)
    ensure_employee_schema(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("employees")}
    assert {"login_enabled", "email_notifications_enabled", "company_task_access", "company_calendar_access", "password_vault_access"} <= columns
    with engine.connect() as connection:
        rows = {row.timestation_id: row for row in connection.execute(text("SELECT timestation_id, email_notifications_enabled, company_task_access, company_calendar_access, password_vault_access FROM employees"))}
    assert rows[MARC_ID].password_vault_access == 1
    assert rows["other-admin"].company_task_access == rows["other-admin"].company_calendar_access == 1
    assert rows["worker"].company_task_access == rows["worker"].company_calendar_access == rows["worker"].password_vault_access == 0
    assert all(row.email_notifications_enabled == 1 for row in rows.values())


def test_permission_administration_exact_id_vault_authority_and_audit(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with Session() as db:
        company = ComplianceCompany(legal_name="Allied", is_active=True)
        db.add(company)
        db.add_all([
            _employee(MARC_ID, "Renamed Marc", "super_admin", password_vault_access=True, company_task_access=True, company_calendar_access=True),
            _employee(NICOLE_ID, "Renamed Nicole", "employee", password_vault_access=True),
            _employee("normal-admin", "Admin", "admin"),
            _employee("arbitrary-super", "Super", "super_admin"),
            _employee("new-nicole", "Nicole Mancuso", "super_admin", email="nicole@alliedalliancegroupinc.com"),
            _employee("target", "Target"),
        ])
        db.flush()
        db.add(CompanyPermission(employee_id="target", company_id=company.id, can_edit=True))
        db.commit()

    current = {"id": MARC_ID}
    app = FastAPI()
    for router in (manager.router, tasks.router, company_calendar.router, vault.router):
        app.include_router(router)

    def override_db():
        with Session() as db:
            yield db

    def override_user():
        with Session() as db:
            employee = db.query(Employee).filter_by(timestation_id=current["id"]).one()
            return {"timestation_id": employee.timestation_id, "name": employee.name, "email": employee.email, "role": employee.role,
                    "email_notifications_enabled": employee.email_notifications_enabled, "company_task_access": employee.company_task_access,
                    "company_calendar_access": employee.company_calendar_access, "password_vault_access": employee.password_vault_access}

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    client = TestClient(app)

    endpoint = "/api/manager/employee/target/permissions"
    ordinary = {"email_notifications_enabled": False, "company_task_access": True, "company_calendar_access": True}
    for actor in ("normal-admin", "arbitrary-super", "new-nicole"):
        current["id"] = actor
        assert client.put(endpoint, json={**ordinary, "password_vault_access": True}).status_code == 403
    current["id"] = "arbitrary-super"
    assert client.get("/api/tasks").status_code == 403
    assert client.get("/api/company-calendar", params={"company_id": 1, "start": "2030-01-01T00:00:00Z", "end": "2030-02-01T00:00:00Z"}).status_code == 403
    assert client.get("/api/password-vault/status").status_code == 404
    with Session() as db:
        assert db.query(Employee).filter_by(timestation_id="target").one().password_vault_access is False

    current["id"] = MARC_ID
    granted = client.put(endpoint, json={**ordinary, "password_vault_access": True})
    assert granted.status_code == 200, granted.text
    assert granted.json()["password_vault_access"] is True
    assert client.put(endpoint, json={"password_vault_access": False}).status_code == 200

    current["id"] = NICOLE_ID
    assert client.put(endpoint, json={**ordinary, "password_vault_access": True}).status_code == 403
    assert client.put(endpoint, json={"password_vault_access": True}).status_code == 200
    assert client.put(endpoint, json={"password_vault_access": False}).status_code == 200

    with Session() as db:
        audits = db.query(EmployeePermissionAudit).filter_by(target_employee_id="target", permission="password_vault_access").order_by(EmployeePermissionAudit.id).all()
        assert [(row.actor_employee_id, row.old_value, row.new_value) for row in audits] == [(MARC_ID, False, True), (MARC_ID, True, False), (NICOLE_ID, False, True), (NICOLE_ID, True, False)]


def test_feature_flags_are_required_in_addition_to_company_permissions():
    assert tasks._user_can_tasks({"role": "super_admin", "company_task_access": False}) is False
    assert tasks._user_can_tasks({"role": "employee", "company_task_access": True}) is True
    assert company_calendar._user_can_calendar({"role": "super_admin", "company_calendar_access": False}) is False
    assert company_calendar._user_can_calendar({"role": "employee", "company_calendar_access": True}) is True
    assert vault._user_can_vault({"timestation_id": "target", "password_vault_access": True}) is True
    assert vault._user_can_vault({"timestation_id": MARC_ID, "password_vault_access": False}) is False

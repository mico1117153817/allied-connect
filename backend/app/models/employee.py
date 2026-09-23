from sqlalchemy import Column, Integer, String, Boolean, DateTime, inspect, text
from sqlalchemy.sql import func
from app.models.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    timestation_id = Column(String, unique=True, index=True, nullable=False)
    custom_employee_id = Column(String, nullable=True)
    name = Column(String, nullable=False)
    title = Column(String, nullable=True)
    primary_department = Column(String, nullable=True)
    primary_department_id = Column(String, nullable=True)
    pin = Column(String, nullable=False, index=True)
    email = Column(String, nullable=True)
    status = Column(String, default="out")  # in/out from TimeStation
    role = Column(String, default="employee")  # employee / manager / super_admin
    hourly_rate = Column(String, nullable=True)  # private rate set by super admins
    is_active = Column(Boolean, default=True)
    login_enabled = Column(Boolean, nullable=False, default=True)
    email_notifications_enabled = Column(Boolean, nullable=False, default=True)
    company_task_access = Column(Boolean, nullable=False, default=False)
    company_calendar_access = Column(Boolean, nullable=False, default=False)
    password_vault_access = Column(Boolean, nullable=False, default=False)
    last_synced = Column(DateTime, nullable=True)


class EmployeePermissionAudit(Base):
    __tablename__ = "employee_permission_audit"

    id = Column(Integer, primary_key=True)
    actor_employee_id = Column(String, nullable=False, index=True)
    target_employee_id = Column(String, nullable=False, index=True)
    permission = Column(String, nullable=False, index=True)
    old_value = Column(Boolean, nullable=False)
    new_value = Column(Boolean, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


VAULT_PERMISSION_AUTHORITIES = frozenset({"local_f2a5804ba2e5", "local_262a0ca4abea"})


def ensure_employee_schema(engine):
    """Add employee feature permissions with repeatable, least-privilege backfills."""
    inspector = inspect(engine)
    if "employees" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("employees")}
    definitions = {
        "login_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "email_notifications_enabled": "BOOLEAN NOT NULL DEFAULT TRUE",
        "company_task_access": "BOOLEAN NOT NULL DEFAULT FALSE",
        "company_calendar_access": "BOOLEAN NOT NULL DEFAULT FALSE",
        "password_vault_access": "BOOLEAN NOT NULL DEFAULT FALSE",
    }
    added = set()
    with engine.begin() as connection:
        for name, definition in definitions.items():
            if name not in existing:
                clause = " IF NOT EXISTS" if engine.dialect.name == "postgresql" else ""
                connection.exec_driver_sql(f"ALTER TABLE employees ADD COLUMN{clause} {name} {definition}")
                added.add(name)
        if {"company_task_access", "company_calendar_access"} & added:
            updates = []
            if "company_task_access" in added: updates.append("company_task_access = TRUE")
            if "company_calendar_access" in added: updates.append("company_calendar_access = TRUE")
            connection.execute(text(f"UPDATE employees SET {', '.join(updates)} WHERE role IN ('admin', 'super_admin')"))
        if "password_vault_access" in added:
            connection.execute(text("UPDATE employees SET password_vault_access = TRUE WHERE timestation_id IN (:marc, :nicole)"), {"marc": "local_f2a5804ba2e5", "nicole": "local_262a0ca4abea"})

from sqlalchemy import Column, Integer, String, Boolean, DateTime, inspect
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
    last_synced = Column(DateTime, nullable=True)


def ensure_employee_schema(engine):
    """Add login access control without disturbing existing employee records."""
    inspector = inspect(engine)
    if "employees" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("employees")}
    if "login_enabled" in existing and engine.dialect.name != "postgresql":
        return
    if engine.dialect.name == "postgresql":
        statement = "ALTER TABLE employees ADD COLUMN IF NOT EXISTS login_enabled BOOLEAN NOT NULL DEFAULT TRUE"
    else:
        statement = "ALTER TABLE employees ADD COLUMN login_enabled BOOLEAN NOT NULL DEFAULT 1"
    with engine.begin() as connection:
        connection.exec_driver_sql(statement)

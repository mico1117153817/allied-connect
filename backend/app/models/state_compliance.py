from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String, Text, inspect
from sqlalchemy.sql import func

from app.models.database import Base


class StateCompliance(Base):
    __tablename__ = "state_compliance"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String, unique=True, nullable=False, index=True)
    jurisdiction = Column(String, nullable=True)
    collection_license_requirement = Column(String, nullable=False, default="Unknown")
    license_status = Column(String, nullable=False, default="Not Held")
    license_number = Column(String, nullable=True)
    license_issue_date = Column(Date, nullable=True)
    license_expiration = Column(Date, nullable=True)
    license_renewal_due = Column(Date, nullable=True)
    coa_requirement = Column(String, nullable=False, default="Unknown")
    coa_status = Column(String, nullable=False, default="Unknown")
    coa_number = Column(String, nullable=True)
    coa_issue_date = Column(Date, nullable=True)
    certificate_of_authority = Column(Boolean, nullable=False, default=False)
    bond_requirement = Column(String, nullable=False, default="Unknown")
    bond_status = Column(String, nullable=False, default="Unknown")
    bond_number = Column(String, nullable=True)
    bond_amount = Column(Numeric(12, 2), nullable=True)
    bond_expiration = Column(Date, nullable=True)
    regulator = Column(String, nullable=True)
    state_portal_url = Column(String, nullable=True)
    portal_username = Column(String, nullable=True)
    portal_password_encrypted = Column(Text, nullable=True)
    state_portal_url_migrated = Column(Boolean, nullable=False, default=False)
    notes = Column(Text, nullable=True)
    source_urls_json = Column(Text, nullable=True)
    document_paths_json = Column(Text, nullable=True)
    data_confidence = Column(String, nullable=False, default="Unverified")
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


SCHEMA_UPGRADE_COLUMNS = {
    "jurisdiction": "VARCHAR",
    "collection_license_requirement": "VARCHAR NOT NULL DEFAULT 'Unknown'",
    "license_issue_date": "DATE",
    "license_renewal_due": "DATE",
    "coa_requirement": "VARCHAR NOT NULL DEFAULT 'Unknown'",
    "coa_status": "VARCHAR NOT NULL DEFAULT 'Unknown'",
    "coa_number": "VARCHAR",
    "coa_issue_date": "DATE",
    "bond_requirement": "VARCHAR NOT NULL DEFAULT 'Unknown'",
    "bond_number": "VARCHAR",
    "bond_expiration": "DATE",
    "regulator": "VARCHAR",
    "state_portal_url": "VARCHAR",
    "portal_username": "VARCHAR",
    "portal_password_encrypted": "TEXT",
    "state_portal_url_migrated": "BOOLEAN NOT NULL DEFAULT FALSE",
    "notes": "TEXT",
    "source_urls_json": "TEXT",
    "document_paths_json": "TEXT",
    "data_confidence": "VARCHAR NOT NULL DEFAULT 'Unverified'",
}


def _upgrade_statement(name: str, sql_type: str, dialect: str) -> str:
    if dialect == "postgresql":
        return f"ALTER TABLE state_compliance ADD COLUMN IF NOT EXISTS {name} {sql_type}"
    return f"ALTER TABLE state_compliance ADD COLUMN {name} {sql_type}"


def ensure_state_compliance_schema(engine):
    """Add newly introduced columns without destroying existing compliance data."""
    inspector = inspect(engine)
    if "state_compliance" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("state_compliance")}
    dialect = engine.dialect.name
    with engine.begin() as connection:
        for name, sql_type in SCHEMA_UPGRADE_COLUMNS.items():
            if dialect == "postgresql" or name not in existing:
                connection.exec_driver_sql(_upgrade_statement(name, sql_type, dialect))

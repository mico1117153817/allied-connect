"""Additive corporate PDF schema migration; never seeds or updates company data.

Safe to repeat on an already migrated database. The existing legacy compliance
migration remains authoritative and must run first when its guard rejects a DB.
"""
from app.models.corporate_document import CorporateDocument
from app.models.compliance_migration import assert_compliance_schema_ready
# Register FK targets for standalone invocation too.
from app.models.compliance_company import ComplianceCompany  # noqa: F401
from app.models.employee import Employee  # noqa: F401


def ensure_corporate_document_schema(engine):
    assert_compliance_schema_ready(engine)
    with engine.begin() as connection:
        CorporateDocument.__table__.create(connection, checkfirst=True)

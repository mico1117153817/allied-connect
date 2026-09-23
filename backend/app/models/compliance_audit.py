"""Transactional, field-level compliance audit; secrets never leave this boundary."""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.sql import func
from app.models.database import Base


class ComplianceAudit(Base):
    __tablename__ = 'compliance_audit'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('compliance_companies.id'), nullable=False, index=True)
    user_id = Column(String)
    user_name = Column(String)
    state = Column(String, index=True)
    field = Column(String, nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


def snapshot(row):
    return {c.name: getattr(row, c.name) for c in row.__table__.columns
            if c.name not in {'id', 'company_id', 'updated_at', 'updated_by', 'legacy_preserved', 'state_portal_url_migrated'}}


def audit_event(db, user, company_id, state, field, old, new):
    def safe(value):
        if value is None:
            return None
        if field in {'portal_username', 'portal_password_encrypted'}:
            return '[REDACTED]'
        return value.isoformat() if hasattr(value, 'isoformat') else str(value)
    db.add(ComplianceAudit(company_id=company_id, user_id=user.get('timestation_id'), user_name=user.get('name'),
                           state=state, field=field, old_value=safe(old), new_value=safe(new)))


def audit_diff(db, user, company_id, state, before, row):
    for field, value in snapshot(row).items():
        if before.get(field) != value:
            audit_event(db, user, company_id, state, field, before.get(field), value)

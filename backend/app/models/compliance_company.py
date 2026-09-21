from sqlalchemy import Boolean, Column, Date, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint, LargeBinary
from sqlalchemy.sql import func
from app.models.database import Base


class CompanyLogo(Base):
    __tablename__ = "compliance_company_logos"
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), primary_key=True)
    content = Column(LargeBinary, nullable=False)
    content_type = Column(String, nullable=False)


class CompanyPermission(Base):
    __tablename__ = "compliance_company_permissions"
    id = Column(Integer, primary_key=True)
    employee_id = Column(String, nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), nullable=False, index=True)
    can_edit = Column(Boolean, nullable=False, default=False)
    __table_args__ = (UniqueConstraint("employee_id", "company_id", name="uq_employee_compliance_company"),)


class ComplianceCompany(Base):
    __tablename__ = 'compliance_companies'
    id = Column(Integer, primary_key=True)
    legal_name = Column(String, nullable=False)
    dba_name = Column(String)
    entity_type = Column(String)
    ein = Column(String)
    formation_state = Column(String)
    formation_date = Column(Date)
    business_address = Column(Text)
    mailing_address = Column(Text)
    phone = Column(String)
    email = Column(String)
    website = Column(String)
    registered_agent = Column(String)
    registered_agent_address = Column(Text)
    logo_path = Column(String)
    notes = Column(Text)
    is_active = Column(Boolean, nullable=False, default=True)
    # Migrated registers must never be re-enriched by the legacy workbook seed.
    legacy_preserved = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

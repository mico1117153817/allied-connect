from sqlalchemy import Column, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.sql import func

from app.models.database import Base


class ComplianceAttachment(Base):
    __tablename__ = "compliance_attachments"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), nullable=False, default=1, index=True)
    state = Column(String, nullable=False, index=True)
    item_type = Column(String, nullable=False, index=True)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False, default="application/pdf")
    content = Column(LargeBinary, nullable=False)
    archived_at = Column(DateTime)
    archived_by = Column(String)
    uploaded_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

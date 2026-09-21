"""Private company PDFs, independent of state compliance and expiration tracking."""
import uuid
from sqlalchemy import Column, Integer, String, Text, LargeBinary, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.models.database import Base

CATEGORIES = ('EIN', 'Articles of Incorporation', 'Operating Agreement', 'Bylaws',
              'Certificate of Good Standing', 'Other Corporate Document')


class CorporateDocument(Base):
    __tablename__ = 'corporate_documents'
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey('compliance_companies.id'), nullable=False, index=True)
    document_type = Column(String(64), nullable=False)
    storage_key = Column(String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    original_file_name = Column(String(255), nullable=False)
    uploaded_by_user_id = Column(String, ForeignKey('employees.timestation_id'), nullable=False)
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now())
    notes = Column(Text)
    status = Column(String(16), nullable=False, default='active')
    replaced_document_id = Column(Integer, ForeignKey('corporate_documents.id'))
    content = Column(LargeBinary, nullable=False)
    __table_args__ = (
        CheckConstraint(document_type.in_(CATEGORIES), name='ck_corporate_document_category'),
        CheckConstraint("status IN ('active', 'replaced', 'deleted')", name='ck_corporate_document_status'),
        CheckConstraint('notes IS NULL OR length(notes) <= 4000', name='ck_corporate_document_notes'),
    )

from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.models.database import Base


class DocumentAssignment(Base):
    __tablename__ = "document_assignments"
    __table_args__ = (UniqueConstraint("document_id", "employee_id", name="uq_document_employee_assignment"),)

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(String, nullable=False, index=True)
    assigned_by = Column(String, nullable=True)
    assigned_at = Column(DateTime, server_default=func.now())
    viewed_at = Column(DateTime, nullable=True)
    voided_at = Column(DateTime, nullable=True)
    voided_by = Column(String, nullable=True)

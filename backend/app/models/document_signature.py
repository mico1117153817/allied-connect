from sqlalchemy import Column, Integer, LargeBinary, String, DateTime
from sqlalchemy.sql import func
from app.models.database import Base


class DocumentContent(Base):
    __tablename__ = "document_contents"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, unique=True, index=True)
    content = Column(LargeBinary, nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False, default="application/pdf")
    created_at = Column(DateTime, server_default=func.now())


class DocumentSignature(Base):
    __tablename__ = "document_signatures"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, nullable=False, index=True)
    employee_id = Column(String, nullable=False, index=True)
    signed_at = Column(DateTime, server_default=func.now())
    ip_address = Column(String, nullable=True)
    signature_hash = Column(String, nullable=True)

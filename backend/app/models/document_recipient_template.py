from sqlalchemy import Column, Integer, String, DateTime, Text
from sqlalchemy.sql import func
from app.models.database import Base


class DocumentRecipientTemplate(Base):
    __tablename__ = "document_recipient_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    employee_ids_json = Column(Text, nullable=False, default="[]")
    created_by = Column(String, nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

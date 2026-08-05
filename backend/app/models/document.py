from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from app.models.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)  # pdf, docx
    version = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    requires_signature = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    created_by = Column(String, nullable=True)  # manager timestation_id

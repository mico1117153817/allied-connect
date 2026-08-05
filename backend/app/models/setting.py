from sqlalchemy import Column, Integer, String, Boolean
from app.models.database import Base


class Setting(Base):
    """Key-value store for portal-wide settings configurable by managers."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(String, nullable=False)
    description = Column(String, nullable=True)

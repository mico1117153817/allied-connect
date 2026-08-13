from sqlalchemy import Boolean, Column, Date, DateTime, Integer, Numeric, String
from sqlalchemy.sql import func

from app.models.database import Base


class StateCompliance(Base):
    __tablename__ = "state_compliance"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String, unique=True, nullable=False, index=True)
    certificate_of_authority = Column(Boolean, nullable=False, default=False)
    license_status = Column(String, nullable=False, default="Not Held")
    license_number = Column(String, nullable=True)
    license_expiration = Column(Date, nullable=True)
    bond_status = Column(String, nullable=False, default="Expired")
    bond_amount = Column(Numeric(12, 2), nullable=True)
    updated_by = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

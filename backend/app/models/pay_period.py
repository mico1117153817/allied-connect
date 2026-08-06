from sqlalchemy import Column, Integer, String, Date, Boolean, DateTime
from sqlalchemy.sql import func
from app.models.database import Base


class PayPeriod(Base):
    __tablename__ = "pay_periods"

    id = Column(Integer, primary_key=True, index=True)
    pay_date = Column(Date, nullable=False, index=True)  # the actual pay date (8th or 22nd)
    label = Column(String, nullable=False)  # e.g. "8/8" or "8/22"
    start_date = Column(Date, nullable=False)  # first day included in this pay period
    end_date = Column(Date, nullable=False)  # last day included in this pay period
    is_active = Column(Boolean, default=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

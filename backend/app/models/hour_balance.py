from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text
from sqlalchemy.sql import func
from app.models.database import Base


class HourBalance(Base):
    """Running balance of hours per employee per type."""
    __tablename__ = "hour_balances"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)  # back_hours, vacation_hours, sick_hours
    balance = Column(Numeric(10, 2), default=0)
    updated_at = Column(DateTime, server_default=func.now())


class HourTransaction(Base):
    """Audit log of every hour addition or deduction."""
    __tablename__ = "hour_transactions"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False, index=True)
    type = Column(String, nullable=False)  # back_hours, vacation_hours, sick_hours
    amount = Column(Numeric(10, 2), nullable=False)  # positive = added, negative = deducted
    action = Column(String, nullable=False)  # "added" or "deducted"
    reason = Column(Text, nullable=True)
    input_by = Column(String, nullable=True)  # timestation_id of who did it
    input_by_name = Column(String, nullable=True)
    time_off_request_id = Column(Integer, nullable=True)  # link to time-off request if deduction
    created_at = Column(DateTime, server_default=func.now())

from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric
from sqlalchemy.sql import func
from app.models.database import Base


class TimeOffRequest(Base):
    __tablename__ = "time_off_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False, index=True)
    request_type = Column(String, nullable=False)  # vacation, sick, personal, unpaid, back_hours
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(String, nullable=True)
    status = Column(String, default="pending")  # pending, approved, denied
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    # New: hours to use from balance
    hour_type = Column(String, nullable=True)  # back_hours, vacation_hours, sick_hours (which pool to deduct from)
    hours_requested = Column(Numeric(10, 2), nullable=True)  # how many hours to use

from sqlalchemy import Column, Integer, String, Time
from app.models.database import Base


class ScheduledShift(Base):
    __tablename__ = "scheduled_shifts"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False, index=True)  # timestation_id
    day_of_week = Column(Integer, nullable=False)  # 0=Mon..6=Sun
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    department_id = Column(String, nullable=True)

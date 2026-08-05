from sqlalchemy import Column, Integer, String, Numeric, Date, DateTime
from sqlalchemy.sql import func
from app.models.database import Base


class PayAdjustment(Base):
    __tablename__ = "pay_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(String, nullable=False, index=True)
    pay_date = Column(Date, nullable=False, index=True)
    type = Column(String, nullable=False)  # back_hours or vacation_hours
    hours = Column(Numeric(10, 2), nullable=False)
    description = Column(String, nullable=True)
    input_by = Column(String, nullable=True)  # manager timestation_id
    created_at = Column(DateTime, server_default=func.now())

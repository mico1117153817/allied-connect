"""Employee dashboard API: profile, hours, calendar, pay summary, email update."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.models.employee import Employee
from app.models.scheduled_shift import ScheduledShift
from app.models.pay_adjustment import PayAdjustment
from app.services.timestation import timestation
from app.services.calendar import build_calendar_data
from app.services.settings_service import get_setting
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/me", tags=["employee"])


# ── Schemas ──────────────────────────────────────────────────────────


class EmailUpdate(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        v = v.strip()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("must be a valid email address")
        return v


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/")
async def get_profile(user: dict = Depends(get_current_user)):
    """Return the current authenticated employee's profile."""
    return {
        "timestation_id": user.get("timestation_id"),
        "name": user.get("name"),
        "role": user.get("role"),
        "email": user.get("email"),
    }


@router.get("/hours")
async def get_hours(
    start: str,
    end: str,
    user: dict = Depends(get_current_user),
):
    """Get worked shifts and total hours for a date range."""
    shifts = await timestation.get_shifts(user["timestation_id"], start, end)
    total_minutes = sum(int(s.get("total_minutes", 0) or 0) for s in shifts)
    return {
        "start": start,
        "end": end,
        "total_hours": round(total_minutes / 60.0, 2),
        "shifts": shifts,
    }


@router.get("/calendar")
async def get_calendar(
    start: str,
    end: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get calendar data for a date range, with late-arrival detection."""
    shifts = await timestation.get_shifts(user["timestation_id"], start, end)
    scheduled_shifts = (
        db.query(ScheduledShift)
        .filter(ScheduledShift.employee_id == user["timestation_id"])
        .all()
    )
    # Get late threshold from settings (DB) or config default
    threshold_str = get_setting(db, "late_threshold_minutes")
    threshold = int(threshold_str) if threshold_str else settings.LATE_THRESHOLD_MINUTES
    calendar = build_calendar_data(shifts, scheduled_shifts, start, end, late_threshold_minutes=threshold)
    return {
        "start": start,
        "end": end,
        "late_threshold_minutes": threshold,
        "days": calendar,
    }


@router.get("/pay-summary")
async def get_pay_summary(
    pay_date: str,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get pay summary (back_hours + vacation_hours) for a given pay date."""
    try:
        pay_date_obj = date.fromisoformat(pay_date)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="pay_date must be in YYYY-MM-DD format",
        )

    adjustments = (
        db.query(PayAdjustment)
        .filter(
            PayAdjustment.employee_id == user["timestation_id"],
            PayAdjustment.pay_date == pay_date_obj,
        )
        .all()
    )

    back_hours = 0.0
    vacation_hours = 0.0
    items = []
    for adj in adjustments:
        hours = float(adj.hours)
        items.append({
            "id": adj.id,
            "type": adj.type,
            "hours": hours,
            "description": adj.description,
        })
        if adj.type == "back_hours":
            back_hours += hours
        elif adj.type == "vacation_hours":
            vacation_hours += hours

    return {
        "pay_date": pay_date,
        "back_hours": round(back_hours, 2),
        "vacation_hours": round(vacation_hours, 2),
        "total_hours": round(back_hours + vacation_hours, 2),
        "items": items,
    }


@router.put("/email")
async def update_email(
    payload: EmailUpdate,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update the current employee's email address."""
    employee = (
        db.query(Employee)
        .filter(Employee.timestation_id == user["timestation_id"])
        .first()
    )
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee record not found",
        )
    employee.email = payload.email
    db.commit()
    db.refresh(employee)
    return {
        "timestation_id": employee.timestation_id,
        "email": employee.email,
    }

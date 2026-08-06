"""Employee dashboard API: profile, hours, calendar, pay summary, email update, pay periods."""
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.models.employee import Employee
from app.models.scheduled_shift import ScheduledShift
from app.models.pay_adjustment import PayAdjustment
from app.models.pay_period import PayPeriod
from app.models.hour_balance import HourBalance, HourTransaction
from app.services.timestation import timestation
from app.services.calendar import build_calendar_data
from app.services.settings_service import get_setting
from app.services.hour_balance_service import get_all_balances, get_transaction_history
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
    # Get thresholds from settings (DB) or config default
    threshold_str = get_setting(db, "late_threshold_minutes")
    threshold = int(threshold_str) if threshold_str else settings.LATE_THRESHOLD_MINUTES
    early_str = get_setting(db, "early_leave_threshold_minutes")
    early_threshold = int(early_str) if early_str else threshold
    calendar = build_calendar_data(shifts, scheduled_shifts, start, end, late_threshold_minutes=threshold, early_leave_threshold_minutes=early_threshold)
    return {
        "start": start,
        "end": end,
        "late_threshold_minutes": threshold,
        "early_leave_threshold_minutes": early_threshold,
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


# ── Pay Periods (employee view) ───────────────────────────────

@router.get("/pay-periods")
async def list_pay_periods(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all available pay periods for the employee to select from."""
    periods = db.query(PayPeriod).filter(PayPeriod.is_active == True).order_by(PayPeriod.pay_date.desc()).all()
    return {
        "pay_periods": [
            {
                "id": p.id,
                "pay_date": p.pay_date.isoformat(),
                "label": p.label,
                "start_date": p.start_date.isoformat(),
                "end_date": p.end_date.isoformat(),
            }
            for p in periods
        ]
    }


@router.get("/pay-period/{period_id}")
async def get_pay_period_data(
    period_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get hours, calendar, and pay adjustments for a specific pay period."""
    pp = db.query(PayPeriod).filter(PayPeriod.id == period_id).first()
    if not pp:
        raise HTTPException(404, "Pay period not found")

    start_str = pp.start_date.isoformat()
    end_str = pp.end_date.isoformat()

    # Get shifts from TimeStation
    shifts = await timestation.get_shifts(user["timestation_id"], start_str, end_str)
    total_minutes = sum(int(s.get("total_minutes", 0) or 0) for s in shifts)

    # Get scheduled shifts for calendar
    scheduled_shifts = (
        db.query(ScheduledShift)
        .filter(ScheduledShift.employee_id == user["timestation_id"])
        .all()
    )
    threshold_str = get_setting(db, "late_threshold_minutes")
    threshold = int(threshold_str) if threshold_str else settings.LATE_THRESHOLD_MINUTES
    early_str = get_setting(db, "early_leave_threshold_minutes")
    early_threshold = int(early_str) if early_str else threshold
    calendar = build_calendar_data(shifts, scheduled_shifts, start_str, end_str,
                                   late_threshold_minutes=threshold, early_leave_threshold_minutes=early_threshold)

    # Get pay adjustments for this pay date
    adjustments = (
        db.query(PayAdjustment)
        .filter(
            PayAdjustment.employee_id == user["timestation_id"],
            PayAdjustment.pay_date == pp.pay_date,
        )
        .all()
    )
    back_hours = sum(float(a.hours) for a in adjustments if a.type == "back_hours")
    vacation_hours = sum(float(a.hours) for a in adjustments if a.type == "vacation_hours")

    # Get employee's private hourly rate for gross pay calculation
    emp = db.query(Employee).filter(Employee.timestation_id == user["timestation_id"]).first()
    hourly_rate = float(emp.hourly_rate) if emp and emp.hourly_rate else None
    worked_hours = round(total_minutes / 60.0, 2)
    gross_pay = None
    if hourly_rate:
        gross_pay = round((worked_hours + back_hours + vacation_hours) * hourly_rate, 2)

    # Stats
    worked_days = [d for d in calendar if d["worked"]]
    late_days = [d for d in calendar if d["is_late"]]
    early_days = [d for d in calendar if d["is_early_leave"]]

    return {
        "pay_period": {
            "id": pp.id,
            "label": pp.label,
            "pay_date": pp.pay_date.isoformat(),
            "start_date": start_str,
            "end_date": end_str,
        },
        "total_hours": worked_hours,
        "days_worked": len(worked_days),
        "late_arrivals": len(late_days),
        "left_early": len(early_days),
        "back_hours": round(back_hours, 2),
        "vacation_hours": round(vacation_hours, 2),
        "hourly_rate": hourly_rate,
        "gross_pay": gross_pay,
        "calendar": calendar,
        "shifts": shifts,
    }


# ── Hour Balances (employee sees their own) ───────────────────

@router.get("/balances")
async def get_my_balances(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current employee's hour balances (back, vacation, sick)."""
    balances = get_all_balances(db, user["timestation_id"])
    return {
        "employee_id": user["timestation_id"],
        "balances": balances,
    }


@router.get("/balance-history")
async def get_my_balance_history(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current employee's full transaction history with date/time stamps."""
    transactions = get_transaction_history(db, user["timestation_id"])
    balances = get_all_balances(db, user["timestation_id"])
    return {
        "balances": balances,
        "transactions": transactions,
    }

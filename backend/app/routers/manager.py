import csv
import io
from datetime import date, time
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.employee import Employee
from app.models.pay_adjustment import PayAdjustment
from app.models.time_off import TimeOffRequest
from app.models.scheduled_shift import ScheduledShift
from app.routers.auth import require_manager
from app.services.timestation import timestation

router = APIRouter(prefix="/api/manager", tags=["manager"])


# ── Today's status (at work / not at work) ──────────────────────

@router.get("/today")
async def get_today_status(user: dict = Depends(require_manager)):
    csv_text = await timestation.get_current_status_csv()
    reader = csv.DictReader(io.StringIO(csv_text))
    at_work = []
    not_at_work = []
    for row in reader:
        status = row.get("Status", "").strip()
        entry = {
            "name": row.get("Name", ""),
            "department": row.get("Primary Department", ""),
            "status": status,
            "last_seen": row.get("Date / Time", ""),
            "custom_id": row.get("Employee ID", ""),
        }
        if status.lower() == "in":
            at_work.append(entry)
        else:
            not_at_work.append(entry)
    return {"at_work": at_work, "not_at_work": not_at_work}


# ── All employees ──────────────────────────────────────────────

@router.get("/employees")
async def list_all_employees(
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    ts_employees = await timestation.get_employees()
    ts_ids = {e["employee_id"] for e in ts_employees}
    result = []

    # TimeStation employees
    for emp in ts_employees:
        db_emp = (
            db.query(Employee)
            .filter(Employee.timestation_id == emp["employee_id"])
            .first()
        )
        result.append(
            {
                "timestation_id": emp["employee_id"],
                "name": emp.get("name", ""),
                "department": emp.get("primary_department", ""),
                "status": emp.get("status", ""),
                "email": emp.get("email") or (db_emp.email if db_emp else None),
                "role": db_emp.role if db_emp else "employee",
                "custom_id": emp.get("custom_employee_id", ""),
            }
        )

    # Local-only employees (not in TimeStation, e.g. execs)
    local_emps = (
        db.query(Employee)
        .filter(~Employee.timestation_id.in_(ts_ids) if ts_ids else True)
        .filter(Employee.is_active == True)
        .all()
    )
    for emp in local_emps:
        result.append(
            {
                "timestation_id": emp.timestation_id,
                "name": emp.name,
                "department": emp.primary_department or "",
                "status": emp.status or "out",
                "email": emp.email,
                "role": emp.role,
                "custom_id": emp.custom_employee_id or "",
            }
        )

    return {"employees": result}


# ── Pay adjustments (back hours & vacation hours) ──────────────

class PayAdjustmentInput(BaseModel):
    employee_id: str
    pay_date: date
    type: str  # back_hours or vacation_hours
    hours: float
    description: str | None = None


@router.post("/pay-adjustment")
async def create_pay_adjustment(
    req: PayAdjustmentInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    if req.type not in ("back_hours", "vacation_hours"):
        raise HTTPException(400, "Type must be back_hours or vacation_hours")
    adj = PayAdjustment(
        employee_id=req.employee_id,
        pay_date=req.pay_date,
        type=req.type,
        hours=req.hours,
        description=req.description,
        input_by=user["timestation_id"],
    )
    db.add(adj)
    db.commit()
    return {"id": adj.id, "status": "created"}


@router.get("/pay-adjustments")
async def get_pay_adjustments(
    pay_date: str = Query(...),
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    adjustments = (
        db.query(PayAdjustment)
        .filter(PayAdjustment.pay_date == pay_date)
        .all()
    )
    result = []
    for a in adjustments:
        emp = (
            db.query(Employee)
            .filter(Employee.timestation_id == a.employee_id)
            .first()
        )
        result.append(
            {
                "id": a.id,
                "employee_name": emp.name if emp else "Unknown",
                "employee_id": a.employee_id,
                "type": a.type,
                "hours": float(a.hours),
                "description": a.description,
                "pay_date": a.pay_date.isoformat(),
            }
        )
    return {"pay_date": pay_date, "adjustments": result}


# ── Approved time off ──────────────────────────────────────────

@router.get("/approved-time-off")
async def get_approved_time_off(
    start: str = Query(...),
    end: str = Query(...),
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    requests = (
        db.query(TimeOffRequest)
        .filter(
            TimeOffRequest.status == "approved",
            TimeOffRequest.start_date >= start,
            TimeOffRequest.end_date <= end,
        )
        .all()
    )
    result = []
    for r in requests:
        emp = (
            db.query(Employee)
            .filter(Employee.timestation_id == r.employee_id)
            .first()
        )
        result.append(
            {
                "employee_name": emp.name if emp else "Unknown",
                "type": r.request_type,
                "start_date": r.start_date.isoformat(),
                "end_date": r.end_date.isoformat(),
            }
        )
    return {"approved_time_off": result}


# ── Scheduled shifts (for late detection) ──────────────────────

class ScheduledShiftInput(BaseModel):
    employee_id: str
    day_of_week: int  # 0=Mon..6=Sun
    start_time: str  # "09:00"
    end_time: str  # "17:00"
    department_id: str | None = None


@router.post("/scheduled-shifts")
async def set_scheduled_shift(
    req: ScheduledShiftInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    # Remove existing shift for this employee + day
    existing = (
        db.query(ScheduledShift)
        .filter(
            ScheduledShift.employee_id == req.employee_id,
            ScheduledShift.day_of_week == req.day_of_week,
        )
        .first()
    )
    if existing:
        db.delete(existing)
    ss = ScheduledShift(
        employee_id=req.employee_id,
        day_of_week=req.day_of_week,
        start_time=time.fromisoformat(req.start_time),
        end_time=time.fromisoformat(req.end_time),
        department_id=req.department_id,
    )
    db.add(ss)
    db.commit()
    return {"id": ss.id, "status": "created"}


@router.get("/scheduled-shifts/{employee_id}")
async def get_scheduled_shifts(
    employee_id: str,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    shifts = (
        db.query(ScheduledShift)
        .filter(ScheduledShift.employee_id == employee_id)
        .all()
    )
    return {
        "scheduled_shifts": [
            {
                "id": s.id,
                "day_of_week": s.day_of_week,
                "start_time": s.start_time.isoformat(),
                "end_time": s.end_time.isoformat(),
            }
            for s in shifts
        ]
    }


# ── Bulk schedule: apply to all employees at once ─────────────

class BulkScheduleInput(BaseModel):
    schedules: list[dict]  # [{"day_of_week": 0, "start_time": "09:00", "end_time": "17:00"}, ...]
    employee_ids: list[str] | None = None  # if None, apply to all


@router.post("/bulk-schedule")
async def set_bulk_schedule(
    req: BulkScheduleInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Apply a schedule template to all (or selected) employees at once.
    Overwrites any existing scheduled shifts for the given days."""
    # Determine target employees
    if req.employee_ids:
        target_ids = req.employee_ids
    else:
        # All employees in the DB
        all_emps = db.query(Employee).filter(Employee.is_active == True).all()
        target_ids = [e.timestation_id for e in all_emps]

    count = 0
    for emp_id in target_ids:
        for sched in req.schedules:
            dow = sched["day_of_week"]
            start = sched["start_time"]
            end = sched.get("end_time", "17:00")

            # Remove existing shift for this employee + day
            existing = (
                db.query(ScheduledShift)
                .filter(
                    ScheduledShift.employee_id == emp_id,
                    ScheduledShift.day_of_week == dow,
                )
                .first()
            )
            if existing:
                db.delete(existing)

            ss = ScheduledShift(
                employee_id=emp_id,
                day_of_week=dow,
                start_time=time.fromisoformat(start),
                end_time=time.fromisoformat(end),
            )
            db.add(ss)
            count += 1

    db.commit()
    return {
        "status": "created",
        "employees_updated": len(target_ids),
        "total_shifts": count,
    }


# ── Set manager role ───────────────────────────────────────────

class SetRoleInput(BaseModel):
    employee_id: str
    role: str  # "employee" or "manager"


@router.put("/role")
async def set_employee_role(
    req: SetRoleInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    emp = (
        db.query(Employee)
        .filter(Employee.timestation_id == req.employee_id)
        .first()
    )
    if not emp:
        raise HTTPException(404, "Employee not found")
    if req.role not in ("employee", "manager"):
        raise HTTPException(400, "Role must be employee or manager")
    emp.role = req.role
    db.commit()
    return {"employee_id": emp.timestation_id, "role": emp.role}


# ── Create local-only account (for execs not in TimeStation) ───

class CreateLocalAccountInput(BaseModel):
    name: str
    pin: str
    email: str | None = None
    title: str | None = None
    role: str = "manager"  # default to manager for execs


@router.post("/local-account")
async def create_local_account(
    req: CreateLocalAccountInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Create a local-only employee account (not synced from TimeStation).
    Used for executives like President/VP who don't clock in via TimeStation."""
    # Check PIN isn't already in use
    existing = db.query(Employee).filter(Employee.pin == req.pin).first()
    if existing:
        raise HTTPException(400, f"PIN {req.pin} is already assigned to {existing.name}")

    # Generate a local ID
    import hashlib
    local_id = f"local_{hashlib.md5(req.name.encode()).hexdigest()[:12]}"

    emp = Employee(
        timestation_id=local_id,
        name=req.name,
        pin=req.pin,
        email=req.email,
        title=req.title,
        role=req.role,
        status="out",
        is_active=True,
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return {
        "employee_id": emp.timestation_id,
        "name": emp.name,
        "pin": emp.pin,
        "role": emp.role,
        "status": "created",
    }


# ── View any employee's hours and calendar (manager) ──────────

@router.get("/employee/{employee_id}/hours")
async def get_employee_hours(
    employee_id: str,
    start: str = Query(...),
    end: str = Query(...),
    user: dict = Depends(require_manager),
):
    """Get any employee's shifts and total hours for a date range."""
    shifts = await timestation.get_shifts(employee_id, start, end)
    total_minutes = sum(int(s.get("total_minutes", 0) or 0) for s in shifts)
    return {
        "employee_id": employee_id,
        "start": start,
        "end": end,
        "total_hours": round(total_minutes / 60.0, 2),
        "shift_count": len(shifts),
        "shifts": shifts,
    }


@router.get("/employee/{employee_id}/calendar")
async def get_employee_calendar(
    employee_id: str,
    start: str = Query(...),
    end: str = Query(...),
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Get any employee's calendar data with late-arrival detection."""
    from app.services.calendar import build_calendar_data
    from app.services.settings_service import get_setting
    from app.config import settings

    shifts = await timestation.get_shifts(employee_id, start, end)
    scheduled_shifts = (
        db.query(ScheduledShift)
        .filter(ScheduledShift.employee_id == employee_id)
        .all()
    )
    threshold_str = get_setting(db, "late_threshold_minutes")
    threshold = int(threshold_str) if threshold_str else settings.LATE_THRESHOLD_MINUTES
    early_str = get_setting(db, "early_leave_threshold_minutes")
    early_threshold = int(early_str) if early_str else threshold
    calendar = build_calendar_data(shifts, scheduled_shifts, start, end, late_threshold_minutes=threshold, early_leave_threshold_minutes=early_threshold)
    return {
        "employee_id": employee_id,
        "start": start,
        "end": end,
        "late_threshold_minutes": threshold,
        "early_leave_threshold_minutes": early_threshold,
        "days": calendar,
    }


# ── Pay Period Management ──────────────────────────────────────

from app.models.pay_period import PayPeriod as PayPeriodModel


class PayPeriodInput(BaseModel):
    pay_date: date
    label: str  # e.g. "8/8" or "8/22"
    start_date: date
    end_date: date


@router.get("/pay-periods")
async def list_pay_periods(
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """List all pay periods, newest first."""
    periods = db.query(PayPeriodModel).order_by(PayPeriodModel.pay_date.desc()).all()
    return {
        "pay_periods": [
            {
                "id": p.id,
                "pay_date": p.pay_date.isoformat(),
                "label": p.label,
                "start_date": p.start_date.isoformat(),
                "end_date": p.end_date.isoformat(),
                "is_active": p.is_active,
            }
            for p in periods
        ]
    }


@router.post("/pay-periods")
async def create_pay_period(
    req: PayPeriodInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Create a pay period. If one already exists for this pay_date, update it."""
    existing = db.query(PayPeriodModel).filter(PayPeriodModel.pay_date == req.pay_date).first()
    if existing:
        existing.label = req.label
        existing.start_date = req.start_date
        existing.end_date = req.end_date
        db.commit()
        return {"id": existing.id, "status": "updated"}
    pp = PayPeriodModel(
        pay_date=req.pay_date,
        label=req.label,
        start_date=req.start_date,
        end_date=req.end_date,
        created_by=user["timestation_id"],
    )
    db.add(pp)
    db.commit()
    return {"id": pp.id, "status": "created"}


@router.delete("/pay-periods/{period_id}")
async def delete_pay_period(
    period_id: int,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    pp = db.query(PayPeriodModel).filter(PayPeriodModel.id == period_id).first()
    if not pp:
        raise HTTPException(404, "Pay period not found")
    db.delete(pp)
    db.commit()
    return {"id": period_id, "status": "deleted"}


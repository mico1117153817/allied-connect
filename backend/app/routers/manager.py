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


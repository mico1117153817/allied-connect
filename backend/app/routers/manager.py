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
from app.models.hour_balance import HourBalance, HourTransaction
from app.services.hour_balance_service import (
    add_hours, get_balance, get_all_balances, get_transaction_history, deduct_hours
)
from app.models.scheduled_shift import ScheduledShift
from app.routers.auth import require_manager, require_super_admin
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
                "login_enabled": db_emp.login_enabled if db_emp else True,
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
                "login_enabled": emp.login_enabled,
                "custom_id": emp.custom_employee_id or "",
            }
        )

    return {"employees": result}


# ── Employee portal login access ────────────────────────────────

class LoginAccessInput(BaseModel):
    login_enabled: bool


@router.put("/employee/{employee_id}/login-access")
def set_employee_login_access(
    employee_id: str,
    req: LoginAccessInput,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    emp = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    if emp.role == "super_admin" and not req.login_enabled:
        raise HTTPException(403, "Super-admin login access cannot be disabled from this screen")
    if emp.timestation_id == user.get("timestation_id") and not req.login_enabled:
        raise HTTPException(400, "You cannot disable your own login")
    emp.login_enabled = req.login_enabled
    db.commit()
    return {
        "employee_id": emp.timestation_id,
        "name": emp.name,
        "login_enabled": emp.login_enabled,
    }


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
    if req.role not in ("employee", "manager", "super_admin"):
        raise HTTPException(400, "Role must be employee, manager, or super_admin")
    if req.role == "super_admin" and user.get("role") != "super_admin":
        raise HTTPException(403, "Only a super admin can grant super-admin access")
    if emp.role == "super_admin" and req.role != "super_admin" and user.get("role") != "super_admin":
        raise HTTPException(403, "Only a super admin can change a super-admin role")
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
    if req.role not in ("employee", "manager", "super_admin"):
        raise HTTPException(400, "Role must be employee, manager, or super_admin")
    if req.role == "super_admin" and user.get("role") != "super_admin":
        raise HTTPException(403, "Only a super admin can create a super-admin account")
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


@router.get("/employee/{employee_id}/pay-period/{period_id}")
async def get_employee_pay_period(
    employee_id: str,
    period_id: int,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """View an employee's pay-period data with pay fields restricted to super admins."""
    employee = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")

    # Reuse the employee endpoint's calculations so both views stay identical.
    from app.routers.employee import get_pay_period_data
    data = await get_pay_period_data(
        period_id=period_id,
        user={"timestation_id": employee_id},
        db=db,
    )
    data["employee"] = {"timestation_id": employee_id, "name": employee.name}
    data["can_view_pay"] = user.get("role") == "super_admin"

    if not data["can_view_pay"]:
        data.pop("hourly_rate", None)
        data.pop("gross_pay", None)
    return data


@router.get("/employee/{employee_id}/balances")
async def get_employee_balances(
    employee_id: str,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Return the selected employee's balances and audit history to management."""
    employee = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")
    return {
        "employee_id": employee_id,
        "name": employee.name,
        "balances": get_all_balances(db, employee_id),
        "transactions": get_transaction_history(db, employee_id),
    }


@router.get("/employee/{employee_id}/time-off")
async def get_employee_time_off(
    employee_id: str,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Return one employee's complete time-off request history."""
    employee = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")
    from app.routers.time_off import _serialize
    rows = (
        db.query(TimeOffRequest)
        .filter(TimeOffRequest.employee_id == employee_id)
        .order_by(TimeOffRequest.created_at.desc(), TimeOffRequest.id.desc())
        .all()
    )
    return {"requests": [_serialize(row, employee_name=employee.name) for row in rows]}


@router.post("/employee/{employee_id}/time-off")
async def create_employee_time_off(
    employee_id: str,
    payload: dict,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Submit a time-off request on behalf of the employee selected in Employee View."""
    employee = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Employee not found")
    from app.routers.time_off import TimeOffCreate, create_request
    try:
        request_payload = TimeOffCreate.model_validate(payload)
    except Exception as exc:
        raise HTTPException(422, detail=str(exc))
    return create_request(
        payload=request_payload,
        db=db,
        user={
            "timestation_id": employee_id,
            "name": employee.name,
            "role": employee.role,
        },
    )


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


# ── Hourly Rate Management (super admin only) ─────────────────

class HourlyRateInput(BaseModel):
    employee_id: str
    hourly_rate: str  # e.g. "25.00"


@router.put("/hourly-rate")
async def set_hourly_rate(
    req: HourlyRateInput,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Set an employee's private hourly rate. Only super admins can set it."""
    emp = db.query(Employee).filter(Employee.timestation_id == req.employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    emp.hourly_rate = req.hourly_rate
    db.commit()
    return {"employee_id": emp.timestation_id, "hourly_rate": emp.hourly_rate}


@router.get("/hourly-rate/{employee_id}")
async def get_hourly_rate(
    employee_id: str,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Get an employee's hourly rate. Super admins and managers can see it."""
    emp = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    return {"employee_id": emp.timestation_id, "name": emp.name, "hourly_rate": emp.hourly_rate}


# ── Hour Balance Management (super admin only) ────────────────

class AddHoursInput(BaseModel):
    employee_id: str
    type: str  # back_hours, vacation_hours, sick_hours
    amount: float
    reason: str | None = None
    pay_period_id: int | None = None  # which pay period the hours apply to


class DeductHoursInput(BaseModel):
    employee_id: str
    type: str  # back_hours, vacation_hours, sick_hours
    amount: float
    reason: str | None = None


@router.post("/hour-balance/add")
async def add_hour_balance(
    req: AddHoursInput,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Add hours to an employee's balance. Super admins only (Marc/Nicole)."""
    if req.type not in ("back_hours", "vacation_hours", "sick_hours"):
        raise HTTPException(400, "Type must be back_hours, vacation_hours, or sick_hours")
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    emp = db.query(Employee).filter(Employee.timestation_id == req.employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    result = add_hours(
        db, req.employee_id, req.type, req.amount,
        input_by=user["timestation_id"],
        input_by_name=user["name"],
        reason=req.reason,
        pay_period_id=req.pay_period_id,
    )
    return result


@router.post("/hour-balance/deduct")
async def deduct_hour_balance(
    req: DeductHoursInput,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Manually deduct hours from an employee's running balance. Super admins only."""
    if req.type not in ("back_hours", "vacation_hours", "sick_hours"):
        raise HTTPException(400, "Type must be back_hours, vacation_hours, or sick_hours")
    if req.amount <= 0:
        raise HTTPException(400, "Amount must be positive")
    emp = db.query(Employee).filter(Employee.timestation_id == req.employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    try:
        result = deduct_hours(
            db, req.employee_id, req.type, req.amount,
            input_by=user["timestation_id"],
            input_by_name=user["name"],
            reason=req.reason or "Manual balance deduction by super admin",
        )
    except ValueError:
        current = get_balance(db, req.employee_id, req.type)
        label = req.type.replace("_", " ")
        raise HTTPException(
            400,
            f"Insufficient {label} — employee has {current}h remaining, but deduction requested is {req.amount}h",
        )
    return result


@router.get("/hour-balance/{employee_id}")
async def get_hour_balance(
    employee_id: str,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Get an employee's hour balances + full transaction history. Super admins only."""
    emp = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Employee not found")
    balances = get_all_balances(db, employee_id)
    transactions = get_transaction_history(db, employee_id)
    return {
        "employee_id": employee_id,
        "name": emp.name,
        "balances": balances,
        "transactions": transactions,
    }


class AssignPeriodInput(BaseModel):
    pay_period_id: int | None = None


@router.put("/hour-balance/transaction/{transaction_id}/assign-period")
async def assign_transaction_period(
    transaction_id: int,
    req: AssignPeriodInput,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """Assign a transaction to a pay period. Super admins only."""
    txn = db.query(HourTransaction).filter(HourTransaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    txn.pay_period_id = req.pay_period_id
    db.commit()
    return {"transaction_id": transaction_id, "pay_period_id": req.pay_period_id}


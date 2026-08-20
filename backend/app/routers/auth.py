"""Authentication router: PIN login, JWT issuance, and auth dependencies."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.jwt import create_access_token, decode_access_token
from app.auth.rate_limiter import rate_limiter
from app.models.database import get_db
from app.models.employee import Employee
from app.services.timestation import timestation

router = APIRouter(prefix="/auth", tags=["auth"])


# ── request / response schemas ─────────────────────────────────────

class LoginRequest(BaseModel):
    pin: str


class EmployeeInfo(BaseModel):
    name: str | None = None
    role: str | None = None
    department: str | None = None
    email: str | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    employee: EmployeeInfo


# ── routes ─────────────────────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> LoginResponse:
    """Authenticate an employee by PIN.

    Validates *pin* against the live TimeStation employee list, upserts the
    matching employee record in the local DB, and returns a JWT access token.
    """
    pin = body.pin
    client_ip = request.client.host if request.client else "unknown"

    # Rate-limit checks (before hitting TimeStation)
    if rate_limiter.is_pin_locked(pin):
        raise HTTPException(
            status_code=429,
            detail="Too many failed PIN attempts. Please try again later.",
        )
    if rate_limiter.is_ip_banned(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts from this IP. Please try again later.",
        )

    # Look up the PIN in the local DB first (for non-TimeStation users like execs)
    local_emp = (
        db.query(Employee).filter(Employee.pin == pin).first()
    )

    ts_emp = None
    if not local_emp or local_emp.timestation_id.startswith("local_"):
        # Also check TimeStation roster
        employees = await timestation.get_employees()
        ts_emp = next((e for e in employees if e.get("pin") == pin), None)

    # Prefer TimeStation data if found there, fall back to local-only
    if ts_emp:
        matched = ts_emp
        is_local_only = False
    elif local_emp:
        matched = {
            "employee_id": local_emp.timestation_id,
            "name": local_emp.name,
            "pin": local_emp.pin,
            "email": local_emp.email,
            "status": local_emp.status,
            "primary_department": local_emp.primary_department,
            "primary_department_id": local_emp.primary_department_id,
            "custom_employee_id": local_emp.custom_employee_id,
            "title": local_emp.title,
        }
        is_local_only = True
    else:
        matched = None
        is_local_only = False

    if not matched:
        rate_limiter.record_failed_pin(pin)
        rate_limiter.record_failed_ip(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN",
        )

    # Disabled local records remain authoritative even when TimeStation still lists the PIN.
    if local_emp and local_emp.login_enabled is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your Allied Connect login has been disabled. Contact management for assistance.",
        )

    # Upsert Employee in the local DB (preserve existing role and login access)
    timestation_id = ts_emp.get("employee_id", "") if ts_emp else matched.get("employee_id", "")
    existing = (
        db.query(Employee).filter(Employee.timestation_id == timestation_id).first()
    )
    if existing and existing.login_enabled is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your Allied Connect login has been disabled. Contact management for assistance.",
        )

    if existing:
        # Update from TimeStation if available; preserve role and email if local-only
        if ts_emp:
            existing.name = ts_emp.get("name", existing.name)
            existing.pin = pin
            if ts_emp.get("email"):
                existing.email = ts_emp["email"]
            existing.status = ts_emp.get("status", existing.status)
            existing.primary_department = ts_emp.get(
                "primary_department", existing.primary_department
            )
            existing.primary_department_id = ts_emp.get(
                "primary_department_id", existing.primary_department_id
            )
            existing.custom_employee_id = ts_emp.get(
                "custom_employee_id", existing.custom_employee_id
            )
            existing.title = ts_emp.get("title", existing.title)
        db.commit()
        db.refresh(existing)
    else:
        existing = Employee(
            timestation_id=timestation_id,
            custom_employee_id=matched.get("custom_employee_id"),
            name=matched.get("name", ""),
            title=matched.get("title"),
            primary_department=matched.get("primary_department"),
            primary_department_id=matched.get("primary_department_id"),
            pin=pin,
            email=matched.get("email"),
            status=matched.get("status", "out"),
            role="employee",
        )
        db.add(existing)
        db.commit()
        db.refresh(existing)

    # Issue JWT
    token = create_access_token(
        {
            "sub": timestation_id,
            "name": existing.name,
            "role": existing.role,
            "email": existing.email or "",
        }
    )

    # Successful login → clear failed attempts for this PIN
    rate_limiter.clear_pin_attempts(pin)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        employee=EmployeeInfo(
            name=existing.name,
            role=existing.role,
            department=existing.primary_department,
            email=existing.email,
        ),
    )


# ── dependencies ────────────────────────────────────────────────────

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Decode the JWT from the ``Authorization: Bearer …`` header.

    Returns a dict with ``timestation_id``, ``name``, ``role``, and ``email``.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    payload = decode_access_token(token)

    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = db.query(Employee).filter(Employee.timestation_id == payload.get("sub")).first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if employee.login_enabled is False:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your Allied Connect login has been disabled. Contact management for assistance.",
        )

    return {
        "timestation_id": payload.get("sub"),
        "name": employee.name,
        "role": employee.role,
        "email": employee.email,
    }


def require_manager(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that ensures the current user has the ``manager`` or ``super_admin`` role."""
    if user.get("role") not in ("manager", "super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )
    return user


def require_super_admin(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that ensures the current user has the ``super_admin`` role."""
    if user.get("role") != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return user

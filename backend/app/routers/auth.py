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

    # Look up the PIN in the TimeStation employee roster
    employees = await timestation.get_employees()
    ts_emp = next((e for e in employees if e.get("pin") == pin), None)

    if ts_emp is None:
        rate_limiter.record_failed_pin(pin)
        rate_limiter.record_failed_ip(client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid PIN",
        )

    # Upsert Employee in the local DB (preserve existing role)
    timestation_id = ts_emp.get("employee_id", "")
    existing = (
        db.query(Employee).filter(Employee.timestation_id == timestation_id).first()
    )

    if existing:
        existing.name = ts_emp.get("name", existing.name)
        existing.pin = pin
        existing.email = ts_emp.get("email", existing.email)
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
            custom_employee_id=ts_emp.get("custom_employee_id"),
            name=ts_emp.get("name", ""),
            title=ts_emp.get("title"),
            primary_department=ts_emp.get("primary_department"),
            primary_department_id=ts_emp.get("primary_department_id"),
            pin=pin,
            email=ts_emp.get("email"),
            status=ts_emp.get("status", "out"),
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

    return {
        "timestation_id": payload.get("sub"),
        "name": payload.get("name"),
        "role": payload.get("role"),
        "email": payload.get("email"),
    }


def require_manager(user: dict = Depends(get_current_user)) -> dict:
    """Dependency that ensures the current user has the ``manager`` role."""
    if user.get("role") != "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manager access required",
        )
    return user

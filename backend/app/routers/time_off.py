"""Time-off request API.

Endpoints
---------
- POST   /api/time-off/            -> employee creates a request (status=pending)
- GET    /api/time-off/            -> employee lists their own requests (newest first)
- GET    /api/time-off/all         -> manager lists all requests, optionally filtered by status, includes employee name
- PUT    /api/time-off/{id}/review -> manager approves/denies a request, sends email to employee
"""

from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.employee import Employee
from app.models.time_off import TimeOffRequest
from app.routers.auth import get_current_user, require_manager
from app.services.email import send_time_off_notification

router = APIRouter(prefix="/api/time-off", tags=["time-off"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class TimeOffCreate(BaseModel):
    request_type: str = Field(..., description="vacation | sick | personal | unpaid")
    start_date: date
    end_date: date
    reason: Optional[str] = None


class TimeOffReview(BaseModel):
    status: str = Field(..., description="approved | denied")


class TimeOffOut(BaseModel):
    id: int
    employee_id: str
    employee_name: Optional[str] = None
    request_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: str
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
VALID_REQUEST_TYPES = {"vacation", "sick", "personal", "unpaid"}
VALID_REVIEW_STATUSES = {"approved", "denied"}


def _serialize(req: TimeOffRequest, employee_name: Optional[str] = None) -> dict:
    return {
        "id": req.id,
        "employee_id": req.employee_id,
        "employee_name": employee_name,
        "request_type": req.request_type,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "reason": req.reason,
        "status": req.status,
        "reviewed_by": req.reviewed_by,
        "reviewed_at": req.reviewed_at,
        "created_at": req.created_at,
    }


@router.post("/", response_model=TimeOffOut, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: TimeOffCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """Create a new time-off request for the logged-in employee."""
    if payload.request_type not in VALID_REQUEST_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"request_type must be one of {sorted(VALID_REQUEST_TYPES)}",
        )
    if payload.end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")

    req = TimeOffRequest(
        employee_id=user["timestation_id"],
        request_type=payload.request_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return _serialize(req, employee_name=user.get("name"))


@router.get("/", response_model=list[TimeOffOut])
def list_my_requests(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """List the logged-in employee's own requests, newest first."""
    stmt = (
        select(TimeOffRequest)
        .where(TimeOffRequest.employee_id == user["timestation_id"])
        .order_by(TimeOffRequest.created_at.desc(), TimeOffRequest.id.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [_serialize(r, employee_name=user.get("name")) for r in rows]


@router.get("/all", response_model=list[TimeOffOut])
def list_all_requests(
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_manager),
):
    """Manager: list all requests, optionally filtered by status. Includes employee name."""
    stmt = select(TimeOffRequest, Employee).join(
        Employee, Employee.timestation_id == TimeOffRequest.employee_id, isouter=True
    )
    if status_filter:
        stmt = stmt.where(TimeOffRequest.status == status_filter)
    stmt = stmt.order_by(TimeOffRequest.created_at.desc(), TimeOffRequest.id.desc())

    rows = db.execute(stmt).all()
    return [
        _serialize(req, employee_name=emp.name if emp else None)
        for req, emp in rows
    ]


@router.put("/{request_id}/review", response_model=TimeOffOut)
def review_request(
    request_id: int,
    payload: TimeOffReview,
    db: Session = Depends(get_db),
    user: dict = Depends(require_manager),
):
    """Manager: approve or deny a time-off request, then notify the employee by email."""
    if payload.status not in VALID_REVIEW_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status must be one of {sorted(VALID_REVIEW_STATUSES)}",
        )

    req = db.get(TimeOffRequest, request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Time-off request not found")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    req.status = payload.status
    req.reviewed_by = user["timestation_id"]
    req.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(req)

    # Look up the employee to get name/email for notification.
    emp = db.execute(
        select(Employee).where(Employee.timestation_id == req.employee_id)
    ).scalars().first()
    employee_name = emp.name if emp else req.employee_id
    employee_email = emp.email if emp else None

    if employee_email:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                send_time_off_notification(
                    to_email=employee_email,
                    employee_name=employee_name,
                    status=req.status,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    request_type=req.request_type,
                )
            )
        except RuntimeError:
            # No running event loop (e.g. when called via sync TestClient)
            asyncio.run(
                send_time_off_notification(
                    to_email=employee_email,
                    employee_name=employee_name,
                    status=req.status,
                    start_date=req.start_date,
                    end_date=req.end_date,
                    request_type=req.request_type,
                )
            )

    return _serialize(req, employee_name=employee_name)

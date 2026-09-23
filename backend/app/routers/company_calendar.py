import hashlib
import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Response
from pathlib import Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.company_workflow import CalendarAttachment, CalendarAttendee, CalendarAudit, CompanyCalendarEvent
from app.models.compliance_company import ComplianceCompany
from app.models.database import get_db
from app.models.employee import Employee
from app.models.task import Task
from app.routers.auth import get_current_user
from app.routers.compliance import _company_access
from app.routers.notifications import create_notification

router = APIRouter(prefix="/api/company-calendar", tags=["company-calendar"])
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv", "image/jpeg", "image/png",
}


def _require(user: dict = Depends(get_current_user)):
    if user.get("role") not in {"manager", "admin", "super_admin"} and not user.get("company_task_access"):
        raise HTTPException(403, "Company Calendar access required")
    return user


class EventInput(BaseModel):
    company_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    start_at: datetime
    end_at: datetime | None = None
    all_day: bool = False
    color: str = "#2563eb"
    notes: str | None = None
    reminder_minutes: int | None = Field(None, ge=0, le=525600)
    attendee_ids: list[str] = []


class EventUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    all_day: bool | None = None
    color: str | None = None
    notes: str | None = None
    reminder_minutes: int | None = Field(None, ge=0, le=525600)
    attendee_ids: list[str] | None = None


def _serialize(db, row):
    return {"id": row.id, "source_type": "event", "company_id": row.company_id, "title": row.title, "description": row.description, "start_at": row.start_at.isoformat(), "end_at": row.end_at.isoformat() if row.end_at else None, "all_day": row.all_day, "color": row.color, "notes": row.notes, "reminder_minutes": row.reminder_minutes, "attendee_ids": [a.employee_id for a in db.query(CalendarAttendee).filter_by(event_id=row.id).all()]}


def _event(db, user, event_id, write=False):
    row = db.get(CompanyCalendarEvent, event_id)
    if not row or row.archived_at:
        raise HTTPException(404, "Calendar event not found")
    _company_access(db, user, row.company_id, write=write)
    return row


def _validated_attendees(db, employee_ids):
    result = list(dict.fromkeys(employee_ids))
    existing = {row.timestation_id for row in db.query(Employee).filter(
        Employee.timestation_id.in_(result), Employee.is_active.is_(True)
    ).all()} if result else set()
    missing = [employee_id for employee_id in result if employee_id not in existing]
    if missing:
        raise HTTPException(400, f"Attendee not found: {missing[0]}")
    return result


@router.get("")
def list_events(company_id: int, start: datetime, end: datetime, user: dict = Depends(_require), db: Session = Depends(get_db)):
    _company_access(db, user, company_id)
    rows = db.query(CompanyCalendarEvent).filter(CompanyCalendarEvent.company_id == company_id, CompanyCalendarEvent.archived_at.is_(None), CompanyCalendarEvent.start_at >= start.replace(tzinfo=None), CompanyCalendarEvent.start_at < end.replace(tzinfo=None)).all()
    tasks = db.query(Task).filter(Task.company_id == company_id, Task.archived_at.is_(None), Task.due_at.is_not(None), Task.due_at >= start.replace(tzinfo=None), Task.due_at < end.replace(tzinfo=None)).all()
    data = [_serialize(db, row) for row in rows]
    data.extend({"id": f"task-{t.id}", "source_type": "task", "source_id": t.id, "company_id": t.company_id, "title": t.title, "start_at": t.due_at.isoformat(), "end_at": None, "all_day": False, "color": "#dc2626" if t.status not in {"Completed", "Cancelled"} else "#16a34a", "notes": t.notes} for t in tasks)
    return {"events": sorted(data, key=lambda item: item["start_at"])}


@router.post("", status_code=201)
def create_event(payload: EventInput, user: dict = Depends(_require), db: Session = Depends(get_db)):
    _company_access(db, user, payload.company_id, write=True)
    row = CompanyCalendarEvent(**payload.model_dump(exclude={"attendee_ids"}), created_by=user["timestation_id"])
    db.add(row); db.flush()
    for employee_id in _validated_attendees(db, payload.attendee_ids):
        db.add(CalendarAttendee(event_id=row.id, employee_id=employee_id))
        create_notification(db, employee_id=employee_id, company_id=row.company_id, event_type="calendar_invitation", title=row.title, body="You were added to a company event", link="/company-calendar", key=f"calendar:{row.id}:invite:{employee_id}")
    db.add(CalendarAudit(event_id=row.id, actor_employee_id=user["timestation_id"], action="created"))
    db.commit(); db.refresh(row)
    return _serialize(db, row)


@router.get("/events/{event_id}")
def event_detail(event_id: int, user: dict = Depends(_require), db: Session = Depends(get_db)):
    row = _event(db, user, event_id)
    result = _serialize(db, row)
    result["audit"] = [{"action": a.action, "detail": a.detail, "actor_employee_id": a.actor_employee_id, "created_at": a.created_at.isoformat() if a.created_at else None} for a in db.query(CalendarAudit).filter_by(event_id=event_id).order_by(CalendarAudit.id).all()]
    result["attachments"] = [{"id": a.id, "filename": a.filename, "content_type": a.content_type} for a in db.query(CalendarAttachment).filter_by(event_id=event_id).all()]
    return result


@router.put("/{event_ref}")
def update_event(event_ref: str, payload: EventUpdate, user: dict = Depends(_require), db: Session = Depends(get_db)):
    if event_ref.startswith("task-"):
        try: task = db.get(Task, int(event_ref[5:]))
        except ValueError: task = None
        if not task or task.archived_at: raise HTTPException(404, "Task not found")
        _company_access(db, user, task.company_id, write=True)
        if payload.start_at is not None: task.due_at = payload.start_at
        db.commit()
        return {"id": event_ref, "source_type": "task", "start_at": task.due_at.isoformat() if task.due_at else None}
    row = _event(db, user, int(event_ref), write=True)
    changes = payload.model_dump(exclude_unset=True, exclude={"attendee_ids"})
    for key, value in changes.items(): setattr(row, key, value)
    if payload.attendee_ids is not None:
        attendee_ids = _validated_attendees(db, payload.attendee_ids)
        db.query(CalendarAttendee).filter_by(event_id=row.id).delete()
        for employee_id in attendee_ids:
            db.add(CalendarAttendee(event_id=row.id, employee_id=employee_id))
            create_notification(db, employee_id=employee_id, company_id=row.company_id, event_type="calendar_updated", title=row.title, body="A company event was updated", link="/company-calendar", key=f"calendar:{row.id}:updated:{employee_id}:{row.updated_at or row.created_at}")
    db.add(CalendarAudit(event_id=row.id, actor_employee_id=user["timestation_id"], action="updated", detail=json.dumps(sorted(changes))))
    db.commit(); db.refresh(row)
    return _serialize(db, row)


@router.post("/events/{event_id}/attachments")
async def upload(event_id: int, file: UploadFile = File(...), user: dict = Depends(_require), db: Session = Depends(get_db)):
    _event(db, user, event_id, write=True)
    if file.content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(400, "Unsupported calendar attachment type")
    content = await file.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024: raise HTTPException(400, "Attachment exceeds 25 MiB")
    digest = hashlib.sha256(content).hexdigest()
    if db.query(CalendarAttachment).filter_by(event_id=event_id, content_hash=digest).first(): raise HTTPException(409, "Duplicate attachment")
    row = CalendarAttachment(event_id=event_id, filename=Path(file.filename or "attachment").name[-255:], content_type=file.content_type, content_hash=digest, content=content, uploaded_by=user["timestation_id"])
    db.add(row); db.flush(); db.add(CalendarAudit(event_id=event_id, actor_employee_id=user["timestation_id"], action="attachment_uploaded", detail=str(row.id))); db.commit()
    return {"id": row.id, "filename": row.filename}


@router.get("/events/{event_id}/attachments/{attachment_id}")
def download_attachment(event_id: int, attachment_id: int, user: dict = Depends(_require), db: Session = Depends(get_db)):
    _event(db, user, event_id)
    row = db.query(CalendarAttachment).filter_by(id=attachment_id, event_id=event_id).first()
    if not row:
        raise HTTPException(404, "Attachment not found")
    return Response(row.content, media_type=row.content_type, headers={"Content-Disposition": f'attachment; filename="{row.filename}"', "Cache-Control": "private, no-store"})


@router.delete("/events/{event_id}/attachments/{attachment_id}", status_code=204)
def delete_attachment(event_id: int, attachment_id: int, user: dict = Depends(_require), db: Session = Depends(get_db)):
    _event(db, user, event_id, write=True)
    row = db.query(CalendarAttachment).filter_by(id=attachment_id, event_id=event_id).first()
    if not row:
        raise HTTPException(404, "Attachment not found")
    db.add(CalendarAudit(event_id=event_id, actor_employee_id=user["timestation_id"], action="attachment_archived", detail=str(row.id)))
    db.delete(row)
    db.commit()


@router.delete("/events/{event_id}", status_code=204)
def archive_event(event_id: int, user: dict = Depends(_require), db: Session = Depends(get_db)):
    row = _event(db, user, event_id, write=True)
    row.archived_at = datetime.utcnow()
    db.add(CalendarAudit(event_id=row.id, actor_employee_id=user["timestation_id"], action="archived"))
    db.commit()

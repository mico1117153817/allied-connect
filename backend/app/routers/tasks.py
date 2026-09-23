from datetime import datetime, timezone
import hashlib
import html
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Response
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.models.database import get_db
from app.models.employee import Employee
from app.models.task import (
    TASK_CATEGORIES,
    TASK_PRIORITIES,
    TASK_STATUSES,
    Task,
    TaskActivity,
    TaskAssignment,
    TaskAttachment,
    TaskCategory,
    TaskReminder,
    TaskNotification,
    TaskSummaryDelivery,
)
from app.routers.auth import get_current_user
from app.routers.compliance import _company_access
from app.services.task_notifications import enqueue_task_event
from app.routers.notifications import notify_task_assignees

router = APIRouter(prefix="/api/tasks", tags=["tasks"])
ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf", "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv", "image/jpeg", "image/png",
}


class TaskCreate(BaseModel):
    company_id: int
    title: str = Field(min_length=1, max_length=300)
    description: str | None = None
    department: str | None = None
    category_id: int | None = None
    state_compliance_id: int | None = None
    priority: str = "Normal"
    status: str = "Not Started"
    start_at: datetime | None = None
    due_at: datetime | None = None
    notes: str | None = None
    assigned_employee_ids: list[str] = []


class TaskUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=300)
    description: str | None = None
    department: str | None = None
    category_id: int | None = None
    state_compliance_id: int | None = None
    priority: str | None = None
    status: str | None = None
    start_at: datetime | None = None
    due_at: datetime | None = None
    notes: str | None = None
    completion_notes: str | None = None
    assigned_employee_ids: list[str] | None = None


class TaskNote(BaseModel):
    note: str = Field(min_length=1, max_length=10000)


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class SummarySendInput(BaseModel):
    employee_ids: list[str] = []
    external_emails: list[str] = []
    include_pdf: bool = False
    idempotency_key: str = Field(min_length=1, max_length=200)



def _user_can_tasks(user: dict) -> bool:
    return bool(user.get("company_task_access"))


def _require_tasks(user: dict = Depends(get_current_user)) -> dict:
    if not _user_can_tasks(user):
        raise HTTPException(403, "Company Task access required")
    return user


def _company(db: Session, user: dict, company_id: int, write: bool = False) -> ComplianceCompany:
    return _company_access(db, user, company_id, write=write)


def _visible_company_ids(db: Session, user: dict) -> list[int] | None:
    if user.get("role") == "super_admin":
        return None
    return [row.company_id for row in db.query(CompanyPermission).filter_by(employee_id=user.get("timestation_id")).all()]


def _task(db: Session, user: dict, task_id: int, write: bool = False) -> Task:
    task = db.get(Task, task_id)
    if not task or task.archived_at:
        raise HTTPException(404, "Task not found")
    _company(db, user, task.company_id, write=write)
    return task


def _employee_name(db: Session, employee_id: str) -> str:
    employee = db.query(Employee).filter(Employee.timestation_id == employee_id).first()
    return employee.name if employee else employee_id


def _effective_status(task: Task) -> str:
    if task.status not in {"Completed", "Cancelled"} and task.due_at:
        due = task.due_at if task.due_at.tzinfo else task.due_at.replace(tzinfo=timezone.utc)
        if due < datetime.now(timezone.utc):
            return "Overdue"
    return task.status


def _serialize(db: Session, task: Task) -> dict:
    assignments = db.query(TaskAssignment).filter_by(task_id=task.id).all()
    category = db.get(TaskCategory, task.category_id) if task.category_id else None
    return {
        "id": task.id,
        "task_id": task.task_key,
        "company_id": task.company_id,
        "title": task.title,
        "description": task.description,
        "department": task.department,
        "category": category.name if category else None,
        "category_id": task.category_id,
        "priority": task.priority,
        "status": _effective_status(task),
        "stored_status": task.status,
        "start_at": task.start_at.isoformat() if task.start_at else None,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "notes": task.notes,
        "completion_notes": task.completion_notes,
        "created_by": task.created_by,
        "created_by_name": _employee_name(db, task.created_by),
        "completed_by": task.completed_by,
        "completed_by_name": _employee_name(db, task.completed_by) if task.completed_by else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        "assignments": [{"employee_id": a.employee_id, "name": _employee_name(db, a.employee_id), "is_primary": a.is_primary} for a in assignments],
    }


def _activity(db, task, user, action, description, old=None, new=None, attachment_id=None):
    db.add(TaskActivity(task_id=task.id, actor_employee_id=user["timestation_id"], actor_name=user.get("name"), action_type=action, description=description, old_value=old, new_value=new, attachment_id=attachment_id))


def _next_task_key(db: Session) -> str:
    # IDs remain monotonic even if a task is later archived.
    last = db.query(Task).order_by(Task.id.desc()).first()
    return f"TASK-{(last.id + 1 if last else 1):06d}"


def _calendar_events(db, start, end, company_id=None, visible_company_ids=None):
    query = db.query(Task).filter(Task.archived_at.is_(None))
    if company_id is not None:
        query = query.filter(Task.company_id == company_id)
    elif visible_company_ids is not None:
        query = query.filter(Task.company_id.in_(visible_company_ids))
    query = query.filter(or_(Task.start_at.between(start, end), Task.due_at.between(start, end)))
    events = []
    task_ids = []
    for task in query.all():
        task_ids.append(task.id)
        if task.start_at and start <= task.start_at.replace(tzinfo=task.start_at.tzinfo or timezone.utc) <= end:
            events.append({"kind": "task_start", "at": task.start_at.isoformat(), "task_id": task.id, "title": task.title, "status": _effective_status(task)})
        if task.due_at and start <= task.due_at.replace(tzinfo=task.due_at.tzinfo or timezone.utc) <= end:
            events.append({"kind": "task_due", "at": task.due_at.isoformat(), "task_id": task.id, "title": task.title, "status": _effective_status(task)})
    reminders = db.query(TaskReminder, Task).join(Task, Task.id == TaskReminder.task_id).filter(TaskReminder.enabled.is_(True), Task.archived_at.is_(None), TaskReminder.scheduled_at.between(start, end))
    if company_id is not None: reminders = reminders.filter(Task.company_id == company_id)
    elif visible_company_ids is not None: reminders = reminders.filter(Task.company_id.in_(visible_company_ids))
    for reminder, task in reminders.all():
        events.append({"kind": "reminder", "at": reminder.scheduled_at.isoformat(), "task_id": task.id, "title": task.title, "status": _effective_status(task)})
    return sorted(events, key=lambda event: (event["at"], {"task_start": 0, "reminder": 1, "task_due": 2}[event["kind"]]))


@router.get("/calendar/events")
def calendar_events(start: datetime, end: datetime, company_id: int | None = None, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    if end < start or end - start > __import__('datetime').timedelta(days=370):
        raise HTTPException(400, "Invalid calendar range")
    if company_id is not None: _company(db, user, company_id)
    return {"events": _calendar_events(db, start, end, company_id, _visible_company_ids(db, user))}


@router.get("/categories")
def categories(user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    rows = db.query(TaskCategory).filter_by(is_active=True).order_by(TaskCategory.name).all()
    if not rows:
        rows = [TaskCategory(name=name, created_by=user["timestation_id"]) for name in TASK_CATEGORIES]
        db.add_all(rows)
        db.commit()
    return {"categories": [{"id": row.id, "name": row.name} for row in rows]}


@router.post("/categories", status_code=201)
def create_category(payload: CategoryInput, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    if db.query(TaskCategory).filter_by(name=payload.name).first(): raise HTTPException(409, "Task category already exists")
    row = TaskCategory(name=payload.name, created_by=user["timestation_id"]); db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.put("/categories/{category_id}")
def update_category(category_id: int, payload: CategoryInput, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    row = db.query(TaskCategory).filter_by(id=category_id, is_active=True).first()
    if not row: raise HTTPException(404, "Task category not found")
    row.name = payload.name; db.commit(); return {"id": row.id, "name": row.name}


@router.delete("/categories/{category_id}", status_code=204)
def archive_category(category_id: int, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    row = db.query(TaskCategory).filter_by(id=category_id, is_active=True).first()
    if not row: raise HTTPException(404, "Task category not found")
    row.is_active = False; db.commit()


@router.get("/companies")
def task_companies(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(ComplianceCompany).filter_by(is_active=True)
    visible_ids = _visible_company_ids(db, user)
    if visible_ids is not None:
        query = query.filter(ComplianceCompany.id.in_(visible_ids))
    companies = query.order_by(ComplianceCompany.legal_name).all()
    return {"companies": [{"id": company.id, "legal_name": company.legal_name} for company in companies]}


@router.get("")
def list_tasks(company_id: int | None = None, status: str | None = None, assigned_to: str | None = None, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    query = db.query(Task).filter(Task.archived_at.is_(None))
    if company_id is not None:
        _company(db, user, company_id)
        query = query.filter(Task.company_id == company_id)
    else:
        visible_ids = _visible_company_ids(db, user)
        if visible_ids is not None:
            query = query.filter(Task.company_id.in_(visible_ids))
    if status:
        query = query.filter(Task.status == status)
    if assigned_to:
        query = query.join(TaskAssignment).filter(TaskAssignment.employee_id == assigned_to)
    rows = query.order_by(Task.due_at.asc().nullslast(), Task.created_at.desc()).all()
    return {"tasks": [_serialize(db, row) for row in rows]}


@router.post("", status_code=201)
def create_task(payload: TaskCreate, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    _company(db, user, payload.company_id, write=True)
    if payload.priority not in TASK_PRIORITIES or payload.status not in TASK_STATUSES[:-1]:
        raise HTTPException(400, "Invalid task priority or status")
    if payload.category_id and not db.query(TaskCategory).filter_by(id=payload.category_id, is_active=True).first():
        raise HTTPException(400, "Invalid task category")
    task = Task(task_key=_next_task_key(db), company_id=payload.company_id, created_by=user["timestation_id"], **payload.model_dump(exclude={"assigned_employee_ids", "company_id"}))
    db.add(task)
    db.flush()
    assignments = list(dict.fromkeys(payload.assigned_employee_ids))
    for index, employee_id in enumerate(assignments):
        if not db.query(Employee).filter_by(timestation_id=employee_id, is_active=True).first():
            raise HTTPException(400, f"Assigned employee not found: {employee_id}")
        db.add(TaskAssignment(task_id=task.id, employee_id=employee_id, is_primary=index == 0, assigned_by=user["timestation_id"]))
    db.flush()
    _activity(db, task, user, "created", f"{user.get('name', 'User')} created task {task.task_key}")
    enqueue_task_event(db, task, "assigned", user["timestation_id"])
    db.commit()
    db.refresh(task)
    return _serialize(db, task)


@router.get("/inbox-notifications")
def notification_inbox(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(TaskNotification).filter_by(employee_id=user["timestation_id"], channel="internal", status="sent").order_by(TaskNotification.sent_at.desc()).limit(100).all()
    return {"notifications": [{"id": row.id, "task_id": row.task_id, "event_type": row.event_type, "subject": row.subject, "body": row.body, "sent_at": row.sent_at.isoformat() if row.sent_at else None} for row in rows]}


@router.get("/{task_id}")
def get_task(task_id: int, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id)
    result = _serialize(db, task)
    result["company"] = {"id": task.company_id, "legal_name": db.get(ComplianceCompany, task.company_id).legal_name}
    result["activity"] = [{"id": a.id, "user": a.actor_name or a.actor_employee_id, "action_type": a.action_type, "description": a.description, "old_value": a.old_value, "new_value": a.new_value, "created_at": a.created_at.isoformat() if a.created_at else None} for a in db.query(TaskActivity).filter_by(task_id=task.id).order_by(TaskActivity.created_at, TaskActivity.id).all()]
    result["attachments"] = [{"id": a.id, "filename": a.original_filename, "content_type": a.content_type, "file_size": a.file_size, "uploaded_by": a.uploaded_by, "created_at": a.created_at.isoformat() if a.created_at else None} for a in db.query(TaskAttachment).filter_by(task_id=task.id, archived_at=None).order_by(TaskAttachment.created_at.desc()).all()]
    return result


@router.put("/{task_id}")
def update_task(task_id: int, payload: TaskUpdate, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    previous_status = task.status
    changes = payload.model_dump(exclude_unset=True, exclude={"assigned_employee_ids"})
    if changes.get("priority") is not None and changes["priority"] not in TASK_PRIORITIES:
        raise HTTPException(400, "Invalid task priority")
    if changes.get("status") is not None and changes["status"] not in TASK_STATUSES:
        raise HTTPException(400, "Invalid task status")
    for field, value in changes.items():
        old = getattr(task, field)
        if old != value:
            setattr(task, field, value)
            _activity(db, task, user, f"changed_{field}", f"{user.get('name', 'User')} changed {field}", str(old) if old is not None else None, str(value) if value is not None else None)
    if payload.assigned_employee_ids is not None:
        old_ids = {a.employee_id for a in db.query(TaskAssignment).filter_by(task_id=task.id).all()}
        new_ids = set(payload.assigned_employee_ids)
        if old_ids != new_ids:
            for assignment in db.query(TaskAssignment).filter_by(task_id=task.id).all():
                db.delete(assignment)
            for index, employee_id in enumerate(dict.fromkeys(payload.assigned_employee_ids)):
                if not db.query(Employee).filter_by(timestation_id=employee_id, is_active=True).first():
                    raise HTTPException(400, f"Assigned employee not found: {employee_id}")
                db.add(TaskAssignment(task_id=task.id, employee_id=employee_id, is_primary=index == 0, assigned_by=user["timestation_id"]))
            _activity(db, task, user, "assignments_changed", f"{user.get('name', 'User')} changed task assignments", ",".join(sorted(old_ids)), ",".join(sorted(new_ids)))
            db.flush()
            enqueue_task_event(db, task, "assigned", user["timestation_id"])
    if previous_status == "Completed" and task.status != "Completed":
        task.completed_by = None
        task.completed_at = None
    if task.status in {"Completed", "Cancelled"}:
        db.query(TaskReminder).filter_by(task_id=task.id, enabled=True).update({TaskReminder.enabled: False}, synchronize_session=False)
        db.query(TaskNotification).filter(
            TaskNotification.task_id == task.id,
            TaskNotification.status == "pending",
            or_(TaskNotification.event_type.like("reminder:%"), TaskNotification.event_type.in_(("overdue", "task_overdue"))),
        ).update({TaskNotification.status: "cancelled"}, synchronize_session=False)
    if task.status == "Completed" and previous_status != "Completed":
        task.completed_by = user["timestation_id"]
        task.completed_at = datetime.now(timezone.utc)
        _activity(db, task, user, "completed", f"{user.get('name', 'User')} marked task Completed")
        notify_task_assignees(db, task, "task_completed")
        enqueue_task_event(db, task, "completed", user["timestation_id"])
    db.commit()
    db.refresh(task)
    return _serialize(db, task)


def _simple_pdf(lines: list[str]) -> bytes:
    safe = [line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")[:160] for line in lines]
    stream = "BT /F1 11 Tf 50 760 Td " + " Tj 0 -18 Td ".join(f"({line})" for line in safe) + " Tj ET"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>", "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>", f"<< /Length {len(stream.encode())} >>\nstream\n{stream}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    result = bytearray(b"%PDF-1.4\n"); offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result)); result.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode())
    xref = len(result); result.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(result)


@router.get("/{task_id}/summary.pdf")
def task_summary_pdf(task_id: int, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id)
    assignments = ", ".join(a["name"] for a in _serialize(db, task)["assignments"]) or "Unassigned"
    body = _simple_pdf([f"{task.task_key} - {task.title}", f"Status: {_effective_status(task)}", f"Priority: {task.priority}", f"Due: {task.due_at or 'Not set'}", f"Assigned: {assignments}", task.description or ""])
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{task.task_key}.pdf"', "Cache-Control": "private, no-store"})


def _summary_html(task, assignments):
    return f'''<!DOCTYPE html><html><body style="font-family:Arial,Helvetica,sans-serif;color:#1f2937;background:#f3f4f6;padding:24px"><table role="presentation" style="max-width:640px;margin:auto;background:white;border:1px solid #e5e7eb;border-radius:8px"><tr><td style="padding:28px"><h2 style="margin-top:0">Task Summary</h2><p><strong>{html.escape(task.task_key)} - {html.escape(task.title)}</strong></p><p>Status: {html.escape(_effective_status(task))}<br>Priority: {html.escape(task.priority)}<br>Due: {html.escape(str(task.due_at or 'Not set'))}<br>Assigned: {html.escape(assignments or 'Unassigned')}</p><p>{html.escape(task.description or '')}</p><p style="color:#6b7280;font-size:12px">Sent by Allied Connect.</p></td></tr></table></body></html>'''


@router.post("/{task_id}/send-summary", status_code=202)
def send_task_summary(task_id: int, payload: SummarySendInput, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    recipients = []
    for employee_id in dict.fromkeys(payload.employee_ids):
        employee = db.query(Employee).filter_by(timestation_id=employee_id, is_active=True).first()
        if not employee or not employee.email: raise HTTPException(400, "Internal recipient does not have a deliverable email")
        if employee.email_notifications_enabled is False: continue
        recipients.append((employee.email.lower(), employee_id))
    for address in dict.fromkeys(email.strip().lower() for email in payload.external_emails):
        if "@" not in address or "." not in address.rsplit("@", 1)[-1]: raise HTTPException(400, "Invalid external email address")
        known = db.query(Employee).filter(Employee.is_active.is_(True), func.lower(Employee.email) == address).first()
        if known and known.email_notifications_enabled is False: continue
        recipients.append((address, known.timestation_id if known else None))
    recipients = list(dict.fromkeys(recipients))
    if not recipients: raise HTTPException(400, "At least one recipient is required")
    names = ", ".join(a["name"] for a in _serialize(db, task)["assignments"])
    pdf = _simple_pdf([f"{task.task_key} - {task.title}", f"Status: {_effective_status(task)}", f"Priority: {task.priority}", f"Due: {task.due_at or 'Not set'}", f"Assigned: {names or 'Unassigned'}", task.description or ""]) if payload.include_pdf else None
    created = 0
    for address, employee_id in recipients:
        key = hashlib.sha256(f"{task.id}|{payload.idempotency_key}|{address}".encode()).hexdigest()
        try:
            with db.begin_nested():
                db.add(TaskSummaryDelivery(task_id=task.id, recipient_email=address, recipient_employee_id=employee_id, subject=f"[{task.task_key}] Task Summary", html_body=_summary_html(task, names), pdf_content=pdf, secure_link=None, idempotency_key=key, created_by=user["timestation_id"]))
                db.flush()
            created += 1
        except IntegrityError:
            continue
    if created:
        _activity(db, task, user, "summary_queued", f"{user.get('name', 'User')} queued a task summary for {created} recipient(s)")
    db.commit()
    return {"created": created, "status": "pending" if created else "duplicate"}


@router.post("/{task_id}/notes")
def add_note(task_id: int, payload: TaskNote, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    _activity(db, task, user, "note_added", f"{user.get('name', 'User')} added a note", new=payload.note)
    db.commit()
    return {"status": "ok"}


@router.post("/{task_id}/attachments")
async def upload_attachment(task_id: int, file: UploadFile = File(...), user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    if file.content_type not in ALLOWED_ATTACHMENT_TYPES:
        raise HTTPException(400, "Unsupported task attachment type")
    content = await file.read(25 * 1024 * 1024 + 1)
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(400, "Attachment exceeds 25 MiB")
    if any(existing.content == content for existing in db.query(TaskAttachment).filter_by(task_id=task.id, archived_at=None).all()):
        raise HTTPException(409, "This attachment content is already on the task")
    original = Path(file.filename or "attachment").name
    digest = hashlib.sha256(content).hexdigest()
    if db.query(TaskAttachment).filter_by(task_id=task.id, content_hash=digest).first():
        raise HTTPException(409, "Duplicate task attachment")
    stored = f"task-{task.id}-{uuid4().hex}-{original}"
    attachment = TaskAttachment(task_id=task.id, original_filename=original, stored_filename=stored, content_type=file.content_type, file_size=len(content), content_hash=digest, content=content, uploaded_by=user["timestation_id"])
    db.add(attachment)
    db.flush()
    _activity(db, task, user, "attachment_uploaded", f"{user.get('name', 'User')} uploaded {original}", attachment_id=attachment.id)
    db.commit()
    return {"id": attachment.id, "filename": original}


@router.get("/{task_id}/attachments/{attachment_id}")
def download_attachment(task_id: int, attachment_id: int, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id)
    row = db.query(TaskAttachment).filter_by(id=attachment_id, task_id=task_id, archived_at=None).first()
    if not task or task.archived_at or not row: raise HTTPException(404, "Attachment not found")
    return Response(row.content, media_type=row.content_type, headers={"Content-Disposition": f'attachment; filename="{row.original_filename}"', "Cache-Control": "private, no-store"})


@router.delete("/{task_id}/attachments/{attachment_id}", status_code=204)
def archive_attachment(task_id: int, attachment_id: int, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    row = db.query(TaskAttachment).filter_by(id=attachment_id, task_id=task_id, archived_at=None).first()
    if not row: raise HTTPException(404, "Attachment not found")
    row.archived_at = datetime.now(timezone.utc); row.archived_by = user["timestation_id"]
    _activity(db, task, user, "attachment_archived", f"{user.get('name', 'User')} archived {row.original_filename}", attachment_id=row.id)
    db.commit()


class ReminderInput(BaseModel):
    rule: str = Field(min_length=1, max_length=100)
    scheduled_at: datetime


@router.post("/{task_id}/reminders", status_code=201)
def create_reminder(task_id: int, payload: ReminderInput, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    if task.status in {"Completed", "Cancelled"}:
        raise HTTPException(409, "Reminders cannot be added to a terminal task")
    row = TaskReminder(task_id=task.id, rule=payload.rule, scheduled_at=payload.scheduled_at, created_by=user["timestation_id"])
    db.add(row); db.flush(); _activity(db, task, user, "reminder_created", f"Reminder scheduled for {payload.scheduled_at.isoformat()}"); enqueue_task_event(db, task, f"reminder:{row.id}", user["timestation_id"], payload.scheduled_at); db.commit()
    return {"id": row.id, "rule": row.rule, "scheduled_at": row.scheduled_at.isoformat()}


@router.delete("/{task_id}", status_code=204)
def archive_task(task_id: int, user: dict = Depends(_require_tasks), db: Session = Depends(get_db)):
    task = _task(db, user, task_id, write=True)
    task.archived_at = datetime.now(timezone.utc); task.archived_by = user["timestation_id"]
    db.query(TaskReminder).filter_by(task_id=task.id, enabled=True).update({TaskReminder.enabled: False}, synchronize_session=False)
    db.query(TaskNotification).filter_by(task_id=task.id, status="pending").update({TaskNotification.status: "cancelled"}, synchronize_session=False)
    _activity(db, task, user, "archived", f"{user.get('name', 'User')} archived the task"); db.commit()

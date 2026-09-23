from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.company_workflow import InternalNotification, NotificationDelivery
from app.models.database import get_db
from app.models.employee import Employee
from app.models.task import Task, TaskAssignment
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def create_notification(db: Session, *, employee_id: str, company_id: int, event_type: str, title: str, body: str, link: str, key: str) -> bool:
    if db.query(InternalNotification).filter_by(idempotency_key=key).first():
        return False
    notification = InternalNotification(employee_id=employee_id, company_id=company_id, event_type=event_type, title=title, body=body, link=link, idempotency_key=key)
    db.add(notification)
    db.flush()
    db.add(NotificationDelivery(notification_id=notification.id, channel="internal", recipient=employee_id, template=event_type, idempotency_key=f"internal:{key}", status="delivered", attempted_at=datetime.now(timezone.utc)))
    employee = db.query(Employee).filter_by(timestation_id=employee_id).first()
    if employee and employee.email:
        # A durable outbox record is claimed by the scheduler/worker. No remote call occurs in request transactions.
        db.add(NotificationDelivery(notification_id=notification.id, channel="email", recipient=employee.email, template=event_type, idempotency_key=f"email:{key}", status="pending"))
    return True


def notify_task_assignees(db: Session, task: Task, event_type: str, occurrence: str = "once") -> int:
    created = 0
    recipients = {assignment.employee_id for assignment in db.query(TaskAssignment).filter_by(task_id=task.id).all()}
    recipients.add(task.created_by)
    for employee_id in recipients:
        key = f"task:{task.id}:{event_type}:{employee_id}:{occurrence}"
        created += int(create_notification(db, employee_id=employee_id, company_id=task.company_id, event_type=event_type, title=f"{task.task_key}: {task.title}", body=f"Task {event_type.replace('_', ' ')}", link=f"/company-tasks?task={task.id}", key=key))
    return created


@router.get("")
def list_notifications(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(InternalNotification).filter_by(employee_id=user["timestation_id"]).order_by(InternalNotification.created_at.desc(), InternalNotification.id.desc()).all()
    return {"notifications": [{"id": r.id, "company_id": r.company_id, "event_type": r.event_type, "title": r.title, "body": r.body, "link": r.link, "read_at": r.read_at.isoformat() if r.read_at else None, "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]}


@router.post("/{notification_id}/read")
def read_notification(notification_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(InternalNotification).filter_by(id=notification_id, employee_id=user["timestation_id"]).first()
    if row:
        row.read_at = datetime.now(timezone.utc)
        db.commit()
    return {"status": "ok"}


class DueRun(BaseModel):
    as_of: datetime | None = None


@router.post("/run-due")
def run_due(payload: DueRun, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.get("role") not in {"admin", "super_admin"}:
        from fastapi import HTTPException
        raise HTTPException(403, "Administrator access required")
    now = payload.as_of or datetime.now(timezone.utc)
    now_naive = now.replace(tzinfo=None) if now.tzinfo else now
    created = 0
    for task in db.query(Task).filter(Task.archived_at.is_(None), Task.due_at.is_not(None)).all():
        due = task.due_at.replace(tzinfo=None) if task.due_at.tzinfo else task.due_at
        if task.status not in {"Completed", "Cancelled"} and due < now_naive:
            occurrence = now.date().isoformat()
            created += int(notify_task_assignees(db, task, "task_overdue", occurrence) > 0)
        elif task.status not in {"Completed", "Cancelled"} and 0 <= (due - now_naive).total_seconds() <= 86400:
            created += int(notify_task_assignees(db, task, "task_reminder", due.isoformat()) > 0)
    db.commit()
    return {"created": created, "as_of": now.isoformat()}

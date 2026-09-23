import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.models.employee import Employee
from app.models.task import TaskAssignment, TaskNotification


def _now(): return datetime.now(timezone.utc)


def enqueue_task_event(db, task, event_type, actor_id, scheduled_at=None):
    assignments = db.query(TaskAssignment).filter_by(task_id=task.id).all()
    for assignment in assignments:
        employee = db.query(Employee).filter_by(timestation_id=assignment.employee_id).first()
        subject = f"[{task.task_key}] {task.title}"
        body = f"Task {task.task_key}: {task.title}\nEvent: {event_type}"
        for channel in ("internal", "email"):
            if channel == "email" and (not employee or not employee.email): continue
            raw = f"{task.id}|{event_type}|{assignment.employee_id}|{channel}|{scheduled_at or ''}"
            key = hashlib.sha256(raw.encode()).hexdigest()
            if db.query(TaskNotification).filter_by(idempotency_key=key).first(): continue
            db.add(TaskNotification(idempotency_key=key, task_id=task.id, employee_id=assignment.employee_id, recipient_email=employee.email if employee else None, channel=channel, event_type=event_type, subject=subject, body=body, available_at=scheduled_at or _now()))


def process_due_notifications(db, send_email, limit=100):
    now = _now()
    candidate_ids = [row.id for row in db.query(TaskNotification.id).filter(
        TaskNotification.status == "pending", TaskNotification.available_at <= now
    ).order_by(TaskNotification.id).limit(limit).all()]
    claimed = []
    for row_id in candidate_ids:
        token = secrets.token_hex(16)
        updated = db.query(TaskNotification).filter(
            TaskNotification.id == row_id, TaskNotification.status == "pending"
        ).update({TaskNotification.status: "processing", TaskNotification.claim_token: token,
                  TaskNotification.claimed_at: now, TaskNotification.attempts: TaskNotification.attempts + 1},
                 synchronize_session=False)
        db.commit()
        if updated:
            claimed.append((row_id, token))
    for row_id, token in claimed:
        row = db.query(TaskNotification).filter_by(id=row_id, claim_token=token, status="processing").first()
        if not row:
            continue
        try:
            if row.channel == "email": send_email(row.recipient_email, row.subject, row.body)
            row.status = "sent"; row.sent_at = now; row.last_error = None
        except Exception as exc:
            # The durable processing claim is intentionally not made pending again: after a
            # process crash or an indeterminate provider result, retrying could double-send.
            row.status = "failed"
            row.last_error = str(exc)[:1000]
        db.commit()
    return len(claimed)

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.models.employee import Employee
from app.models.task import Task, TaskAssignment, TaskNotification, TaskSummaryDelivery
from app.models.company_workflow import CalendarAttendee, CompanyCalendarEvent, InternalNotification, NotificationDelivery


def _now(): return datetime.now(timezone.utc)


def enqueue_task_event(db, task, event_type, actor_id, scheduled_at=None):
    assignments = db.query(TaskAssignment).filter_by(task_id=task.id).all()
    for assignment in assignments:
        employee = db.query(Employee).filter_by(timestation_id=assignment.employee_id).first()
        subject = f"[{task.task_key}] {task.title}"
        body = f"Task {task.task_key}: {task.title}\nEvent: {event_type}"
        for channel in ("internal", "email"):
            if channel == "email" and (not employee or not employee.email or employee.email_notifications_enabled is False): continue
            raw = f"{task.id}|{event_type}|{assignment.employee_id}|{channel}|{scheduled_at or ''}"
            key = hashlib.sha256(raw.encode()).hexdigest()
            if db.query(TaskNotification).filter_by(idempotency_key=key).first(): continue
            db.add(TaskNotification(idempotency_key=key, task_id=task.id, employee_id=assignment.employee_id, recipient_email=employee.email if employee else None, channel=channel, event_type=event_type, subject=subject, body=body, available_at=scheduled_at or _now()))


def process_due_notifications(db, send_email, limit=100):
    now = _now()
    candidate_ids = [row.id for row in db.query(TaskNotification.id).join(Task, Task.id == TaskNotification.task_id).filter(
        TaskNotification.status == "pending", TaskNotification.available_at <= now,
        Task.archived_at.is_(None),
        ~((Task.status.in_(("Completed", "Cancelled"))) & ((TaskNotification.event_type == "overdue") | TaskNotification.event_type.like("reminder%")))
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


def process_summary_deliveries(db, send_summary, limit=50):
    """Claim durable summary deliveries before transport so repeated jobs cannot double-send."""
    ids = [row.id for row in db.query(TaskSummaryDelivery.id).filter_by(status="pending").order_by(TaskSummaryDelivery.id).limit(limit).all()]
    processed = 0
    for row_id in ids:
        updated = db.query(TaskSummaryDelivery).filter_by(id=row_id, status="pending").update({TaskSummaryDelivery.status: "processing", TaskSummaryDelivery.attempts: TaskSummaryDelivery.attempts + 1}, synchronize_session=False)
        db.commit()
        if not updated: continue
        row = db.get(TaskSummaryDelivery, row_id)
        try:
            if row.recipient_employee_id:
                employee = db.query(Employee).filter_by(timestation_id=row.recipient_employee_id).first()
                if not employee or employee.email_notifications_enabled is False:
                    row.status = "cancelled"; row.last_error = None; db.commit(); processed += 1; continue
            result = send_summary(row.recipient_email, row.subject, row.html_body, row.pdf_content)
            row.status = "sent"; row.sent_at = _now(); row.last_error = None
            if result: row.provider_message_id = result.get("MessageID")
        except Exception:
            row.status = "failed"
            row.last_error = "Task summary delivery failed"
        db.commit(); processed += 1
    return processed


def process_notification_deliveries(db, send_email, limit=100):
    """Atomically claim and deliver the generic email outbox."""
    ids = [row.id for row in db.query(NotificationDelivery.id).filter_by(channel="email", status="pending").order_by(NotificationDelivery.id).limit(limit).all()]
    processed = 0
    for row_id in ids:
        updated = db.query(NotificationDelivery).filter_by(id=row_id, status="pending").update(
            {NotificationDelivery.status: "processing", NotificationDelivery.attempted_at: _now()}, synchronize_session=False)
        db.commit()
        if not updated:
            continue
        row = db.get(NotificationDelivery, row_id)
        notification = db.get(InternalNotification, row.notification_id) if row.notification_id else None
        try:
            result = send_email(row.recipient, notification.title if notification else row.template, notification.body if notification else "")
            row.status = "delivered"
            row.error = None
            if result:
                row.provider_message_id = result.get("MessageID")
        except Exception:
            row.status = "failed"
            row.error = "Notification delivery failed"
        db.commit()
        processed += 1
    return processed


def generate_calendar_reminders(db, now=None, horizon_minutes=None):
    """Create durable attendee reminders when standalone events enter their reminder window."""
    from app.routers.notifications import create_notification
    now = now or _now()

    events = db.query(CompanyCalendarEvent).filter(CompanyCalendarEvent.archived_at.is_(None), CompanyCalendarEvent.reminder_minutes.is_not(None)).all()
    created = 0
    for event in events:
        start = event.start_at if event.start_at.tzinfo else event.start_at.replace(tzinfo=timezone.utc)
        reminder_at = start - timedelta(minutes=event.reminder_minutes)
        if reminder_at > now:
            continue
        for attendee in db.query(CalendarAttendee).filter_by(event_id=event.id).all():
            key = f"calendar:{event.id}:reminder:{attendee.employee_id}:{reminder_at.isoformat()}"
            created += int(create_notification(db, employee_id=attendee.employee_id, company_id=event.company_id, event_type="calendar_reminder", title=event.title, body=f"Calendar event starts at {start.isoformat()}", link=f"/company-calendar?event={event.id}", key=key))
    return created

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from concurrent.futures import ThreadPoolExecutor

from app.models.database import Base
from app.models.employee import Employee
from app.models.compliance_company import ComplianceCompany
from app.models.task import Task, TaskAssignment, TaskNotification, TaskReminder, TaskSummaryDelivery, VaultAudit, VaultEntry, VaultUnlock
from app.models.company_workflow import CalendarAttendee, CompanyCalendarEvent, InternalNotification, NotificationDelivery
from app.services.task_notifications import enqueue_task_event, process_due_notifications, process_notification_deliveries, generate_calendar_reminders
from app.routers.notifications import create_notification
from app.services.vault import VaultService, vault_employee_allowed
from app.routers.tasks import _calendar_events


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        ComplianceCompany(id=1, legal_name="Allied"),
        Employee(timestation_id="local_f2a5804ba2e5", name="Allowed One", pin="1", email="one@example.test", role="employee"),
        Employee(timestation_id="local_262a0ca4abea", name="Allowed Two", pin="2", email="two@example.test", role="employee"),
        Employee(timestation_id="local_f2a5804ba2e50", name="Prefix Attack", pin="3", role="super_admin"),
    ])
    session.commit()
    yield session
    session.close()


def test_vault_allowlist_uses_exact_employee_ids():
    assert vault_employee_allowed("local_f2a5804ba2e5")
    assert vault_employee_allowed("local_262a0ca4abea")
    assert not vault_employee_allowed("local_f2a5804ba2e50")
    assert not vault_employee_allowed("LOCAL_F2A5804BA2E5")
    assert not vault_employee_allowed(None)


def test_vault_unlock_is_separate_hash_and_ciphertext_uses_dedicated_key(db, monkeypatch):
    monkeypatch.setenv("PASSWORD_VAULT_KEY", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")
    service = VaultService(db, lock_minutes=15)
    service.configure_unlock("local_f2a5804ba2e5", "correct horse battery staple")
    assert service.unlock("local_f2a5804ba2e5", "wrong") is None
    token = service.unlock("local_f2a5804ba2e5", "correct horse battery staple")
    assert token
    entry = service.create_entry(token, "local_f2a5804ba2e5", "Vendor", "marc", "secret", "https://example.test", None)
    assert b"secret" not in entry.secret_ciphertext
    assert service.reveal(token, "local_f2a5804ba2e5", entry.id)["password"] == "secret"
    service.lock_now(token, "local_f2a5804ba2e5")
    with pytest.raises(PermissionError):
        service.reveal(token, "local_f2a5804ba2e5", entry.id)
    actions = [row.action for row in db.query(VaultAudit).order_by(VaultAudit.id)]
    assert actions == ["unlock_configured", "unlock_failed", "unlocked", "entry_created", "secret_revealed", "locked"]


def test_task_notifications_are_durable_and_idempotent(db):
    task = Task(task_key="TASK-000001", company_id=1, title="Renew license", created_by="local_f2a5804ba2e5", due_at=datetime.now(timezone.utc) + timedelta(days=1))
    db.add(task); db.flush()
    db.add(TaskAssignment(task_id=task.id, employee_id="local_262a0ca4abea", is_primary=True, assigned_by="local_f2a5804ba2e5"))
    db.commit()
    enqueue_task_event(db, task, "assigned", actor_id="local_f2a5804ba2e5")
    enqueue_task_event(db, task, "assigned", actor_id="local_f2a5804ba2e5")
    db.commit()
    assert db.query(TaskNotification).count() == 2  # internal + email, not duplicated
    sent = []
    process_due_notifications(db, lambda to, subject, body: sent.append((to, subject, body)))
    process_due_notifications(db, lambda *args: sent.append(args))
    assert len(sent) == 1
    assert db.query(TaskNotification).filter_by(channel="internal", status="sent").count() == 1
    assert db.query(TaskNotification).filter_by(channel="email", status="sent").count() == 1


def test_calendar_combines_tasks_and_reminders_without_archived_items(db):
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    task = Task(task_key="TASK-000002", company_id=1, title="Annual report", created_by="local_f2a5804ba2e5", start_at=start, due_at=start + timedelta(days=2))
    archived = Task(task_key="TASK-000003", company_id=1, title="Hidden", created_by="local_f2a5804ba2e5", due_at=start, archived_at=start)
    db.add_all([task, archived]); db.flush()
    db.add(TaskReminder(task_id=task.id, rule="custom", scheduled_at=start + timedelta(days=1), created_by="local_f2a5804ba2e5")); db.commit()
    events = _calendar_events(db, start - timedelta(days=1), start + timedelta(days=4), 1)
    assert [(e["kind"], e["title"]) for e in events] == [("task_start", "Annual report"), ("reminder", "Annual report"), ("task_due", "Annual report")]


def test_notification_claim_is_atomic_across_workers(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'claims.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as seed:
        seed.add_all([
            ComplianceCompany(id=1, legal_name="Allied"),
            Employee(timestation_id="worker-target", name="Target", pin="1", email="target@example.test"),
        ])
        seed.flush()
        task = Task(task_key="TASK-CLAIM", company_id=1, title="Claim me", created_by="worker-target")
        seed.add(task); seed.flush()
        seed.add(TaskNotification(idempotency_key="claim-once", task_id=task.id, employee_id="worker-target", recipient_email="target@example.test", channel="email", event_type="assigned", subject="Claim", body="Once", available_at=datetime.now(timezone.utc)))
        seed.commit()
    sent = []
    def worker():
        with Session() as session:
            return process_due_notifications(session, lambda *args: sent.append(args))
    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(lambda _: worker(), range(2)))
    assert sum(counts) == 1
    assert len(sent) == 1
    with Session() as check:
        row = check.query(TaskNotification).filter_by(idempotency_key="claim-once").one()
        assert row.status == "sent" and row.attempts == 1 and row.claim_token


def test_create_notification_honors_email_opt_out_and_is_idempotent(db):
    employee = db.query(Employee).filter_by(timestation_id="local_262a0ca4abea").one()
    employee.email_notifications_enabled = False
    db.commit()
    assert create_notification(db, employee_id=employee.timestation_id, company_id=1, event_type="test", title="Test", body="Body", link="/", key="same")
    db.commit()
    assert not create_notification(db, employee_id=employee.timestation_id, company_id=1, event_type="test", title="Test", body="Body", link="/", key="same")
    assert db.query(InternalNotification).count() == 1
    assert db.query(NotificationDelivery).filter_by(channel="email").count() == 0


def test_due_claim_skips_terminal_and_archived_tasks(db):
    _now = datetime.now(timezone.utc)
    for index, kwargs in enumerate(({"status": "Completed"}, {"status": "Cancelled"}, {"archived_at": _now}), 1):
        task = Task(task_key=f"TERMINAL-{index}", company_id=1, title="No send", created_by="local_f2a5804ba2e5", **kwargs)
        db.add(task); db.flush()
        db.add(TaskNotification(idempotency_key=f"terminal-{index}", task_id=task.id, channel="email", event_type="reminder:1", subject="No", body="No", recipient_email="one@example.test", available_at=_now))
    db.commit()
    sent = []
    assert process_due_notifications(db, lambda *args: sent.append(args)) == 0
    assert sent == []


def test_notification_outbox_claim_and_calendar_reminders(db):
    event = CompanyCalendarEvent(company_id=1, title="Board", start_at=datetime.now(timezone.utc) + timedelta(minutes=30), reminder_minutes=30, created_by="local_f2a5804ba2e5")
    db.add(event); db.flush()
    db.add(CalendarAttendee(event_id=event.id, employee_id="local_262a0ca4abea")); db.commit()
    now = datetime.now(timezone.utc)
    assert generate_calendar_reminders(db, now=now) == 1
    assert generate_calendar_reminders(db, now=now) == 0
    db.commit()
    sent = []
    assert process_notification_deliveries(db, lambda *args: sent.append(args)) == 1
    assert process_notification_deliveries(db, lambda *args: sent.append(args)) == 0
    assert len(sent) == 1

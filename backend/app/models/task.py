from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, inspect, text
from sqlalchemy.sql import func

from app.models.database import Base


class TaskCategory(Base):
    __tablename__ = "task_categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class VaultCategory(Base):
    __tablename__ = "vault_categories"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    task_key = Column(String, nullable=False, unique=True, index=True)
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    department = Column(String, nullable=True, index=True)
    category_id = Column(Integer, ForeignKey("task_categories.id"), nullable=True, index=True)
    state_compliance_id = Column(Integer, ForeignKey("state_compliance.id"), nullable=True, index=True)
    priority = Column(String, nullable=False, default="Normal", index=True)
    status = Column(String, nullable=False, default="Not Started", index=True)
    start_at = Column(DateTime, nullable=True, index=True)
    due_at = Column(DateTime, nullable=True, index=True)
    notes = Column(Text, nullable=True)
    completion_notes = Column(Text, nullable=True)
    created_by = Column(String, nullable=False, index=True)
    completed_by = Column(String, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    archived_at = Column(DateTime, nullable=True)
    archived_by = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_tasks_company_due", "company_id", "due_at"),
        Index("ix_tasks_company_status", "company_id", "status"),
    )


class TaskAssignment(Base):
    __tablename__ = "task_assignments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(String, nullable=False, index=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    assigned_by = Column(String, nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("task_id", "employee_id", name="uq_task_assignment_user"),
    )


class TaskActivity(Base):
    __tablename__ = "task_activity"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_employee_id = Column(String, nullable=False)
    actor_name = Column(String, nullable=True)
    action_type = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    attachment_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String, nullable=False)
    stored_filename = Column(String, nullable=False, unique=True)
    content_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    content_hash = Column(String, nullable=True, index=True)
    content = Column(LargeBinary, nullable=False)
    uploaded_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    archived_at = Column(DateTime, nullable=True)
    archived_by = Column(String, nullable=True)

    __table_args__ = (UniqueConstraint("task_id", "content_hash", name="uq_task_attachment_hash"),)


class TaskReminder(Base):
    __tablename__ = "task_reminders"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    rule = Column(String, nullable=False)
    scheduled_at = Column(DateTime, nullable=True, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class TaskNotificationRecipient(Base):
    __tablename__ = "task_notification_recipients"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(String, nullable=True, index=True)
    external_email = Column(String, nullable=True)
    notification_type = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_task_recipient_type", "task_id", "notification_type"),
    )


class TaskNotification(Base):
    __tablename__ = "task_notifications"
    id = Column(Integer, primary_key=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id = Column(String, nullable=True, index=True)
    recipient_email = Column(String, nullable=True)
    channel = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    status = Column(String, nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, nullable=False, server_default=func.now(), index=True)
    sent_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    claim_token = Column(String, nullable=True, unique=True, index=True)
    claimed_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())


class TaskSummaryDelivery(Base):
    __tablename__ = "task_summary_deliveries"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_email = Column(String, nullable=False)
    recipient_employee_id = Column(String, nullable=True, index=True)
    subject = Column(String, nullable=False)
    html_body = Column(Text, nullable=False)
    pdf_content = Column(LargeBinary, nullable=True)
    secure_link = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    provider_message_id = Column(String, nullable=True)
    last_error = Column(Text, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    sent_at = Column(DateTime, nullable=True)


class VaultUnlock(Base):
    __tablename__ = "vault_unlocks"
    employee_id = Column(String, primary_key=True)
    password_hash = Column(String, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class VaultSession(Base):
    __tablename__ = "vault_sessions"
    token_hash = Column(String, primary_key=True)
    employee_id = Column(String, nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class VaultEntry(Base):
    __tablename__ = "vault_entries"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("vault_categories.id"), nullable=True, index=True)
    name = Column(String, nullable=False)
    username_ciphertext = Column(LargeBinary, nullable=True)
    secret_ciphertext = Column(LargeBinary, nullable=False)
    url_ciphertext = Column(LargeBinary, nullable=True)
    notes_ciphertext = Column(LargeBinary, nullable=True)
    account_ref_ciphertext = Column(LargeBinary, nullable=True)
    mfa_notes_ciphertext = Column(LargeBinary, nullable=True)
    recovery_notes_ciphertext = Column(LargeBinary, nullable=True)
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    archived_at = Column(DateTime, nullable=True)


class VaultAudit(Base):
    __tablename__ = "vault_audit"
    id = Column(Integer, primary_key=True)
    employee_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False, index=True)
    entry_id = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)


TASK_CATEGORIES = (
    "Administration", "Accounting", "Finance", "Compliance", "State Licensing",
    "Legal", "Operations", "Collections", "Human Resources", "IT",
    "Software Development", "Management", "Client Management", "Vendor Management",
    "Banking", "Insurance", "Reporting", "Project", "Meeting / Follow-Up", "Other",
)
TASK_PRIORITIES = ("Low", "Normal", "High", "Urgent")
TASK_STATUSES = ("Not Started", "In Progress", "Waiting", "Completed", "Cancelled", "Overdue")


def ensure_task_workflow_schema(engine):
    """Apply only additive, repeatable upgrades for databases created before claims existed."""
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "task_notifications" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("task_notifications")}
    with engine.begin() as connection:
        if "claim_token" not in columns:
            connection.execute(text("ALTER TABLE task_notifications ADD COLUMN claim_token VARCHAR"))
        if "claimed_at" not in columns:
            connection.execute(text("ALTER TABLE task_notifications ADD COLUMN claimed_at TIMESTAMP"))
        if "vault_entries" in tables:
            vault_columns = {column["name"] for column in inspector.get_columns("vault_entries")}
            if "category_id" not in vault_columns:
                connection.execute(text("ALTER TABLE vault_entries ADD COLUMN category_id INTEGER"))
            for column in ("account_ref_ciphertext", "mfa_notes_ciphertext", "recovery_notes_ciphertext"):
                if column not in vault_columns:
                    sql_type = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
                    connection.execute(text(f"ALTER TABLE vault_entries ADD COLUMN {column} {sql_type}"))
        if "company_calendar_events" in tables:
            calendar_columns = {column["name"] for column in inspector.get_columns("company_calendar_events")}
            if "event_type_id" not in calendar_columns:
                connection.execute(text("ALTER TABLE company_calendar_events ADD COLUMN event_type_id INTEGER"))

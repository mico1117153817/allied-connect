from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.sql import func

from app.models.database import Base


class InternalNotification(Base):
    __tablename__ = "internal_notifications"
    id = Column(Integer, primary_key=True)
    employee_id = Column(String, nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), nullable=False, index=True)
    event_type = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    link = Column(String, nullable=True)
    idempotency_key = Column(String, nullable=False, unique=True)
    read_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id = Column(Integer, primary_key=True)
    notification_id = Column(Integer, ForeignKey("internal_notifications.id", ondelete="CASCADE"), nullable=True)
    channel = Column(String, nullable=False)
    recipient = Column(String, nullable=False)
    template = Column(String, nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="pending")
    provider_message_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    attempted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class CompanyCalendarEvent(Base):
    __tablename__ = "company_calendar_events"
    id = Column(Integer, primary_key=True)
    company_id = Column(Integer, ForeignKey("compliance_companies.id"), nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    start_at = Column(DateTime, nullable=False, index=True)
    end_at = Column(DateTime, nullable=True)
    all_day = Column(Boolean, nullable=False, default=False)
    color = Column(String, nullable=False, default="#2563eb")
    notes = Column(Text, nullable=True)
    reminder_minutes = Column(Integer, nullable=True)
    created_by = Column(String, nullable=False)
    archived_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class CalendarAttendee(Base):
    __tablename__ = "calendar_attendees"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("company_calendar_events.id", ondelete="CASCADE"), nullable=False)
    employee_id = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("event_id", "employee_id", name="uq_calendar_attendee"),)


class CalendarAttachment(Base):
    __tablename__ = "calendar_attachments"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, ForeignKey("company_calendar_events.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    content_type = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    content = Column(LargeBinary, nullable=False)
    uploaded_by = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("event_id", "content_hash", name="uq_calendar_attachment_hash"),)


class CalendarAudit(Base):
    __tablename__ = "calendar_audit"
    id = Column(Integer, primary_key=True)
    event_id = Column(Integer, nullable=False, index=True)
    actor_employee_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


Index("ix_calendar_company_start", CompanyCalendarEvent.company_id, CompanyCalendarEvent.start_at)

"""Email notification service for time-off requests using Postmark.

In dev mode (no POSTMARK_API_KEY), this simply logs the notification instead of
sending a real email, so the app works out of the box without an account.
"""

from datetime import date
from typing import Optional

import httpx

from app.config import settings


def _status_label(status: str) -> str:
    return {
        "approved": "Approved ✅",
        "denied": "Denied ❌",
        "pending": "Submitted ⏳",
    }.get(status, status.capitalize())


def _build_html(
    employee_name: str,
    status: str,
    start_date: date,
    end_date: date,
    request_type: str,
) -> str:
    label = _status_label(status)
    dates = (
        start_date.strftime("%B %d, %Y")
        if start_date == end_date
        else f"{start_date.strftime('%B %d, %Y')} – {end_date.strftime('%B %d, %Y')}"
    )
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: Arial, Helvetica, sans-serif; color: #1f2937; background:#f9fafb; margin:0; padding:24px;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px; margin:0 auto; background:#ffffff; border-radius:10px; border:1px solid #e5e7eb;">
    <tr>
      <td style="padding:24px 32px 8px;">
        <h2 style="margin:0 0 4px; color:#111827;">Time-Off Request Update</h2>
        <p style="margin:0; color:#6b7280; font-size:14px;">Allied Connect</p>
      </td>
    </tr>
    <tr>
      <td style="padding:16px 32px;">
        <p style="margin:0 0 16px; font-size:16px;">Hi <strong>{employee_name}</strong>,</p>
        <p style="margin:0 0 16px;">Your time-off request has been <strong>{label}</strong>.</p>
        <table role="presentation" cellpadding="8" cellspacing="0" style="width:100%; border-collapse:collapse; font-size:14px;">
          <tr><td style="background:#f3f4f6; width:40%; color:#6b7280;">Request type</td><td style="background:#f9fafb;">{request_type.capitalize()}</td></tr>
          <tr><td style="background:#f3f4f6; color:#6b7280;">Dates</td><td style="background:#f9fafb;">{dates}</td></tr>
          <tr><td style="background:#f3f4f6; color:#6b7280;">Status</td><td style="background:#f9fafb;">{label}</td></tr>
        </table>
      </td>
    </tr>
    <tr>
      <td style="padding:16px 32px 28px;">
        <p style="margin:0; color:#6b7280; font-size:13px;">
          If you have questions, please reach out to your manager.
        </p>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _build_subject(status: str, request_type: str) -> str:
    return f"Time-Off Request {status.capitalize()} – {request_type.capitalize()}"


async def send_time_off_notification(
    to_email: str,
    employee_name: str,
    status: str,
    start_date: date,
    end_date: date,
    request_type: str,
) -> Optional[dict]:
    """Send a time-off decision email to an employee via Postmark.

    Returns the Postmark response dict when an email was actually sent, or
    ``None`` in dev mode (no API key configured).
    """
    subject = _build_subject(status, request_type)
    html = _build_html(employee_name, status, start_date, end_date, request_type)

    if not settings.POSTMARK_API_KEY:
        # Dev mode: just log it.
        print(
            "[email] (dev mode) time-off notification -> "
            f"to={to_email!r} employee={employee_name!r} status={status} "
            f"type={request_type} start={start_date} end={end_date}"
        )
        return None

    # Postmark API: https://postmarkapp.com/developer/api/email-api
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.postmarkapp.com/email",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": settings.POSTMARK_API_KEY,
            },
            json={
                "From": settings.EMAIL_FROM,
                "To": to_email,
                "Subject": subject,
                "HtmlBody": html,
            },
            timeout=15.0,
        )
        return {"status_code": response.status_code, "body": response.json()}


async def _send_postmark_email(to_email: str, subject: str, html: str) -> Optional[dict]:
    """Send a generic Allied Connect email, or log it when Postmark is not configured."""
    if not settings.POSTMARK_API_KEY:
        print(f"[email] (dev mode) document notification -> to={to_email!r} subject={subject!r}")
        return None
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.postmarkapp.com/email",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Postmark-Server-Token": settings.POSTMARK_API_KEY,
            },
            json={"From": settings.EMAIL_FROM, "To": to_email, "Subject": subject, "HtmlBody": html},
            timeout=15.0,
        )
        return {"status_code": response.status_code, "body": response.json()}


async def send_document_notification(
    to_email: str,
    employee_name: str,
    document_title: str,
    requires_signature: bool,
) -> Optional[dict]:
    action = "Review and signature are required before you can continue using Allied Connect." if requires_signature else "Please log in to Allied Connect to review it."
    html = f"""<html><body style="font-family:Arial;color:#1f2937">
    <h2>New Document Available</h2><p>Hi <strong>{employee_name}</strong>,</p>
    <p><strong>{document_title}</strong> has been sent to you.</p><p>{action}</p>
    <p><a href="{settings.FRONTEND_URL}/documents">Open Allied Connect Documents</a></p>
    </body></html>"""
    return await _send_postmark_email(to_email, f"New Document - {document_title}", html)


async def send_document_void_notification(
    to_email: str,
    employee_name: str,
    document_title: str,
) -> Optional[dict]:
    html = f"""<html><body style="font-family:Arial;color:#1f2937">
    <h2>Document Voided</h2><p>Hi <strong>{employee_name}</strong>,</p>
    <p><strong>{document_title}</strong> has been voided by management. It is no longer available and no action is required.</p>
    </body></html>"""
    return await _send_postmark_email(to_email, f"Document Voided - {document_title}", html)

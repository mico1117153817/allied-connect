"""Email notification service for time-off requests using the Resend SDK.

In dev mode (no RESEND_API_KEY), this simply logs the notification instead of
sending a real email, so the app works out of the box without an account.
"""

from datetime import date
from typing import Optional

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
        <p style="margin:0; color:#6b7280; font-size:14px;">Employee Portal</p>
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
    """Send a time-off decision email to an employee.

    Returns the Resend response dict when an email was actually sent, or
    ``None`` in dev mode (no API key configured).
    """
    subject = _build_subject(status, request_type)
    html = _build_html(employee_name, status, start_date, end_date, request_type)

    if not settings.RESEND_API_KEY:
        # Dev mode: just log it.
        print(
            "[email] (dev mode) time-off notification -> "
            f"to={to_email!r} employee={employee_name!r} status={status} "
            f"type={request_type} start={start_date} end={end_date}"
        )
        return None

    import resend

    resend.api_key = settings.RESEND_API_KEY
    response = resend.Emails.send(
        {
            "from": settings.EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html,
        }
    )
    return response

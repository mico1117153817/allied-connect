import logging
from datetime import date, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.config import settings
from app.services.timestation import timestation
from app.models.database import SessionLocal
from app.models.employee import Employee

logger = logging.getLogger(__name__)


async def sync_employees():
    """Sync employee list from TimeStation into local DB."""
    db = SessionLocal()
    try:
        employees = await timestation.get_employees()
        count = 0
        for emp in employees:
            db_emp = (
                db.query(Employee)
                .filter(Employee.timestation_id == emp["employee_id"])
                .first()
            )
            if db_emp:
                # Update fields from TimeStation
                db_emp.name = emp.get("name", db_emp.name)
                db_emp.status = emp.get("status", db_emp.status)
                db_emp.email = emp.get("email") or db_emp.email
                db_emp.primary_department = emp.get(
                    "primary_department", db_emp.primary_department
                )
                db_emp.primary_department_id = emp.get(
                    "primary_department_id", db_emp.primary_department_id
                )
                db_emp.title = emp.get("title", db_emp.title)
                db_emp.custom_employee_id = emp.get(
                    "custom_employee_id", db_emp.custom_employee_id
                )
                db_emp.last_synced = __import__("datetime").datetime.now()
            else:
                # Create new employee record
                db_emp = Employee(
                    timestation_id=emp["employee_id"],
                    name=emp.get("name", ""),
                    pin=emp.get("pin", ""),
                    email=emp.get("email"),
                    primary_department=emp.get("primary_department"),
                    primary_department_id=emp.get("primary_department_id"),
                    status=emp.get("status", "out"),
                    title=emp.get("title"),
                    custom_employee_id=emp.get("custom_employee_id"),
                )
                db.add(db_emp)
            count += 1
        db.commit()
        logger.info(f"Synced {count} employees from TimeStation")
    except Exception as e:
        logger.error(f"Employee sync failed: {e}")
        db.rollback()
    finally:
        db.close()


async def check_pay_date_reminder():
    """Check if tomorrow is a pay date (8th or 22nd) and log a reminder."""
    tomorrow = date.today() + timedelta(days=1)
    if tomorrow.day in settings.PAY_DATES:
        logger.info(
            f"PAY DATE REMINDER: Tomorrow ({tomorrow.isoformat()}) is a pay date. "
            "Ensure back hours and vacation hours are entered."
        )


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # Sync employees daily at 2 AM
    scheduler.add_job(sync_employees, "cron", hour=2, minute=0)
    # Pay date reminder daily at 8 AM
    scheduler.add_job(check_pay_date_reminder, "cron", hour=8, minute=0)
    scheduler.start()
    logger.info("Scheduler started: employee sync (2 AM), pay date reminders (8 AM)")
    return scheduler

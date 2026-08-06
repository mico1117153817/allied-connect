"""Set up managers and local-only accounts for the Allied Connect portal.

Usage:
    cd backend
    source .venv/Scripts/activate  # Windows git-bash
    python -m scripts.set_manager

This script:
  1. Syncs employees from TimeStation into local DB
  2. Sets Margaret Montimerano and Brandon Shampoe as managers
  3. Creates local-only accounts for Marc Mancuso (President) and Nicole Mancuso (VP)
     since they don't exist in TimeStation
"""
import asyncio
import hashlib
from app.models.database import SessionLocal, engine, Base
from app.models.employee import Employee
from app.services.timestation import timestation


# TimeStation employees to set as managers
TIMESTATION_MANAGERS = [
    "Margaret Montimerano",
    "Brandon Shampoe",
]

# Local-only accounts (not in TimeStation)
# PINs chosen to avoid collision with existing TimeStation PINs
LOCAL_ACCOUNTS = [
    {"name": "Marc Mancuso", "pin": "1001", "email": "marcmancuso@alliedalliancegroupinc.com", "title": "President", "role": "super_admin"},
    {"name": "Nicole Mancuso", "pin": "1002", "email": "nicole@alliedalliancegroupinc.com", "title": "Vice President", "role": "super_admin"},
]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # 1. Sync employees from TimeStation
    print("Syncing employees from TimeStation...")
    employees = asyncio.run(timestation.get_employees())
    for emp in employees:
        existing = db.query(Employee).filter(
            Employee.timestation_id == emp["employee_id"]
        ).first()
        if not existing:
            db.add(Employee(
                timestation_id=emp["employee_id"],
                name=emp.get("name", ""),
                pin=emp.get("pin", ""),
                email=emp.get("email"),
                primary_department=emp.get("primary_department"),
                primary_department_id=emp.get("primary_department_id"),
                status=emp.get("status", "out"),
            ))
        else:
            # Update existing
            existing.name = emp.get("name", existing.name)
            existing.pin = emp.get("pin", existing.pin)
            if emp.get("email"):
                existing.email = emp["email"]
            existing.status = emp.get("status", existing.status)
    db.commit()
    print(f"Synced {len(employees)} employees from TimeStation.")

    # 2. Set TimeStation employees as managers
    print("\nSetting up TimeStation managers:")
    for name in TIMESTATION_MANAGERS:
        emp = db.query(Employee).filter(Employee.name == name).first()
        if emp:
            emp.role = "manager"
            print(f"  ✓ Set {emp.name} as manager (PIN: {emp.pin})")
        else:
            print(f"  ✗ Not found in TimeStation: {name}")

    # 3. Create local-only accounts
    print("\nCreating local-only accounts:")
    for account in LOCAL_ACCOUNTS:
        # Check if already exists (by name or PIN)
        existing = db.query(Employee).filter(
            (Employee.name == account["name"]) | (Employee.pin == account["pin"])
        ).first()
        if existing:
            existing.role = account["role"]
            existing.email = account["email"]
            existing.title = account["title"]
            print(f"  ✓ Updated {existing.name} (PIN: {existing.pin}, role: {existing.role})")
        else:
            local_id = f"local_{hashlib.md5(account['name'].encode()).hexdigest()[:12]}"
            emp = Employee(
                timestation_id=local_id,
                name=account["name"],
                pin=account["pin"],
                email=account["email"],
                title=account["title"],
                role=account["role"],
                status="out",
                is_active=True,
            )
            db.add(emp)
            print(f"  ✓ Created {account['name']} (PIN: {account['pin']}, role: {account['role']})")

    db.commit()
    db.close()
    print("\nDone! Manager accounts ready:")
    print("  Margaret Montimerano - PIN: 2586")
    print("  Brandon Shampoe - PIN: 7111")
    print("  Marc Mancuso - PIN: 1001")
    print("  Nicole Mancuso - PIN: 1002")


if __name__ == "__main__":
    run()

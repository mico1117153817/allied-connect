"""Set one or more employees as managers by name.

Usage:
    cd backend
    source .venv/Scripts/activate  # Windows
    # or: source .venv/bin/activate  # Linux/Mac
    python -m scripts.set_manager "Carolyn Ward" "Andrew Cook"

You can also use their TimeStation employee IDs:
    python -m scripts.set_manager emp_ekj8x0q7p4
"""
import sys
from app.models.database import SessionLocal, engine, Base
from app.models.employee import Employee
from app.services.timestation import timestation
import asyncio


def set_managers(identifiers: list[str]):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # Sync employees from TimeStation first
    print("Syncing employees from TimeStation...")
    employees = asyncio.run(timestation.get_employees())
    for emp in employees:
        existing = db.query(Employee).filter(Employee.timestation_id == emp["employee_id"]).first()
        if not existing:
            db.add(Employee(
                timestation_id=emp["employee_id"],
                name=emp.get("name", ""),
                pin=emp.get("pin", ""),
                email=emp.get("email"),
                primary_department=emp.get("primary_department"),
                status=emp.get("status", "out"),
            ))
    db.commit()
    print(f"Synced {len(employees)} employees.")

    for identifier in identifiers:
        # Try matching by name or timestation_id
        emp = db.query(Employee).filter(
            (Employee.name == identifier) | (Employee.timestation_id == identifier)
        ).first()
        if emp:
            emp.role = "manager"
            print(f"  ✓ Set {emp.name} as manager")
        else:
            print(f"  ✗ Not found: {identifier}")

    db.commit()
    db.close()
    print("Done!")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    set_managers(sys.argv[1:])

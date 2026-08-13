import os
import asyncio
import hashlib
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.models.database import Base, engine, SessionLocal
from app.models.employee import Employee
from app.routers import auth, employee, time_off, manager, documents, settings as settings_router, compliance
from app.services.scheduler import start_scheduler
from app.services.settings_service import init_defaults
from app.services.timestation import timestation


# Managers to set up on first start
TIMESTATION_MANAGERS = ["Margaret Montimerano", "Brandon Shampoe"]
LOCAL_ACCOUNTS = [
    {"name": "Marc Mancuso", "pin": "1001", "email": "marcmancuso@alliedalliancegroupinc.com", "title": "President", "role": "super_admin"},
    {"name": "Nicole Mancuso", "pin": "1002", "email": "nicole@alliedalliancegroupinc.com", "title": "Vice President", "role": "super_admin"},
]


async def bootstrap_managers():
    """Sync employees from TimeStation and set up managers + local accounts on first start."""
    db = SessionLocal()
    try:
        # Check if already bootstrapped (any managers exist)
        existing_mgrs = db.query(Employee).filter(Employee.role == "manager").count()
        if existing_mgrs >= 4:
            return  # Already set up

        # Sync employees from TimeStation
        print("[bootstrap] Syncing employees from TimeStation...")
        employees = await timestation.get_employees()
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
                    title=emp.get("title"),
                    custom_employee_id=emp.get("custom_employee_id"),
                ))
            else:
                # Update from TimeStation but preserve role
                existing.name = emp.get("name", existing.name)
                existing.pin = emp.get("pin", existing.pin)
                if emp.get("email"):
                    existing.email = emp["email"]
                existing.status = emp.get("status", existing.status)
                existing.primary_department = emp.get("primary_department", existing.primary_department)
        db.commit()
        print(f"[bootstrap] Synced {len(employees)} employees")

        # Set TimeStation managers
        for name in TIMESTATION_MANAGERS:
            emp = db.query(Employee).filter(Employee.name == name).first()
            if emp:
                emp.role = "manager"
                print(f"[bootstrap] Set {emp.name} as manager")
            else:
                print(f"[bootstrap] WARNING: {name} not found in TimeStation")

        # Create local-only accounts
        for acct in LOCAL_ACCOUNTS:
            existing = db.query(Employee).filter(
                (Employee.name == acct["name"]) | (Employee.pin == acct["pin"])
            ).first()
            if existing:
                existing.role = acct.get("role", "manager")
                existing.email = acct["email"]
                existing.title = acct["title"]
                print(f"[bootstrap] Updated {existing.name} as {existing.role}")
            else:
                local_id = f"local_{hashlib.md5(acct['name'].encode()).hexdigest()[:12]}"
                db.add(Employee(
                    timestation_id=local_id,
                    name=acct["name"],
                    pin=acct["pin"],
                    email=acct["email"],
                    title=acct["title"],
                    role=acct.get("role", "manager"),
                    status="out",
                    is_active=True,
                ))
                print(f"[bootstrap] Created {acct['name']} as {acct.get('role', 'manager')}")

        db.commit()
        print("[bootstrap] Done — 4 managers ready")
    except Exception as e:
        print(f"[bootstrap] ERROR: {e}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Seed default settings
    db = SessionLocal()
    try:
        init_defaults(db)
    finally:
        db.close()
    # Bootstrap managers (async — syncs from TimeStation on first start)
    await bootstrap_managers()
    # Start background scheduler
    scheduler = start_scheduler()
    yield
    # Shutdown
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Allied Connect",
    description="Employee portal with TimeStation integration, time-off requests, "
    "calendar, pay adjustments, and document management.",
    version="0.3.0",
    lifespan=lifespan,
)

# CORS — allow the Render domain and custom domain
allowed_origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://allied-connect.onrender.com",
    "https://connect.alliedalliancegroupinc.com",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router)
app.include_router(employee.router)
app.include_router(time_off.router)
app.include_router(manager.router)
app.include_router(documents.router)
app.include_router(settings_router.router)
app.include_router(compliance.router)


# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "allied-connect"}


# Serve React build (production)
static_dir = os.environ.get("STATIC_DIR", "../frontend/dist")
if os.path.isdir(static_dir):
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=os.path.join(static_dir, "assets")), name="assets")

    # Catch-all: serve index.html for any non-API route (SPA routing)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str, request: Request):
        # Don't intercept API routes
        if full_path.startswith("api/") or full_path.startswith("auth/"):
            raise HTTPException(404, "Not found")

        # Try to serve a real static file (e.g. allied-logo.jpg, favicon)
        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        # Otherwise return index.html for client-side routing
        index_path = os.path.join(static_dir, "index.html")
        return FileResponse(index_path)

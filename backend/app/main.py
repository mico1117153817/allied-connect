import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.database import Base, engine, SessionLocal
from app.routers import auth, employee, time_off, manager, documents, settings as settings_router
from app.services.scheduler import start_scheduler
from app.services.settings_service import init_defaults


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
    # Start background scheduler
    scheduler = start_scheduler()
    yield
    # Shutdown
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Allied Connect",
    description="Employee portal with TimeStation integration, time-off requests, "
    "calendar, pay adjustments, and document management.",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS
allowed_origins = [
    settings.FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
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


# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "allied-connect"}


# Serve React build (production)
static_dir = os.environ.get("STATIC_DIR", "../frontend/dist")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

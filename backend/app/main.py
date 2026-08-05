import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models.database import Base, engine
from app.routers import auth, employee, time_off, manager, documents
from app.services.scheduler import start_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    Base.metadata.create_all(bind=engine)
    # Start background scheduler
    scheduler = start_scheduler()
    yield
    # Shutdown
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="Employee Portal",
    description="Employee portal with TimeStation integration, time-off requests, "
    "calendar, pay adjustments, and document management.",
    version="0.1.0",
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


# Health check
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "employee-portal"}


# Serve React build (production)
static_dir = os.environ.get("STATIC_DIR", "../frontend/dist")
if os.path.isdir(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

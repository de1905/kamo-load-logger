"""KAMO Load Logger - Main FastAPI application."""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import __version__
from app.config import get_settings
from app.database import init_db, get_db, LoadData, SubstationSnapshot, ImportLog, Cooperative, Setting, now_central
from app.scheduler import start_scheduler, stop_scheduler, import_job, get_next_run_time
from app.services.importer import DataImporter
from app.routers import status_router, load_router, substations_router, export_router, backups_router

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info(f"Starting KAMO Load Logger v{__version__}")
    init_db()
    logger.info("Database initialized")

    # Run initial import
    logger.info("Running initial import...")
    await import_job()

    # Start scheduler
    start_scheduler()

    yield

    # Shutdown
    stop_scheduler()
    logger.info("KAMO Load Logger stopped")


app = FastAPI(
    title="KAMO Load Logger",
    description="Historical load data collection service for KAMO Power cooperatives",
    version=__version__,
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Include API routers
app.include_router(status_router, prefix="/api", tags=["Status"])
app.include_router(load_router, prefix="/api", tags=["Load Data"])
app.include_router(substations_router, prefix="/api", tags=["Substations"])
app.include_router(export_router, prefix="/api", tags=["Export"])
app.include_router(backups_router, prefix="/api", tags=["Backups"])


# --- Web Dashboard Routes ---

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    """Main dashboard page."""
    importer = DataImporter()

    # Get stats
    last_import = importer.get_last_import(db)
    last_success = importer.get_last_successful_import(db)
    stats_24h = importer.get_import_stats(db, hours=24)
    stats_7d = importer.get_import_stats(db, hours=168)

    # Database stats
    load_count = db.query(func.count(LoadData.id)).scalar() or 0
    sub_count = db.query(func.count(SubstationSnapshot.id)).scalar() or 0
    coop_count = db.query(func.count(Cooperative.id)).scalar() or 0

    oldest = db.query(func.min(LoadData.timestamp)).scalar()
    newest = db.query(func.max(LoadData.timestamp)).scalar()

    # Database file size
    db_path = settings.database_url.replace("sqlite:///", "")
    db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0

    # Recent imports
    recent_imports = (
        db.query(ImportLog)
        .order_by(ImportLog.started_at.desc())
        .limit(10)
        .all()
    )

    # Next scheduled run
    next_run = get_next_run_time()

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "version": __version__,
            "last_import": last_import,
            "last_success": last_success,
            "stats_24h": stats_24h,
            "stats_7d": stats_7d,
            "load_count": load_count,
            "sub_count": sub_count,
            "coop_count": coop_count,
            "oldest_record": oldest,
            "newest_record": newest,
            "db_size_mb": db_size_mb,
            "recent_imports": recent_imports,
            "next_run": next_run,
            "notifications_enabled": settings.notifications_enabled,
            "poll_interval": settings.poll_interval_minutes,
            "now": now_central(),
        },
    )


@app.get("/inspector", response_class=HTMLResponse)
async def data_inspector(request: Request, db: Session = Depends(get_db)):
    """Data inspector page - view load data like the iOS app."""
    cooperatives = db.query(Cooperative).order_by(Cooperative.id).all()

    return templates.TemplateResponse(
        "inspector.html",
        {
            "request": request,
            "version": __version__,
            "cooperatives": cooperatives,
            "poll_interval": settings.poll_interval_minutes,
        },
    )


@app.get("/tables", response_class=HTMLResponse)
async def database_tables(request: Request, db: Session = Depends(get_db)):
    """Database tables inspector page."""
    tables = [
        {
            "name": "cooperatives",
            "description": "Cached cooperative/area list from KAMO API",
            "count": db.query(func.count(Cooperative.id)).scalar() or 0,
        },
        {
            "name": "load_data",
            "description": "Historical hourly load data",
            "count": db.query(func.count(LoadData.id)).scalar() or 0,
        },
        {
            "name": "substation_snapshots",
            "description": "Point-in-time substation snapshots",
            "count": db.query(func.count(SubstationSnapshot.id)).scalar() or 0,
        },
        {
            "name": "import_log",
            "description": "Import operation history",
            "count": db.query(func.count(ImportLog.id)).scalar() or 0,
        },
    ]

    return templates.TemplateResponse(
        "tables.html",
        {
            "request": request,
            "version": __version__,
            "tables": tables,
            "poll_interval": settings.poll_interval_minutes,
        },
    )


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    """Settings configuration page."""
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "version": __version__,
            "poll_interval": settings.poll_interval_minutes,
        },
    )


@app.get("/history", response_class=HTMLResponse)
async def import_history(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
):
    """Import history page."""
    per_page = 50
    offset = (page - 1) * per_page

    total = db.query(func.count(ImportLog.id)).scalar() or 0
    total_pages = (total + per_page - 1) // per_page

    imports = (
        db.query(ImportLog)
        .order_by(ImportLog.started_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "version": __version__,
            "imports": imports,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "now": now_central(),
        },
    )


@app.get("/backups", response_class=HTMLResponse)
async def backups_page(request: Request):
    """Backup management page."""
    return templates.TemplateResponse(
        "backups.html",
        {
            "request": request,
            "version": __version__,
            "poll_interval": settings.poll_interval_minutes,
        },
    )

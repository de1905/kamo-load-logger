"""Status and health endpoints."""

import os
import time
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import func

from app import __version__
from app.config import get_settings
from app.database import get_db, Cooperative, LoadData, SubstationSnapshot, ImportLog
from app.models import (
    HealthResponse,
    SystemStatus,
    DatabaseStats,
    ImportLogEntry,
    CooperativeResponse,
)
from app.services.importer import DataImporter
from app.services.settings import get_settings_service, CONFIGURABLE_SETTINGS
from app.services.notifications import NotificationService
from app.scheduler import trigger_manual_import, get_next_run_time, restart_scheduler

router = APIRouter()

# Timezone
CENTRAL_TZ = ZoneInfo("America/Chicago")

# Track startup time
_startup_time = time.time()


def now_central():
    """Get current time in Central timezone."""
    return datetime.now(CENTRAL_TZ).replace(tzinfo=None)


def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key for protected endpoints."""
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=now_central(),
        version=__version__,
    )


@router.get("/status", response_model=SystemStatus)
async def get_status(db: Session = Depends(get_db)):
    """Get detailed system status."""
    settings = get_settings()
    importer = DataImporter()

    # Get import stats
    last_import = importer.get_last_import(db)
    last_success = importer.get_last_successful_import(db)
    stats_24h = importer.get_import_stats(db, hours=24)

    # Database stats
    db_path = settings.database_url.replace("sqlite:///", "")
    db_size = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0

    load_count = db.query(func.count(LoadData.id)).scalar() or 0
    sub_count = db.query(func.count(SubstationSnapshot.id)).scalar() or 0
    coop_count = db.query(func.count(Cooperative.id)).scalar() or 0

    oldest = db.query(func.min(LoadData.timestamp)).scalar()
    newest = db.query(func.max(LoadData.timestamp)).scalar()

    # Determine overall status
    status = "healthy"
    if last_import and last_import.status == "failed":
        status = "degraded"
    if stats_24h["success_rate"] < 50:
        status = "unhealthy"

    return SystemStatus(
        status=status,
        uptime_seconds=time.time() - _startup_time,
        last_import=ImportLogEntry.model_validate(last_import) if last_import else None,
        last_successful_import=last_success.completed_at if last_success else None,
        imports_last_24h=stats_24h["total"],
        success_rate_24h=stats_24h["success_rate"],
        database_stats=DatabaseStats(
            total_load_records=load_count,
            total_substation_records=sub_count,
            total_cooperatives=coop_count,
            database_size_mb=round(db_size, 2),
            oldest_record=oldest,
            newest_record=newest,
        ),
        notifications_enabled=settings.notifications_enabled,
        poll_interval_minutes=settings.poll_interval_minutes,
    )


@router.get("/cooperatives", response_model=List[CooperativeResponse])
async def get_cooperatives(db: Session = Depends(get_db)):
    """Get list of all cooperatives."""
    cooperatives = db.query(Cooperative).order_by(Cooperative.name).all()
    return [CooperativeResponse.model_validate(c) for c in cooperatives]


@router.get("/imports", response_model=List[ImportLogEntry])
async def get_import_history(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Get import history."""
    imports = (
        db.query(ImportLog)
        .order_by(ImportLog.started_at.desc())
        .limit(limit)
        .all()
    )
    return [ImportLogEntry.model_validate(i) for i in imports]


@router.delete("/imports/{import_id}")
async def delete_import(
    import_id: int,
    db: Session = Depends(get_db),
):
    """Delete an import log entry."""
    import_log = db.query(ImportLog).filter(ImportLog.id == import_id).first()
    if not import_log:
        raise HTTPException(status_code=404, detail=f"Import {import_id} not found")

    db.delete(import_log)
    db.commit()
    return {"success": True, "deleted_id": import_id}


@router.post("/import/trigger")
async def manual_import(
    authenticated: bool = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """Trigger a manual import (requires API key)."""
    result = await trigger_manual_import()
    return {
        "success": result.success,
        "load_imported": result.load_imported,
        "load_skipped": result.load_skipped,
        "substations_imported": result.substations_imported,
        "substations_skipped": result.substations_skipped,
        "duration_seconds": result.duration_seconds,
        "error": result.error,
    }


@router.get("/next-import")
async def get_next_import():
    """Get the next scheduled import time."""
    next_run = get_next_run_time()
    return {
        "next_import": next_run.isoformat() if next_run else None,
    }


@router.get("/tables")
async def get_tables(db: Session = Depends(get_db)):
    """Get list of database tables with row counts."""
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
    return {"tables": tables}


@router.get("/tables/{table_name}")
async def get_table_data(
    table_name: str,
    limit: int = 100,
    offset: int = 0,
    sort_by: str = None,
    sort_order: str = "desc",
    db: Session = Depends(get_db),
):
    """Get data from a specific table with pagination and sorting."""
    table_map = {
        "cooperatives": Cooperative,
        "load_data": LoadData,
        "substation_snapshots": SubstationSnapshot,
        "import_log": ImportLog,
    }

    if table_name not in table_map:
        raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found")

    model = table_map[table_name]
    total = db.query(func.count(model.id)).scalar() or 0

    # Get column names
    columns = [c.name for c in model.__table__.columns]

    # Determine sort column and order
    if sort_by and sort_by in columns:
        sort_column = getattr(model, sort_by)
        if sort_order == "asc":
            query = db.query(model).order_by(sort_column.asc())
        else:
            query = db.query(model).order_by(sort_column.desc())
    elif table_name == "cooperatives":
        query = db.query(model).order_by(model.id)
    elif table_name == "load_data":
        query = db.query(model).order_by(model.timestamp.desc())
    elif table_name == "substation_snapshots":
        query = db.query(model).order_by(model.snapshot_time.desc())
    else:
        query = db.query(model).order_by(model.id.desc())

    rows = query.offset(offset).limit(limit).all()

    # Convert to list of dicts
    data = []
    for row in rows:
        row_dict = {}
        for col in columns:
            val = getattr(row, col)
            # Convert datetime to string for JSON serialization
            if isinstance(val, datetime):
                val = val.isoformat()
            row_dict[col] = val
        data.append(row_dict)

    return {
        "table": table_name,
        "columns": columns,
        "data": data,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/settings")
async def get_all_settings(db: Session = Depends(get_db)):
    """Get all configurable settings."""
    service = get_settings_service(db)
    return {
        "settings": service.get_all(),
    }


@router.get("/settings/{key}")
async def get_setting(key: str, db: Session = Depends(get_db)):
    """Get a specific setting value."""
    service = get_settings_service(db)
    value = service.get(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"key": key, "value": value}


@router.put("/settings/{key}")
async def update_setting(
    key: str,
    body: dict,
    db: Session = Depends(get_db),
):
    """Update a setting value."""
    if "value" not in body:
        raise HTTPException(status_code=400, detail="Missing 'value' in request body")

    service = get_settings_service(db)
    old_value = service.get(key)
    success = service.set(key, body["value"])

    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to update setting '{key}'")

    # Restart scheduler if poll interval changed
    if key == "poll_interval_minutes" and old_value != body["value"]:
        restart_scheduler()

    return {"key": key, "value": body["value"], "success": True}


@router.post("/settings")
async def update_multiple_settings(
    body: dict,
    db: Session = Depends(get_db),
):
    """Update multiple settings at once."""
    if "settings" not in body:
        raise HTTPException(status_code=400, detail="Missing 'settings' in request body")

    service = get_settings_service(db)
    old_poll_interval = service.get("poll_interval_minutes")

    results = service.set_multiple(body["settings"])

    # Restart scheduler if poll interval changed
    new_poll_interval = service.get("poll_interval_minutes")
    if old_poll_interval != new_poll_interval:
        restart_scheduler()

    return {"results": results}


@router.delete("/settings/{key}")
async def reset_setting(key: str, db: Session = Depends(get_db)):
    """Reset a setting to its default value."""
    service = get_settings_service(db)
    old_value = service.get(key)
    success = service.reset(key)

    if not success:
        raise HTTPException(status_code=400, detail=f"Failed to reset setting '{key}'")

    # Restart scheduler if poll interval was reset
    if key == "poll_interval_minutes":
        restart_scheduler()

    return {"key": key, "reset": True}


@router.post("/test-email")
async def send_test_email():
    """Send a test email to verify SMTP configuration."""
    service = NotificationService()
    success, error = await service.send_test_email()

    if success:
        return {"success": True, "message": "Test email sent successfully"}
    else:
        raise HTTPException(
            status_code=400,
            detail=error or "Failed to send test email"
        )

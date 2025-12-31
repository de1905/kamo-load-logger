"""Data export endpoints."""

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, Cooperative, LoadData, SubstationSnapshot

router = APIRouter(prefix="/export", tags=["Export"])


def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key for protected endpoints."""
    settings = get_settings()
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def get_cooperative_or_404(db: Session, area_id: int) -> Cooperative:
    """Get cooperative by ID or raise 404."""
    coop = db.query(Cooperative).filter(Cooperative.id == area_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail=f"Area {area_id} not found")
    return coop


@router.get("/load/{area_id}")
async def export_load_data(
    area_id: int,
    format: str = Query("csv", regex="^(csv|json)$"),
    start: Optional[datetime] = Query(None, description="Start datetime"),
    end: Optional[datetime] = Query(None, description="End datetime"),
    days: Optional[int] = Query(None, description="Last N days"),
    authenticated: bool = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Export load data for an area (requires API key).

    Returns CSV or JSON file.
    """
    coop = get_cooperative_or_404(db, area_id)

    query = db.query(LoadData).filter(LoadData.area_id == area_id)

    # Apply filters
    if days:
        start = datetime.utcnow() - timedelta(days=days)
    if start:
        query = query.filter(LoadData.timestamp >= start)
    if end:
        query = query.filter(LoadData.timestamp <= end)

    data = query.order_by(LoadData.timestamp).all()

    if not data:
        raise HTTPException(status_code=404, detail="No data to export")

    filename = f"load_{coop.abbreviation}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "load_kw"])
        for row in data:
            writer.writerow([row.timestamp.isoformat(), row.load_kw])

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )
    else:
        export_data = {
            "area_id": coop.id,
            "area_name": coop.name,
            "exported_at": datetime.utcnow().isoformat(),
            "record_count": len(data),
            "data": [
                {"timestamp": row.timestamp.isoformat(), "load_kw": row.load_kw}
                for row in data
            ],
        }

        return StreamingResponse(
            iter([json.dumps(export_data, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}.json"},
        )


@router.get("/substations/{area_id}")
async def export_substation_data(
    area_id: int,
    format: str = Query("csv", regex="^(csv|json)$"),
    start: Optional[datetime] = Query(None, description="Start datetime"),
    end: Optional[datetime] = Query(None, description="End datetime"),
    days: Optional[int] = Query(None, description="Last N days"),
    authenticated: bool = Depends(verify_api_key),
    db: Session = Depends(get_db),
):
    """
    Export substation data for an area (requires API key).

    Returns CSV or JSON file.
    """
    coop = get_cooperative_or_404(db, area_id)

    query = db.query(SubstationSnapshot).filter(SubstationSnapshot.area_id == area_id)

    # Apply filters
    if days:
        start = datetime.utcnow() - timedelta(days=days)
    if start:
        query = query.filter(SubstationSnapshot.snapshot_time >= start)
    if end:
        query = query.filter(SubstationSnapshot.snapshot_time <= end)

    data = query.order_by(
        SubstationSnapshot.snapshot_time, SubstationSnapshot.substation_name
    ).all()

    if not data:
        raise HTTPException(status_code=404, detail="No data to export")

    filename = f"substations_{coop.abbreviation}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["snapshot_time", "substation_name", "kw", "kvar", "pf", "quality", "quality_now"])
        for row in data:
            writer.writerow([
                row.snapshot_time.isoformat(),
                row.substation_name,
                row.kw,
                row.kvar,
                row.pf,
                row.quality,
                row.quality_now,
            ])

        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}.csv"},
        )
    else:
        export_data = {
            "area_id": coop.id,
            "area_name": coop.name,
            "exported_at": datetime.utcnow().isoformat(),
            "record_count": len(data),
            "data": [
                {
                    "snapshot_time": row.snapshot_time.isoformat(),
                    "substation_name": row.substation_name,
                    "kw": row.kw,
                    "kvar": row.kvar,
                    "pf": row.pf,
                    "quality": row.quality,
                    "quality_now": row.quality_now,
                }
                for row in data
            ],
        }

        return StreamingResponse(
            iter([json.dumps(export_data, indent=2)]),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}.json"},
        )

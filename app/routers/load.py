"""Load data API endpoints."""

from datetime import datetime, timedelta
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db, Cooperative, LoadData

CENTRAL_TZ = ZoneInfo("America/Chicago")


def now_central():
    """Get current time in Central timezone."""
    return datetime.now(CENTRAL_TZ).replace(tzinfo=None)


from app.models import (
    LoadDataResponse,
    LoadDataPoint,
    CurrentLoadResponse,
    PeakLoadResponse,
)

router = APIRouter(prefix="/load", tags=["Load Data"])


def get_cooperative_or_404(db: Session, area_id: int) -> Cooperative:
    """Get cooperative by ID or raise 404."""
    coop = db.query(Cooperative).filter(Cooperative.id == area_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail=f"Area {area_id} not found")
    return coop


@router.get("/current/{area_id}", response_model=CurrentLoadResponse)
async def get_current_load(area_id: int, db: Session = Depends(get_db)):
    """Get the most recent load value for an area."""
    coop = get_cooperative_or_404(db, area_id)

    latest = (
        db.query(LoadData)
        .filter(LoadData.area_id == area_id)
        .order_by(desc(LoadData.timestamp))
        .first()
    )

    if not latest:
        raise HTTPException(status_code=404, detail="No load data available")

    return CurrentLoadResponse(
        area_id=coop.id,
        area_name=coop.name,
        load_kw=latest.load_kw,
        timestamp=latest.timestamp,
    )


@router.get("/history/{area_id}", response_model=LoadDataResponse)
async def get_load_history(
    area_id: int,
    start: Optional[datetime] = Query(None, description="Start datetime (ISO format)"),
    end: Optional[datetime] = Query(None, description="End datetime (ISO format)"),
    hours: Optional[int] = Query(None, description="Last N hours (alternative to start/end)"),
    limit: int = Query(1000, le=10000, description="Maximum records to return"),
    db: Session = Depends(get_db),
):
    """
    Get historical load data for an area.

    Either use start/end datetime range, or use 'hours' for last N hours.
    """
    coop = get_cooperative_or_404(db, area_id)

    query = db.query(LoadData).filter(LoadData.area_id == area_id)

    # Apply time filters
    if hours:
        start = now_central() - timedelta(hours=hours)
        query = query.filter(LoadData.timestamp >= start)
    else:
        if start:
            query = query.filter(LoadData.timestamp >= start)
        if end:
            query = query.filter(LoadData.timestamp <= end)

    # Order and limit
    data = (
        query
        .order_by(LoadData.timestamp)
        .limit(limit)
        .all()
    )

    return LoadDataResponse(
        area_id=coop.id,
        area_name=coop.name,
        data=[LoadDataPoint(timestamp=d.timestamp, load_kw=d.load_kw) for d in data],
        count=len(data),
    )


@router.get("/peaks/{area_id}", response_model=List[PeakLoadResponse])
async def get_peak_loads(
    area_id: int,
    period: str = Query("day", regex="^(day|month|year)$", description="Period: day, month, or year"),
    limit: int = Query(10, le=100, description="Number of peaks to return"),
    db: Session = Depends(get_db),
):
    """Get peak load records for an area by period."""
    coop = get_cooperative_or_404(db, area_id)

    # Group by period and find max
    if period == "day":
        date_trunc = func.date(LoadData.timestamp)
    elif period == "month":
        date_trunc = func.strftime("%Y-%m", LoadData.timestamp)
    else:  # year
        date_trunc = func.strftime("%Y", LoadData.timestamp)

    # Subquery to get max per period
    subquery = (
        db.query(
            date_trunc.label("period"),
            func.max(LoadData.load_kw).label("max_load"),
        )
        .filter(LoadData.area_id == area_id)
        .group_by(date_trunc)
        .subquery()
    )

    # Join back to get the full record with timestamp
    results = (
        db.query(LoadData)
        .join(
            subquery,
            (date_trunc == subquery.c.period) & (LoadData.load_kw == subquery.c.max_load),
        )
        .filter(LoadData.area_id == area_id)
        .order_by(desc(LoadData.load_kw))
        .limit(limit)
        .all()
    )

    return [
        PeakLoadResponse(
            area_id=coop.id,
            area_name=coop.name,
            peak_kw=r.load_kw,
            timestamp=r.timestamp,
            period=period,
        )
        for r in results
    ]


@router.get("/stats/{area_id}")
async def get_load_stats(
    area_id: int,
    hours: int = Query(24, description="Calculate stats for last N hours"),
    db: Session = Depends(get_db),
):
    """Get load statistics for an area."""
    coop = get_cooperative_or_404(db, area_id)

    cutoff = now_central() - timedelta(hours=hours)

    stats = (
        db.query(
            func.count(LoadData.id).label("count"),
            func.min(LoadData.load_kw).label("min"),
            func.max(LoadData.load_kw).label("max"),
            func.avg(LoadData.load_kw).label("avg"),
        )
        .filter(LoadData.area_id == area_id, LoadData.timestamp >= cutoff)
        .first()
    )

    return {
        "area_id": coop.id,
        "area_name": coop.name,
        "period_hours": hours,
        "record_count": stats.count or 0,
        "min_kw": round(stats.min, 2) if stats.min else None,
        "max_kw": round(stats.max, 2) if stats.max else None,
        "avg_kw": round(stats.avg, 2) if stats.avg else None,
    }

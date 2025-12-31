"""Substation data API endpoints."""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, distinct

from app.database import get_db, Cooperative, SubstationSnapshot
from app.models import SubstationSnapshotResponse, SubstationDataPoint

router = APIRouter(prefix="/substations", tags=["Substations"])


def get_cooperative_or_404(db: Session, area_id: int) -> Cooperative:
    """Get cooperative by ID or raise 404."""
    coop = db.query(Cooperative).filter(Cooperative.id == area_id).first()
    if not coop:
        raise HTTPException(status_code=404, detail=f"Area {area_id} not found")
    return coop


@router.get("/current/{area_id}", response_model=SubstationSnapshotResponse)
async def get_current_substations(area_id: int, db: Session = Depends(get_db)):
    """Get the most recent substation snapshot for an area."""
    coop = get_cooperative_or_404(db, area_id)

    # Get the latest snapshot time
    latest_time = (
        db.query(func.max(SubstationSnapshot.snapshot_time))
        .filter(SubstationSnapshot.area_id == area_id)
        .scalar()
    )

    if not latest_time:
        raise HTTPException(status_code=404, detail="No substation data available")

    # Get all substations at that time
    substations = (
        db.query(SubstationSnapshot)
        .filter(
            SubstationSnapshot.area_id == area_id,
            SubstationSnapshot.snapshot_time == latest_time,
        )
        .order_by(SubstationSnapshot.substation_name)
        .all()
    )

    return SubstationSnapshotResponse(
        area_id=coop.id,
        area_name=coop.name,
        snapshot_time=latest_time,
        substations=[
            SubstationDataPoint(
                substation_name=s.substation_name,
                kw=s.kw,
                kvar=s.kvar,
                pf=s.pf,
                quality=s.quality,
                quality_now=s.quality_now,
            )
            for s in substations
        ],
    )


@router.get("/history/{area_id}")
async def get_substation_history(
    area_id: int,
    substation: Optional[str] = Query(None, description="Filter by substation name"),
    start: Optional[datetime] = Query(None, description="Start datetime"),
    end: Optional[datetime] = Query(None, description="End datetime"),
    hours: Optional[int] = Query(None, description="Last N hours"),
    limit: int = Query(100, le=1000, description="Maximum snapshots"),
    db: Session = Depends(get_db),
):
    """
    Get historical substation data.

    Can filter by specific substation name and time range.
    """
    coop = get_cooperative_or_404(db, area_id)

    query = db.query(SubstationSnapshot).filter(SubstationSnapshot.area_id == area_id)

    # Filter by substation
    if substation:
        query = query.filter(SubstationSnapshot.substation_name == substation)

    # Time filters
    if hours:
        start = datetime.utcnow() - timedelta(hours=hours)
        query = query.filter(SubstationSnapshot.snapshot_time >= start)
    else:
        if start:
            query = query.filter(SubstationSnapshot.snapshot_time >= start)
        if end:
            query = query.filter(SubstationSnapshot.snapshot_time <= end)

    # Get unique snapshot times
    snapshot_times = (
        query
        .with_entities(SubstationSnapshot.snapshot_time)
        .distinct()
        .order_by(desc(SubstationSnapshot.snapshot_time))
        .limit(limit)
        .all()
    )

    # Build response
    snapshots = []
    for (snapshot_time,) in snapshot_times:
        subs_query = (
            db.query(SubstationSnapshot)
            .filter(
                SubstationSnapshot.area_id == area_id,
                SubstationSnapshot.snapshot_time == snapshot_time,
            )
        )
        if substation:
            subs_query = subs_query.filter(SubstationSnapshot.substation_name == substation)

        subs = subs_query.order_by(SubstationSnapshot.substation_name).all()

        snapshots.append({
            "snapshot_time": snapshot_time.isoformat(),
            "substations": [
                {
                    "name": s.substation_name,
                    "kw": s.kw,
                    "kvar": s.kvar,
                    "pf": s.pf,
                }
                for s in subs
            ],
        })

    return {
        "area_id": coop.id,
        "area_name": coop.name,
        "snapshots": snapshots,
        "count": len(snapshots),
    }


@router.get("/list/{area_id}")
async def list_substations(area_id: int, db: Session = Depends(get_db)):
    """Get list of all substations for an area."""
    coop = get_cooperative_or_404(db, area_id)

    substations = (
        db.query(distinct(SubstationSnapshot.substation_name))
        .filter(SubstationSnapshot.area_id == area_id)
        .order_by(SubstationSnapshot.substation_name)
        .all()
    )

    return {
        "area_id": coop.id,
        "area_name": coop.name,
        "substations": [s[0] for s in substations],
        "count": len(substations),
    }


@router.get("/stats/{area_id}/{substation_name}")
async def get_substation_stats(
    area_id: int,
    substation_name: str,
    hours: int = Query(24, description="Calculate stats for last N hours"),
    db: Session = Depends(get_db),
):
    """Get statistics for a specific substation."""
    coop = get_cooperative_or_404(db, area_id)

    cutoff = datetime.utcnow() - timedelta(hours=hours)

    stats = (
        db.query(
            func.count(SubstationSnapshot.id).label("count"),
            func.min(SubstationSnapshot.kw).label("min_kw"),
            func.max(SubstationSnapshot.kw).label("max_kw"),
            func.avg(SubstationSnapshot.kw).label("avg_kw"),
            func.avg(SubstationSnapshot.pf).label("avg_pf"),
        )
        .filter(
            SubstationSnapshot.area_id == area_id,
            SubstationSnapshot.substation_name == substation_name,
            SubstationSnapshot.snapshot_time >= cutoff,
        )
        .first()
    )

    if not stats.count:
        raise HTTPException(
            status_code=404,
            detail=f"No data for substation '{substation_name}'",
        )

    return {
        "area_id": coop.id,
        "area_name": coop.name,
        "substation_name": substation_name,
        "period_hours": hours,
        "snapshot_count": stats.count,
        "min_kw": round(stats.min_kw, 2) if stats.min_kw else None,
        "max_kw": round(stats.max_kw, 2) if stats.max_kw else None,
        "avg_kw": round(stats.avg_kw, 2) if stats.avg_kw else None,
        "avg_pf": round(stats.avg_pf, 3) if stats.avg_pf else None,
    }

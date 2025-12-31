"""Pydantic models for API requests and responses."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# --- Cooperative Models ---

class CooperativeResponse(BaseModel):
    """Cooperative data response."""
    id: int
    name: str
    abbreviation: str
    is_aggregate: bool

    class Config:
        from_attributes = True


# --- Load Data Models ---

class LoadDataPoint(BaseModel):
    """Single load data point."""
    timestamp: datetime
    load_kw: float

    class Config:
        from_attributes = True


class LoadDataResponse(BaseModel):
    """Load data response with metadata."""
    area_id: int
    area_name: str
    data: List[LoadDataPoint]
    count: int


class CurrentLoadResponse(BaseModel):
    """Current load response."""
    area_id: int
    area_name: str
    load_kw: float
    timestamp: datetime


class PeakLoadResponse(BaseModel):
    """Peak load record."""
    area_id: int
    area_name: str
    peak_kw: float
    timestamp: datetime
    period: str  # day, month, year


# --- Substation Models ---

class SubstationDataPoint(BaseModel):
    """Substation snapshot data."""
    substation_name: str
    kw: float
    kvar: float
    pf: float
    quality: Optional[bool]
    quality_now: Optional[bool]

    class Config:
        from_attributes = True


class SubstationSnapshotResponse(BaseModel):
    """Substation snapshot response."""
    area_id: int
    area_name: str
    snapshot_time: datetime
    substations: List[SubstationDataPoint]


# --- Status Models ---

class ImportLogEntry(BaseModel):
    """Import log entry."""
    id: int
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    load_records_imported: int
    load_records_skipped: int
    substation_records_imported: int
    substation_records_skipped: int
    error_message: Optional[str]
    duration_seconds: Optional[float]

    class Config:
        from_attributes = True


class DatabaseStats(BaseModel):
    """Database statistics."""
    total_load_records: int
    total_substation_records: int
    total_cooperatives: int
    database_size_mb: float
    oldest_record: Optional[datetime]
    newest_record: Optional[datetime]


class SystemStatus(BaseModel):
    """System status response."""
    status: str  # healthy, degraded, unhealthy
    uptime_seconds: float
    last_import: Optional[ImportLogEntry]
    last_successful_import: Optional[datetime]
    imports_last_24h: int
    success_rate_24h: float
    database_stats: DatabaseStats
    notifications_enabled: bool
    poll_interval_minutes: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: datetime
    version: str


# --- KAMO API Models (for parsing responses) ---

class KAMOCooperative(BaseModel):
    """Cooperative from KAMO API."""
    id: int
    name: str
    abrev: str
    selected: bool


class KAMOChartSeries(BaseModel):
    """Chart series from KAMO API."""
    data: List[Optional[float]]
    label: str


class KAMOAreaGridResponse(BaseModel):
    """Response from /api/areagrid endpoint."""
    Id: int
    chartLineData: List[KAMOChartSeries]
    lineChartLabels: List[str]


class KAMOSubstation(BaseModel):
    """Substation from KAMO API."""
    name: str
    kw: float
    kvar: float
    pf: float
    quality: bool
    qualityNow: bool


class KAMOAreaLoadTableResponse(BaseModel):
    """Response from /api/arealoadtable endpoint."""
    Id: int
    areaLoadData: List[KAMOSubstation]

"""Database setup and SQLAlchemy models."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    Boolean,
    DateTime,
    Text,
    Index,
    UniqueConstraint,
    ForeignKey,
    event,
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.pool import StaticPool

from app.config import get_settings

Base = declarative_base()

# Central timezone for all timestamps
CENTRAL_TZ = ZoneInfo("America/Chicago")


def now_central():
    """Get current time in Central timezone (naive datetime for SQLite)."""
    return datetime.now(CENTRAL_TZ).replace(tzinfo=None)


class Cooperative(Base):
    """Cooperative/area cached from KAMO API."""

    __tablename__ = "cooperatives"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    abbreviation = Column(String(10), nullable=False)
    is_aggregate = Column(Boolean, default=False)
    updated_at = Column(DateTime, default=now_central, onupdate=now_central)

    # Relationships
    load_data = relationship("LoadData", back_populates="cooperative")
    substation_snapshots = relationship("SubstationSnapshot", back_populates="cooperative")


class LoadData(Base):
    """Historical actual load data."""

    __tablename__ = "load_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    area_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)
    load_kw = Column(Float, nullable=False)
    created_at = Column(DateTime, default=now_central)

    # Relationships
    cooperative = relationship("Cooperative", back_populates="load_data")

    __table_args__ = (
        UniqueConstraint("area_id", "timestamp", name="uq_load_data_area_timestamp"),
        Index("idx_load_data_area_time", "area_id", "timestamp"),
        Index("idx_load_data_timestamp", "timestamp"),
    )


class SubstationSnapshot(Base):
    """Point-in-time substation data snapshots."""

    __tablename__ = "substation_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    area_id = Column(Integer, ForeignKey("cooperatives.id"), nullable=False)
    snapshot_time = Column(DateTime, nullable=False)
    substation_name = Column(String(255), nullable=False)
    kw = Column(Float, nullable=False)
    kvar = Column(Float, nullable=False)
    pf = Column(Float, nullable=False)
    quality = Column(Boolean)
    quality_now = Column(Boolean)
    created_at = Column(DateTime, default=now_central)

    # Relationships
    cooperative = relationship("Cooperative", back_populates="substation_snapshots")

    __table_args__ = (
        UniqueConstraint(
            "area_id", "snapshot_time", "substation_name",
            name="uq_substation_snapshot"
        ),
        Index("idx_substation_area_time", "area_id", "snapshot_time"),
    )


class ImportLog(Base):
    """Log of import operations."""

    __tablename__ = "import_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, nullable=False, default=now_central)
    completed_at = Column(DateTime)
    status = Column(String(20), nullable=False, default="running")  # running, success, failed
    load_records_imported = Column(Integer, default=0)
    load_records_skipped = Column(Integer, default=0)
    substation_records_imported = Column(Integer, default=0)
    substation_records_skipped = Column(Integer, default=0)
    error_message = Column(Text)
    duration_seconds = Column(Float)

    __table_args__ = (
        Index("idx_import_log_started", "started_at"),
    )


# Database engine and session
_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.database_url

        # Ensure data directory exists
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(db_path) if os.path.dirname(db_path) else ".", exist_ok=True)

        # SQLite-specific settings
        if "sqlite" in db_url:
            _engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
            # Enable WAL mode for better concurrent access
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
        else:
            _engine = create_engine(db_url)

    return _engine


def get_session_local():
    """Get session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db():
    """Dependency for getting database session."""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

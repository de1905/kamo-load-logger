"""Data import service with deduplication."""

import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from zoneinfo import ZoneInfo

# Central timezone for all timestamps
CENTRAL_TZ = ZoneInfo("America/Chicago")


def now_central():
    """Get current time in Central timezone (naive datetime for SQLite)."""
    return datetime.now(CENTRAL_TZ).replace(tzinfo=None)

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy import func

from app.database import (
    Cooperative,
    LoadData,
    SubstationSnapshot,
    ImportLog,
    get_session_local,
)
from app.services.kamo_client import KAMOClient
from app.services.notifications import NotificationService

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of an import operation."""
    success: bool
    load_imported: int = 0
    load_skipped: int = 0
    substations_imported: int = 0
    substations_skipped: int = 0
    error: Optional[str] = None
    duration_seconds: float = 0.0


class DataImporter:
    """Imports data from KAMO API with deduplication."""

    # Aggregate area IDs (MO Region, OK Region, KAMO Total)
    AGGREGATE_IDS = {18, 19, 20}

    def __init__(
        self,
        kamo_client: Optional[KAMOClient] = None,
        notification_service: Optional[NotificationService] = None,
    ):
        self.client = kamo_client or KAMOClient()
        self.notifications = notification_service or NotificationService()
        self._consecutive_failures = 0

    async def run_import(self) -> ImportResult:
        """Run a full import cycle."""
        start_time = now_central()
        SessionLocal = get_session_local()
        db = SessionLocal()

        # Create import log entry
        import_log = ImportLog(started_at=start_time, status="running")
        db.add(import_log)
        db.commit()

        result = ImportResult(success=False)

        try:
            # Check connectivity
            if not await self.client.check_connectivity():
                internet_ok = await self.client.check_internet()
                if internet_ok:
                    raise ConnectionError("KAMO API is unreachable (internet is working)")
                else:
                    raise ConnectionError("No internet connection")

            # Sync cooperatives
            await self._sync_cooperatives(db)

            # Get all cooperative IDs
            cooperatives = db.query(Cooperative).all()

            # Import load data and substations for each cooperative
            for coop in cooperatives:
                try:
                    # Import load data
                    load_result = await self._import_load_data(db, coop.id)
                    result.load_imported += load_result[0]
                    result.load_skipped += load_result[1]

                    # Import substation data (skip aggregates - they don't have substations)
                    if coop.id not in self.AGGREGATE_IDS:
                        sub_result = await self._import_substations(db, coop.id)
                        result.substations_imported += sub_result[0]
                        result.substations_skipped += sub_result[1]

                except Exception as e:
                    logger.error(f"Error importing data for {coop.name}: {e}")
                    # Continue with other cooperatives

            result.success = True
            self._consecutive_failures = 0

        except Exception as e:
            logger.error(f"Import failed: {e}")
            result.error = str(e)
            self._consecutive_failures += 1

            # Send notification after 3 consecutive failures
            if self._consecutive_failures >= 3:
                await self.notifications.send_failure_alert(
                    f"Import has failed {self._consecutive_failures} consecutive times. "
                    f"Latest error: {e}"
                )

        finally:
            # Update import log
            end_time = now_central()
            result.duration_seconds = (end_time - start_time).total_seconds()

            import_log.completed_at = end_time
            import_log.status = "success" if result.success else "failed"
            import_log.load_records_imported = result.load_imported
            import_log.load_records_skipped = result.load_skipped
            import_log.substation_records_imported = result.substations_imported
            import_log.substation_records_skipped = result.substations_skipped
            import_log.error_message = result.error
            import_log.duration_seconds = result.duration_seconds

            db.commit()
            db.close()

        logger.info(
            f"Import completed: success={result.success}, "
            f"load={result.load_imported}+/{result.load_skipped}-, "
            f"subs={result.substations_imported}+/{result.substations_skipped}- "
            f"in {result.duration_seconds:.2f}s"
        )

        return result

    async def _sync_cooperatives(self, db: Session) -> None:
        """Sync cooperative list from KAMO API."""
        cooperatives = await self.client.get_cooperatives()

        for coop in cooperatives:
            existing = db.query(Cooperative).filter(Cooperative.id == coop.id).first()
            if existing:
                existing.name = coop.name
                existing.abbreviation = coop.abrev
                existing.is_aggregate = coop.id in self.AGGREGATE_IDS
            else:
                db.add(Cooperative(
                    id=coop.id,
                    name=coop.name,
                    abbreviation=coop.abrev,
                    is_aggregate=coop.id in self.AGGREGATE_IDS,
                ))

        db.commit()
        logger.debug(f"Synced {len(cooperatives)} cooperatives")

    async def _import_load_data(self, db: Session, area_id: int) -> tuple[int, int]:
        """
        Import load data for an area.

        Returns (imported_count, skipped_count).
        """
        response = await self.client.get_area_grid(area_id)
        actual_data = self.client.extract_actual_data(response)

        if not actual_data:
            return 0, 0

        imported = 0
        skipped = 0

        for timestamp, load_kw in actual_data:
            # Use INSERT OR IGNORE for deduplication
            stmt = sqlite_insert(LoadData).values(
                area_id=area_id,
                timestamp=timestamp,
                load_kw=load_kw,
            ).on_conflict_do_nothing(
                index_elements=["area_id", "timestamp"]
            )

            result = db.execute(stmt)
            if result.rowcount > 0:
                imported += 1
            else:
                skipped += 1

        db.commit()
        return imported, skipped

    async def _import_substations(self, db: Session, area_id: int) -> tuple[int, int]:
        """
        Import current substation data for an area.

        Returns (imported_count, skipped_count).
        """
        response = await self.client.get_area_substations(area_id)
        # Round to nearest 5-minute mark for standardized timestamps (e.g., 9:00, 9:05, 9:10)
        now = now_central()
        rounded_minute = (now.minute // 5) * 5
        snapshot_time = now.replace(minute=rounded_minute, second=0, microsecond=0)

        imported = 0
        skipped = 0

        for sub in response.areaLoadData:
            stmt = sqlite_insert(SubstationSnapshot).values(
                area_id=area_id,
                snapshot_time=snapshot_time,
                substation_name=sub.name,
                kw=sub.kw,
                kvar=sub.kvar,
                pf=sub.pf,
                quality=sub.quality,
                quality_now=sub.qualityNow,
            ).on_conflict_do_nothing(
                index_elements=["area_id", "snapshot_time", "substation_name"]
            )

            result = db.execute(stmt)
            if result.rowcount > 0:
                imported += 1
            else:
                skipped += 1

        db.commit()
        return imported, skipped

    def get_last_import(self, db: Session) -> Optional[ImportLog]:
        """Get the most recent import log entry."""
        return db.query(ImportLog).order_by(ImportLog.started_at.desc()).first()

    def get_last_successful_import(self, db: Session) -> Optional[ImportLog]:
        """Get the most recent successful import."""
        return (
            db.query(ImportLog)
            .filter(ImportLog.status == "success")
            .order_by(ImportLog.started_at.desc())
            .first()
        )

    def get_import_stats(self, db: Session, hours: int = 24) -> dict:
        """Get import statistics for the last N hours."""
        cutoff = now_central().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if hours < 24:
            cutoff = now_central() - timedelta(hours=hours)

        total = db.query(func.count(ImportLog.id)).filter(
            ImportLog.started_at >= cutoff
        ).scalar() or 0

        successful = db.query(func.count(ImportLog.id)).filter(
            ImportLog.started_at >= cutoff,
            ImportLog.status == "success"
        ).scalar() or 0

        return {
            "total": total,
            "successful": successful,
            "failed": total - successful,
            "success_rate": (successful / total * 100) if total > 0 else 0.0,
        }

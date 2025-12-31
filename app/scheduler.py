"""APScheduler setup for periodic data imports."""

import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.services.importer import DataImporter

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler: AsyncIOScheduler = None
importer: DataImporter = None


async def import_job():
    """Scheduled import job."""
    global importer
    if importer is None:
        importer = DataImporter()

    logger.info("Starting scheduled import...")
    try:
        result = await importer.run_import()
        if result.success:
            logger.info(
                f"Scheduled import completed: "
                f"{result.load_imported} load records, "
                f"{result.substations_imported} substation records"
            )
        else:
            logger.error(f"Scheduled import failed: {result.error}")
    except Exception as e:
        logger.exception(f"Unexpected error in scheduled import: {e}")


def start_scheduler():
    """Start the background scheduler."""
    global scheduler

    if scheduler is not None and scheduler.running:
        logger.warning("Scheduler already running")
        return

    settings = get_settings()
    scheduler = AsyncIOScheduler()

    # Add the import job
    scheduler.add_job(
        import_job,
        trigger=IntervalTrigger(minutes=settings.poll_interval_minutes),
        id="kamo_import",
        name="KAMO Data Import",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )

    scheduler.start()
    logger.info(
        f"Scheduler started with {settings.poll_interval_minutes} minute interval"
    )


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


async def trigger_manual_import():
    """Trigger an immediate import (for manual trigger endpoint)."""
    global importer
    if importer is None:
        importer = DataImporter()
    return await importer.run_import()


def get_next_run_time():
    """Get the next scheduled run time."""
    global scheduler
    if scheduler and scheduler.running:
        job = scheduler.get_job("kamo_import")
        if job:
            return job.next_run_time
    return None

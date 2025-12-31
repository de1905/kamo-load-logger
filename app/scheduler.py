"""APScheduler setup for periodic data imports.

Polling Strategy:
- KAMO API updates substation data approximately every 3 minutes
- We poll every 5 minutes for good resolution without excessive API load
- Scheduler runs at even 5-minute marks (0, 5, 10, 15... minutes of each hour)
- Timestamps are standardized to these marks for consistent data
"""

import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import get_settings
from app.services.importer import DataImporter
from app.services.settings import get_setting

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

    scheduler = AsyncIOScheduler()

    # Get poll interval from settings service (DB > ENV > default)
    interval = get_setting("poll_interval_minutes")

    if interval == 5:
        # Use cron trigger for exact 5-minute marks: 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55
        trigger = CronTrigger(minute="0,5,10,15,20,25,30,35,40,45,50,55")
        trigger_desc = "every 5 minutes at :00, :05, :10..."
    elif interval == 10:
        # Every 10 minutes
        trigger = CronTrigger(minute="0,10,20,30,40,50")
        trigger_desc = "every 10 minutes at :00, :10, :20..."
    elif interval == 15:
        # Every 15 minutes
        trigger = CronTrigger(minute="0,15,30,45")
        trigger_desc = "every 15 minutes at :00, :15, :30, :45"
    elif interval == 30:
        # Every 30 minutes
        trigger = CronTrigger(minute="0,30")
        trigger_desc = "every 30 minutes at :00, :30"
    else:
        # Fallback to interval trigger for non-standard intervals
        trigger = IntervalTrigger(minutes=interval)
        trigger_desc = f"every {interval} minutes (interval-based)"

    # Add the import job
    scheduler.add_job(
        import_job,
        trigger=trigger,
        id="kamo_import",
        name="KAMO Data Import",
        replace_existing=True,
        max_instances=1,  # Prevent overlapping runs
    )

    scheduler.start()
    logger.info(f"Scheduler started: {trigger_desc}")


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def restart_scheduler():
    """Restart the scheduler with updated settings."""
    global scheduler
    logger.info("Restarting scheduler with new settings...")
    stop_scheduler()
    scheduler = None  # Reset so start_scheduler creates fresh instance
    start_scheduler()


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

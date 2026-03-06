"""
Scheduler — reserved for future tasks.
Invite link revocation is handled natively by Telegram via expire_date.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def setup_scheduler():
    # No jobs needed — Telegram handles invite link expiry via expire_date
    scheduler.start()
    logger.info("✅ Scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")

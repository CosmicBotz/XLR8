from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


def setup_scheduler(bot: Bot):
    """Initialize and start the revoke scheduler."""
    from services.link_gen import revoke_expired_links

    async def revoke_job():
        await revoke_expired_links(bot)

    scheduler.add_job(
        revoke_job,
        trigger="interval",
        minutes=1,
        id="revoke_links",
        replace_existing=True
    )
    scheduler.start()
    logger.info("✅ Scheduler started — checking expired links every minute.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")
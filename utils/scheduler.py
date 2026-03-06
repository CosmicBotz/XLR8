"""
Scheduler — persists delete jobs so Render spin-down doesn't lose them.
Jobs are stored in MongoDB so they survive restarts.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
import logging

from config import MONGO_URI

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(
    jobstores={
        "default": MongoDBJobStore(
            database="CosmicBotz",
            collection="scheduler_jobs",
            host=MONGO_URI
        )
    },
    executors={"default": AsyncIOExecutor()},
    job_defaults={"coalesce": True, "max_instances": 5},
)


def setup_scheduler():
    scheduler.start()
    logger.info("✅ Scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped.")

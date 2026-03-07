"""
Scheduler — simple in-memory task manager.
Keeps strong references so GC never cancels pending deletions.
No DB, no APScheduler — just asyncio done right.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def schedule(self, coro, delay: int):
        """Schedule a coroutine to run after `delay` seconds."""
        async def _runner():
            await asyncio.sleep(delay)
            await coro

        task = asyncio.create_task(_runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.debug(f"Scheduled task in {delay}s — {len(self._tasks)} pending")

    def cancel_all(self):
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()


# Global singleton
task_manager = TaskManager()


def setup_scheduler():
    # Nothing to start — asyncio event loop handles everything
    logger.info("✅ Task manager ready.")


def stop_scheduler():
    task_manager.cancel_all()
    logger.info("Task manager stopped.")

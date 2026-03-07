"""
Scheduler — simple in-memory task manager.
Keeps strong references so GC never cancels pending deletions.
"""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    async def schedule(self, coro, delay: int):
        """Schedule a coroutine to run after delay seconds."""
        async def _runner():
            await asyncio.sleep(delay)
            try:
                await coro
            except Exception as e:
                logger.debug(f"Scheduled task error: {e}")

        task = asyncio.create_task(_runner())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        logger.debug(f"Scheduled in {delay}s — {len(self._tasks)} pending")

    def cancel_all(self):
        for task in list(self._tasks):
            task.cancel()
        self._tasks.clear()


task_manager = TaskManager()


def setup_scheduler():
    logger.info("✅ Task manager ready.")


def stop_scheduler():
    task_manager.cancel_all()
    logger.info("Task manager stopped.")

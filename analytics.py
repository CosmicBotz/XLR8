"""
analytics.py — Search logs & analytics for Auto Filter CosmicBotz.

Initialised automatically by database.py after connect():
    Analytics.init(db)  ← called inside Database.connect()

Usage anywhere in the bot:
    from analytics import Analytics
    await Analytics.log_search(query, user_id, group_id, found=True)
    await Analytics.log_missed_search(query, user_id, group_id)
    data = await Analytics.get_analytics()
"""

from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Analytics:

    _db = None  # injected by Database.connect()

    @classmethod
    def init(cls, db):
        cls._db = db

    @classmethod
    def _get_db(cls):
        if cls._db is None:
            raise RuntimeError("Analytics not initialised. Call Analytics.init(db) first.")
        return cls._db

    # ──────────────────────────────────────────────────────────────────────────
    # INDEX SETUP
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    async def ensure_indexes(cls):
        from pymongo import ASCENDING
        db = cls._get_db()
        await db.search_logs.create_index([("count",    -1)])
        await db.search_logs.create_index([("query",    ASCENDING)], unique=True)
        await db.analytics.create_index(  [("day",      ASCENDING)])
        await db.analytics.create_index(  [("found",    ASCENDING)])
        await db.analytics.create_index(  [("group_id", ASCENDING)])
        logger.info("✅ Analytics indexes ensured")

    # ──────────────────────────────────────────────────────────────────────────
    # LOGGING
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    async def log_missed_search(cls, query: str, user_id: int, group_id: int):
        """Record a search that returned no results."""
        db  = cls._get_db()
        now = datetime.utcnow()
        await db.search_logs.update_one(
            {"query": query.lower().strip()},
            {
                "$inc":         {"count": 1},
                "$set":         {"last_searched": now},
                "$setOnInsert": {"first_searched": now, "fulfilled": False},
                "$addToSet":    {"groups": group_id},
            },
            upsert=True,
        )

    @classmethod
    async def log_search(cls, query: str, user_id: int, group_id: int, found: bool):
        """Record every search for analytics."""
        db  = cls._get_db()
        now = datetime.utcnow()
        await db.analytics.insert_one({
            "query":    query.lower().strip(),
            "user_id":  user_id,
            "group_id": group_id,
            "found":    found,
            "date":     now,
            "day":      now.strftime("%Y-%m-%d"),
        })

    # ──────────────────────────────────────────────────────────────────────────
    # MISSED SEARCHES
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    async def get_missed_searches(cls, limit: int = 10) -> list:
        """Top unmatched searches sorted by count."""
        db     = cls._get_db()
        cursor = db.search_logs.find({"fulfilled": False}).sort("count", -1).limit(limit)
        return await cursor.to_list(length=limit)

    @classmethod
    async def mark_fulfilled(cls, query: str):
        """Mark a missed search as fulfilled after content is added."""
        db = cls._get_db()
        await db.search_logs.update_one(
            {"query": query.lower().strip()},
            {"$set": {"fulfilled": True}},
        )

    # ──────────────────────────────────────────────────────────────────────────
    # AGGREGATED ANALYTICS  (used by /stats in start.py)
    # ──────────────────────────────────────────────────────────────────────────

    @classmethod
    async def get_analytics(cls) -> dict:
        """
        Returns dict used by /stats in start.py:
            today_searches, today_found, today_missed
            total_searches, total_found, total_missed, hit_rate
            top_today      → str  (top query string today, or "")
            top_group_id   → int | None
            top_group_cnt  → int
            missed_top     → list[dict]
        """
        db    = cls._get_db()
        today = datetime.utcnow().strftime("%Y-%m-%d")

        total_searches = await db.analytics.count_documents({})
        today_searches = await db.analytics.count_documents({"day": today})
        today_found    = await db.analytics.count_documents({"day": today, "found": True})
        today_missed   = await db.analytics.count_documents({"day": today, "found": False})
        total_found    = await db.analytics.count_documents({"found": True})
        total_missed   = await db.analytics.count_documents({"found": False})

        # Top query today
        top_q_res = await db.analytics.aggregate([
            {"$match":  {"day": today}},
            {"$group":  {"_id": "$query", "count": {"$sum": 1}}},
            {"$sort":   {"count": -1}},
            {"$limit":  1},
        ]).to_list(length=1)
        top_today = top_q_res[0]["_id"] if top_q_res else ""

        # Most active group (all-time)
        top_grp_res = await db.analytics.aggregate([
            {"$group":  {"_id": "$group_id", "count": {"$sum": 1}}},
            {"$sort":   {"count": -1}},
            {"$limit":  1},
        ]).to_list(length=1)
        top_group_id  = top_grp_res[0]["_id"]   if top_grp_res else None
        top_group_cnt = top_grp_res[0]["count"] if top_grp_res else 0

        missed_top = await cls.get_missed_searches(limit=5)

        return {
            "total_searches": total_searches,
            "today_searches": today_searches,
            "today_found":    today_found,
            "today_missed":   today_missed,
            "total_found":    total_found,
            "total_missed":   total_missed,
            "hit_rate":       round((total_found / total_searches * 100), 1) if total_searches else 0,
            "top_today":      top_today,
            "top_group_id":   top_group_id,
            "top_group_cnt":  top_group_cnt,
            "missed_top":     missed_top,
        }

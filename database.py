"""
database.py — Single database module for Auto Filter CosmicBotz.
"""

import re
import unicodedata
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from bson import ObjectId
from datetime import datetime
from config import MONGO_URI, DB_NAME, AUTO_REVOKE_MINUTES, OWNER_ID
import logging

logger = logging.getLogger(__name__)


class Database:

    def __init__(self):
        self._client: AsyncIOMotorClient | None = None
        self._db = None

    # ══════════════════════════════════════════════════════════════════════════
    # CONNECTION
    # ══════════════════════════════════════════════════════════════════════════

    async def connect(self):
        if self._client is not None:
            return

        self._client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=10
        )
        self._db = self._client[DB_NAME]
        await self._client.admin.command("ping")
        logger.info(f"✅ MongoDB connected → {DB_NAME}")
        await self._ensure_indexes()

    async def close(self):
        if self._client:
            self._client.close()
            self._client = None
            self._db = None

    def db(self):
        if self._db is None:
            raise RuntimeError("Database not connected.")
        return self._db

    async def _ensure_indexes(self):
        db = self.db()
        await db.filters.create_index([("first_letter", ASCENDING)])
        await db.filters.create_index([("title",        ASCENDING)])
        await db.filters.create_index([("acronym",      ASCENDING)])
        await db.filters.create_index([("title_normalized", ASCENDING)])
        await db.slots.create_index(  [("owner_id",     ASCENDING)])
        await db.groups.create_index( [("group_id",     ASCENDING)], unique=True)
        await db.search_logs.create_index([("count", -1)])
        await db.analytics.create_index([("day", ASCENDING)])
        logger.info("✅ MongoDB indexes ensured")

    # ══════════════════════════════════════════════════════════════════════════
    # FILTERS & SEARCH (UPGRADED)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_title(s: str) -> str:
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.lower()
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    async def add_filter(self, data: dict) -> str | None:
        db = self.db()
        title = data.get("title", "")
        data["title_normalized"] = self._normalize_title(title)
        data["first_letter"] = title[0].upper() if title else "#"
        data["created_at"]   = datetime.utcnow()

        # 🔥 SMART ACRONYM (2+ word titles)
        chunks = re.split(r'[\s\-_]+', title)
        chunks = [c for c in chunks if c]
        if len(chunks) >= 2:
            data["acronym"] = "".join(c[0].lower() for c in chunks if c[0].isalnum())
        else:
            data["acronym"] = ""

        existing = await db.filters.find_one({"title": title, "media_type": data.get("media_type")})
        if existing: return None
        result = await db.filters.insert_one(data)
        return str(result.inserted_id)

    async def search_title(self, query: str) -> list:
        norm_q_raw = self._normalize_title(query.strip())
        ABBR = await self.get_abbr_map()
        
        # Expand query based on Abbreviations
        tokens = norm_q_raw.split()
        norm_q = " ".join([ABBR.get(t, t) for t in tokens])

        db = self.db()
        seen, results = set(), []

        async def _add(cursor):
            async for doc in cursor:
                oid = str(doc["_id"])
                if oid not in seen:
                    seen.add(oid); results.append(doc)

        # 🚀 STRATEGY 1: Regex with flexible spacing/hyphens
        flex_pat = norm_q.replace(" ", r"[\s\-._]*")
        try:
            pattern = r"(?i).*\b" + flex_pat + r"\b.*"
            await _add(db.filters.find({"$or": [{"title_normalized": {"$regex": pattern}}, {"title": {"$regex": pattern}}]}))
        except: pass

        # 🚀 STRATEGY 2: Acronym Match
        if not results and len(norm_q_raw) >= 2:
            await _add(db.filters.find({"acronym": norm_q_raw}))

        # 🚀 STRATEGY 3: Word-by-word Match
        if not results and len(tokens) >= 2:
            wf = [{"title_normalized": {"$regex": r"(?i)\b" + re.escape(w) + r"\b"}} for w in tokens if len(w) > 2]
            if wf: await _add(db.filters.find({"$and": wf}))

        return sorted(results, key=lambda x: x.get("title", ""))[:20]

    async def get_filter_by_id(self, filter_id: str) -> dict | None:
        return await self.db().filters.find_one({"_id": ObjectId(filter_id)})

    async def update_filter_post(self, filter_id: str, log_channel_id: int, message_id: int, permanent_invite: str, slot_channel_id: int = 0):
        await self.db().filters.update_one({"_id": ObjectId(filter_id)}, {"$set": {"log_channel_id": log_channel_id, "message_id": message_id, "permanent_invite": permanent_invite, "slot_channel_id": slot_channel_id, "posted": True}})

    async def delete_filter(self, title: str, media_type: str) -> bool:
        res = await self.db().filters.delete_one({"title": title, "media_type": media_type})
        return res.deleted_count > 0

    async def get_all_letters(self) -> list:
        return sorted(await self.db().filters.distinct("first_letter"))

    async def get_by_letter(self, letter: str) -> list:
        return await self.db().filters.find({"first_letter": letter.upper()}).sort("title", ASCENDING).to_list(length=100)

    # ══════════════════════════════════════════════════════════════════════════
    # SLOTS (ALL RESTORED)
    # ══════════════════════════════════════════════════════════════════════════

    async def add_slot(self, owner_id: int, channel_id: int, channel_name: str, slot_name: str) -> tuple[bool, str]:
        if await self.db().slots.find_one({"channel_id": channel_id}): return False, "Already exists."
        await self.db().slots.insert_one({"owner_id": owner_id, "channel_id": channel_id, "channel_name": channel_name, "slot_name": slot_name, "active": True, "created_at": datetime.utcnow()})
        return True, "Added."

    async def remove_slot(self, owner_id: int, channel_id: int, is_owner: bool = False) -> bool:
        q = {"channel_id": channel_id}
        if not is_owner: q["owner_id"] = owner_id
        return (await self.db().slots.delete_one(q)).deleted_count > 0

    async def get_slots(self, owner_id: int, is_owner: bool = False) -> list:
        q = {} if is_owner else {"owner_id": owner_id}
        return await self.db().slots.find(q).to_list(length=None)

    async def get_slot(self, channel_id: int) -> dict | None:
        return await self.db().slots.find_one({"channel_id": channel_id})

    async def get_slots_all(self) -> list:
        return await self.db().slots.find({}).to_list(length=None)

    # ══════════════════════════════════════════════════════════════════════════
    # ADMINS & GROUPS (ALL RESTORED)
    # ══════════════════════════════════════════════════════════════════════════

    async def add_admin(self, user_id: int):
        await self.db().admins.update_one({"owner_id": OWNER_ID}, {"$addToSet": {"admins": user_id}}, upsert=True)

    async def remove_admin(self, user_id: int):
        await self.db().admins.update_one({"owner_id": OWNER_ID}, {"$pull": {"admins": user_id}})

    async def get_admins(self) -> list:
        doc = await self.db().admins.find_one({"owner_id": OWNER_ID})
        return doc.get("admins", []) if doc else []

    async def is_admin(self, user_id: int) -> bool:
        if user_id == OWNER_ID: return True
        return user_id in await self.get_admins()

    async def add_group(self, group_id: int, group_name: str, added_by: int) -> bool:
        if await self.db().groups.find_one({"group_id": group_id}): return False
        await self.db().groups.insert_one({"group_id": group_id, "group_name": group_name, "added_by": added_by, "verified": False, "created_at": datetime.utcnow()})
        return True

    async def verify_group(self, group_id: int, verified_by: int, invite_link: str = "") -> bool:
        res = await self.db().groups.update_one({"group_id": group_id}, {"$set": {"verified": True, "verified_by": verified_by, "verified_at": datetime.utcnow(), "invite_link": invite_link}}, upsert=True)
        return res.modified_count > 0 or res.upserted_id is not None

    async def unverify_group(self, group_id: int):
        await self.db().groups.update_one({"group_id": group_id}, {"$set": {"verified": False, "verified_by": None}})

    async def is_group_verified(self, group_id: int) -> bool:
        doc = await self.db().groups.find_one({"group_id": group_id})
        return doc.get("verified", False) if doc else False

    async def get_group(self, group_id: int) -> dict | None:
        return await self.db().groups.find_one({"group_id": group_id})

    async def get_verified_group_links(self) -> list:
        return await self.db().groups.find({"verified": True, "invite_link": {"$ne": ""}}).to_list(length=50)

    async def get_all_groups(self, verified_only: bool = False) -> list:
        q = {"verified": True} if verified_only else {}
        return await self.db().groups.find(q).sort("created_at", -1).to_list(length=200)

    async def remove_group(self, group_id: int):
        await self.db().groups.delete_one({"group_id": group_id})

    # ══════════════════════════════════════════════════════════════════════════
    # SETTINGS & ABBR (RESTORED)
    # ══════════════════════════════════════════════════════════════════════════

    async def get_settings(self) -> dict:
        doc = await self.db().settings.find_one({"owner_id": OWNER_ID})
        defaults = {"auto_revoke_minutes": AUTO_REVOKE_MINUTES, "caption_quality": "1080p FHD", "caption_audio": "हिंदी", "watermark_text": "", "watermark_logo_id": ""}
        if not doc: return defaults
        for k, v in defaults.items(): doc.setdefault(k, v)
        return doc

    async def update_setting(self, key: str, value):
        await self.db().settings.update_one({"owner_id": OWNER_ID}, {"$set": {key: value}}, upsert=True)

    async def get_abbr_map(self) -> dict:
        docs = await self.db().abbreviations.find().to_list(length=500)
        return {d["abbr"]: d["full"] for d in docs}

    async def set_abbr(self, abbr: str, full: str):
        await self.db().abbreviations.update_one({"abbr": abbr.lower()}, {"$set": {"abbr": abbr.lower(), "full": full}}, upsert=True)

    async def del_abbr(self, abbr: str) -> bool:
        return (await self.db().abbreviations.delete_one({"abbr": abbr.lower()})).deleted_count > 0

    # ══════════════════════════════════════════════════════════════════════════
    # ANALYTICS & LOGS (RESTORED)
    # ══════════════════════════════════════════════════════════════════════════

    async def log_missed_search(self, query: str, user_id: int, group_id: int):
        now = datetime.utcnow()
        await self.db().search_logs.update_one({"query": query.lower().strip()}, {"$inc": {"count": 1}, "$set": {"last_searched": now}, "$setOnInsert": {"first_searched": now, "fulfilled": False}, "$addToSet": {"groups": group_id}}, upsert=True)

    async def log_search(self, query: str, user_id: int, group_id: int, found: bool):
        now = datetime.utcnow()
        await self.db().analytics.insert_one({"query": query.lower().strip(), "user_id": user_id, "group_id": group_id, "found": found, "date": now, "day": now.strftime("%Y-%m-%d")})

    async def get_missed_searches(self, limit: int = 10) -> list:
        return await self.db().search_logs.find({"fulfilled": False}).sort("count", -1).to_list(length=limit)

    async def mark_fulfilled(self, query: str):
        await self.db().search_logs.update_one({"query": query.lower().strip()}, {"$set": {"fulfilled": True}})

    async def get_analytics(self) -> dict:
        db, today = self.db(), datetime.utcnow().strftime("%Y-%m-%d")
        total = await db.analytics.count_documents({})
        found = await db.analytics.count_documents({"found": True})
        return {"total_searches": total, "total_found": found, "total_missed": total-found}

    async def get_stats(self) -> dict:
        db = self.db()
        return {
            "anime":  await db.filters.count_documents({"media_type": "anime"}),
            "tvshow": await db.filters.count_documents({"media_type": "tvshow"}),
            "movie":  await db.filters.count_documents({"media_type": "movie"}),
            "total":  await db.filters.count_documents({}),
            "groups": await db.groups.count_documents({}),
            "slots":  await db.slots.count_documents({}),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # 🚨 TEMPORARY MIGRATION SCRIPT 🚨
    # ══════════════════════════════════════════════════════════════════════════
    async def temp_fix_database(self) -> int:
        db, count = self.db(), 0
        cursor = db.filters.find({"title_normalized": {"$exists": False}})
        async for doc in cursor:
            title = doc.get("title", "")
            norm_title = self._normalize_title(title)
            chunks = re.split(r'[\s\-_]+', title)
            chunks = [c for c in chunks if c]
            acronym = "".join(c[0].lower() for c in chunks if c[0].isalnum()) if len(chunks) >= 2 else ""
            await db.filters.update_one({"_id": doc["_id"]}, {"$set": {"title_normalized": norm_title, "acronym": acronym}})
            count += 1
        return count

# 🟢 CRITICAL EXPORT FOR bot.py
CosmicBotz = Database()
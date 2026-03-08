"""
database.py — Single database module for Auto Filter CosmicBotz.

Usage anywhere in the bot:
    from database import CosmicBotz
    await CosmicBotz.connect()
    await CosmicBotz.add_filter(data)
    ...
"""

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
        """Call once at bot startup."""
        if self._client is not None:
            return  # already connected

        self._client = AsyncIOMotorClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=10
        )
        self._db = self._client[DB_NAME]

        await self._client.admin.command("ping")
        logger.info(f"✅ MongoDB connected → {DB_NAME}")

        await self._ensure_indexes()

        # Initialise analytics module with the same DB handle
        from analytics import Analytics
        Analytics.init(self._db)

    async def close(self):
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
            logger.info("MongoDB connection closed.")

    def db(self):
        if self._db is None:
            raise RuntimeError("Database not connected. Call await CosmicBotz.connect() first.")
        return self._db

    async def _ensure_indexes(self):
        db = self.db()
        await db.filters.create_index([("first_letter", ASCENDING)])
        await db.filters.create_index([("title",        ASCENDING)])
        await db.filters.create_index([("acronym",      ASCENDING)])
        await db.slots.create_index(  [("owner_id",     ASCENDING)])
        await db.groups.create_index( [("group_id",     ASCENDING)], unique=True)

        # Analytics indexes now owned by analytics.py
        from analytics import Analytics
        Analytics.init(self._db)
        await Analytics.ensure_indexes()

        logger.info("✅ MongoDB indexes ensured")

    # ══════════════════════════════════════════════════════════════════════════
    # FILTERS  (anime / tvshow / movie index)
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_title(s: str) -> str:
        import re, unicodedata
        s = unicodedata.normalize("NFD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        s = s.lower()
        s = re.sub(r"[^a-z0-9 ]", " ", s)
        return re.sub(r"\s+", " ", s).strip()

    async def add_filter(self, data: dict) -> str | None:
        """Add a title to the index. Returns inserted _id str or None if duplicate."""
        db = self.db()
        title = data.get("title", "")
        data["first_letter"] = title[0].upper() if title else "#"
        data["created_at"]   = datetime.utcnow()

        # Auto-generate acronym from first letters of each word (3+ word titles only)
        words = title.split()
        if len(words) >= 3:
            data["acronym"] = "".join(w[0].lower() for w in words if w)
        else:
            data["acronym"] = ""

        existing = await db.filters.find_one(
            {"title": title, "media_type": data.get("media_type")}
        )
        if existing:
            return None

        result = await db.filters.insert_one(data)
        return str(result.inserted_id)

    async def get_by_letter(self, letter: str) -> list:
        """All titles whose first letter matches."""
        db = self.db()
        cursor = db.filters.find(
            {"first_letter": letter.upper()}
        ).sort("title", ASCENDING)
        return await cursor.to_list(length=100)

    async def search_title(self, query: str) -> list:
        """
        Fuzzy title search with 7-strategy pipeline.
        S1  exact phrase (word-boundary)
        S2  original query exact
        S3  acronym lookup
        S4  all words present (any order)
        S5  longest-word fallback
        S6  prefix fallback
        S7  rapidfuzz token_set_ratio ≥ 70 % (last resort)
        """
        import re, unicodedata

        def _normalize(s: str) -> str:
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            s = s.lower()
            s = re.sub(r"[^a-z0-9 ]", " ", s)
            return re.sub(r"\s+", " ", s).strip()

        norm_q_raw = _normalize(query.strip())
        q_lower    = norm_q_raw

        # ── Abbreviation expansion ────────────────────────────────────────────
        ABBR = await self.get_abbr_map()

        if q_lower in ABBR:
            norm_q = _normalize(ABBR[q_lower])
        else:
            tokens   = q_lower.split()
            expanded = [ABBR.get(t, t) for t in tokens]
            norm_q   = " ".join(expanded)

        db      = self.db()
        seen    = set()
        results = []

        async def _add(cursor):
            async for doc in cursor:
                oid = str(doc["_id"])
                if oid not in seen:
                    seen.add(oid)
                    results.append(doc)

        words = [w for w in norm_q.split() if len(w) >= 2]

        # Guard: block 1-2 char queries that aren't abbreviations
        orig_words = norm_q_raw.split()
        if len(orig_words) == 1 and len(norm_q_raw) <= 2 and norm_q_raw not in ABBR:
            return []

        # S1: Exact phrase (word-boundary)
        try:
            pattern = r"(?i)\b" + re.escape(norm_q) + r"\b"
            await _add(db.filters.find({"title_normalized": {"$regex": pattern}}))
        except Exception:
            pass

        # S2: Original query exact match
        if not results:
            try:
                pattern = r"(?i)\b" + re.escape(query.strip()) + r"\b"
                await _add(db.filters.find({"title": {"$regex": pattern}}))
            except Exception:
                pass

        # S3: Acronym match (indexed)
        if not results and len(norm_q_raw) >= 2 and " " not in norm_q_raw:
            try:
                await _add(db.filters.find({"acronym": norm_q_raw}))
            except Exception:
                pass

        # S4: All words present (any order), 2+ words only
        if len(words) >= 2 and len(results) < 5:
            try:
                wf = [{"title_normalized": {"$regex": r"(?i)\b" + re.escape(w) + r"\b"}} for w in words]
                await _add(db.filters.find({"$and": wf}))
            except Exception:
                pass

        # S5: Longest-word fallback — 2+ word queries only
        if not results and len(words) >= 2:
            longest = max(words, key=len)
            if len(longest) >= 4:
                try:
                    await _add(db.filters.find({"title_normalized": {"$regex": r"(?i)\b" + re.escape(longest) + r"\b"}}))
                except Exception:
                    pass

        # S6: Prefix fallback — "food war" → "Food Wars"
        if not results:
            for w in sorted(words, key=len, reverse=True):
                if len(w) >= 4:
                    try:
                        await _add(db.filters.find({"title_normalized": {"$regex": r"(?i)\b" + re.escape(w)}}))
                        if results:
                            break
                    except Exception:
                        pass

        # S7: Fuzzy — last resort for scrambled typos ("dimon sleyr" → "Demon Slayer")
        if not results:
            try:
                from rapidfuzz import fuzz
                all_docs  = await db.filters.find({}, {"title_normalized": 1, "title": 1}).to_list(length=2000)
                threshold = 70
                scored    = []
                for doc in all_docs:
                    t_norm = doc.get("title_normalized", "")
                    score  = fuzz.token_set_ratio(norm_q, t_norm)
                    if score >= threshold:
                        scored.append((score, doc))
                scored.sort(key=lambda x: x[0], reverse=True)
                for score, doc in scored[:5]:
                    oid = str(doc["_id"])
                    if oid not in seen:
                        seen.add(oid)
                        full = await db.filters.find_one({"_id": doc["_id"]})
                        if full:
                            results.append(full)
            except ImportError:
                pass
            except Exception:
                pass

        return sorted(results, key=lambda x: x.get("title", ""))[:20]

    async def get_filter_by_id(self, filter_id: str) -> dict | None:
        db = self.db()
        return await db.filters.find_one({"_id": ObjectId(filter_id)})

    async def update_filter_post(
        self,
        filter_id: str,
        log_channel_id: int,
        message_id: int,
        permanent_invite: str,
        slot_channel_id: int = 0,
    ):
        """Store log channel post location + permanent invite link + slot channel after /addcontent."""
        db = self.db()
        await db.filters.update_one(
            {"_id": ObjectId(filter_id)},
            {"$set": {
                "log_channel_id":   log_channel_id,
                "message_id":       message_id,
                "permanent_invite": permanent_invite,
                "slot_channel_id":  slot_channel_id,
                "posted":           True
            }}
        )

    async def delete_filter(self, title: str, media_type: str) -> bool:
        db = self.db()
        result = await db.filters.delete_one({"title": title, "media_type": media_type})
        return result.deleted_count > 0

    async def get_all_letters(self) -> list:
        db = self.db()
        return sorted(await db.filters.distinct("first_letter"))

    # ══════════════════════════════════════════════════════════════════════════
    # STATS  (content index counts)
    # ══════════════════════════════════════════════════════════════════════════

    async def get_stats(self) -> dict:
        db = self.db()
        anime  = await db.filters.count_documents({"media_type": "anime"})
        tvshow = await db.filters.count_documents({"media_type": "tvshow"})
        movie  = await db.filters.count_documents({"media_type": "movie"})
        total  = await db.filters.count_documents({})
        groups          = await db.groups.count_documents({})
        verified_groups = await db.groups.count_documents({"verified": True})
        slots           = await db.slots.count_documents({})
        return {
            "anime":           anime,
            "tvshow":          tvshow,
            "movie":           movie,
            "total":           total,
            "groups":          groups,
            "verified_groups": verified_groups,
            "slots":           slots,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # SLOTS  (channel posting slots)
    # ══════════════════════════════════════════════════════════════════════════

    async def add_slot(
        self,
        owner_id: int,
        channel_id: int,
        channel_name: str,
        slot_name: str
    ) -> tuple[bool, str]:
        db = self.db()
        if await db.slots.find_one({"channel_id": channel_id}):
            return False, "Channel already has a slot."

        await db.slots.insert_one({
            "owner_id":     owner_id,
            "channel_id":   channel_id,
            "channel_name": channel_name,
            "slot_name":    slot_name,
            "active":       True,
            "created_at":   datetime.utcnow()
        })
        return True, "Slot added."

    async def remove_slot(self, owner_id: int, channel_id: int) -> bool:
        db = self.db()
        result = await db.slots.delete_one(
            {"owner_id": owner_id, "channel_id": channel_id}
        )
        return result.deleted_count > 0

    async def get_slots(self, owner_id: int) -> list:
        db = self.db()
        return await db.slots.find({"owner_id": owner_id}).to_list(length=50)

    async def get_slots_all(self) -> list:
        db = self.db()
        return await db.slots.find({}).to_list(length=50)

    async def get_slot(self, channel_id: int) -> dict | None:
        return await self.db().slots.find_one({"channel_id": channel_id})

    # ══════════════════════════════════════════════════════════════════════════
    # ADMINS
    # ══════════════════════════════════════════════════════════════════════════

    async def add_admin(self, user_id: int):
        db = self.db()
        await db.admins.update_one(
            {"owner_id": OWNER_ID},
            {"$addToSet": {"admins": user_id}},
            upsert=True
        )

    async def remove_admin(self, user_id: int):
        db = self.db()
        await db.admins.update_one(
            {"owner_id": OWNER_ID},
            {"$pull": {"admins": user_id}}
        )

    async def get_admins(self) -> list:
        db = self.db()
        doc = await db.admins.find_one({"owner_id": OWNER_ID})
        return doc.get("admins", []) if doc else []

    async def is_admin(self, user_id: int) -> bool:
        if user_id == OWNER_ID:
            return True
        return user_id in await self.get_admins()

    # ══════════════════════════════════════════════════════════════════════════
    # SETTINGS
    # ══════════════════════════════════════════════════════════════════════════

    async def get_settings(self) -> dict:
        db  = self.db()
        doc = await db.settings.find_one({"owner_id": OWNER_ID})
        defaults = {
            "auto_revoke_minutes": AUTO_REVOKE_MINUTES,
            "caption_quality":     "1080p FHD | 720p HD | 480p WEB-DL",
            "caption_audio":       "हिंदी (Hindi)",
            "watermark_text":      "",
            "watermark_logo_id":   "",
        }
        if not doc:
            return defaults
        for k, v in defaults.items():
            doc.setdefault(k, v)
        return doc

    async def update_setting(self, key: str, value):
        db = self.db()
        await db.settings.update_one(
            {"owner_id": OWNER_ID},
            {"$set": {key: value}},
            upsert=True
        )

    # ══════════════════════════════════════════════════════════════════════════
    # GROUPS  (verification)
    # ══════════════════════════════════════════════════════════════════════════

    async def add_group(self, group_id: int, group_name: str, added_by: int) -> bool:
        db = self.db()
        if await db.groups.find_one({"group_id": group_id}):
            return False
        await db.groups.insert_one({
            "group_id":    group_id,
            "group_name":  group_name,
            "added_by":    added_by,
            "verified":    False,
            "verified_by": None,
            "verified_at": None,
            "created_at":  datetime.utcnow()
        })
        return True

    async def verify_group(
        self,
        group_id: int,
        verified_by: int,
        invite_link: str = ""
    ) -> bool:
        db = self.db()
        result = await db.groups.update_one(
            {"group_id": group_id},
            {"$set": {
                "verified":     True,
                "verified_by":  verified_by,
                "verified_at":  datetime.utcnow(),
                "invite_link":  invite_link,
            }},
            upsert=True
        )
        return result.modified_count > 0 or result.upserted_id is not None

    async def unverify_group(self, group_id: int):
        db = self.db()
        await db.groups.update_one(
            {"group_id": group_id},
            {"$set": {"verified": False, "verified_by": None, "verified_at": None}}
        )

    async def is_group_verified(self, group_id: int) -> bool:
        db = self.db()
        doc = await db.groups.find_one({"group_id": group_id})
        return doc.get("verified", False) if doc else False

    async def get_group(self, group_id: int) -> dict | None:
        return await self.db().groups.find_one({"group_id": group_id})

    async def get_verified_group_links(self) -> list:
        db = self.db()
        cursor = db.groups.find({"verified": True, "invite_link": {"$ne": ""}})
        return await cursor.to_list(length=50)

    async def get_all_groups(self, verified_only: bool = False) -> list:
        db = self.db()
        query = {"verified": True} if verified_only else {}
        cursor = db.groups.find(query).sort("created_at", -1)
        return await cursor.to_list(length=200)

    async def remove_group(self, group_id: int):
        await self.db().groups.delete_one({"group_id": group_id})

    # ══════════════════════════════════════════════════════════════════════════
    # ABBREVIATIONS
    # ══════════════════════════════════════════════════════════════════════════

    async def get_abbr_map(self) -> dict:
        db   = self.db()
        docs = await db.abbreviations.find().to_list(length=500)
        return {d["abbr"]: d["full"] for d in docs}

    async def set_abbr(self, abbr: str, full: str):
        db = self.db()
        await db.abbreviations.update_one(
            {"abbr": abbr.lower()},
            {"$set": {"abbr": abbr.lower(), "full": full}},
            upsert=True
        )

    async def del_abbr(self, abbr: str) -> bool:
        db     = self.db()
        result = await db.abbreviations.delete_one({"abbr": abbr.lower()})
        return result.deleted_count > 0


# ── Singleton ──────────────────────────────────────────────────────────────────
CosmicBotz = Database()

"""
database.py — Single database module for Auto Filter CosmicBotz.

"""

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING
from bson import ObjectId
from datetime import datetime, timedelta
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
        await db.slots.create_index(  [("owner_id",     ASCENDING)])
        await db.groups.create_index( [("group_id",     ASCENDING)], unique=True)
        await db.posts.create_index(  [("expires_at",   ASCENDING)], expireAfterSeconds=0)
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
        Fuzzy title search — handles:
        - Missing punctuation: "Fullmetal Alchemist Brotherhood" → matches "Fullmetal Alchemist: Brotherhood"
        - Diacritics: "Shippuden" → matches "Shippūden" (already normalized on save)
        - Typos / extra spaces: tries word-by-word AND tokens approach
        Strategy:
          1. Exact regex match (fastest, catches most)
          2. Strip punctuation from both query and stored titles — word token match
          3. All words present anywhere in title (any order)
        Returns deduplicated results ranked by closeness.
        """
        import re, unicodedata

        # Load custom abbreviations from DB
        ABBR = await self.get_abbr_map()

        def _normalize(s: str) -> str:
            # Remove diacritics, lowercase, strip punctuation, collapse spaces
            s = unicodedata.normalize("NFD", s)
            s = "".join(c for c in s if unicodedata.category(c) != "Mn")
            s = s.lower()
            s = re.sub(r"[^a-z0-9 ]", " ", s)
            return re.sub(r"\s+", " ", s).strip()

        # Expand abbreviations in query
        norm_q_raw = _normalize(query)
        tokens = norm_q_raw.split()
        expanded = [ABBR.get(t, t) for t in tokens]
        norm_q = " ".join(expanded)
        # Also try full query as abbreviation key
        if norm_q_raw in ABBR:
            norm_q = ABBR[norm_q_raw]

        db    = self.db()
        seen  = set()
        results = []

        async def _add(cursor):
            async for doc in cursor:
                oid = str(doc["_id"])
                if oid not in seen:
                    seen.add(oid)
                    results.append(doc)

        # 1. Direct regex match (original query)
        try:
            escaped = re.escape(query)
            await _add(db.filters.find({"title": {"$regex": escaped, "$options": "i"}}))
        except Exception:
            pass

        # 2. Normalized query — strip punctuation and search
        # norm_q already set above via abbreviation expansion
        if norm_q:
            try:
                await _add(db.filters.find({"title_normalized": {"$regex": re.escape(norm_q), "$options": "i"}}))
            except Exception:
                pass

        # 3. All words present (any order) — only if user typed 2+ words
        # Prevents "brotherhood" alone matching unrelated chat
        words = [w for w in norm_q.split() if len(w) >= 3]
        if len(words) >= 2 and len(results) < 5:
            word_filters = [{"title_normalized": {"$regex": re.escape(w), "$options": "i"}} for w in words]
            try:
                await _add(db.filters.find({"$and": word_filters}))
            except Exception:
                pass

        # 4. Fallback — only if query has 2+ words and still no results
        # Never match single casual words like "brotherhood", "attack", "hero"
        if not results and len(words) >= 2:
            longest = max(words, key=len)
            try:
                await _add(db.filters.find({"title": {"$regex": re.escape(longest), "$options": "i"}}))
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
        # Fill missing keys with defaults
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
    # POSTS  (invite link tracking)
    # ══════════════════════════════════════════════════════════════════════════

    async def save_post(
        self,
        channel_id: int,
        message_id: int,
        invite_link: str,
        revoke_minutes: int
    ) -> tuple[str, datetime]:
        db = self.db()
        expires_at = datetime.utcnow() + timedelta(minutes=revoke_minutes)
        result = await db.posts.insert_one({
            "channel_id":  channel_id,
            "message_id":  message_id,
            "invite_link": invite_link,
            "expires_at":  expires_at,
            "revoked":     False,
            "created_at":  datetime.utcnow()
        })
        return str(result.inserted_id), expires_at

    async def get_pending_revokes(self) -> list:
        """Posts whose invite link has expired and not yet revoked."""
        db = self.db()
        cursor = db.posts.find(
            {"expires_at": {"$lte": datetime.utcnow()}, "revoked": False}
        )
        return await cursor.to_list(length=100)

    async def mark_revoked(self, post_id: str):
        db = self.db()
        await db.posts.update_one(
            {"_id": ObjectId(post_id)},
            {"$set": {"revoked": True}}
        )

    async def get_active_post(self, channel_id: int, message_id: int) -> dict | None:
        return await self.db().posts.find_one({
            "channel_id": channel_id,
            "message_id": message_id,
            "revoked":    False
        })

    # ══════════════════════════════════════════════════════════════════════════
    # GROUPS  (verification)
    # ══════════════════════════════════════════════════════════════════════════

    async def add_group(self, group_id: int, group_name: str, added_by: int) -> bool:
        """Register a new group as pending. Returns False if already exists."""
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
        """Return list of verified groups that have invite links stored."""
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
        """Return all custom abbreviations as {abbr: full_title}."""
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

    # ══════════════════════════════════════════════════════════════════════════
    # STATS
    # ══════════════════════════════════════════════════════════════════════════

    async def get_stats(self) -> dict:
        db = self.db()
        return {
            "total":   await db.filters.count_documents({}),
            "anime":   await db.filters.count_documents({"media_type": "anime"}),
            "tvshow":  await db.filters.count_documents({"media_type": "tvshow"}),
            "movie":   await db.filters.count_documents({"media_type": "movie"}),
            "slots":   await db.slots.count_documents({}),
            "groups":  await db.groups.count_documents({}),
            "verified_groups": await db.groups.count_documents({"verified": True}),
        }

    async def get_slots_all(self) -> list:
        """Get all slots — used for invite link generation."""
        db = self.db()
        return await db.slots.find({}).to_list(length=50)


# ── Singleton instance ────────────────────────────────────────────────────────
CosmicBotz = Database()

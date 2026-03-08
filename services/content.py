"""
Shared content-posting logic.
Used by both /addcontent wizard and the quick-slot auto-flow.
"""
import re
import unicodedata
from io import BytesIO

from aiogram import Bot
from aiogram.types import BufferedInputFile

from config import LOG_CHANNEL_ID
from database import CosmicBotz
from services.caption import build_caption
from services.thumbnail import build_thumbnail
from keyboards.inline import watch_download_keyboard
import logging

logger = logging.getLogger(__name__)


def clean_channel_name(name: str) -> str:
    """
    Strip common suffixes from channel names before TMDB search.
    e.g. "Girls' Frontline Hindi Dub [Multi]" → "Girls' Frontline"
    """
    # Remove bracketed/parenthesised tags like [Multi], (Official), [4K]
    name = re.sub(r"[\[\(][^\]\)]*[\]\)]", "", name)
    # Remove common dub/sub suffixes (case-insensitive)
    suffixes = [
        r"\bHindi\s*Dub(bed)?\b", r"\bHindi\b", r"\bDubbed\b",
        r"\bSub(bed|titles?)?\b", r"\bMulti\b", r"\bOfficial\b",
        r"\bSony\s*[Yy]ay\b", r"\bby\s+\w+\b",
        r"\b(1080p|720p|480p|4K|HD|FHD|WEB.?DL)\b",
        r"\bSeason\s*\d+\b", r"\bS\d{1,2}\b",
    ]
    for pat in suffixes:
        name = re.sub(pat, "", name, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", name).strip(" -|·")


async def post_content(
    bot: Bot,
    media_data: dict,
    slot_channel_id: int,
) -> tuple[bool, str]:
    """
    Normalize title, post thumbnail+caption to log channel,
    save to DB. Returns (success, message).
    """
    if not LOG_CHANNEL_ID:
        return False, "LOG_CHANNEL_ID not set."

    # Normalize title
    raw   = media_data.get("title", "")
    norm  = unicodedata.normalize("NFD", raw)
    media_data["title"] = "".join(c for c in norm if unicodedata.category(c) != "Mn")

    # Save filter
    filter_id = await CosmicBotz.add_filter(media_data.copy())
    if not filter_id:
        return False, "Title already exists in index."

    settings = await CosmicBotz.get_settings()

    # Create permanent invite link
    permanent_invite = None
    if slot_channel_id:
        try:
            lnk = await bot.create_chat_invite_link(
                chat_id=slot_channel_id,
                creates_join_request=False
            )
            permanent_invite = lnk.invite_link
        except Exception as e:
            logger.warning(f"Invite link failed for {slot_channel_id}: {e}")

    caption = await build_caption(media_data)
    kb      = watch_download_keyboard(permanent_invite) if permanent_invite else None

    # Build and post thumbnail
    try:
        thumb = await build_thumbnail(
            poster_url=media_data.get("poster_url"),
            backdrop_url=media_data.get("backdrop_url"),
            watermark=settings.get("watermark_text", ""),
            watermark_logo_id=settings.get("watermark_logo_id", ""),
            bot=bot,
            meta={**media_data, "_category": media_data.get("media_type", "anime")}
        )
        log_msg = await bot.send_photo(
            chat_id=LOG_CHANNEL_ID,
            photo=BufferedInputFile(thumb, filename="poster.jpg"),
            caption=caption,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await CosmicBotz.db().filters.delete_one({"title": media_data["title"]})
        return False, f"Failed to post: {e}"

    await CosmicBotz.update_filter_post(
        filter_id=filter_id,
        log_channel_id=LOG_CHANNEL_ID,
        message_id=log_msg.message_id,
        permanent_invite=permanent_invite or "",
        slot_channel_id=slot_channel_id,
    )

    return True, media_data["title"]

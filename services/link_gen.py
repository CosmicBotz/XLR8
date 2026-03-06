"""
Invite link generator — creates single-use, time-limited Telegram invite links.
No DB tracking needed for invite links anymore since we don't post to channels.
Scheduler still revokes via Telegram's own expiry (expire_date handles it).
"""
from aiogram import Bot
from datetime import datetime, timedelta


async def create_invite_link(bot: Bot, channel_id: int, revoke_minutes: int) -> str:
    """Create a single-use invite link that expires after revoke_minutes."""
    expire_time = datetime.utcnow() + timedelta(minutes=revoke_minutes)
    link = await bot.create_chat_invite_link(
        chat_id=channel_id,
        expire_date=expire_time,
        member_limit=1,
        creates_join_request=False
    )
    return link.invite_link

from aiogram import Bot
from datetime import datetime, timedelta
from database import CosmicBotz


async def create_invite_link(bot: Bot, channel_id: int, revoke_minutes: int) -> str:
    expire_time = datetime.utcnow() + timedelta(minutes=revoke_minutes)
    link = await bot.create_chat_invite_link(
        chat_id=channel_id,
        expire_date=expire_time,
        member_limit=1,
        creates_join_request=False
    )
    return link.invite_link


async def create_and_save_link(
    bot: Bot,
    channel_id: int,
    message_id: int,
    revoke_minutes: int
) -> tuple[str, datetime]:
    invite_link = await create_invite_link(bot, channel_id, revoke_minutes)
    _, expires_at = await CosmicBotz.save_post(channel_id, message_id, invite_link, revoke_minutes)
    return invite_link, expires_at


async def revoke_expired_links(bot: Bot):
    pending = await CosmicBotz.get_pending_revokes()
    for post in pending:
        try:
            await bot.revoke_chat_invite_link(
                chat_id=post["channel_id"],
                invite_link=post["invite_link"]
            )
        except Exception as e:
            print(f"⚠️ Revoke failed: {e}")
        finally:
            await CosmicBotz.mark_revoked(str(post["_id"]))

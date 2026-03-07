import functools
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message
from aiogram.enums import ChatType
from config import OWNER_ID
from database import CosmicBotz

logger = logging.getLogger(__name__)

_ALWAYS_ALLOWED = {"/start", "/verify", "/help"}


class AuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = data.get("event_from_user")
        chat = getattr(event, "chat", None)
        if chat is None and hasattr(event, "message"):
            chat = getattr(event.message, "chat", None)

        uid            = user.id if user else 0
        is_owner       = uid == OWNER_ID
        admins         = await CosmicBotz.get_admins() if uid else []
        is_admin_flag  = is_owner or (uid in admins)
        is_group       = bool(chat and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP))
        group_verified = True

        if is_group and chat:
            group_verified = await CosmicBotz.is_group_verified(chat.id)
            if not group_verified and not is_owner:
                if isinstance(event, Message):
                    text = event.text or ""
                    cmd  = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""
                    if cmd not in _ALWAYS_ALLOWED:
                        return
                else:
                    return

        data["is_owner"]       = is_owner
        data["is_admin"]       = is_admin_flag
        data["is_group"]       = is_group
        data["group_verified"] = group_verified

        return await handler(event, data)


# ── Decorators — use functools.wraps so aiogram 3 can inspect original sig ────

def owner_only(func):
    @functools.wraps(func)
    async def wrapper(message: Message, is_owner: bool = False, **kwargs):
        if not is_owner:
            await message.answer("⛔ This command is for the bot owner only.")
            return
        return await func(message, is_owner=is_owner, **kwargs)
    return wrapper


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(message: Message, is_admin: bool = False, **kwargs):
        if not is_admin:
            await message.answer("⛔ You don't have permission to use this command.")
            return
        return await func(message, is_admin=is_admin, **kwargs)
    return wrapper


def dm_only(func):
    @functools.wraps(func)
    async def wrapper(message: Message, is_group: bool = False, **kwargs):
        if is_group:
            await message.answer("⛔ This command only works in DM with the bot.")
            return
        return await func(message, is_group=is_group, **kwargs)
    return wrapper

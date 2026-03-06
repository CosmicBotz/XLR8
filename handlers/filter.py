"""
Filter handler — letter index + title search.
When user taps a result:
  → Delete user's search message + index message
  → Copy image + caption from log channel (no TMDB call)
  → Attach fresh expiring invite link button
  → Schedule deletion of both the sent post + user request after link expires
"""
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery

from database import CosmicBotz
from services.link_gen import create_invite_link
from services.caption import build_index_caption
from keyboards.inline import index_results_keyboard, watch_download_keyboard

router   = Router()
ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


# ── Auto-delete helper ────────────────────────────────────────────────────────

async def _delete_after(bot: Bot, chat_id: int, message_ids: list[int], delay: int):
    """Wait delay seconds then delete all given messages. Errors silently ignored."""
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


# ── Text: single letter or search ────────────────────────────────────────────

@router.message(F.text)
async def handle_text(
    message: Message,
    is_group: bool = False,
    group_verified: bool = True,
    **kwargs
):
    if is_group and not group_verified:
        return

    text = (message.text or "").strip()
    if text.startswith("/"):
        return

    # Single letter → index
    if len(text) == 1 and text.upper() in ALPHABET:
        letter  = text.upper()
        results = await CosmicBotz.get_by_letter(letter)
        if not results:
            await message.answer(
                f"📂 <b>Index: '{letter}'</b>\n\nNo titles found.",
                parse_mode="HTML"
            )
            return
        sent = await message.answer(
            build_index_caption(letter, results),
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )
        return

    # Multi-char → search
    if len(text) >= 2:
        results = await CosmicBotz.search_title(text)
        if not results:
            await message.answer(
                f"🔍 No results found for: <b>{text}</b>",
                parse_mode="HTML"
            )
            return
        await message.answer(
            f"🔍 <b>Search: '{text}'</b>\nFound: <b>{len(results)}</b> result(s)",
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )


# ── User taps a title button ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("show_"))
async def cb_show_title(call: CallbackQuery, bot: Bot):
    """
    1. Delete the index message + user's original search message
    2. Copy post from log channel with fresh expiring invite link
    3. After link expires → delete the sent post + user's callback message
    """
    filter_id = call.data.split("_", 1)[1]
    await call.answer()

    item = await CosmicBotz.get_filter_by_id(filter_id)
    if not item:
        await call.answer("⚠️ Title not found.", show_alert=True)
        return

    log_channel_id = item.get("log_channel_id")
    message_id     = item.get("message_id")

    if not log_channel_id or not message_id:
        await call.answer(
            "⚠️ This title hasn't been posted yet. Ask admin to re-add it.",
            show_alert=True
        )
        return

    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)
    slots          = await CosmicBotz.get_slots_all()

    # Generate fresh expiring invite link
    invite_link = None
    if slots:
        try:
            invite_link = await create_invite_link(bot, slots[0]["channel_id"], revoke_minutes)
        except Exception:
            invite_link = item.get("permanent_invite") or None

    kb = watch_download_keyboard(invite_link, f"{revoke_minutes} min") if invite_link else None

    chat_id = call.message.chat.id

    # ── Delete index message + user search message ────────────────────────────
    try:
        await call.message.delete()                    # index/search result msg
    except Exception:
        pass
    try:
        await bot.delete_message(chat_id, call.message.reply_to_message.message_id)  # user's text
    except Exception:
        pass

    # ── Send copied post ──────────────────────────────────────────────────────
    sent = None
    try:
        sent = await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=log_channel_id,
            message_id=message_id,
            reply_markup=kb
        )
    except Exception as e:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ Could not retrieve this title's post.\n<code>" + str(e) + "</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    # ── Schedule auto-delete after link expires ───────────────────────────────
    if sent:
        delay = revoke_minutes * 60
        # Delete: sent post + user's original callback message
        msgs_to_delete = [sent.message_id, call.message.message_id]
        asyncio.create_task(
            _delete_after(bot, chat_id, msgs_to_delete, delay)
        )


@router.callback_query(F.data.startswith("nf_"))
async def cb_not_found(call: CallbackQuery):
    await call.answer("⚠️ Title not available yet.", show_alert=True)

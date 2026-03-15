"""
Filter handler — letter index + title search.
- Single result → send post directly (user msg + post deleted together after timer)
- Multiple results → show buttons
- Group: all users get filter
- DM: owner/admin get full filter, regular users get join group message
- Silent on no results
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatType

from database import CosmicBotz
from services.caption import build_index_caption
from services.link_gen import create_invite_link
from keyboards.inline import index_results_keyboard, watch_download_keyboard, join_groups_keyboard
from utils.scheduler import task_manager

router   = Router()
ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


# ── Delete helper ─────────────────────────────────────────────────────────────

async def _delete_messages(bot: Bot, chat_id: int, message_ids: list):
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


# ── Send post helper ──────────────────────────────────────────────────────────

async def _send_post(
    bot: Bot,
    item: dict,
    chat_id: int,
    revoke_minutes: int,
    user_msg_id: int      # deleted together with post after timer
):
    slot_channel_id = item.get("slot_channel_id") or 0
    invite_link     = None

    if slot_channel_id:
        try:
            invite_link = await create_invite_link(bot, slot_channel_id, revoke_minutes)
        except Exception:
            invite_link = item.get("permanent_invite") or None
    else:
        slots = await CosmicBotz.get_slots_all()
        if slots:
            try:
                invite_link = await create_invite_link(bot, slots[0]["channel_id"], revoke_minutes)
            except Exception:
                invite_link = item.get("permanent_invite") or None

    kb = watch_download_keyboard(invite_link, str(revoke_minutes) + " min") if invite_link else None

    try:
        sent = await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=item["log_channel_id"],
            message_id=item["message_id"],
            reply_markup=kb,
            reply_to_message_id=user_msg_id if user_msg_id else None,
            allow_sending_without_reply=True
        )
    except Exception as e:
        try:
            await bot.send_message(chat_id, "⚠️ Could not retrieve post. Error: " + str(e))
        except Exception:
            pass
        return

    # Delete user msg + bot post together after timer
    await task_manager.schedule(
        _delete_messages(bot, chat_id, [sent.message_id, user_msg_id]),
        delay=revoke_minutes * 60
    )


# ── Join groups helper ────────────────────────────────────────────────────────

async def _send_join_groups(message: Message):
    groups = await CosmicBotz.get_verified_group_links()
    if groups:
        await message.answer(
            "📢 <b>Use me inside our group!</b>\n\nJoin a verified group to browse and get content:",
            reply_markup=join_groups_keyboard(groups),
            parse_mode="HTML"
        )
    else:
        await message.answer("📢 Use me inside a verified group to get content!")


# ── Filter core logic (shared by group and privileged DM) ────────────────────

async def _handle_filter(
    bot: Bot,
    message: Message,
    text: str,
    revoke_minutes: int
):
    # Single letter → index
    if len(text) == 1 and text.upper() in ALPHABET:
        letter  = text.upper()
        results = await CosmicBotz.get_by_letter(letter)
        if not results:
            return

        if len(results) == 1:
            item = results[0]
            if item.get("posted") and item.get("log_channel_id") and item.get("message_id"):
                await _send_post(bot, item, message.chat.id, revoke_minutes, message.message_id)
                return

        await message.answer(
            build_index_caption(letter, results),
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )
        return

    # Multi-char → search
    if len(text) >= 2:
        uid      = message.from_user.id if message.from_user else 0
        gid      = message.chat.id
        results  = await CosmicBotz.search_title(text)

        if not results:
            settings = await CosmicBotz.get_settings()
            if settings.get("missed_logging", True):
                await CosmicBotz.log_missed_search(text, uid, gid)
            return

        await CosmicBotz.log_search(text, uid, gid, found=True)

        if len(results) == 1:
            item = results[0]
            if item.get("posted") and item.get("log_channel_id") and item.get("message_id"):
                await _send_post(bot, item, message.chat.id, revoke_minutes, message.message_id)
                return

        title = "🔍 <b>Search: '" + text + "'</b>\nFound: <b>" + str(len(results)) + "</b> result(s)"
        await message.answer(
            title,
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )


# ── Text handler ──────────────────────────────────────────────────────────────

@router.message(F.text)
async def handle_text(
    message: Message,
    bot: Bot,
    is_group: bool     = False,
    is_admin: bool     = False,
    is_owner: bool     = False,
    group_verified: bool = True,
    **kwargs
):
    if is_group and not group_verified:
        return

    text = (message.text or "").strip()
    if text.startswith("/"):
        return

    is_private    = message.chat.type == ChatType.PRIVATE
    is_privileged = is_admin or is_owner

    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)

    # DM
    if is_private:
        if is_privileged:
            await _handle_filter(bot, message, text, revoke_minutes)
        elif (len(text) == 1 and text.upper() in ALPHABET) or len(text) >= 2:
            await _send_join_groups(message)
        return

    # Group
    await _handle_filter(bot, message, text, revoke_minutes)


# ── User taps a title button ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("show_"))
async def cb_show_title(
    call: CallbackQuery,
    bot: Bot,
    is_admin: bool = False,
    is_owner: bool = False,
    **kwargs
):
    await call.answer()

    filter_id = call.data.split("_", 1)[1]
    chat_id   = call.message.chat.id
    is_group  = call.message.chat.type in ("group", "supergroup")
    is_private = call.message.chat.type == ChatType.PRIVATE

    if is_private and not (is_admin or is_owner):
        await call.answer("📢 This works inside a verified group only!", show_alert=True)
        return

    item = await CosmicBotz.get_filter_by_id(filter_id)
    if not item:
        await call.answer("⚠️ Title not found.", show_alert=True)
        return

    if not item.get("log_channel_id") or not item.get("message_id"):
        await call.answer("⚠️ Not posted yet. Ask admin to re-add it.", show_alert=True)
        return

    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)

    # Original user search message (index msg is a reply to it)
    orig_msg_id = None
    if call.message.reply_to_message:
        orig_msg_id = call.message.reply_to_message.message_id

    # Delete index message immediately
    try:
        await call.message.delete()
    except Exception:
        pass

    await _send_post(bot, item, chat_id, revoke_minutes, orig_msg_id)


@router.callback_query(F.data.startswith("nf_"))
async def cb_not_found(call: CallbackQuery, **kwargs):
    await call.answer("⚠️ Title not available yet.", show_alert=True)

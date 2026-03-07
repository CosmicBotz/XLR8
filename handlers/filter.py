"""
Filter handler — letter index + title search.
- Single result → send post directly, no index step
- Multiple results → show buttons
- Group only for content delivery
- DM → show join group buttons
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


# ── Send post helper (reused by both direct & callback) ───────────────────────

async def _send_post(bot: Bot, item: dict, chat_id: int, reply_to: int, revoke_minutes: int, user_msg_id: int):
    """Fetch slot link, copy post, schedule deletion."""
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

    kb = watch_download_keyboard(invite_link, f"{revoke_minutes} min") if invite_link else None

    sent = None
    try:
        sent = await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=item["log_channel_id"],
            message_id=item["message_id"],
            reply_markup=kb,
            reply_to_message_id=reply_to
        )
    except Exception as e:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ Could not retrieve post.\n<code>" + str(e) + "</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass
        return

    if sent:
        delay = revoke_minutes * 60
        await task_manager.schedule(
            _delete_messages(bot, chat_id, [sent.message_id, user_msg_id]),
            delay=delay
        )


# ── Join groups helper ────────────────────────────────────────────────────────

async def _send_join_groups(message: Message):
    groups = await CosmicBotz.get_verified_group_links()
    if groups:
        await message.answer(
            "📢 <b>Use me inside our group!</b>\n\nJoin a verified group to browse & get content:",
            reply_markup=join_groups_keyboard(groups),
            parse_mode="HTML"
        )
    else:
        await message.answer("📢 Use me inside a verified group to get content!")


# ── Text handler ──────────────────────────────────────────────────────────────

@router.message(F.text)
async def handle_text(
    message: Message,
    bot: Bot,
    is_group: bool = False,
    is_admin: bool = False,
    is_owner: bool = False,
    group_verified: bool = True,
    **kwargs
):
    if is_group and not group_verified:
        return

    text = (message.text or "").strip()
    if text.startswith("/"):
        return

    is_private = message.chat.type == ChatType.PRIVATE

    # ── DM ────────────────────────────────────────────────────────────────────
    if is_private:
        is_privileged = is_admin or is_owner
        if not is_privileged:
            if (len(text) == 1 and text.upper() in ALPHABET) or len(text) >= 3:
                await _send_join_groups(message)
        return

    # ── GROUP ─────────────────────────────────────────────────────────────────
    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)

    # Single letter → index
    if len(text) == 1 and text.upper() in ALPHABET:
        letter  = text.upper()
        results = await CosmicBotz.get_by_letter(letter)
        if not results:
            return  # silent

        # Single result → send post directly, skip index
        if len(results) == 1:
            item = results[0]
            if item.get("posted") and item.get("log_channel_id") and item.get("message_id"):
                await message.delete()  # delete user's letter msg
                await _send_post(bot, item, message.chat.id, 0, revoke_minutes, message.message_id)
                return

        await message.answer(
            build_index_caption(letter, results),
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )
        return

    # Multi-char → search
    if len(text) >= 2:
        results = await CosmicBotz.search_title(text)
        if not results:
            return  # silent

        # Single result → send post directly
        if len(results) == 1:
            item = results[0]
            if item.get("posted") and item.get("log_channel_id") and item.get("message_id"):
                await message.delete()
                await _send_post(bot, item, message.chat.id, 0, revoke_minutes, message.message_id)
                return

        await message.answer(
            f"🔍 <b>Search: '{text}'</b>\nFound: <b>{len(results)}</b> result(s)",
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )


# ── User taps a title button ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("show_"))
async def cb_show_title(call: CallbackQuery, bot: Bot):
    filter_id = call.data.split("_", 1)[1]
    chat_id   = call.message.chat.id
    is_group  = call.message.chat.type in ("group", "supergroup")

    await call.answer()

    if not is_group:
        await call.answer("📢 This feature only works inside a verified group!", show_alert=True)
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

    # Delete bot index message
    try:
        await call.message.delete()
    except Exception:
        pass

    user_search_msg_id = call.message.message_id - 1
    await _send_post(bot, item, chat_id, user_search_msg_id, revoke_minutes, user_search_msg_id)


@router.callback_query(F.data.startswith("nf_"))
async def cb_not_found(call: CallbackQuery):
    await call.answer("⚠️ Title not available yet.", show_alert=True)

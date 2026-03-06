"""
Filter handler — letter index + title search.
When user taps a result:
  → Bot copies image + caption from log channel message (no TMDB call)
  → Adds a NEW expiring invite link button (fresh each request)
Works in DMs and verified groups.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatType

from database import CosmicBotz
from services.link_gen import create_invite_link
from services.caption import build_index_caption
from keyboards.inline import index_results_keyboard, watch_download_keyboard

router   = Router()
ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


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
    Copy image + caption from log channel post.
    Attach a fresh expiring invite link button.
    No TMDB call — reuses what was stored on /addcontent.
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

    # Generate fresh expiring invite link
    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)
    slots          = await CosmicBotz.get_slots_all()

    invite_link = None
    if slots:
        try:
            invite_link = await create_invite_link(bot, slots[0]["channel_id"], revoke_minutes)
        except Exception:
            # Fall back to permanent invite if generating fails
            invite_link = item.get("permanent_invite") or None

    kb = watch_download_keyboard(invite_link, f"{revoke_minutes} min") if invite_link else None

    # Copy the log channel message to user with new button
    try:
        await bot.copy_message(
            chat_id=call.message.chat.id,
            from_chat_id=log_channel_id,
            message_id=message_id,
            reply_markup=kb
        )
    except Exception as e:
        await call.message.answer(
            f"⚠️ Could not retrieve this title's post.\n<code>{e}</code>",
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("nf_"))
async def cb_not_found(call: CallbackQuery):
    await call.answer("⚠️ Title not available yet.", show_alert=True)

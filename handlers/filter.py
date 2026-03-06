"""
Filter handler — letter index + title search.
When user taps a result → bot sends poster + caption + Watch/Download invite link.
Works in both DMs and verified groups.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, URLInputFile

from database import CosmicBotz
from services.caption import build_caption, build_index_caption
from services.link_gen import create_invite_link
from keyboards.inline import index_results_keyboard, watch_download_keyboard
from config import LOG_CHANNEL_ID

router  = Router()
ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")


# ── Text handler: single letter or search query ───────────────────────────────

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

    # Single letter → index browse
    if len(text) == 1 and text.upper() in ALPHABET:
        letter  = text.upper()
        results = await CosmicBotz.get_by_letter(letter)
        if not results:
            await message.answer(
                f"📂 <b>Index: '{letter}'</b>\n\nNo titles found for this letter.",
                parse_mode="HTML"
            )
            return
        await message.answer(
            build_index_caption(letter, results),
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )
        return

    # Multi-char → title search
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
async def cb_show_title(call: CallbackQuery):
    """
    User tapped a title from the index.
    Bot sends: poster + caption + Watch/Download invite link button.
    """
    from bson import ObjectId
    filter_id = call.data.split("_", 1)[1]

    await call.answer()

    item = await CosmicBotz.get_filter_by_id(filter_id)
    if not item:
        await call.answer("⚠️ Title not found.", show_alert=True)
        return

    # Get the slot's channel to generate invite link from
    slots = await CosmicBotz.get_slots_all()
    if not slots:
        await call.answer("⚠️ No channel configured yet.", show_alert=True)
        return

    # Use first active slot to generate invite link
    slot = slots[0]
    channel_id = slot["channel_id"]

    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)

    try:
        from aiogram import Bot
        bot = call.bot
        invite_link = await create_invite_link(bot, channel_id, revoke_minutes)
    except Exception as e:
        await call.message.answer(
            f"⚠️ Could not generate link. Make sure bot is admin in the channel.\n<code>{e}</code>",
            parse_mode="HTML"
        )
        return

    caption  = build_caption(item)
    poster   = item.get("poster_url")
    expires  = f"{revoke_minutes} min"
    kb       = watch_download_keyboard(invite_link, expires)

    try:
        if poster:
            await call.message.answer_photo(
                photo=URLInputFile(poster),
                caption=caption,
                reply_markup=kb,
                parse_mode="HTML"
            )
        else:
            await call.message.answer(
                caption,
                reply_markup=kb,
                parse_mode="HTML"
            )
    except Exception:
        await call.message.answer(caption, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("nf_"))
async def cb_not_found(call: CallbackQuery):
    await call.answer("⚠️ Title not available yet.", show_alert=True)

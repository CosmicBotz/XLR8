"""
Filter handler — letter index + title search.

GROUP only for content delivery.
DM: show join group buttons, no content.
Silent on no results — never send "not found" noise.
"""
from datetime import datetime, timedelta, timezone
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatType

from database import CosmicBotz
from services.caption import build_index_caption
from keyboards.inline import index_results_keyboard, watch_download_keyboard, join_groups_keyboard

router   = Router()
ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789")

# Keep strong references to tasks so GC doesn't cancel them before they fire
_pending_tasks: set = set()


async def _delete_after(bot: Bot, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass


async def _send_join_groups(message: Message):
    """DM: show inline buttons to all verified groups with invite links."""
    groups = await CosmicBotz.get_verified_group_links()
    if groups:
        kb = join_groups_keyboard(groups)
        await message.answer(
            "📢 <b>Use me inside our group!</b>\n\nJoin a verified group to browse & get content:",
            reply_markup=kb,
            parse_mode="HTML"
        )
    else:
        await message.answer("📢 Use me inside a verified group to get content!")


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

    is_private = message.chat.type == ChatType.PRIVATE

    # ── DM → show join group buttons, never content ───────────────────────────
    if is_private:
        if len(text) == 1 and text.upper() in ALPHABET:
            await _send_join_groups(message)
        elif len(text) >= 2:
            # Only respond if it looks like an anime/show request — 2+ words or known pattern
            # Silent on short casual text to avoid spam
            if len(text) >= 3:
                await _send_join_groups(message)
        return

    # ── GROUP ─────────────────────────────────────────────────────────────────

    # Single letter → index
    if len(text) == 1 and text.upper() in ALPHABET:
        letter  = text.upper()
        results = await CosmicBotz.get_by_letter(letter)
        if not results:
            return  # silent — no "not found" noise
        await message.answer(
            build_index_caption(letter, results),
            reply_markup=index_results_keyboard(results),
            parse_mode="HTML"
        )
        return

    # Multi-char search — silent if no match, never interrupt normal chat
    if len(text) >= 2:
        results = await CosmicBotz.search_title(text)
        if not results:
            return  # silent
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
        await call.answer(
            "📢 This feature only works inside a verified group!",
            show_alert=True
        )
        return

    item = await CosmicBotz.get_filter_by_id(filter_id)
    if not item:
        await call.answer("⚠️ Title not found.", show_alert=True)
        return

    log_channel_id = item.get("log_channel_id")
    message_id     = item.get("message_id")

    if not log_channel_id or not message_id:
        await call.answer(
            "⚠️ This title has not been posted yet. Ask admin to re-add it.",
            show_alert=True
        )
        return

    settings       = await CosmicBotz.get_settings()
    revoke_minutes = settings.get("auto_revoke_minutes", 30)

    # Get this group's stored invite link
    group_doc    = await CosmicBotz.get_group(chat_id)
    group_invite = group_doc.get("invite_link", "") if group_doc else ""

    # Generate one on the fly if missing
    if not group_invite:
        try:
            link         = await bot.create_chat_invite_link(chat_id=chat_id, creates_join_request=False)
            group_invite = link.invite_link
            await CosmicBotz.db().groups.update_one(
                {"group_id": chat_id},
                {"$set": {"invite_link": group_invite}}
            )
        except Exception:
            pass

    kb = watch_download_keyboard(group_invite, f"{revoke_minutes} min") if group_invite else None

    # Delete bot index message immediately
    try:
        await call.message.delete()
    except Exception:
        pass

    # Send post in group — reply to user's original search message
    user_search_msg_id = call.message.message_id - 1
    sent = None
    try:
        sent = await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=log_channel_id,
            message_id=message_id,
            reply_markup=kb,
            reply_to_message_id=user_search_msg_id
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

    # After link expires: delete bot post + user's search msg
    if sent:
        delay = revoke_minutes * 60
        from utils.scheduler import scheduler
        from config import BOT_TOKEN
        run_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
        scheduler.add_job(
            _delete_messages,
            trigger="date",
            run_date=run_at,
            args=[chat_id, [sent.message_id, user_search_msg_id], BOT_TOKEN],
            misfire_grace_time=120
        )


@router.callback_query(F.data.startswith("nf_"))
async def cb_not_found(call: CallbackQuery):
    await call.answer("⚠️ Title not available yet.", show_alert=True)

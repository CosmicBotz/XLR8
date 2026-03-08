from aiogram import Router, F, Bot
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.enums import ChatType

from database import CosmicBotz
from middlewares.auth import owner_only, admin_only
from keyboards.inline import quick_add_slot_keyboard, quick_tmdb_keyboard
from config import OWNER_ID
import logging

logger = logging.getLogger(__name__)
router = Router()


# ── Bot promoted to admin in a CHANNEL ───────────────────────────────────────

@router.my_chat_member()
async def bot_channel_admin(event: ChatMemberUpdated, bot: Bot):
    """Fires when bot's status changes in any chat."""
    chat      = event.chat
    new_stat  = event.new_chat_member.status
    old_stat  = event.old_chat_member.status
    added_by  = event.from_user.id if event.from_user else None

    # Only care about channel promotions
    if chat.type != ChatType.CHANNEL:
        return
    if new_stat != "administrator":
        return
    if old_stat == "administrator":
        return  # already was admin, ignore

    logger.info(f"Bot promoted to admin in channel: {chat.title} ({chat.id}) by {added_by}")

    # ── Owner added the bot → auto add slot + search TMDB immediately ────────
    if added_by == OWNER_ID:
        from services.content import clean_channel_name
        from services.tmdb import search_tmdb

        ok, msg = await CosmicBotz.add_slot(
            owner_id=OWNER_ID,
            channel_id=chat.id,
            channel_name=chat.title or str(chat.id),
            slot_name=chat.title or str(chat.id)
        )

        if not ok:
            try:
                await bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        "📡 <b>Channel detected</b> — <b>" + (chat.title or str(chat.id)) + "</b>\n\n"
                        "⚠️ Slot not added: " + msg
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        query = clean_channel_name(chat.title or "")

        try:
            results = await search_tmdb(query, "multi")
        except Exception as e:
            try:
                await bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        "✅ Slot saved for <b>" + (chat.title or str(chat.id)) + "</b>\n\n"
                        "⚠️ TMDB search failed: " + str(e) + "\n"
                        "Use /addcontent to add content manually."
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        if not results:
            try:
                await bot.send_message(
                    chat_id=OWNER_ID,
                    text=(
                        "✅ Slot saved for <b>" + (chat.title or str(chat.id)) + "</b>\n\n"
                        "❌ No TMDB results for <b>" + query + "</b>\n"
                        "Use /addcontent to add content manually."
                    ),
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text=(
                    "✅ Slot saved!\n\n"
                    "🎬 Pick the correct title for <b>" + (chat.title or str(chat.id)) + "</b>:"
                ),
                reply_markup=quick_tmdb_keyboard(results, chat.id),
                parse_mode="HTML"
            )
        except Exception as e:
            logger.warning(f"Could not send TMDB picker to owner: {e}")

        return

    # ── Admin or unknown added the bot → ask confirmation as before ───────────
    notify_text = (
        "📡 <b>Bot added as admin in a channel!</b>\n\n"
        "🏷 Channel: <b>" + (chat.title or "Unknown") + "</b>\n"
        "🆔 ID: <code>" + str(chat.id) + "</code>\n\n"
        "Do you want to add this channel as a content slot?"
    )

    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=notify_text,
            reply_markup=quick_add_slot_keyboard(chat.id, chat.title or ""),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.warning(f"Could not notify owner about channel admin: {e}")

    # Notify all admins
    try:
        admins = await CosmicBotz.get_admins()
        for admin_id in admins:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=notify_text,
                    reply_markup=quick_add_slot_keyboard(chat.id, chat.title or ""),
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception:
        pass


# ── Bot added to group ────────────────────────────────────────────────────────

@router.my_chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def bot_added_to_group(event: ChatMemberUpdated, bot: Bot):
    chat = event.chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return

    added_by = event.from_user.id
    await CosmicBotz.add_group(chat.id, chat.title, added_by)
    logger.info(f"Bot added to group: {chat.title} ({chat.id}) by {added_by}")

    await bot.send_message(
        chat_id=chat.id,
        text=(
            "👋 Hello! I'm <b>Auto Filter CosmicBotz</b>.\n\n"
            "⚠️ I'm not fully active yet.\n\n"
            "🔐 An owner or admin must send <b>/verify</b> in this group "
            "to unlock all features.\n\n"
            "Until then I'll only respond to /start."
        ),
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=(
                f"📢 Bot added to a new group!\n\n"
                f"🏷 Name: <b>{chat.title}</b>\n"
                f"🆔 ID: <code>{chat.id}</code>\n"
                f"👤 Added by: <code>{added_by}</code>\n\n"
                f"Send /verify inside the group, or:\n"
                f"/verifygroup <code>{chat.id}</code> from here."
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass


# ── Bot removed from group ────────────────────────────────────────────────────

@router.my_chat_member()
async def bot_left_group(event: ChatMemberUpdated):
    if event.new_chat_member.status in ("left", "kicked"):
        await CosmicBotz.remove_group(event.chat.id)
        logger.info(f"Bot removed from: {event.chat.title} ({event.chat.id})")


# ── /verify (inside group) ────────────────────────────────────────────────────

@router.message(Command("verify"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def cmd_verify_group(message: Message, bot: Bot, is_admin: bool = False, **kwargs):
    if not is_admin:
        await message.answer("⛔ Only the bot owner or admins can verify groups.")
        return

    await CosmicBotz.add_group(message.chat.id, message.chat.title, message.from_user.id)

    invite_link = ""
    try:
        link = await bot.create_chat_invite_link(
            chat_id=message.chat.id,
            creates_join_request=False
        )
        invite_link = link.invite_link
    except Exception:
        pass

    ok = await CosmicBotz.verify_group(message.chat.id, message.from_user.id, invite_link)

    if ok:
        await message.answer(
            f"✅ <b>{message.chat.title}</b> is now verified!\n\n"
            "All bot features are now active:\n"
            "• Send a letter (A–Z) to browse the index\n"
            "• Search titles by name\n"
            "• Admins can use management commands here",
            parse_mode="HTML"
        )
    else:
        await message.answer("⚠️ Could not verify this group. Try again.")


# ── /verifygroup GROUP_ID (from DM) ──────────────────────────────────────────

@router.message(Command("verifygroup"), F.chat.type == ChatType.PRIVATE)
@owner_only
async def cmd_verify_by_id(message: Message, bot: Bot, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/verifygroup GROUP_ID</code>", parse_mode="HTML")
        return
    try:
        group_id = int(args[1].strip())
    except ValueError:
        await message.answer("⚠️ Invalid group ID.")
        return

    ok = await CosmicBotz.verify_group(group_id, message.from_user.id)
    if ok:
        await message.answer(f"✅ Group <code>{group_id}</code> verified.", parse_mode="HTML")
        try:
            await bot.send_message(
                chat_id=group_id,
                text="✅ This group has been verified by the bot owner. All features are now active!"
            )
        except Exception:
            pass
    else:
        await message.answer("⚠️ Failed to verify group.")


# ── /unverify ─────────────────────────────────────────────────────────────────

@router.message(Command("unverify"), F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
@owner_only
async def cmd_unverify_group(message: Message, **kwargs):
    await CosmicBotz.unverify_group(message.chat.id)
    await message.answer(
        "🔒 This group has been <b>unverified</b>. "
        "Features are restricted until re-verified.",
        parse_mode="HTML"
    )


# ── /groups (owner DM) ────────────────────────────────────────────────────────

@router.message(Command("groups"), F.chat.type == ChatType.PRIVATE)
@owner_only
async def cmd_list_groups(message: Message, **kwargs):
    all_groups = await CosmicBotz.get_all_groups()
    if not all_groups:
        await message.answer("📭 No groups registered yet.")
        return

    verified = [g for g in all_groups if g.get("verified")]
    pending  = [g for g in all_groups if not g.get("verified")]
    lines    = [f"📋 <b>All Groups ({len(all_groups)})</b>\n"]

    if verified:
        lines.append(f"✅ <b>Verified ({len(verified)}):</b>")
        for g in verified:
            lines.append(f"  • <b>{g['group_name']}</b> — <code>{g['group_id']}</code>")

    if pending:
        lines.append(f"\n⏳ <b>Pending ({len(pending)}):</b>")
        for g in pending:
            lines.append(
                f"  • <b>{g['group_name']}</b> — <code>{g['group_id']}</code>\n"
                f"    /verifygroup {g['group_id']}"
            )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ── Callbacks ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "qslot_ignore")
async def cb_qslot_ignore(call: CallbackQuery, **kwargs):
    await call.answer()
    await call.message.edit_text("❌ Channel ignored.")


@router.callback_query(F.data == "qslot_cancel")
async def cb_qslot_cancel(call: CallbackQuery, **kwargs):
    await call.answer()
    await call.message.edit_text("❌ Cancelled.")


@router.callback_query(F.data.startswith("qslot_add|"))
async def cb_quick_slot_add(call: CallbackQuery, bot: Bot, is_owner: bool = False, is_admin: bool = False, **kwargs):
    await call.answer()

    if not (is_owner or is_admin):
        await call.answer("⛔ Not allowed.", show_alert=True)
        return

    # qslot_add|channel_id|name_truncated
    parts        = call.data.split("|", 2)
    channel_id   = int(parts[1])
    channel_name = parts[2] if len(parts) > 2 else str(channel_id)

    ok, msg = await CosmicBotz.add_slot(
        owner_id=call.from_user.id,
        channel_id=channel_id,
        channel_name=channel_name,
        slot_name=channel_name
    )

    if not ok:
        await call.message.edit_text("⚠️ " + msg)
        return

    from services.content import clean_channel_name
    from services.tmdb import search_tmdb

    query = clean_channel_name(channel_name)
    await call.message.edit_text(
        "✅ Slot saved!\n\n"
        "🔍 Searching TMDB for: <b>" + query + "</b>...",
        parse_mode="HTML"
    )

    try:
        results = await search_tmdb(query, "multi")
    except Exception as e:
        await call.message.edit_text(
            "✅ Slot saved!\n\n"
            "⚠️ TMDB search failed: " + str(e) + "\n"
            "Use /addcontent to add content manually.",
            parse_mode="HTML"
        )
        return

    if not results:
        await call.message.edit_text(
            "✅ Slot saved!\n\n"
            "❌ No TMDB results for <b>" + query + "</b>\n"
            "Use /addcontent to add content manually.",
            parse_mode="HTML"
        )
        return

    await call.message.edit_text(
        "✅ Slot saved!\n\n"
        "🎬 Pick the correct title for <b>" + channel_name + "</b>:",
        reply_markup=quick_tmdb_keyboard(results, channel_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("qslot_tmdb|"))
async def cb_quick_slot_tmdb(call: CallbackQuery, bot: Bot, is_owner: bool = False, is_admin: bool = False, **kwargs):
    await call.answer("⏳ Posting content...")

    if not (is_owner or is_admin):
        await call.answer("⛔ Not allowed.", show_alert=True)
        return

    # qslot_tmdb|channel_id|tmdb_id|media_type
    parts      = call.data.split("|")
    channel_id = int(parts[1])
    tmdb_id    = int(parts[2])
    tmdb_type  = parts[3]

    await call.message.edit_text("⏳ Fetching details and posting...")

    from services.tmdb import get_tv_details, get_movie_details, build_media_data
    from services.content import post_content

    try:
        if tmdb_type == "movie":
            details    = await get_movie_details(tmdb_id)
            media_data = build_media_data(details, "movie")
        else:
            details   = await get_tv_details(tmdb_id)
            genre_ids = [g.get("id") for g in details.get("genres", [])]
            mtype     = "anime" if 16 in genre_ids else "tvshow"
            media_data = build_media_data(details, mtype)
    except Exception as e:
        await call.message.edit_text("❌ TMDB fetch failed: " + str(e))
        return

    ok, result = await post_content(bot, media_data, channel_id)

    if ok:
        await call.message.edit_text(
            "✅ <b>" + result + "</b> added to index!\n\n"
            "📋 Posted to Log Channel with invite link.\n"
            "Users can now find it by searching.",
            parse_mode="HTML"
        )
        try:
            await bot.send_message(
                chat_id=OWNER_ID,
                text=(
                    "🎉 <b>Filter Added!</b>\n\n"
                    "📌 Title: <b>" + result + "</b>\n"
                    "📢 Channel: <code>" + str(channel_id) + "</code>\n\n"
                    "✅ Users can now search and find this title."
                ),
                parse_mode="HTML"
            )
        except Exception:
            pass
    else:
        await call.message.edit_text("❌ " + result)

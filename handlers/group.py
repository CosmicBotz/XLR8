from aiogram import Router, F, Bot
from aiogram.types import Message, ChatMemberUpdated
from aiogram.filters import Command, ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION
from aiogram.enums import ChatType

from database import CosmicBotz
from middlewares.auth import owner_only, admin_only
from keyboards.inline import quick_add_slot_keyboard
from config import OWNER_ID
import logging

logger = logging.getLogger(__name__)
router = Router()



# ── Bot promoted to admin in a CHANNEL ───────────────────────────────────────

@router.my_chat_member()
async def bot_channel_admin(event: ChatMemberUpdated, bot: Bot):
    """Fires when bot's status changes in any chat."""
    chat     = event.chat
    new_stat = event.new_chat_member.status
    old_stat = event.old_chat_member.status

    # Only care about channel promotions
    if chat.type != ChatType.CHANNEL:
        return
    if new_stat != "administrator":
        return
    if old_stat == "administrator":
        return  # already was admin, ignore

    logger.info(f"Bot promoted to admin in channel: {chat.title} ({chat.id})")

    # Notify owner
    try:
        await bot.send_message(
            chat_id=OWNER_ID,
            text=(
                "📡 <b>Bot added as admin in a channel!</b>\n\n"
                "🏷 Channel: <b>" + (chat.title or "Unknown") + "</b>\n"
                "🆔 ID: <code>" + str(chat.id) + "</code>\n\n"
                "Do you want to add this channel as a content slot?"
            ),
            reply_markup=quick_add_slot_keyboard(chat.id, chat.title or "Unknown"),
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
                    text=(
                        "📡 <b>Bot added as admin in a channel!</b>\n\n"
                        "🏷 Channel: <b>" + (chat.title or "Unknown") + "</b>\n"
                        "🆔 ID: <code>" + str(chat.id) + "</code>\n\n"
                        "Do you want to add this channel as a content slot?"
                    ),
                    reply_markup=quick_add_slot_keyboard(chat.id, chat.title or "Unknown"),
                    parse_mode="HTML"
                )
            except Exception:
                pass
    except Exception:
        pass


# ── Callback: quick add slot ──────────────────────────────────────────────────

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

    # Generate permanent invite link for the group
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


@router.callback_query(F.data.startswith("qslot_"))
async def cb_quick_slot(call: CallbackQuery, bot: Bot, is_owner: bool = False, is_admin: bool = False, **kwargs):
    await call.answer()

    if not (is_owner or is_admin):
        await call.answer("⛔ Not allowed.", show_alert=True)
        return

    if call.data == "qslot_ignore":
        await call.message.edit_text("❌ Channel ignored.")
        return

    # qslot_add|channel_id|channel_name
    parts = call.data.split("|", 2)
    if len(parts) < 3:
        await call.message.edit_text("⚠️ Invalid data.")
        return

    channel_id   = int(parts[1])
    channel_name = parts[2]

    ok, msg = await CosmicBotz.add_slot(
        owner_id=call.from_user.id,
        channel_id=channel_id,
        channel_name=channel_name,
        slot_name=channel_name
    )

    if ok:
        await call.message.edit_text(
            "✅ <b>" + channel_name + "</b> added as a slot!\n\n"
            "Use /addcontent to post content to this slot.",
            parse_mode="HTML"
        )
    else:
        await call.message.edit_text("⚠️ " + msg)

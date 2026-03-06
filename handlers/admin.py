from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType, ParseMode

from database import CosmicBotz
from middlewares.auth import owner_only, admin_only, dm_only
from keyboards.inline import (
    slot_list_keyboard, 
    admin_list_keyboard,
    confirm_delete_keyboard,
    delete_search_keyboard,
    confirm_remove_slot_keyboard  # New: For /removeslot confirmation
)

router = Router()

# Global bot instance (assuming it's passed or accessible)
# bot: Bot = ...  # Set this in your main.py or pass via middleware


class AddSlotState(StatesGroup):
    waiting_channel_id = State()
    waiting_slot_name = State()


class AddAdminState(StatesGroup):
    waiting_user_id = State()  # New: FSM for safer admin addition


# ── /addslot — Enhanced with better validation & progress feedback ────────────

@router.message(Command("addslot"))
@owner_only
@dm_only
async def cmd_addslot(message: Message, state: FSMContext):
    await message.answer(
        "➕ <b>Add New Slot</b>\n\n"
        "Step 1/2: Forward a message from the <b>target channel</b>, "
        "or send its ID (e.g. <code>-1001234567890</code>).\n\n"
        "💡 <i>Tip: Bot must be admin in the channel.</i>",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(AddSlotState.waiting_channel_id)


@router.message(AddSlotState.waiting_channel_id)
async def slot_got_channel(message: Message, state: FSMContext):
    channel_id = None
    channel_name = "Unknown"

    if message.forward_from_chat:
        channel_id = message.forward_from_chat.id
        channel_name = message.forward_from_chat.title or "Unnamed Channel"
    elif message.text and message.text.lstrip("-").isdigit():
        try:
            channel_id = int(message.text.strip())
            # Optional: Fetch channel info via bot.get_chat for better UX
            # chat = await bot.get_chat(channel_id)
            # channel_name = chat.title or str(channel_id)
        except ValueError:
            pass
    else:
        await message.answer(
            "⚠️ <b>Invalid input!</b>\n\n"
            "Please forward a message or send a valid channel ID.",
            parse_mode=ParseMode.HTML
        )
        return

    if channel_id is None:
        await message.answer("❌ Failed to extract channel ID. Try again.", parse_mode=ParseMode.HTML)
        return

    await state.update_data(channel_id=channel_id, channel_name=channel_name)
    await message.answer(
        f"✅ <b>Channel Selected:</b> {channel_name} (<code>{channel_id}</code>)\n\n"
        "Step 2/2: Send a <b>friendly name/label</b> for this slot\n"
        "(e.g. <i>Anime Hindi Dub</i>):",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(AddSlotState.waiting_slot_name)


@router.message(AddSlotState.waiting_slot_name)
async def slot_got_name(message: Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data["channel_id"]
    channel_name = data["channel_name"]
    slot_name = message.text.strip()[:50]  # Limit length for sanity

    if not slot_name:
        await message.answer("⚠️ Slot name cannot be empty. Try again.", parse_mode=ParseMode.HTML)
        return

    await state.clear()

    try:
        ok, msg = await CosmicBotz.add_slot(
            message.from_user.id, channel_id, channel_name, slot_name
        )
        if ok:
            await message.answer(
                f"🎉 <b>Slot Added!</b>\n\n"
                f"📢 <b>{slot_name}</b> → {channel_name}\n\n"
                "Next: Use <code>/addcontent</code> to post to this slot.",
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer(f"❌ {msg}", parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.answer(f"❌ Unexpected error: {str(e)}", parse_mode=ParseMode.HTML)


# ── /slots — With quick actions inline ────────────────────────────────────────

@router.message(Command("slots"))
@owner_only
async def cmd_slots(message: Message):
    try:
        slots = await CosmicBotz.get_slots(message.from_user.id)
        if not slots:
            await message.answer(
                "📭 <b>No Slots Yet</b>\n\n"
                "Get started with <code>/addslot</code>!",
                parse_mode=ParseMode.HTML
            )
            return
        text = f"📋 <b>Your Slots ({len(slots)})</b>\n\nTap to manage:"
        await message.answer(
            text,
            reply_markup=slot_list_keyboard(slots),  # Assume this has remove/edit buttons
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await message.answer("❌ Failed to load slots. Try again.", parse_mode=ParseMode.HTML)


# ── /removeslot — Safer with confirmation ─────────────────────────────────────

@router.message(Command("removeslot"))
@owner_only
async def cmd_removeslot(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🗑 <b>Remove Slot</b>\n\n"
            "Usage: <code>/removeslot CHANNEL_ID</code>\n\n"
            "💡 List your slots first with <code>/slots</code> to copy ID.",
            parse_mode=ParseMode.HTML
        )
        return
    try:
        channel_id = int(args[1].strip())
    except ValueError:
        await message.answer("⚠️ <b>Invalid ID!</b> Must be a number.", parse_mode=ParseMode.HTML)
        return

    # Check if slot exists first
    slots = await CosmicBotz.get_slots(message.from_user.id)
    slot = next((s for s in slots if s['channel_id'] == channel_id), None)
    if not slot:
        await message.answer("⚠️ Slot not found for this ID.", parse_mode=ParseMode.HTML)
        return

    # Inline confirmation
    await message.answer(
        f"⚠️ <b>Confirm Remove?</b>\n\n"
        f"📢 Slot: <b>{slot['name']}</b> ({slot['channel_name']})\n\n"
        f"This can't be undone!",
        reply_markup=confirm_remove_slot_keyboard(channel_id, slot['name']),
        parse_mode=ParseMode.HTML
    )


# New callback for slot removal confirmation (add to keyboards.inline.py)
@router.callback_query(F.data.startswith("rmslot_"))
async def cb_confirm_remove_slot(call: CallbackQuery):
    try:
        channel_id = int(call.data.split("_")[1])
        ok = await CosmicBotz.remove_slot(call.from_user.id, channel_id)
        if ok:
            await call.message.edit_text(f"✅ <b>Slot Removed!</b>\n\nUse /slots to view updated list.", parse_mode=ParseMode.HTML)
            await call.answer("Removed!")
        else:
            await call.answer("Failed to remove.", show_alert=True)
    except Exception:
        await call.answer("Error removing slot.", show_alert=True)


# ── /addadmin — FSM for safer input, with user mention if possible ────────────

@router.message(Command("addadmin"))
@owner_only
async def cmd_addadmin(message: Message, state: FSMContext):
    await message.answer(
        "👥 <b>Add Admin</b>\n\n"
        "Send the <b>User ID</b> (e.g. <code>123456789</code>).\n\n"
        "💡 <i>Tip: Forward a message from them to auto-fill.</i>",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(AddAdminState.waiting_user_id)


@router.message(AddAdminState.waiting_user_id)
async def admin_got_id(message: Message, state: FSMContext):
    user_id = None
    user_mention = "Unknown User"

    if message.forward_from:
        user_id = message.forward_from.id
        user_mention = f"@{message.forward_from.username or user_mention}"
    elif message.text and message.text.lstrip("-").isdigit():
        try:
            user_id = abs(int(message.text.strip()))  # Handle negative IDs
        except ValueError:
            pass

    if user_id is None:
        await message.answer("⚠️ <b>Invalid input!</b> Send a User ID or forward a message.", parse_mode=ParseMode.HTML)
        return

    await state.clear()
    try:
        await CosmicBotz.add_admin(user_id)
        await message.answer(
            f"✅ <b>{user_mention}</b> (<code>{user_id}</code>) added as admin!\n\n"
            "They can now use <code>/addcontent</code>, <code>/delcontent</code>, etc.",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}", parse_mode=ParseMode.HTML)


@router.message(Command("removeadmin"))
@owner_only
async def cmd_removeadmin(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/removeadmin USER_ID</code>\n💡 See /admins for list.", parse_mode=ParseMode.HTML)
        return
    try:
        user_id = int(args[1].strip())
    except ValueError:
        await message.answer("⚠️ Invalid User ID.", parse_mode=ParseMode.HTML)
        return

    try:
        await CosmicBotz.remove_admin(user_id)
        await message.answer(f"✅ Admin <code>{user_id}</code> removed.", parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer("❌ Not found or error occurred.", parse_mode=ParseMode.HTML)


@router.message(Command("admins"))
@owner_only
async def cmd_list_admins(message: Message):
    try:
        admins = await CosmicBotz.get_admins()
        if not admins:
            await message.answer(
                "👥 <b>No Admins</b>\n\nAdd one with <code>/addadmin</code>!",
                parse_mode=ParseMode.HTML
            )
            return
        text = f"👥 <b>Admins ({len(admins)})</b>\n\nTap to remove:"
        await message.answer(
            text,
            reply_markup=admin_list_keyboard(admins),
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await message.answer("❌ Failed to load admins.", parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("rmadmin_"))
async def cb_remove_admin(call: CallbackQuery):
    try:
        uid = int(call.data.split("_")[1])
        await CosmicBotz.remove_admin(uid)
        await call.answer(f"✅ Removed {uid}")
        await call.message.edit_text(
            f"✅ Admin <code>{uid}</code> removed.\n\nUpdated list:",
            reply_markup=admin_list_keyboard(await CosmicBotz.get_admins()),  # Refresh list
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await call.answer("Error removing admin.", show_alert=True)


# ── /setrevoke — With validation & preview ───────────────────────────────────

@router.message(Command("setrevoke"))
@owner_only
async def cmd_setrevoke(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        settings = await CosmicBotz.get_settings()
        current = settings.get("auto_revoke_minutes", 30)
        await message.answer(
            f"⏱ <b>Auto-Revoke Timer</b>\n\n"
            f"Current: <b>{current} minutes</b>\n\n"
            f"Set new: <code>/setrevoke {current + 10}</code>\n"
            f"(Min: 1 min)",
            parse_mode=ParseMode.HTML
        )
        return
    try:
        minutes = int(args[1].strip())
        if minutes < 1 or minutes > 1440:  # Max 1 day
            raise ValueError("Out of range (1-1440 min)")
    except ValueError:
        await message.answer("⚠️ Valid number? (1-1440 minutes)", parse_mode=ParseMode.HTML)
        return
    await CosmicBotz.update_setting("auto_revoke_minutes", minutes)
    await message.answer(
        f"✅ <b>Updated!</b> Auto-revoke: <b>{minutes} min</b>\n\n"
        f"💡 Revokes post access after timer.",
        parse_mode=ParseMode.HTML
    )


# ── /settings — Enhanced with templates & quick links ────────────────────────

@router.message(Command("settings"))
@owner_only
async def cmd_settings(message: Message):
    try:
        settings = await CosmicBotz.get_settings()
        admins = await CosmicBotz.get_admins()
        slots = await CosmicBotz.get_slots(message.from_user.id)
        revoke = settings.get("auto_revoke_minutes", 30)

        quality = settings.get("caption_quality", "Multiple")
        audio = settings.get("caption_audio", "हिंदी (Hindi)")

        # New: Template status
        series_template = await CosmicBotz.get_setting("caption_template_series", None)
        template_status = "✅ Custom" if series_template else "📋 Default"

        wm_text = settings.get("watermark_text", "—")
        wm_logo = settings.get("watermark_logo_id", "")

        text = (
            "⚙️ <b>Bot Settings</b>\n\n"
            f"⏱ <b>Auto-Revoke:</b> <b>{revoke} min</b>\n"
            f"👥 <b>Admins:</b> {len(admins)}\n"
            f"📢 <b>Slots:</b> {len(slots)}\n\n"
            "✏️ <b>Captions:</b>\n"
            f"🎬 Quality: <code>{quality}</code>\n"
            f"🔊 Audio: <code>{audio}</code>\n"
            f"📝 Template: {template_status}\n\n"
            "🖼 <b>Watermark:</b>\n"
            f"📝 Text: <code>{wm_text or 'None'}</code>\n"
            f"🏷 Logo: {'✅ Set' if wm_logo else 'None'}\n\n"
            "<b>Quick Commands:</b>\n"
            "• /setrevoke · /addadmin · /addslot\n"
            "• /setquality · /setaudio · /setcaptemplate\n"
            "• /setwatermark · /clearwatermark"
        )
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception:
        await message.answer("❌ Failed to load settings. Try again.", parse_mode=ParseMode.HTML)


# ── /delcontent — Improved search & multi-select UX ─────────────────────────

@router.message(Command("delcontent"))
@admin_only
async def cmd_delcontent(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🗑 <b>Delete Content</b>\n\n"
            "Usage: <code>/delcontent TITLE</code>\n\n"
            "💡 Search first with /search, then copy exact title.\n"
            "Shows top 10 matches — tap to confirm delete.",
            parse_mode=ParseMode.HTML
        )
        return

    query = args[1].strip()

    try:
        from database import CosmicBotz as _db
        results = await _db.search_title(query)

        if not results:
            await message.answer(f"❌ No matches for <b>'{query}'</b>\n\nTry a broader search.", parse_mode=ParseMode.HTML)
            return

        if len(results) == 1:
            item = results[0]
            await message.answer(
                f"⚠️ <b>Delete?</b>\n\n"
                f"📺 <b>{item['title']}</b>\n"
                f"Type: {item.get('media_type', '?')}\n\n"
                f"<i>This removes it from the index only.</i>",
                reply_markup=confirm_delete_keyboard(str(item["_id"]), item["title"]),
                parse_mode=ParseMode.HTML
            )
        else:
            await message.answer(
                f"🔍 <b>{len(results)} Matches</b> for '{query}'\n\n"
                "Select one to delete:",
                reply_markup=delete_search_keyboard(results[:10]),  # Limit to 10
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        await message.answer(f"❌ Search error: {str(e)}", parse_mode=ParseMode.HTML)


@router.callback_query(F.data.startswith("delconfirm_"))
async def cb_confirm_delete(call: CallbackQuery):
    try:
        # Safe split: Extract ID from "delconfirm_{filter_id}"
        filter_id = call.data.split("_", 1)[1]  # Not just call.data!
        from database import CosmicBotz as _db
        from bson import ObjectId
        db = _db.db()
        item = await db.filters.find_one({"_id": ObjectId(filter_id)})
        if not item:
            await call.message.edit_text("⚠️ Item already deleted.", parse_mode=ParseMode.HTML)
            return
        await db.filters.delete_one({"_id": ObjectId(filter_id)})
        await call.message.edit_text(
            f"✅ <b>{item['title']}</b> removed from index.",
            parse_mode=ParseMode.HTML
        )
        await call.answer("Deleted!")
    except Exception as e:  # This is the missing piece!
        print(f"Delete error: {e}")  # Log for debugging
        await call.answer("Error deleting item.", show_alert=True)
    finally:  # Optional: Always answer to avoid hanging callbacks
        pass


@router.callback_query(F.data.startswith("delselect_"))
async def cb_delete_select(call: CallbackQuery):
    try:
        # Safe split: Extract ID from "delselect_{filter_id}"
        filter_id = call.data.split("_", 1)[1]  # Fix if it was just "call.data"
        from database import CosmicBotz as _db
        from bson import ObjectId
        item = await _db.get_filter_by_id(filter_id)
        if not item:
            await call.answer("Not found.", show_alert=True)
            return
        await call.message.edit_text(
            f"⚠️ <b>Delete?</b>\n\n"
            f"📺 <b>{item['title']}</b>\n"
            f"Type: {item.get('media_type', '?')}",
            reply_markup=confirm_delete_keyboard(filter_id, item["title"]),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:  # Ensure this exists!
        print(f"Select error: {e}")
        await call.answer("Error loading item.", show_alert=True)


@router.callback_query(F.data == "delcancel")
async def cb_delete_cancel(call: CallbackQuery):
    await call.message.edit_text("❌ <b>Cancelled</b>\n\nUse /delcontent to try again.", parse_mode=ParseMode.HTML)
    await call.answer()


# ── Caption Commands — Updated with templates ────────────────────────────────

@router.message(Command("setcaption"))
@owner_only
async def cmd_setcaption(message: Message):
    settings = await CosmicBotz.get_settings()
    quality = settings.get("caption_quality", "Multiple")
    audio = settings.get("caption_audio", "हिंदी (Hindi)")
    series_template = await CosmicBotz.get_setting("caption_template_series", None)

    text = (
        "✏️ <b>Caption Settings</b>\n\n"
        f"🎬 <b>Quality:</b> <code>{quality}</code>\n"
        f"🔊 <b>Audio:</b> <code>{audio}</code>\n"
        f"📝 <b>Template:</b> {'✅ Custom' if series_template else '📋 Default (Naruto-style)'}\n\n"
        "<b>Quick Set:</b>\n"
        "• <code>/setquality Multiple</code>\n"
        "• <code>/setaudio हिंदी (Hindi)</code>\n"
        "• <code>/setcaptemplate series {your template}</code>\n"
        "• <code>/getcaptemplate series</code> (preview)"
    )
    await message.answer(text, parse_mode=ParseMode.HTML)


@router.message(Command("setquality"))
@owner_only
async def cmd_setquality(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🎬 <b>Set Quality</b>\n\n"
            "Usage: <code>/setquality Multiple</code>\n\n"
            "Examples: <code>1080p FHD</code> | <code>720p HD | 480p</code>",
            parse_mode=ParseMode.HTML
        )
        return
    value = args[1].strip()[:50]  # Sanitize
    await CosmicBotz.update_setting("caption_quality", value)
    await message.answer(f"✅ <b>Quality Updated:</b> <code>{value}</code>", parse_mode=ParseMode.HTML)


@router.message(Command("setaudio"))
@owner_only
async def cmd_setaudio(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🔊 <b>Set Audio</b>\n\n"
            "Usage: <code>/setaudio हिंदी (Hindi)</code>\n\n"
            "Examples: <code>English</code> | <code>हिंदी #Dub</code>",
            parse_mode=ParseMode.HTML
        )
        return
    value = args[1].strip()[:50]
    await CosmicBotz.update_setting("caption_audio", value)
    await message.answer(f"✅ <b>Audio Updated:</b> <code>{value}</code>", parse_mode=ParseMode.HTML)


# New: /setcaptemplate, /getcaptemplate, /resetcaptemplate

@router.message(Command("setcaptemplate"))
@owner_only
async def cmd_setcaptemplate(message: Message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "📝 <b>Set Caption Template</b>\n\n"
            "Usage: <code>/setcaptemplate &lt;type&gt; &lt;template&gt;</code>\n\n"
            "Types: <code>series</code> (anime/TV) | <code>movie</code> | <code>index</code>\n\n"
            "💡 Use {title}, {quality}, {genres} etc. \\n for newlines.\n"
            "Example: <code>/setcaptemplate series {title}\\n&lt;blockquote&gt;➣ Type: {media_label}&lt;/blockquote&gt;</code>\n\n"
            "Preview with /getcaptemplate series",
            parse_mode=ParseMode.HTML
        )
        return

    template_type = args[1].strip().lower()
    if template_type not in ("series", "movie", "index"):
        await message.answer("⚠️ Type must be: series, movie, or index.", parse_mode=ParseMode.HTML)
        return

    template_text = args[2].strip()
    if len(template_text) > 2000:  # Telegram limit
        await message.answer("⚠️ Template too long! Keep under 2000 chars.", parse_mode=ParseMode.HTML)
        return

    try:
        await CosmicBotz.update_setting(f"caption_template_{template_type}", template_text)
        await message.answer(
            f"✅ <b>{template_type.upper()} Template Saved!</b>\n\n"
            f"Preview: <code>/getcaptemplate {template_type}</code>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(f"❌ Save error: {str(e)}", parse_mode=ParseMode.HTML)


@router.message(Command("getcaptemplate"))
@owner_only
async def cmd_getcaptemplate(message: Message):
    args = message.text.split(maxsplit=1)
    template_type = (args[1].strip().lower() if len(args) > 1 else "series")

    if template_type not in ("series", "movie", "index"):
        await message.answer("⚠️ Type: series, movie, or index.", parse_mode=ParseMode.HTML)
        return

    try:
        template = await CosmicBotz.get_setting(f"caption_template_{template_type}")
        if not template:
            await message.answer(f"📋 No custom {template_type} template. Using default.", parse_mode=ParseMode.HTML)
            return

        # Dummy preview context (from previous response)
        if template_type == "index":
            preview = template.format(letter="A", count=5)
            preview_context = {"letter": "A", "count": 5}
        else:
            preview_context = {
                "title": "Naruto Shippūden",
                "media_label": "TV Series" if template_type == "series" else "Movie",
                "status": "Ended",
                "episodes": "500",
                "season": "20",
                "runtime": "24",
                "quality": "Multiple",
                "audio": "हिंदी (Hindi)",
                "genres": "Animation, Action"
            }
            if template_type == "movie":
                del preview_context["status"]
                del preview_context["episodes"]
                del preview_context["season"]
            preview = template.format(**preview_context)

        text = (
            f"<b>{template_type.upper()} Template</b>\n\n"
            f"<pre>{template}</pre>\n\n"  # Raw
            f"<b>Preview:</b>\n<pre>{preview}</pre>"  # Rendered
        )
        await message.answer(text, parse_mode=ParseMode.HTML)
    except Exception as e:
        await message.answer(f"❌ Load error: {str(e)}", parse_mode=ParseMode.HTML)


@router.message(Command("resetcaptemplate"))
@owner_only
async def cmd_resetcaptemplate(message: Message):
    args = message.text.split(maxsplit=1)
    template_type = (args[1].strip().lower() if len(args) > 1 else "series")

    if template_type not in ("series", "movie", "index"):
        await message.answer("⚠️ Type: series, movie, or index.", parse_mode=ParseMode.HTML)
        return

    try:
        await CosmicBotz.delete_setting(f"caption_template_{template_type}")  # Assume delete_setting exists
        await message.answer(
            f"✅ <b>{template_type.upper()} Template Reset</b>\n\n"
            f"Back to default. Preview: /getcaptemplate {template_type}",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await message.answer("❌ Reset failed.", parse_mode=ParseMode.HTML)


# ── Watermark Commands — With previews if possible ──────────────────────────

@router.message(Command("setwatermark"))
@owner_only
async def cmd_setwatermark(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "🖼 <b>Set Watermark Text</b>\n\n"
            "Usage: <code>/setwatermark YourChannel</code>\n\n"
            "Appears as a pill on thumbnails (top-right).",
            parse_mode=ParseMode.HTML
        )
        return
    value = args[1].strip()[:30]  # Short limit
    await CosmicBotz.update_setting("watermark_text", value)
    await message.answer(
        f"✅ <b>Watermark Text:</b> <code>{value}</code>\n\n"
        "💡 Test on next /addcontent thumbnail.",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("setlogo"))
@owner_only
async def cmd_setlogo(message: Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.answer(
            "🏷 <b>Set Logo</b>\n\n"
            "Reply to a <b>photo</b> (your logo) with <code>/setlogo</code>.\n\n"
            "It overlays on thumbnails with text.",
            parse_mode=ParseMode.HTML
        )
        return
    file_id = message.reply_to_message.photo[-1].file_id
    await CosmicBotz.update_setting("watermark_logo_id", file_id)
    await message.answer(
        "✅ <b>Logo Saved!</b>\n\n"
        "Will appear on new thumbnails. Clear with /clearwatermark.",
        parse_mode=ParseMode.HTML
    )


@router.message(Command("clearwatermark"))
@owner_only
async def cmd_clearwatermark(message: Message):
    await CosmicBotz.update_setting("watermark_text", "")
    await CosmicBotz.update_setting("watermark_logo_id", "")
    await message.answer(
        "✅ <b>Watermark Cleared</b>\n\n"
        "Thumbnails now plain. Set new with /setwatermark.",
        parse_mode=ParseMode.HTML
    )
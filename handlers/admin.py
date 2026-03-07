from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType

from database import CosmicBotz
from middlewares.auth import owner_only, admin_only, dm_only
from keyboards.inline import slot_list_keyboard, admin_list_keyboard

router = Router()


class AddSlotState(StatesGroup):
    waiting_channel_id = State()
    waiting_slot_name  = State()


# ── /addslot ──────────────────────────────────────────────────────────────────

@router.message(Command("addslot"))
@owner_only
@dm_only
async def cmd_addslot(message: Message, state: FSMContext, **kwargs):
    await message.answer(
        "➕ <b>Add New Slot</b>\n\n"
        "Forward any message from the <b>target channel</b>, "
        "or send its ID (e.g. <code>-100xxxxxxxxxx</code>).\n\n"
        "The bot must be an <b>admin</b> in that channel.",
        parse_mode="HTML"
    )
    await state.set_state(AddSlotState.waiting_channel_id)


@router.message(AddSlotState.waiting_channel_id)
async def slot_got_channel(message: Message, state: FSMContext):
    if message.forward_from_chat:
        channel_id   = message.forward_from_chat.id
        channel_name = message.forward_from_chat.title
    elif message.text and message.text.lstrip("-").isdigit():
        channel_id   = int(message.text.strip())
        channel_name = str(channel_id)
    else:
        await message.answer("⚠️ Send a valid channel ID or forward a message from the channel.")
        return

    await state.update_data(channel_id=channel_id, channel_name=channel_name)
    await message.answer(
        f"✅ Channel: <b>{channel_name}</b> (<code>{channel_id}</code>)\n\n"
        "Now send a <b>name/label</b> for this slot (e.g. <i>Anime Hindi Dub</i>):",
        parse_mode="HTML"
    )
    await state.set_state(AddSlotState.waiting_slot_name)


@router.message(AddSlotState.waiting_slot_name)
async def slot_got_name(message: Message, state: FSMContext):
    data         = await state.get_data()
    channel_id   = data["channel_id"]
    channel_name = data["channel_name"]
    slot_name    = message.text.strip()
    await state.clear()

    ok, msg = await CosmicBotz.add_slot(
        message.from_user.id, channel_id, channel_name, slot_name
    )
    if ok:
        await message.answer(
            f"✅ Slot <b>{slot_name}</b> added for <b>{channel_name}</b>!\n"
            "Use /addcontent to post content to this slot.",
            parse_mode="HTML"
        )
    else:
        await message.answer(f"⚠️ {msg}")


# ── /slots ────────────────────────────────────────────────────────────────────

@router.message(Command("slots"))
@owner_only
async def cmd_slots(message: Message, **kwargs):
    slots = await CosmicBotz.get_slots(message.from_user.id)
    if not slots:
        await message.answer("📭 No slots configured. Use /addslot to add one.")
        return
    await message.answer(
        f"📋 <b>Your Slots ({len(slots)})</b>",
        reply_markup=slot_list_keyboard(slots),
        parse_mode="HTML"
    )


# ── /removeslot ───────────────────────────────────────────────────────────────

@router.message(Command("removeslot"))
@owner_only
async def cmd_removeslot(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/removeslot CHANNEL_ID</code>", parse_mode="HTML")
        return
    try:
        channel_id = int(args[1].strip())
    except ValueError:
        await message.answer("⚠️ Invalid channel ID.")
        return

    ok = await CosmicBotz.remove_slot(message.from_user.id, channel_id)
    if ok:
        await message.answer(f"✅ Slot removed for <code>{channel_id}</code>.", parse_mode="HTML")
    else:
        await message.answer("⚠️ Slot not found.")


# ── /addadmin / /removeadmin / /admins ────────────────────────────────────────

@router.message(Command("addadmin"))
@owner_only
async def cmd_addadmin(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/addadmin USER_ID</code>", parse_mode="HTML")
        return
    try:
        user_id = int(args[1].strip())
    except ValueError:
        await message.answer("⚠️ Invalid user ID.")
        return
    await CosmicBotz.add_admin(user_id)
    await message.answer(f"✅ <code>{user_id}</code> added as admin.", parse_mode="HTML")


@router.message(Command("removeadmin"))
@owner_only
async def cmd_removeadmin(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/removeadmin USER_ID</code>", parse_mode="HTML")
        return
    try:
        user_id = int(args[1].strip())
    except ValueError:
        await message.answer("⚠️ Invalid user ID.")
        return
    await CosmicBotz.remove_admin(user_id)
    await message.answer(f"✅ <code>{user_id}</code> removed from admins.", parse_mode="HTML")


@router.message(Command("admins"))
@owner_only
async def cmd_list_admins(message: Message, **kwargs):
    admins = await CosmicBotz.get_admins()
    if not admins:
        await message.answer("👥 No admins set. Use /addadmin USER_ID.")
        return
    await message.answer(
        f"👥 <b>Admins ({len(admins)})</b>\nTap to remove:",
        reply_markup=admin_list_keyboard(admins),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("rmadmin_"))
async def cb_remove_admin(call: CallbackQuery):
    uid = int(call.data.split("_")[1])
    await CosmicBotz.remove_admin(uid)
    await call.answer(f"✅ Removed admin {uid}")
    await call.message.edit_text(f"✅ Admin <code>{uid}</code> removed.", parse_mode="HTML")


# ── /setrevoke ────────────────────────────────────────────────────────────────

@router.message(Command("setrevoke"))
@owner_only
async def cmd_setrevoke(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        settings = await CosmicBotz.get_settings()
        current  = settings.get("auto_revoke_minutes", 30)
        await message.answer(
            f"⏱ Current auto-revoke: <b>{current} minutes</b>\n\n"
            "To change: <code>/setrevoke MINUTES</code>",
            parse_mode="HTML"
        )
        return
    try:
        minutes = int(args[1].strip())
        if minutes < 1:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Provide a valid number of minutes (min 1).")
        return
    await CosmicBotz.update_setting("auto_revoke_minutes", minutes)
    await message.answer(f"✅ Auto-revoke set to <b>{minutes} minutes</b>.", parse_mode="HTML")


# ── /settings ─────────────────────────────────────────────────────────────────

@router.message(Command("settings"))
@owner_only
async def cmd_settings(message: Message, **kwargs):
    settings = await CosmicBotz.get_settings()
    admins   = await CosmicBotz.get_admins()
    slots    = await CosmicBotz.get_slots(message.from_user.id)
    revoke   = settings.get("auto_revoke_minutes", 30)

    settings = await CosmicBotz.get_settings()
    quality  = settings.get("caption_quality", "1080p FHD | 720p HD | 480p WEB-DL")
    audio    = settings.get("caption_audio",   "हिंदी (Hindi)")

    wm_text = settings.get("watermark_text", "—")
    wm_logo = settings.get("watermark_logo_id", "")

    await message.answer(
        "⚙️ <b>Bot Settings</b>\n\n"
        f"🔗 Auto-Revoke: <b>{revoke} min</b> — /setrevoke\n"
        f"👥 Admins: <b>{len(admins)}</b> — /admins\n"
        f"📢 Slots: <b>{len(slots)}</b> — /slots\n\n"
        "✏️ <b>Caption</b>\n"
        f"🎬 Quality: <code>{quality}</code>\n"
        f"🔊 Audio: <code>{audio}</code>\n"
        "/setquality · /setaudio · /setcaption\n\n"
        "🖼 <b>Thumbnail Watermark</b>\n"
        f"📝 Text: <code>{wm_text or '—'}</code>\n"
        f"🏷 Logo: {'✅ Set' if wm_logo else '—'}\n"
        "/setwatermark · /setlogo · /clearwatermark\n\n"
        "🗑 /delcontent — remove title from index\n"
        "/addslot · /addcontent · /addadmin · /groups",
        parse_mode="HTML"
    )


# ── /delcontent ───────────────────────────────────────────────────────────────

@router.message(Command("delcontent"))
@admin_only
async def cmd_delcontent(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Usage: <code>/delcontent TITLE</code>\n\n"
            "Example: <code>/delcontent Naruto</code>\n\n"
            "To find exact title, search it first then copy the name.",
            parse_mode="HTML"
        )
        return

    query = args[1].strip()

    # Search for matching titles
    from database import CosmicBotz as _db
    results = await _db.search_title(query)

    if not results:
        await message.answer(f"❌ No title found matching: <b>{query}</b>", parse_mode="HTML")
        return

    if len(results) == 1:
        item = results[0]
        from keyboards.inline import confirm_delete_keyboard
        await message.answer(
            f"⚠️ Delete <b>{item['title']}</b> ({item.get('media_type','?')}) from index?",
            reply_markup=confirm_delete_keyboard(str(item["_id"]), item["title"]),
            parse_mode="HTML"
        )
    else:
        from keyboards.inline import delete_search_keyboard
        await message.answer(
            f"🔍 Found <b>{len(results)}</b> matches. Select one to delete:",
            reply_markup=delete_search_keyboard(results[:10]),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("delconfirm_"))
async def cb_confirm_delete(call: CallbackQuery):
    filter_id = call.data.split("_", 1)[1]
    from database import CosmicBotz as _db
    from bson import ObjectId
    db   = _db.db()
    item = await db.filters.find_one({"_id": ObjectId(filter_id)})
    if not item:
        await call.message.edit_text("⚠️ Already deleted or not found.")
        return
    await db.filters.delete_one({"_id": ObjectId(filter_id)})
    await call.message.edit_text(
        f"✅ <b>{item['title']}</b> removed from index.",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("delselect_"))
async def cb_delete_select(call: CallbackQuery):
    filter_id = call.data.split("_", 1)[1]
    from database import CosmicBotz as _db
    from bson import ObjectId
    item = await _db.get_filter_by_id(filter_id)
    if not item:
        await call.answer("Not found.", show_alert=True)
        return
    from keyboards.inline import confirm_delete_keyboard
    await call.message.edit_text(
        f"⚠️ Delete <b>{item['title']}</b> ({item.get('media_type','?')}) from index?",
        reply_markup=confirm_delete_keyboard(filter_id, item["title"]),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "delcancel")
async def cb_delete_cancel(call: CallbackQuery):
    await call.message.edit_text("❌ Cancelled.")


# ── /setcaption ───────────────────────────────────────────────────────────────

@router.message(Command("setcaption"))
@owner_only
async def cmd_setcaption(message: Message, **kwargs):
    from database import CosmicBotz as _db
    settings = await _db.get_settings()
    quality  = settings.get("caption_quality", "1080p FHD | 720p HD | 480p WEB-DL")
    audio    = settings.get("caption_audio",   "हिंदी (Hindi)")

    await message.answer(
        "✏️ <b>Caption Settings</b>\n\n"
        f"🎬 <b>Quality:</b> <code>{quality}</code>\n"
        f"🔊 <b>Audio:</b> <code>{audio}</code>\n\n"
        "To change:\n"
        "<code>/setquality 1080p FHD | 720p HD | 480p WEB-DL</code>\n"
        "<code>/setaudio हिंदी (Hindi) #Official</code>",
        parse_mode="HTML"
    )


@router.message(Command("setquality"))
@owner_only
async def cmd_setquality(message: Message, **kwargs):
    from database import CosmicBotz as _db
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/setquality 1080p FHD | 720p HD | 480p WEB-DL</code>", parse_mode="HTML")
        return
    value = args[1].strip()
    await _db.update_setting("caption_quality", value)
    await message.answer(f"✅ Quality set to:\n<code>{value}</code>", parse_mode="HTML")


@router.message(Command("setaudio"))
@owner_only
async def cmd_setaudio(message: Message, **kwargs):
    from database import CosmicBotz as _db
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/setaudio हिंदी (Hindi) #Official</code>", parse_mode="HTML")
        return
    value = args[1].strip()
    await _db.update_setting("caption_audio", value)
    await message.answer(f"✅ Audio set to:\n<code>{value}</code>", parse_mode="HTML")


# ── Watermark commands ────────────────────────────────────────────────────────

@router.message(Command("setwatermark"))
@owner_only
async def cmd_setwatermark(message: Message, **kwargs):
    from database import CosmicBotz as _db
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Usage: <code>/setwatermark YourChannelName</code>\n\n"
            "This text appears as a pill in the top-right of every thumbnail.",
            parse_mode="HTML"
        )
        return
    value = args[1].strip()
    await _db.update_setting("watermark_text", value)
    await message.answer(f"✅ Watermark text set to: <code>{value}</code>", parse_mode="HTML")


@router.message(Command("setlogo"))
@owner_only
async def cmd_setlogo(message: Message, **kwargs):
    from database import CosmicBotz as _db
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.answer(
            "📸 Reply to a <b>photo/logo</b> with <code>/setlogo</code>\n\n"
            "The logo will appear in the top-right of every thumbnail alongside your watermark text.",
            parse_mode="HTML"
        )
        return
    file_id = message.reply_to_message.photo[-1].file_id
    await _db.update_setting("watermark_logo_id", file_id)
    await message.answer("✅ Logo watermark saved! It will appear on all new thumbnails.", parse_mode="HTML")


@router.message(Command("clearwatermark"))
@owner_only
async def cmd_clearwatermark(message: Message, **kwargs):
    from database import CosmicBotz as _db
    await _db.update_setting("watermark_text", "")
    await _db.update_setting("watermark_logo_id", "")
    await message.answer("✅ Watermark cleared.", parse_mode="HTML")


# ── Abbreviation commands ─────────────────────────────────────────────────────

@router.message(Command("setabbr"))
@admin_only
async def cmd_setabbr(message: Message, **kwargs):
    from database import CosmicBotz as _db
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or "=" not in args[1]:
        abbr_map = await _db.get_abbr_map()
        if abbr_map:
            lines = "\n".join(f"<code>{k}</code> → {v}" for k, v in sorted(abbr_map.items()))
        else:
            lines = "<i>No abbreviations set yet.</i>"
        await message.answer(
            "🔤 <b>Abbreviations</b>\n\n"
            f"{lines}\n\n"
            "To add: <code>/setabbr AOT=Attack on Titan</code>\n"
            "To remove: <code>/delabbr AOT</code>",
            parse_mode="HTML"
        )
        return
    abbr, full = args[1].split("=", 1)
    abbr = abbr.strip()
    full = full.strip()
    if not abbr or not full:
        await message.answer("⚠️ Usage: <code>/setabbr AOT=Attack on Titan</code>", parse_mode="HTML")
        return
    await _db.set_abbr(abbr, full)
    await message.answer(
        f"✅ <code>{abbr.upper()}</code> → <b>{full}</b>",
        parse_mode="HTML"
    )


@router.message(Command("delabbr"))
@admin_only
async def cmd_delabbr(message: Message, **kwargs):
    from database import CosmicBotz as _db
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/delabbr AOT</code>", parse_mode="HTML")
        return
    abbr = args[1].strip()
    ok   = await _db.del_abbr(abbr)
    if ok:
        await message.answer(f"✅ Removed abbreviation: <code>{abbr.upper()}</code>", parse_mode="HTML")
    else:
        await message.answer(f"⚠️ <code>{abbr.upper()}</code> not found.", parse_mode="HTML")

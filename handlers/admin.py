from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import CosmicBotz
from middlewares.auth import owner_only, admin_only, dm_only
from keyboards.inline import slot_list_keyboard, admin_list_keyboard
from config import OWNER_ID
import logging

router = Router()

class AddSlotState(StatesGroup):
    waiting_channel_id = State()
    waiting_slot_name  = State()

# ── /addslot (FSM Logic) ─────────────────────────────────────────────────────

@router.message(Command("fixdb"), F.from_user.id == OWNER_ID)
async def cmd_fix_database(message: Message):
    """
    Temporary Owner-only command to migrate the database
    to the new normalized search & acronym system.
    """
    status_msg = await message.reply("⚙️ **Migration Started...**\nProcessing old database entries...")
    
    try:
        # Calls the function we just added to database.py
        count = await CosmicBotz.temp_fix_database()
        
        await status_msg.edit_text(
            f"✅ **Migration Successful!**\n\n"
            f"🔸 **Updated:** `{count}` entries\n"
            f"🔸 **System:** Normalized Search & Smart Acronyms\n\n"
            f"You can now test search results for titles like 'Hana-Kimi' using 'hana kimi'."
        )
    except Exception as e:
        await status_msg.edit_text(f"❌ **Migration Failed!**\nError: `{e}`")
        logger.error(f"Migration Error: {e}")


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

# ── Slot View Commands (/slot & /slots) ───────────────────────────────────────

@router.message(Command("slot"))
@admin_only
@dm_only
async def cmd_personal_slots(message: Message, **kwargs):
    """View slots added ONLY by you."""
    slots = await CosmicBotz.get_slots(message.from_user.id)
    if not slots:
        await message.answer("📭 You haven't added any slots yet.")
        return
    await message.answer(
        f"👤 <b>Your Personal Slots ({len(slots)})</b>\n<i>Tap a slot to remove it.</i>",
        reply_markup=slot_list_keyboard(slots, page=0, prefix="rmslot_p"),
        parse_mode="HTML"
    )

@router.message(Command("slots"))
@owner_only
async def cmd_all_slots(message: Message, **kwargs):
    """View ALL slots in the database (Owner only)."""
    slots = await CosmicBotz.get_slots_all() 
    if not slots:
        await message.answer("📭 No slots configured in the bot.")
        return
    await message.answer(
        f"🌐 <b>Global Slot List ({len(slots)})</b>\n<i>Showing all slots from all admins.</i>",
        reply_markup=slot_list_keyboard(slots, page=0, prefix="rmslot_g"),
        parse_mode="HTML"
    )

# ── /removeslot (Text Command) ────────────────────────────────────────────────

@router.message(Command("removeslot"))
@admin_only
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

    is_owner = (message.from_user.id == OWNER_ID)
    ok = await CosmicBotz.remove_slot(message.from_user.id, channel_id, is_owner=is_owner)
    if ok:
        await message.answer(f"✅ Slot removed for <code>{channel_id}</code>.", parse_mode="HTML")
    else:
        await message.answer("⚠️ Slot not found or you don't have permission to remove it.")

# ── Slot Callbacks (Pagination & Inline Removal) ──────────────────────────────

@router.callback_query(F.data.startswith("slotpage_"))
async def cb_slot_page(call: CallbackQuery, **kwargs):
    """Universal Pagination Handler for all Slot Lists"""
    await call.answer()
    parts = call.data.split("_") 
    
    # Format: slotpage_{prefix}_{page}
    if len(parts) < 3 or parts[-1] == "noop":
        return
    
    try:
        page = int(parts[-1])
        # Reconstructs prefix (e.g., 'slot' or 'rmslot_p')
        prefix = "_".join(parts[1:-1]) 
    except ValueError:
        return

    is_owner = (call.from_user.id == OWNER_ID)

    # --- OWNER BYPASS & DATA FETCHING ---
    if prefix == "rmslot_g" and is_owner:
        # Owner managing global slots
        slots = await CosmicBotz.get_slots_all()
    elif prefix == "rmslot_p":
        # Admin managing personal slots
        slots = await CosmicBotz.get_slots(call.from_user.id)
    else:
        # Standard flow (e.g., /addcontent)
        # Owner sees all channels, Admins see only theirs
        if is_owner:
            slots = await CosmicBotz.get_slots_all()
        else:
            slots = await CosmicBotz.get_slots(call.from_user.id)

    if not slots:
        await call.message.edit_text("📭 No slots found.")
        return
        
    await call.message.edit_reply_markup(
        reply_markup=slot_list_keyboard(slots, page=page, prefix=prefix)
    )

@router.callback_query(F.data.startswith("rmslot_"))
async def cb_remove_slot_inline(call: CallbackQuery):
    """Handles deletion when a slot button is clicked in the list."""
    parts = call.data.split("_") # rmslot_<p/g>_<cid>
    if len(parts) < 3: return
    
    view_type = parts[1]
    channel_id = int(parts[2])
    
    is_owner = (call.from_user.id == OWNER_ID)
    ok = await CosmicBotz.remove_slot(call.from_user.id, channel_id, is_owner=is_owner)
    
    if ok:
        await call.answer("✅ Slot Removed", show_alert=True)
        # Refresh the current list
        slots = await CosmicBotz.get_slots(call.from_user.id) if view_type == "p" else await CosmicBotz.get_slots_all()
        if slots:
            await call.message.edit_reply_markup(
                reply_markup=slot_list_keyboard(slots, 0, f"rmslot_{view_type}")
            )
        else:
            await call.message.edit_text("📭 All slots have been removed.")
    else:
        await call.answer("⚠️ You can only remove your own slots.", show_alert=True)

# ── Admin Management ─────────────────────────────────────────────────────────

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
        await message.answer("👥 No admins set.")
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

# ── Settings Logic ────────────────────────────────────────────────────────────

@router.message(Command("setrevoke"))
@owner_only
async def cmd_setrevoke(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        settings = await CosmicBotz.get_settings()
        current  = settings.get("auto_revoke_minutes", 30)
        await message.answer(f"⏱ Current: <b>{current}m</b>\nTo change: <code>/setrevoke MINS</code>", parse_mode="HTML")
        return
    try:
        minutes = int(args[1].strip())
        if minutes < 1: raise ValueError
    except ValueError:
        await message.answer("⚠️ Use a valid number.")
        return
    await CosmicBotz.update_setting("auto_revoke_minutes", minutes)
    await message.answer(f"✅ Auto-revoke set to <b>{minutes} minutes</b>.", parse_mode="HTML")

async def _settings_text_and_kb():
    from keyboards.inline import settings_keyboard
    settings = await CosmicBotz.get_settings()
    admins   = await CosmicBotz.get_admins()
    slots    = await CosmicBotz.get_slots_all()

    revoke   = settings.get("auto_revoke_minutes", 30)
    quality  = settings.get("caption_quality",     "1080p FHD | 720p HD | 480p WEB-DL")
    audio    = settings.get("caption_audio",        "हिंदी (Hindi)")
    wm_text  = settings.get("watermark_text",       "")
    wm_logo  = settings.get("watermark_logo_id",    "")

    text = (
        "⚙️ <b>Bot Settings</b>\n\n"
        f"⏱ <b>Auto-Revoke:</b> <code>{revoke} min</code>\n"
        f"📢 <b>Slots:</b> <code>{len(slots)}</code>\n"
        f"👥 <b>Admins:</b> <code>{len(admins)}</code>\n\n"
        f"✏️ <b>Caption</b>\n"
        f"  Quality: <code>{quality}</code>\n"
        f"  Audio:   <code>{audio}</code>\n\n"
        f"🖼 <b>Watermark</b>\n"
        f"  Text: <code>{wm_text or '—'}</code>\n"
        f"  Logo: {'✅ Set' if wm_logo else '—'}\n"
    )
    kb = settings_keyboard(revoke)
    return text, kb

@router.message(Command("settings"))
@owner_only
async def cmd_settings(message: Message, **kwargs):
    text, kb = await _settings_text_and_kb()
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "settings_refresh")
async def cb_settings_refresh(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer("⛔ Owner only.", show_alert=True)
        return
    text, kb = await _settings_text_and_kb()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("set_revoke_"))
async def cb_set_revoke(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer("⛔ Owner only.", show_alert=True)
        return
    minutes = int(call.data.split("_")[-1])
    await CosmicBotz.update_setting("auto_revoke_minutes", minutes)
    await call.answer(f"✅ Set to {minutes}m")
    text, kb = await _settings_text_and_kb()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# ── Content & Watermark Management ───────────────────────────────────────────

@router.message(Command("delcontent"))
@admin_only
async def cmd_delcontent(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Usage: <code>/delcontent TITLE</code>", parse_mode="HTML")
        return

    query = args[1].strip()
    results = await CosmicBotz.search_title(query)

    if not results:
        await message.answer(f"❌ No matches for: <b>{query}</b>", parse_mode="HTML")
        return

    if len(results) == 1:
        item = results[0]
        from keyboards.inline import confirm_delete_keyboard
        await message.answer(
            f"⚠️ Delete <b>{item['title']}</b> from index?",
            reply_markup=confirm_delete_keyboard(str(item["_id"]), item["title"]),
            parse_mode="HTML"
        )
    else:
        from keyboards.inline import delete_search_keyboard
        await message.answer(
            f"🔍 Found {len(results)} matches. Select one:",
            reply_markup=delete_search_keyboard(results[:10]),
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("delconfirm_"))
async def cb_confirm_delete(call: CallbackQuery):
    from bson import ObjectId
    filter_id = call.data.split("_", 1)[1]
    db = CosmicBotz.db()
    item = await db.filters.find_one_and_delete({"_id": ObjectId(filter_id)})
    if item:
        await call.message.edit_text(f"✅ <b>{item['title']}</b> removed.", parse_mode="HTML")
    else:
        await call.message.edit_text("⚠️ Not found.")

@router.message(Command("setcaption"))
@owner_only
async def cmd_setcaption(message: Message, **kwargs):
    from services.caption import DEFAULT_TEMPLATE_SERIES, DEFAULT_TEMPLATE_MOVIE, CAPTION_VARIABLES
    args = message.text.split(maxsplit=2)
    settings = await CosmicBotz.get_settings()

    if len(args) == 1:
        series_t = settings.get("caption_template_series", DEFAULT_TEMPLATE_SERIES)
        movie_t  = settings.get("caption_template_movie",  DEFAULT_TEMPLATE_MOVIE)
        vars_txt = "\n".join(f"<code>{k}</code> — {v}" for k, v in CAPTION_VARIABLES.items())
        await message.answer(
            "✏️ <b>Templates</b>\n\n"
            f"<b>📺 Series:</b> <code>{series_t}</code>\n"
            f"<b>🎬 Movie:</b> <code>{movie_t}</code>\n\n"
            f"<b>Variables:</b>\n{vars_txt}\n\n"
            "Use: <code>/setcaption series TEMPLATE</code>",
            parse_mode="HTML"
        )
        return

    sub = args[1].lower().strip()
    if sub == "reset":
        await CosmicBotz.update_setting("caption_template_series", DEFAULT_TEMPLATE_SERIES)
        await CosmicBotz.update_setting("caption_template_movie",  DEFAULT_TEMPLATE_MOVIE)
        await message.answer("✅ Templates reset.")
        return

    if sub in ("series", "movie") and len(args) == 3:
        template = args[2].strip().replace("\\n", "\n")
        key = f"caption_template_{sub}"
        await CosmicBotz.update_setting(key, template)
        await message.answer(f"✅ {sub.title()} template updated!")

@router.message(Command("setquality"))
@owner_only
async def cmd_setquality(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) == 2:
        await CosmicBotz.update_setting("caption_quality", args[1].strip())
        await message.answer(f"✅ Quality set to: <code>{args[1]}</code>", parse_mode="HTML")

@router.message(Command("setaudio"))
@owner_only
async def cmd_setaudio(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) == 2:
        await CosmicBotz.update_setting("caption_audio", args[1].strip())
        await message.answer(f"✅ Audio set to: <code>{args[1]}</code>", parse_mode="HTML")

@router.message(Command("setwatermark"))
@owner_only
async def cmd_setwatermark(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) == 2:
        await CosmicBotz.update_setting("watermark_text", args[1].strip())
        await message.answer(f"✅ Watermark: <code>{args[1]}</code>", parse_mode="HTML")

@router.message(Command("setlogo"))
@owner_only
async def cmd_setlogo(message: Message, **kwargs):
    if message.reply_to_message and message.reply_to_message.photo:
        file_id = message.reply_to_message.photo[-1].file_id
        await CosmicBotz.update_setting("watermark_logo_id", file_id)
        await message.answer("✅ Logo watermark saved!")

@router.message(Command("clearwatermark"))
@owner_only
async def cmd_clearwatermark(message: Message, **kwargs):
    await CosmicBotz.update_setting("watermark_text", "")
    await CosmicBotz.update_setting("watermark_logo_id", "")
    await message.answer("✅ Watermark cleared.")

# ── Abbreviations ─────────────────────────────────────────────────────────────

@router.message(Command("setabbr"))
@admin_only
async def cmd_setabbr(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or "=" not in args[1]:
        abbr_map = await CosmicBotz.get_abbr_map()
        lines = "\n".join(f"<code>{k}</code> → {v}" for k, v in sorted(abbr_map.items())) if abbr_map else "None"
        await message.answer(f"🔤 <b>Abbreviations</b>\n\n{lines}", parse_mode="HTML")
        return
    abbr, full = [x.strip() for x in args[1].split("=", 1)]
    await CosmicBotz.set_abbr(abbr, full)
    await message.answer(f"✅ <code>{abbr.upper()}</code> → <b>{full}</b>", parse_mode="HTML")

@router.message(Command("delabbr"))
@admin_only
async def cmd_delabbr(message: Message, **kwargs):
    args = message.text.split(maxsplit=1)
    if len(args) == 2:
        ok = await CosmicBotz.del_abbr(args[1].strip())
        await message.answer("✅ Removed" if ok else "⚠️ Not found")

# ── Filters & Missed Searches ────────────────────────────────────────────────

@router.message(Command(["filters", "lists"]))
@owner_only
async def cmd_filters(message: Message, **kwargs):
    from aiogram.types import BufferedInputFile
    db = CosmicBotz.db()
    cursor = db.filters.find({}).sort("title", 1)
    docs = await cursor.to_list(length=5000)
    if not docs:
        await message.answer("📭 No filters.")
        return
    lines = [f"{i}. {'✅' if d.get('posted') else '⏳'} [{d.get('media_type','?').title()}] {d.get('title','?')}" for i, d in enumerate(docs, 1)]
    full_text = "📋 Filter List\n" + "\n".join(lines)
    if len(full_text) > 3500:
        await message.answer_document(BufferedInputFile(full_text.encode(), filename="filters.txt"))
    else:
        await message.answer(f"<pre>{full_text}</pre>", parse_mode="HTML")

async def _missed_text_and_kb(settings: dict, results: list) -> tuple:
    logging_on = settings.get("missed_logging", True)
    toggle_label = "🔴 Disable Logging" if logging_on else "🟢 Enable Logging"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label, callback_data="missed_toggle"), 
         InlineKeyboardButton(text="🗑 Clear All", callback_data="missed_clear")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="missed_refresh")],
    ])
    if not results:
        text = f"🔍 <b>Missed Searches</b>\n\n✅ None! | Logging: {'On' if logging_on else 'Off'}"
    else:
        lines = [f"🔍 <b>Top Missed</b> | Logging: {'On' if logging_on else 'Off'}\n"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. <code>{r['query']}</code> — <b>{r['count']}x</b> in <b>{len(r.get('groups',[]))}</b>")
        text = "\n".join(lines)
    return text, kb

@router.message(Command("missed"))
@owner_only
async def cmd_missed(message: Message, **kwargs):
    settings = await CosmicBotz.get_settings()
    results  = await CosmicBotz.get_missed_searches(limit=15)
    text, kb = await _missed_text_and_kb(settings, results)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "missed_toggle")
async def cb_missed_toggle(call: CallbackQuery, **kwargs):
    settings = await CosmicBotz.get_settings()
    new_val = not settings.get("missed_logging", True)
    await CosmicBotz.update_setting("missed_logging", new_val)
    settings["missed_logging"] = new_val
    results = await CosmicBotz.get_missed_searches(limit=15)
    text, kb = await _missed_text_and_kb(settings, results)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "missed_clear")
async def cb_missed_clear(call: CallbackQuery, **kwargs):
    await CosmicBotz.db().search_logs.delete_many({})
    await call.answer("🗑 Cleared!", show_alert=True)
    settings = await CosmicBotz.get_settings()
    text, kb = await _missed_text_and_kb(settings, [])
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data == "missed_refresh")
async def cb_missed_refresh(call: CallbackQuery, **kwargs):
    await call.answer()
    settings = await CosmicBotz.get_settings()
    results  = await CosmicBotz.get_missed_searches(limit=15)
    text, kb = await _missed_text_and_kb(settings, results)
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
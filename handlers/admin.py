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


# ── Settings helpers ──────────────────────────────────────────────────────────

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
        "⏱ <b>Auto-Revoke:</b> <code>" + str(revoke) + " min</code>\n"
        "📢 <b>Slots:</b> <code>" + str(len(slots)) + "</code>\n"
        "👥 <b>Admins:</b> <code>" + str(len(admins)) + "</code>\n\n"
        "✏️ <b>Caption</b>\n"
        "  Quality: <code>" + quality + "</code>\n"
        "  Audio:   <code>" + audio + "</code>\n\n"
        "🖼 <b>Watermark</b>\n"
        "  Text: <code>" + (wm_text or "—") + "</code>\n"
        "  Logo: " + ("✅ Set" if wm_logo else "—") + "\n"
    )
    kb = settings_keyboard(revoke)
    return text, kb


# ── /settings ─────────────────────────────────────────────────────────────────

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
    await call.answer("Refreshed ✅")
    text, kb = await _settings_text_and_kb()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("set_revoke_"))
async def cb_set_revoke(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer("⛔ Owner only.", show_alert=True)
        return
    minutes = int(call.data.split("_")[-1])
    await CosmicBotz.update_setting("auto_revoke_minutes", minutes)
    await call.answer("✅ Auto-revoke set to " + str(minutes) + " min")
    text, kb = await _settings_text_and_kb()
    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "settings_slots")
async def cb_settings_slots(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer()
        return
    slots = await CosmicBotz.get_slots_all()
    if not slots:
        await call.answer("No slots added yet.", show_alert=True)
        return
    lines = ["📢 <b>Slots</b>\n"]
    for s in slots:
        lines.append("• <b>" + s["slot_name"] + "</b> — <code>" + str(s["channel_id"]) + "</code>")
    await call.answer()
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "settings_admins")
async def cb_settings_admins(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer()
        return
    admins = await CosmicBotz.get_admins()
    if not admins:
        await call.answer("No admins added yet.", show_alert=True)
        return
    lines = ["👥 <b>Admins</b>\n"] + ["• <code>" + str(a) + "</code>" for a in admins]
    await call.answer()
    await call.message.answer("\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "settings_caption")
async def cb_settings_caption(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(
        "✏️ <b>Caption Commands</b>\n\n"
        "/setquality — set quality line\n"
        "/setaudio — set audio line\n"
        "/setcaption — view/edit full templates",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "settings_watermark")
async def cb_settings_watermark(call: CallbackQuery, is_owner: bool = False, **kwargs):
    if not is_owner:
        await call.answer()
        return
    await call.answer()
    await call.message.answer(
        "🖼 <b>Watermark Commands</b>\n\n"
        "/setwatermark TEXT — set watermark text\n"
        "/setlogo — reply to a photo to set logo\n"
        "/clearwatermark — remove watermark",
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
    from services.caption import DEFAULT_TEMPLATE_SERIES, DEFAULT_TEMPLATE_MOVIE, CAPTION_VARIABLES

    args     = message.text.split(maxsplit=2)
    settings = await _db.get_settings()

    # /setcaption — show current templates + all variables
    if len(args) == 1:
        series_t = settings.get("caption_template_series", DEFAULT_TEMPLATE_SERIES)
        movie_t  = settings.get("caption_template_movie",  DEFAULT_TEMPLATE_MOVIE)
        vars_txt = "\n".join(f"<code>{k}</code> — {v}" for k, v in CAPTION_VARIABLES.items())
        await message.answer(
            "✏️ <b>Caption Templates</b>\n\n"
            "<b>📺 Series/Anime template:</b>\n"
            f"<code>{series_t}</code>\n\n"
            "<b>🎬 Movie template:</b>\n"
            f"<code>{movie_t}</code>\n\n"
            "──────────────\n"
            "<b>Available variables:</b>\n"
            f"{vars_txt}\n\n"
            "To change:\n"
            "<code>/setcaption series YOUR TEMPLATE</code>\n"
            "<code>/setcaption movie YOUR TEMPLATE</code>\n"
            "<code>/setcaption reset</code> — restore defaults\n\n"
            "<i>Use \\n for line breaks in template</i>",
            parse_mode="HTML"
        )
        return

    sub = args[1].lower().strip()

    if sub == "reset":
        await _db.update_setting("caption_template_series", DEFAULT_TEMPLATE_SERIES)
        await _db.update_setting("caption_template_movie",  DEFAULT_TEMPLATE_MOVIE)
        await message.answer("✅ Caption templates reset to defaults.")
        return

    if sub not in ("series", "movie"):
        await message.answer(
            "Usage:\n"
            "<code>/setcaption series TEMPLATE</code>\n"
            "<code>/setcaption movie TEMPLATE</code>\n"
            "<code>/setcaption reset</code>",
            parse_mode="HTML"
        )
        return

    if len(args) < 3:
        await message.answer(
            f"⚠️ Provide a template after <code>{sub}</code>.\n\n"
            "Example:\n"
            "<code>/setcaption series &lt;b&gt;{{title}}&lt;/b&gt;\n&lt;blockquote&gt;▶ Episodes: {{episodes}}\n▶ Audio: {{audio}}&lt;/blockquote&gt;</code>",
            parse_mode="HTML"
        )
        return

    template = args[2].strip().replace("\\n", "\n")

    # Validate — try formatting with dummy data
    try:
        template.format(
            title="Test", type="Anime Series (2020)", year="2020",
            status="Ended", episodes="24", season="1",
            quality="1080p", audio="Hindi", genres="Action",
            runtime="24", overview="Test overview"
        )
    except KeyError as e:
        await message.answer(
            f"⚠️ Unknown variable: <code>{e}</code>\n"
            "Use /setcaption to see valid variables.",
            parse_mode="HTML"
        )
        return

    key = "caption_template_series" if sub == "series" else "caption_template_movie"
    await _db.update_setting(key, template)
    await message.answer(f"✅ <b>{sub.title()}</b> caption template updated!", parse_mode="HTML")


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


# ── /filters ──────────────────────────────────────────────────────────────────

@router.message(Command("filters"))
@owner_only
async def cmd_filters(message: Message, **kwargs):
    from database import CosmicBotz as _db
    from aiogram.types import BufferedInputFile

    db     = _db.db()
    cursor = db.filters.find({}).sort("title", 1)
    docs   = await cursor.to_list(length=5000)

    if not docs:
        await message.answer("📭 No filters saved yet.")
        return

    lines = []
    for i, d in enumerate(docs, 1):
        status  = "✅" if d.get("posted") else "⏳"
        mtype   = d.get("media_type", "?").title()
        year    = d.get("year", "")
        year_str = (" (" + str(year) + ")") if year else ""
        lines.append(str(i) + ". " + status + " [" + mtype + "] " + d.get("title", "?") + year_str)

    total  = len(docs)
    posted = sum(1 for d in docs if d.get("posted"))
    header = (
        "📋 All Filters (" + str(total) + " total | "
        + str(posted) + " posted | "
        + str(total - posted) + " pending)\n"
        + "─" * 30 + "\n"
    )

    full_text = header + "\n".join(lines)

    # Send as file if too long
    if len(full_text) > 3500:
        file_bytes = full_text.encode("utf-8")
        await message.answer_document(
            BufferedInputFile(file_bytes, filename="filters.txt"),
            caption="📋 <b>All Filters</b> — " + str(total) + " total, " + str(posted) + " posted",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "<pre>" + full_text + "</pre>",
            parse_mode="HTML"
        )


# ── /missed ───────────────────────────────────────────────────────────────────

@router.message(Command("missed"))
@owner_only
async def cmd_missed(message: Message, **kwargs):
    results = await CosmicBotz.get_missed_searches(limit=15)
    if not results:
        await message.answer("✅ No missed searches yet — everything found!")
        return

    lines = ["🔍 <b>Top Missed Searches</b>\n"]
    for i, r in enumerate(results, 1):
        q      = r.get("query", "?")
        count  = r.get("count", 1)
        groups = len(r.get("groups", []))
        lines.append(
            str(i) + ". <code>" + q + "</code>"
            " — <b>" + str(count) + "x</b>"
            " in <b>" + str(groups) + "</b> group(s)"
        )

    lines.append("\n<i>Add content with /addcontent to clear these.</i>")
    await message.answer("\n".join(lines), parse_mode="HTML")

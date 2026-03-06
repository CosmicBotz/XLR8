"""
/addcontent — TMDB wizard.
On confirm:
  1. Resize poster to 1280x720
  2. Post image + caption + permanent invite link to LOG_CHANNEL (stored once)
  3. Save message_id + permanent_invite to filter index in DB
No TMDB calls on user requests — everything reused from log channel copy.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, URLInputFile, BufferedInputFile
from io import BytesIO
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import CosmicBotz
from middlewares.auth import admin_only
from services.tmdb import search_tmdb, get_tv_details, get_movie_details, build_media_data
from services.caption import build_caption
from services.thumbnail import build_thumbnail
from keyboards.inline import (
    tmdb_results_keyboard, media_type_keyboard,
    confirm_add_keyboard, watch_download_keyboard
)
from config import LOG_CHANNEL_ID
import json

router = Router()


class AddContentState(StatesGroup):
    select_media_type = State()
    search_query      = State()
    select_result     = State()
    confirm_add       = State()


# ── /addcontent ───────────────────────────────────────────────────────────────

@router.message(Command("addcontent"))
@admin_only
async def cmd_addcontent(message: Message, state: FSMContext, **kwargs):
    await state.clear()
    await message.answer(
        "🎬 <b>Add New Content</b>\n\nSelect the media type:",
        reply_markup=media_type_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AddContentState.select_media_type)


@router.callback_query(F.data.startswith("mtype_"), AddContentState.select_media_type)
async def cb_media_type(call: CallbackQuery, state: FSMContext):
    mtype = call.data.split("_")[1]
    label = {"anime": "Anime 🎌", "tvshow": "TV Show 📺", "movie": "Movie 🎬"}.get(mtype, mtype)
    await state.update_data(media_type=mtype)
    await call.message.edit_text(
        f"✅ Type: <b>{label}</b>\n\nSend the <b>title</b> to search on TMDB:",
        parse_mode="HTML"
    )
    await state.set_state(AddContentState.search_query)


@router.message(AddContentState.search_query)
async def got_search_query(message: Message, state: FSMContext):
    query     = message.text.strip()
    data      = await state.get_data()
    mtype     = data.get("media_type", "anime")
    tmdb_type = "movie" if mtype == "movie" else "tv"

    await message.answer(f"🔍 Searching TMDB for: <b>{query}</b>...", parse_mode="HTML")

    try:
        results = await search_tmdb(query, tmdb_type)
    except Exception as e:
        await message.answer(f"❌ TMDB search failed: {e}")
        await state.clear()
        return

    if not results:
        await message.answer("❌ No results found. Try a different title.")
        return

    await state.update_data(tmdb_results=json.dumps(results[:5]))
    await message.answer(
        f"📋 Found <b>{len(results[:5])}</b> results. Select the correct one:",
        reply_markup=tmdb_results_keyboard(results[:5], mtype),
        parse_mode="HTML"
    )
    await state.set_state(AddContentState.select_result)


@router.callback_query(F.data.startswith("tmdb_"), AddContentState.select_result)
async def cb_select_tmdb(call: CallbackQuery, state: FSMContext, bot: Bot):
    parts   = call.data.split("_")
    mtype   = parts[1]
    tmdb_id = int(parts[2])

    await call.message.edit_text("⏳ Fetching details from TMDB...")

    try:
        details    = await (get_movie_details(tmdb_id) if mtype == "movie" else get_tv_details(tmdb_id))
        media_data = build_media_data(details, mtype)
    except Exception as e:
        await call.message.edit_text(f"❌ Failed to fetch details: {e}")
        await state.clear()
        return

    await state.update_data(media_data=json.dumps(media_data))

    # Preview to admin (resized)
    caption = await build_caption(media_data)
    poster  = media_data.get("poster_url")
    try:
        settings = await CosmicBotz.get_settings()
        wm_text  = settings.get("watermark_text", "")
        wm_logo  = settings.get("watermark_logo_id", "")
        thumb = await build_thumbnail(
            poster_url=poster,
            backdrop_url=media_data.get("backdrop_url"),
            watermark=wm_text,
            watermark_logo_id=wm_logo,
            bot=call.bot,
            meta={**media_data, "_category": media_data.get("media_type", "anime")}
        )
        await call.message.answer_photo(
            BufferedInputFile(thumb, filename="poster.jpg"),
            caption=caption, parse_mode="HTML"
        )
    except Exception as e:
        await call.message.answer("Thumbnail error: " + str(e), parse_mode="HTML")



    await call.message.answer(
        "✅ Confirm adding to index?\n"
        "<i>Bot will post to Log Channel with a permanent invite link.</i>",
        reply_markup=confirm_add_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AddContentState.confirm_add)


@router.callback_query(F.data == "confirm_add", AddContentState.confirm_add)
async def cb_confirm_add(call: CallbackQuery, state: FSMContext, bot: Bot):
    data       = await state.get_data()
    media_data = json.loads(data.get("media_data", "{}"))
    await state.clear()

    if not LOG_CHANNEL_ID:
        await call.message.edit_text(
            "❌ <b>LOG_CHANNEL_ID</b> is not set in config!\n"
            "Set it in your .env and redeploy.",
            parse_mode="HTML"
        )
        return

    # Save to filter index first to get filter_id
    filter_id = await CosmicBotz.add_filter(media_data.copy())
    if not filter_id:
        await call.message.edit_text("⚠️ This title already exists in the index!")
        return

    settings = await CosmicBotz.get_settings()
    title  = media_data.get("title", "?")
    letter = title[0].upper()
    poster = media_data.get("poster_url")

    await call.message.edit_text("⏳ Posting to Log Channel...")

    # ── Create permanent invite link ──────────────────────────────────────────
    slots = await CosmicBotz.get_slots_all()
    permanent_invite = None

    if slots:
        try:
            # Permanent = no expire_date, no member_limit
            link = await bot.create_chat_invite_link(
                chat_id=slots[0]["channel_id"],
                creates_join_request=False
            )
            permanent_invite = link.invite_link
        except Exception as e:
            permanent_invite = None

    # ── Build caption + keyboard for log channel ──────────────────────────────
    caption = await build_caption(media_data)
    kb      = watch_download_keyboard(permanent_invite) if permanent_invite else None

    # ── Post to log channel (resized 1280x720) ────────────────────────────────
    try:
        thumb = await build_thumbnail(
            poster_url=poster,
            backdrop_url=media_data.get("backdrop_url"),
            watermark=settings.get("watermark_text", ""),
            watermark_logo_id=settings.get("watermark_logo_id", ""),
            bot=bot,
            meta={**media_data, "_category": media_data.get("media_type", "anime")}
        )
        log_msg = await bot.send_photo(
            chat_id=LOG_CHANNEL_ID,
            photo=BufferedInputFile(thumb, filename="poster.jpg"),
            caption=caption,
            reply_markup=kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await call.message.edit_text(f"❌ Failed to post to Log Channel: {e}")
        return

    # ── Store log channel message info in DB ──────────────────────────────────
    await CosmicBotz.update_filter_post(
        filter_id=filter_id,
        log_channel_id=LOG_CHANNEL_ID,
        message_id=log_msg.message_id,
        permanent_invite=permanent_invite or ""
    )

    await call.message.edit_text(
        f"✅ <b>{title}</b> added!\n"
        f"📂 Index: <b>{letter}</b>\n"
        f"📋 Posted to Log Channel\n"
        f"🔗 Permanent invite: {'✅' if permanent_invite else '❌ No slot configured'}",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "cancel_add")
async def cb_cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Cancelled.")


@router.callback_query(F.data == "cancel_tmdb")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Cancelled.")

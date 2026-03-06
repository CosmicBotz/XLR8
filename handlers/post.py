"""
/addcontent — TMDB wizard to add anime/movie/tvshow to the filter index.
No channel posting. Bot saves metadata to DB and logs to LOG_CHANNEL.
"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, URLInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import CosmicBotz
from middlewares.auth import admin_only
from services.tmdb import search_tmdb, get_tv_details, get_movie_details, build_media_data
from services.caption import build_caption
from keyboards.inline import tmdb_results_keyboard, media_type_keyboard
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

    # Show preview to admin
    caption = build_caption(media_data)
    poster  = media_data.get("poster_url")
    try:
        if poster:
            await call.message.answer_photo(
                URLInputFile(poster), caption=caption, parse_mode="HTML"
            )
        else:
            await call.message.answer(caption, parse_mode="HTML")
    except Exception:
        await call.message.answer(caption, parse_mode="HTML")

    from keyboards.inline import confirm_add_keyboard
    await call.message.answer(
        "✅ Confirm adding this to the index?",
        reply_markup=confirm_add_keyboard(),
        parse_mode="HTML"
    )
    await state.set_state(AddContentState.confirm_add)


@router.callback_query(F.data == "confirm_add", AddContentState.confirm_add)
async def cb_confirm_add(call: CallbackQuery, state: FSMContext, bot: Bot):
    data       = await state.get_data()
    media_data = json.loads(data.get("media_data", "{}"))
    await state.clear()

    # Save to filter index
    filter_id = await CosmicBotz.add_filter(media_data.copy())
    if not filter_id:
        await call.message.edit_text(
            "⚠️ This title already exists in the index!"
        )
        return

    title = media_data.get("title", "?")
    mtype = media_data.get("media_type", "")
    letter = title[0].upper()

    await call.message.edit_text(
        f"✅ <b>{title}</b> added to index!\n"
        f"📂 Indexed under: <b>{letter}</b>",
        parse_mode="HTML"
    )

    # Log to LOG_CHANNEL
    if LOG_CHANNEL_ID:
        type_emoji = {"anime": "🎌", "tvshow": "📺", "movie": "🎬"}.get(mtype, "🎬")
        poster = media_data.get("poster_url")
        log_caption = (
            f"📥 <b>New content added</b>\n\n"
            f"{type_emoji} <b>{title}</b>\n"
            f"📂 Index: <b>{letter}</b>\n"
            f"👤 Added by: <code>{call.from_user.id}</code>"
        )
        try:
            if poster:
                await bot.send_photo(
                    chat_id=LOG_CHANNEL_ID,
                    photo=URLInputFile(poster),
                    caption=log_caption,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=LOG_CHANNEL_ID,
                    text=log_caption,
                    parse_mode="HTML"
                )
        except Exception as e:
            pass  # don't break flow if log fails


@router.callback_query(F.data == "cancel_add")
async def cb_cancel_add(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Cancelled.")


@router.callback_query(F.data == "cancel_tmdb")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("❌ Cancelled.")

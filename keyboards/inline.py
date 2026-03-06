from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def watch_download_keyboard(invite_link: str, expires_text: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    label = f"🎬 Watch / Download"
    if expires_text:
        label += f"  ⏳ {expires_text}"
    builder.button(text=label, url=invite_link)
    return builder.as_markup()


def index_results_keyboard(results: list) -> InlineKeyboardMarkup:
    """Each button triggers bot to send poster+caption+invite link."""
    builder = InlineKeyboardBuilder()
    for item in results:
        title = item.get("title", "?")
        builder.button(
            text=f"🎬 {title}",
            callback_data=f"show_{str(item['_id'])}"
        )
    builder.adjust(1)
    return builder.as_markup()


def tmdb_results_keyboard(results: list, media_type: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, r in enumerate(results):
        title = r.get("title") or r.get("name", "?")
        year  = (r.get("release_date") or r.get("first_air_date") or "")[:4]
        label = f"{title} ({year})" if year else title
        builder.button(
            text=label[:50],
            callback_data=f"tmdb_{media_type}_{r['id']}_{i}"
        )
    builder.button(text="❌ Cancel", callback_data="cancel_tmdb")
    builder.adjust(1)
    return builder.as_markup()


def media_type_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎌 Anime",    callback_data="mtype_anime")
    builder.button(text="📺 TV Show",  callback_data="mtype_tvshow")
    builder.button(text="🎬 Movie",    callback_data="mtype_movie")
    builder.button(text="❌ Cancel",   callback_data="cancel_tmdb")
    builder.adjust(3, 1)
    return builder.as_markup()


def confirm_add_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Add to Index", callback_data="confirm_add")
    builder.button(text="❌ Cancel",       callback_data="cancel_add")
    builder.adjust(2)
    return builder.as_markup()


def slot_list_keyboard(slots: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in slots:
        builder.button(
            text=f"📢 {slot['slot_name']}",
            callback_data=f"slot_{slot['channel_id']}"
        )
    builder.adjust(1)
    return builder.as_markup()


def admin_list_keyboard(admins: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for uid in admins:
        builder.button(text=f"👤 {uid}", callback_data=f"rmadmin_{uid}")
    builder.button(text="🔙 Back", callback_data="back_settings")
    builder.adjust(2)
    return builder.as_markup()

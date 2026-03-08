from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
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


def confirm_delete_keyboard(filter_id: str, title: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=f"🗑 Yes, Delete",  callback_data=f"delconfirm_{filter_id}")
    builder.button(text="❌ Cancel",         callback_data="delcancel")
    builder.adjust(2)
    return builder.as_markup()


def delete_search_keyboard(results: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for item in results:
        label = f"{item.get('title','?')} ({item.get('media_type','?')})"
        builder.button(text=label[:50], callback_data=f"delselect_{str(item['_id'])}")
    builder.button(text="❌ Cancel", callback_data="delcancel")
    builder.adjust(1)
    return builder.as_markup()


def join_groups_keyboard(groups: list) -> InlineKeyboardMarkup:
    """Inline buttons to join verified groups — shown in DM."""
    builder = InlineKeyboardBuilder()
    for g in groups[:5]:
        name = g.get("group_name") or g.get("title") or "Join Group"
        link = g.get("invite_link", "")
        if link:
            builder.button(text=f"📢 {name}", url=link)
    builder.adjust(1)
    return builder.as_markup()


def quick_add_slot_keyboard(channel_id: int, channel_name: str = "") -> InlineKeyboardMarkup:
    """Notification buttons when bot is made admin in a channel.
    Fits channel name inside Telegram's 64-byte callback_data limit.
    """
    prefix   = "qslot_add|" + str(channel_id) + "|"
    max_name = 64 - len(prefix.encode())          # bytes left for name
    name_trunc = channel_name.encode()[:max_name].decode("utf-8", errors="ignore").strip()
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="➕ Add as Slot",
            callback_data=prefix + name_trunc
        ),
        InlineKeyboardButton(
            text="❌ Ignore",
            callback_data="qslot_ignore"
        )
    ]])


def settings_keyboard(current_revoke: int = 30) -> InlineKeyboardMarkup:
    """Inline keyboard for /settings panel."""
    def revoke_btn(minutes: int) -> InlineKeyboardButton:
        label = ("✅ " if minutes == current_revoke else "") + str(minutes) + "m"
        return InlineKeyboardButton(text=label, callback_data="set_revoke_" + str(minutes))

    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📢 Slots",        callback_data="settings_slots"),
            InlineKeyboardButton(text="👥 Admins",       callback_data="settings_admins"),
        ],
        [
            InlineKeyboardButton(text="✏️ Caption",      callback_data="settings_caption"),
            InlineKeyboardButton(text="🖼 Watermark",    callback_data="settings_watermark"),
        ],
        [
            InlineKeyboardButton(text="⏱ Revoke:", callback_data="settings_refresh"),
            revoke_btn(15),
            revoke_btn(30),
            revoke_btn(60),
        ],
        [
            InlineKeyboardButton(text="🔄 Refresh",      callback_data="settings_refresh"),
        ]
    ])


def quick_tmdb_keyboard(results: list, channel_id: int) -> InlineKeyboardMarkup:
    """Show TMDB search results for quick-slot auto-flow."""
    rows = []
    for r in results[:5]:
        tmdb_id = r.get("id", 0)
        title   = (r.get("title") or r.get("name") or "Unknown")[:40]
        year    = (r.get("release_date") or r.get("first_air_date") or "")[:4]
        mtype   = "movie" if r.get("release_date") else "tv"
        label   = title + (" (" + year + ")" if year else "")
        cb      = "qslot_tmdb|" + str(channel_id) + "|" + str(tmdb_id) + "|" + mtype
        rows.append([InlineKeyboardButton(text=label, callback_data=cb)])
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="qslot_cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

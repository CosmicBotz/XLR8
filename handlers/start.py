import random
from datetime import datetime
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandStart
from aiogram.enums import ChatType

from database import CosmicBotz
from analytics import Analytics
from config import START_PICS

START_TIME = datetime.utcnow()  # set when module loads

router = Router()


def _owner_text(name: str) -> str:
    return (
        "👋 Welcome back, <b>" + name + "</b>!\n\n"
        "🤖 <b>Auto Filter CosmicBotz</b> — Owner Panel\n\n"

        "📢 <b>Slots</b>\n"
        "/addslot · /removeslot · /slots\n\n"

        "🎬 <b>Content</b>\n"
        "/addcontent · /delcontent · /filters\n\n"

        "👥 <b>Admins</b>\n"
        "/addadmin · /removeadmin · /admins\n\n"

        "🌐 <b>Groups</b>\n"
        "/groups · /verifygroup · /unverify\n\n"

        "✏️ <b>Caption &amp; Thumbnail</b>\n"
        "/setcaption · /setquality · /setaudio\n"
        "/setwatermark · /setlogo · /clearwatermark\n\n"

        "🔤 <b>Abbreviations</b>\n"
        "/setabbr · /delabbr\n\n"

        "📊 <b>Analytics</b>\n"
        "/stats · /missed\n\n"

        "⚙️ <b>Config</b>\n"
        "/settings · /setrevoke\n\n"

        "🛠 <b>System</b>\n"
        "/ping · /uptime"
    )


def _admin_text(name: str) -> str:
    return (
        "👋 Hello, <b>" + name + "</b>!\n\n"
        "🤖 <b>Auto Filter CosmicBotz</b> — Admin Panel\n\n"

        "🎬 <b>Content</b>\n"
        "/addcontent · /delcontent · /filters\n\n"

        "📊 <b>Analytics</b>\n"
        "/stats · /missed\n\n"

        "🛠 <b>System</b>\n"
        "/ping · /uptime\n\n"

        "Send a letter <b>(A–Z)</b> to browse the index."
    )


def _user_text(name: str) -> str:
    return (
        "👋 Hello, <b>" + name + "</b>!\n\n"
        "🤖 <b>Auto Filter CosmicBotz</b>\n\n"
        "Join our group to browse and get content.\n\n"
        "/help — how to use the bot"
    )


def _group_verified_text() -> str:
    return (
        "🤖 <b>Auto Filter CosmicBotz</b> is active!\n\n"
        "📂 Send a <b>letter</b> (A–Z) to browse the index.\n"
        "🔍 Or type a <b>title</b> to search directly.\n\n"
        "/help — usage guide"
    )


def _group_unverified_text() -> str:
    return (
        "🤖 <b>Auto Filter CosmicBotz</b>\n\n"
        "⚠️ This group is <b>not verified</b> yet.\n"
        "An owner or admin must send /verify to unlock all features."
    )


async def _send_start(message: Message, text: str):
    if START_PICS:
        photo = random.choice(START_PICS)
        try:
            await message.answer_photo(photo=photo, caption=text, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, parse_mode="HTML")


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(
    message: Message,
    is_owner: bool = False,
    is_admin: bool = False,
    **kwargs
):
    name       = message.from_user.full_name
    is_private = message.chat.type == ChatType.PRIVATE

    if is_private:
        if is_owner:
            text = _owner_text(name)
        elif is_admin:
            text = _admin_text(name)
        else:
            text = _user_text(name)
    else:
        verified = await CosmicBotz.is_group_verified(message.chat.id)
        text = _group_verified_text() if verified else _group_unverified_text()

    await _send_start(message, text)


# ── /help ─────────────────────────────────────────────────────────────────────

@router.message(Command("help"))
async def cmd_help(message: Message, is_owner: bool = False, is_admin: bool = False, **kwargs):
    is_private    = message.chat.type == ChatType.PRIVATE
    is_privileged = is_owner or is_admin

    if is_private and is_privileged:
        await message.answer(
            "📖 <b>Admin Usage</b>\n\n"
            "<b>Adding content:</b>\n"
            "1. /addslot — register a channel (bot must be admin there)\n"
            "2. /addcontent — search TMDB, pick slot, post\n\n"
            "<b>Managing content:</b>\n"
            "/filters — list all indexed titles with status\n"
            "/delcontent TITLE — remove a title\n"
            "/missed — top searches with no results\n\n"
            "<b>Groups:</b>\n"
            "/groups — list all groups\n"
            "/verifygroup ID — verify a group from DM\n"
            "/verify — verify current group (use inside group)\n\n"
            "<b>Settings:</b>\n"
            "/settings — full config panel with inline buttons\n"
            "/setrevoke MINUTES — auto-delete timer\n"
            "/setcaption — view/edit post templates\n\n"
            "<b>Filters work in your DM too</b> — send any letter or title.",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "📖 <b>How to use:</b>\n\n"
            "• Send a <b>letter</b> (A–Z) → browse all titles under that letter\n"
            "• Send a <b>title name</b> → search directly\n"
            "• Tap a result → get the Watch/Download link\n"
            "• Link auto-expires after a set time\n\n"
            "Works only inside verified groups.",
            parse_mode="HTML"
        )


# ── /stats ────────────────────────────────────────────────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message, **kwargs):
    s = await CosmicBotz.get_stats()
    a = await Analytics.get_analytics()

    top_q   = ("<code>" + a["top_today"] + "</code>") if a["top_today"] else "—"
    top_grp = (
        "<code>" + str(a["top_group_id"]) + "</code>"
        " (" + str(a["top_group_cnt"]) + " searches)"
    ) if a["top_group_id"] else "—"

    await message.answer(
        "📊 <b>Bot Statistics</b>\n\n"
        "📂 <b>Content Index</b>\n"
        "  🎌 Anime: <b>" + str(s["anime"]) + "</b>\n"
        "  📺 TV Shows: <b>" + str(s["tvshow"]) + "</b>\n"
        "  🎬 Movies: <b>" + str(s["movie"]) + "</b>\n"
        "  📦 Total: <b>" + str(s["total"]) + "</b>\n\n"
        "🌐 <b>Infrastructure</b>\n"
        "  Groups: <b>" + str(s["groups"]) + "</b>  |  Verified: <b>" + str(s["verified_groups"]) + "</b>\n"
        "  Slots: <b>" + str(s["slots"]) + "</b>\n\n"
        "🔍 <b>Search Today</b>\n"
        "  Total: <b>" + str(a["today_searches"]) + "</b>"
        "  |  Found: <b>" + str(a["today_found"]) + "</b>"
        "  |  Missed: <b>" + str(a["today_missed"]) + "</b>\n"
        "  🔥 Top query: " + top_q + "\n"
        "  🏆 Most active group: " + top_grp + "\n\n"
        "📈 All-time searches: <b>" + str(a["total_searches"]) + "</b>",
        parse_mode="HTML"
    )


# ── /ping ─────────────────────────────────────────────────────────────────────

@router.message(Command("ping"))
async def cmd_ping(message: Message, **kwargs):
    import time
    t    = time.monotonic()
    sent = await message.answer("🏓 Pong!")
    ms   = round((time.monotonic() - t) * 1000)
    await sent.edit_text(
        "<b>🏓 Pong!</b>  <code>" + str(ms) + "ms</code>",
        parse_mode="HTML"
    )


# ── /uptime ───────────────────────────────────────────────────────────────────

@router.message(Command("uptime"))
async def cmd_uptime(message: Message, **kwargs):
    delta   = datetime.utcnow() - START_TIME
    days    = delta.days
    hours   = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    seconds = delta.seconds % 60

    parts = []
    if days:    parts.append("<b>" + str(days) + "d</b>")
    if hours:   parts.append("<b>" + str(hours) + "h</b>")
    if minutes: parts.append("<b>" + str(minutes) + "m</b>")
    parts.append("<b>" + str(seconds) + "s</b>")

    await message.answer(
        "🟢 <b>Bot Uptime</b>\n\n⏱ " + " ".join(parts),
        parse_mode="HTML"
    )

MEDIA_EMOJI = {
    "anime": "🎌",
    "tvshow": "📺",
    "movie": "🎬"
}


def build_caption(media_data: dict) -> str:
    """Build formatted caption from media data."""
    mtype = media_data.get("media_type", "anime")
    emoji = MEDIA_EMOJI.get(mtype, "🎬")
    title = media_data.get("title", "Unknown")
    quality = media_data.get("quality", "Multiple")
    audio = media_data.get("audio", "हिंदी (Hindi)")
    audio_tag = media_data.get("audio_tag", "#Official")
    genres = media_data.get("genres", "N/A")
    overview = media_data.get("overview", "")

    lines = [f"{emoji} <b>{title}</b>\n"]

    if mtype in ("anime", "tvshow"):
        episodes = media_data.get("episodes", "N/A")
        season = media_data.get("season", "01")
        lines += [
            f"▶ <b>Episodes:</b> {episodes}",
            f"▶ <b>Season:</b> {season}",
        ]
    elif mtype == "movie":
        release = media_data.get("release_date", "N/A")
        runtime = media_data.get("runtime", "N/A")
        lines += [
            f"▶ <b>Release:</b> {release}",
            f"▶ <b>Runtime:</b> {runtime} min",
        ]

    lines += [
        f"▶ <b>Quality:</b> {quality}",
        f"▶ <b>Audio:</b> {audio} {audio_tag}",
        f"▶ <b>Genres:</b> {genres}",
    ]

    if overview:
        short_overview = overview[:200] + "..." if len(overview) > 200 else overview
        lines.append(f"\n📝 {short_overview}")

    return "\n".join(lines)


def build_index_caption(letter: str, results: list) -> str:
    """Build caption for letter index response."""
    count = len(results)
    return (
        f"📂 <b>Index: '{letter.upper()}'</b>\n"
        f"Total Results: <b>{count}</b>"
    )

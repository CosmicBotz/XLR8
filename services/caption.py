MEDIA_EMOJI = {
    "anime":  "🎌",
    "tvshow": "📺",
    "movie":  "🎬"
}

MEDIA_TYPE_LABEL = {
    "anime":  "Anime Series",
    "tvshow": "TV Series",
    "movie":  "Movie"
}


def build_caption(media_data: dict) -> str:
    mtype   = media_data.get("media_type", "anime")
    title   = media_data.get("title", "Unknown")
    genres  = media_data.get("genres", "N/A")
    quality = media_data.get("quality", "1080p FHD | 720p HD | 480p WEB-DL")
    audio   = media_data.get("audio", "हिंदी (Hindi)")
    label   = MEDIA_TYPE_LABEL.get(mtype, "Series")

    lines = [f"<b>{title}</b>", ""]

    lines.append(f"<blockquote>")

    if mtype in ("anime", "tvshow"):
        year     = (media_data.get("first_air_date") or media_data.get("release_date") or "")[:4]
        episodes = media_data.get("episodes", "N/A")
        season   = media_data.get("seasons", 1)
        status   = media_data.get("status", "N/A")
        lines += [
            f"▶ <b>Type :</b> {label}{f' ({year})' if year else ''}",
            f"▶ <b>Status :</b> {status}",
            f"▶ <b>No of Episodes :</b> {episodes}",
            f"▶ <b>Season :</b> {season}",
            f"▶ <b>Quality :</b> {quality}",
            f"▶ <b>Audio :</b> {audio}",
            f"<b>Genre :</b> {genres}",
        ]
    elif mtype == "movie":
        year    = (media_data.get("release_date") or "")[:4]
        runtime = media_data.get("runtime", "N/A")
        lines += [
            f"▶ <b>Type :</b> {label}{f' ({year})' if year else ''}",
            f"▶ <b>Runtime :</b> {runtime} min",
            f"▶ <b>Quality :</b> {quality}",
            f"▶ <b>Audio :</b> {audio}",
            f"<b>Genre :</b> {genres}",
        ]

    lines.append(f"</blockquote>")

    return "\n".join(lines)


def build_index_caption(letter: str, results: list) -> str:
    count = len(results)
    return (
        f"📂 <b>Index: '{letter.upper()}'</b>\n"
        f"Total Results: <b>{count}</b>"
    )

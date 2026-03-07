"""
caption.py — Build post captions from a customizable template.
Template variables: {title} {type} {year} {status} {episodes} {season} {quality} {audio} {genres} {runtime}
Template stored in DB settings via /setcaption.
"""

MEDIA_TYPE_LABEL = {
    "anime":  "Anime Series",
    "tvshow": "TV Series",
    "movie":  "Movie"
}

DEFAULT_QUALITY  = "1080p FHD | 720p HD | 480p WEB-DL"
DEFAULT_AUDIO    = "हिंदी (Hindi)"

# Default templates — admin can override via /setcaption
DEFAULT_TEMPLATE_SERIES = (
    "<b>{title}</b>\n"
    "<blockquote>"
    "▶ <b>Type :</b> {type}\n"
    "▶ <b>Status :</b> {status}\n"
    "▶ <b>No of Episodes :</b> {episodes}\n"
    "▶ <b>Season :</b> {season}\n"
    "▶ <b>Quality :</b> {quality}\n"
    "▶ <b>Audio :</b> {audio}\n"
    "<b>Genre :</b> {genres}"
    "</blockquote>"
)

DEFAULT_TEMPLATE_MOVIE = (
    "<b>{title}</b>\n"
    "<blockquote>"
    "▶ <b>Type :</b> {type}\n"
    "▶ <b>Runtime :</b> {runtime} min\n"
    "▶ <b>Quality :</b> {quality}\n"
    "▶ <b>Audio :</b> {audio}\n"
    "<b>Genre :</b> {genres}"
    "</blockquote>"
)

# All available variables with descriptions — shown in /setcaption
CAPTION_VARIABLES = {
    "{title}":    "Anime/Show/Movie title",
    "{type}":     "Media type + year e.g. Anime Series (2019)",
    "{year}":     "Release year",
    "{status}":   "Airing status",
    "{episodes}": "Total episodes",
    "{season}":   "Number of seasons",
    "{quality}":  "Quality (set via /setquality)",
    "{audio}":    "Audio language (set via /setaudio)",
    "{genres}":   "Genres",
    "{runtime}":  "Runtime in minutes (movies)",
    "{overview}": "TMDB plot overview",
}


async def _get_settings() -> dict:
    try:
        from database import CosmicBotz
        return await CosmicBotz.get_settings()
    except Exception:
        return {}


async def build_caption(media_data: dict) -> str:
    settings = await _get_settings()
    quality  = media_data.get("quality") or settings.get("caption_quality", DEFAULT_QUALITY)
    audio    = media_data.get("audio")   or settings.get("caption_audio",   DEFAULT_AUDIO)

    mtype    = media_data.get("media_type", "anime")
    title    = media_data.get("title", "Unknown")
    genres   = media_data.get("genres", "N/A")
    overview = media_data.get("overview", "")
    label    = MEDIA_TYPE_LABEL.get(mtype, "Series")

    if mtype in ("anime", "tvshow"):
        year     = (media_data.get("first_air_date") or media_data.get("release_date") or "")[:4]
        episodes = str(media_data.get("episodes", "N/A"))
        season   = str(media_data.get("seasons", 1))
        status   = media_data.get("status", "N/A")
        type_str = f"{label} ({year})" if year else label
        runtime  = "N/A"
        template = settings.get("caption_template_series", DEFAULT_TEMPLATE_SERIES)
    else:
        year     = (media_data.get("release_date") or "")[:4]
        episodes = "N/A"
        season   = "N/A"
        status   = "N/A"
        runtime  = str(media_data.get("runtime", "N/A"))
        type_str = f"{label} ({year})" if year else label
        template = settings.get("caption_template_movie", DEFAULT_TEMPLATE_MOVIE)

    return template.format(
        title    = title,
        type     = type_str,
        year     = year,
        status   = status,
        episodes = episodes,
        season   = season,
        quality  = quality,
        audio    = audio,
        genres   = genres,
        runtime  = runtime,
        overview = overview,
    )


def build_index_caption(letter: str, results: list) -> str:
    count = len(results)
    return (
        f"📂 <b>Index: '{letter.upper()}'</b>\n"
        f"Total Results: <b>{count}</b>"
    )

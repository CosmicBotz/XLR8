"""
caption.py — Build post captions using customizable templates.
Quality and Audio are pulled from DB settings (set via /setquality & /setaudio).
Templates stored in DB under keys like "caption_template_series", "caption_template_movie", etc.
Falls back to defaults if not set.
"""

from typing import Dict, Any
import asyncio

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

DEFAULT_QUALITY = "Multiple"  # Updated to match your example
DEFAULT_AUDIO   = "हिंदी (Hindi)"

# Default templates (hard-coded fallbacks — these match your Naruto example)
DEFAULT_TEMPLATES: Dict[str, str] = {
    "series": """{title}
<blockquote>
➣ Type : {media_label}
➣ Status : {status}
➣ Total Episodes : {episodes}
➣ Season : {season}
➣ Quality : {quality}
➣ Audio : {audio}
➣ Genre : {genres}
</blockquote>""",  # For anime/tvshow — no year in your example, but can add {year} if needed

    "movie": """{title}
<blockquote>
➣ Type : {media_label}
➣ Runtime : {runtime} min
➣ Quality : {quality}
➣ Audio : {audio}
➣ Genre : {genres}
</blockquote>""",

    "index": """📂 Index: '{letter}'
Total Results: {count}"""
}


async def get_caption_defaults() -> tuple[str, str]:
    """Fetch quality & audio from DB settings."""
    try:
        from database import CosmicBotz
        settings = await CosmicBotz.get_settings()
        quality  = settings.get("caption_quality", DEFAULT_QUALITY)
        audio    = settings.get("caption_audio",   DEFAULT_AUDIO)
        return quality, audio
    except Exception:
        return DEFAULT_QUALITY, DEFAULT_AUDIO


async def get_template(template_key: str) -> str:
    """Fetch template from DB, fallback to default."""
    try:
        from database import CosmicBotz
        template = await CosmicBotz.get_setting(template_key)
        if template:
            return template
    except Exception:
        pass
    return DEFAULT_TEMPLATES.get(template_key, "")


async def build_caption(media_data: Dict[str, Any]) -> str:
    """Async caption builder — uses customizable template."""
    mtype = media_data.get("media_type", "anime")

    # Map mtype to template key
    if mtype in ("anime", "tvshow"):
        template_key = "caption_template_series"
        template = await get_template(template_key)
        if not template:
            # Fallback to old logic if no template (rename your old build_caption to this if needed)
            return await build_old_caption(media_data)
        
        # Series-specific prep
        year = (media_data.get("first_air_date") or media_data.get("release_date") or "")[:4]
        episodes = media_data.get("episodes", "N/A")
        season = media_data.get("seasons", 1)
        status = media_data.get("status", "N/A")
        title = media_data.get("title", "Unknown")
        genres = media_data.get("genres", "N/A")
        
        context = {
            "title": title,
            "media_label": MEDIA_TYPE_LABEL.get(mtype, "Series"),
            "status": status,
            "episodes": episodes,
            "season": season,
            "genres": genres,
            # year: year,  # Not in your example, but add if wanted: "➣ Year : {year}"
        }
    
    elif mtype == "movie":
        template_key = "caption_template_movie"
        template = await get_template(template_key)
        if not template:
            return await build_old_movie_caption(media_data)  # Or fallback logic
        
        year = (media_data.get("release_date") or "")[:4]
        runtime = media_data.get("runtime", "N/A")
        title = media_data.get("title", "Unknown")
        genres = media_data.get("genres", "N/A")
        
        context = {
            "title": title,
            "media_label": MEDIA_TYPE_LABEL.get(mtype, "Movie"),
            "runtime": runtime,
            "genres": genres,
            # year: year,
        }
    
    else:
        return f"<b>{media_data.get('title', 'Unknown')}</b>\n<blockquote>Unknown media type</blockquote>"

    # Common fields (quality/audio always included)
    quality, audio = await get_caption_defaults()
    quality = media_data.get("quality") or quality
    audio = media_data.get("audio") or audio
    context.update({
        "quality": quality,
        "audio": audio,
    })

    # Render with .format() — safe fallback if key missing
    try:
        caption = template.format(**context)
    except KeyError as e:
        caption = f"{template}\n\n⚠️ Template error: missing {{ {e} }} — check placeholders."

    return caption


def build_index_caption(letter: str, results: list) -> str:
    """Index caption — also templatable if you want."""
    template = asyncio.run(get_template("caption_template_index"))  # Make async if needed
    if not template:
        template = DEFAULT_TEMPLATES["index"]
    
    context = {
        "letter": letter,
        "count": len(results)
    }
    try:
        return template.format(**context)
    except KeyError:
        return DEFAULT_TEMPLATES["index"].format(**context)


# Helper for old fallback (copy your existing build_caption here, adapted for series/movie split)
async def build_old_caption(media_data: Dict[str, Any]) -> str:
    # Your original code here as fallback
    quality, audio = await get_caption_defaults()
    quality = media_data.get("quality") or quality
    audio = media_data.get("audio") or audio

    mtype = media_data.get("media_type", "anime")
    title = media_data.get("title", "Unknown")
    genres = media_data.get("genres", "N/A")
    label = MEDIA_TYPE_LABEL.get(mtype, "Series")

    lines = [f"<b>{title}</b>"]
    lines.append("<blockquote>")

    if mtype in ("anime", "tvshow"):
        year = (media_data.get("first_air_date") or media_data.get("release_date") or "")[:4]
        episodes = media_data.get("episodes", "N/A")
        season = media_data.get("seasons", 1)
        status = media_data.get("status", "N/A")
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
        year = (media_data.get("release_date") or "")[:4]
        runtime = media_data.get("runtime", "N/A")
        lines += [
            f"▶ <b>Type :</b> {label}{f' ({year})' if year else ''}",
            f"▶ <b>Runtime :</b> {runtime} min",
            f"▶ <b>Quality :</b> {quality}",
            f"▶ <b>Audio :</b> {audio}",
            f"<b>Genre :</b> {genres}",
        ]

    lines.append("</blockquote>")
    return "\n".join(lines)


# For movie fallback — extract if you have separate logic
async def build_old_movie_caption(media_data: Dict[str, Any]) -> str:
    # Simplified movie version of above
    pass  # Implement as needed, or just use the series fallback
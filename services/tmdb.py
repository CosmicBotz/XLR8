import httpx
from config import TMDB_API_KEY, TMDB_BASE_URL, TMDB_IMAGE_BASE


async def search_tmdb(query: str, media_type: str = "multi"):
    """
    Search TMDB for anime, tv show, or movie.
    media_type: 'multi' | 'tv' | 'movie'
    """
    url = f"{TMDB_BASE_URL}/search/{media_type}"
    params = {
        "api_key": TMDB_API_KEY,
        "query": query,
        "language": "en-US",
        "page": 1
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    results = data.get("results", [])
    return results[:5]  # top 5 results


async def get_tv_details(tmdb_id: int):
    url = f"{TMDB_BASE_URL}/tv/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US", "append_to_response": "external_ids"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
    return resp.json()


async def get_movie_details(tmdb_id: int):
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "language": "en-US"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, timeout=10)
        resp.raise_for_status()
    return resp.json()


def build_media_data(tmdb_result: dict, media_type: str) -> dict:
    """
    Normalize TMDB result into bot's internal media_data format.
    media_type: 'anime' | 'tvshow' | 'movie'
    """
    genres = [g["name"] for g in tmdb_result.get("genres", [])]
    if not genres:
        # from search result (no genre objects, just ids)
        genre_map = {
            28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
            80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
            14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
            9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
            53: "Thriller", 10752: "War", 37: "Western",
            10759: "Action & Adventure", 10762: "Kids", 10763: "News",
            10764: "Reality", 10765: "Sci-Fi & Fantasy", 10766: "Soap",
            10767: "Talk", 10768: "War & Politics"
        }
        genre_ids = tmdb_result.get("genre_ids", [])
        genres = [genre_map.get(gid, "") for gid in genre_ids if gid in genre_map]

    title = tmdb_result.get("title") or tmdb_result.get("name", "Unknown")
    poster_path = tmdb_result.get("poster_path", "")
    poster_url = f"{TMDB_IMAGE_BASE}{poster_path}" if poster_path else None
    overview = tmdb_result.get("overview", "")

    backdrop_path = tmdb_result.get("backdrop_path", "")
    backdrop_url  = f"{TMDB_IMAGE_BASE}{backdrop_path}" if backdrop_path else None

    data = {
        "title": title,
        "media_type": media_type,
        "tmdb_id": tmdb_result.get("id"),
        "overview": overview,
        "poster_url": poster_url,
        "backdrop_url": backdrop_url,
        "genres": ", ".join(genres) if genres else "N/A",
        "quality": "Multiple",
        "audio": "हिंदी (Hindi)",
        "audio_tag": "#Official",
    }

    if media_type in ("anime", "tvshow"):
        data["episodes"] = tmdb_result.get("number_of_episodes", "N/A")
        data["seasons"] = tmdb_result.get("number_of_seasons", 1)
        data["season"] = "01"
        data["status"] = tmdb_result.get("status", "")
    elif media_type == "movie":
        data["release_date"] = tmdb_result.get("release_date", "N/A")
        data["runtime"] = tmdb_result.get("runtime", "N/A")

    return data

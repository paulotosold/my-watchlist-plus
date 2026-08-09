"""TMDB match resolution and title search."""

from app.config import TMDB_LANGUAGE
from .client import get_default_client


TMDB_TITLE_SEARCH_PAGE_LIMIT = 5


def find_tmdb_match_by_imdb_id(imdb_id, *, language=None, client=None):
    client = _resolve_client(client)
    language = _resolve_language(language, client)
    result = client.get_json(
        f"find/{imdb_id.strip()}",
        params={
            "external_source": "imdb_id",
            "language": language,
        },
    )

    candidates = []

    for movie in result.get("movie_results", []):
        candidates.append({
            "media_type": "movie",
            "tmdb_id": movie["id"],
            "title": movie.get("title"),
            "release_date": movie.get("release_date"),
        })

    for series in result.get("tv_results", []):
        candidates.append({
            "media_type": "series",
            "tmdb_id": series["id"],
            "title": series.get("name"),
            "release_date": series.get("first_air_date"),
        })

    for episode in result.get("tv_episode_results", []):
        candidates.append({
            "media_type": "episode",
            "tmdb_id": episode["id"],
            "title": episode.get("name"),
            "release_date": episode.get("air_date"),
            "series_tmdb_id": episode.get("show_id"),
            "season_num": episode.get("season_number"),
            "episode_num": episode.get("episode_number"),
        })

    if len(candidates) == 1:
        return {
            "status": "resolved",
            "match": candidates[0],
        }

    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "match": None,
            "reason": "IMDb ID matched multiple TMDB media categories.",
            "candidates": candidates,
        }

    return {
        "status": "not_found",
        "match": None,
        "reason": "IMDb ID did not match any TMDB movie, series, or episode.",
    }


def search_tmdb_title_candidates(
    query,
    *,
    language=None,
    client=None,
):
    """Return up to five organic TMDB result pages for movies and series."""
    query = (query or "").strip()

    if not query:
        return []

    client = _resolve_client(client)
    language = _resolve_language(language, client)
    movies = _search_tmdb_title_pages(
        "search/movie",
        query,
        language,
        client,
    )
    series = _search_tmdb_title_pages(
        "search/tv",
        query,
        language,
        client,
    )

    movie_candidates = [
        _format_tmdb_title_candidate(result, "movie")
        for result in movies
        if result.get("id") is not None
    ]
    series_candidates = [
        _format_tmdb_title_candidate(result, "series")
        for result in series
        if result.get("id") is not None
    ]
    return [*movie_candidates, *series_candidates]


def _search_tmdb_title_pages(endpoint, query, language, client):
    first_page = client.get_json(endpoint, params={
        "query": query,
        "language": language,
        "page": 1,
    })
    results = list(first_page.get("results") or [])
    total_pages = first_page.get("total_pages") or 0

    try:
        total_pages = int(total_pages)
    except (TypeError, ValueError):
        total_pages = 0

    last_page = min(max(total_pages, 1), TMDB_TITLE_SEARCH_PAGE_LIMIT)

    for page in range(2, last_page + 1):
        response = client.get_json(endpoint, params={
            "query": query,
            "language": language,
            "page": page,
        })
        results.extend(response.get("results") or [])

    return results


def _format_tmdb_title_candidate(result, media_type):
    if media_type == "movie":
        title = result.get("title")
        original_title = result.get("original_title")
        release_date = result.get("release_date")
    else:
        title = result.get("name")
        original_title = result.get("original_name")
        release_date = result.get("first_air_date")

    return {
        "source": "tmdb",
        "media_id": None,
        "media_type": media_type,
        "tmdb_id": result["id"],
        "imdb_id": None,
        "title": title,
        "original_title": original_title,
        "release_date": release_date,
        "poster_path": result.get("poster_path"),
    }


def _resolve_client(client):
    return client if client is not None else get_default_client()


def _resolve_language(language, client):
    if language is not None:
        return language

    client_language = getattr(client, "language", None)

    if isinstance(client_language, str) and client_language.strip():
        return client_language

    return TMDB_LANGUAGE

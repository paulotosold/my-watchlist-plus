"""TMDB watch-provider lookup and normalization."""

from app.config import TMDB_WATCH_REGION, WATCH_PROVIDER_ACCESS_TYPES
from .client import get_default_client


def get_tmdb_movie_watch_providers(
    tmdb_id,
    country_code=TMDB_WATCH_REGION,
    *,
    client=None,
):
    return get_tmdb_media_watch_providers(
        {
            "media_type": "movie",
            "tmdb_id": tmdb_id,
        },
        country_code=country_code,
        client=client,
    )


def get_tmdb_media_watch_providers(
    tmdb_id_match,
    country_code=TMDB_WATCH_REGION,
    *,
    client=None,
):
    tmdb_id_match = _unwrap_resolved_match(tmdb_id_match)
    client = _resolve_client(client)
    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        endpoint = (
            f"movie/{tmdb_id_match['tmdb_id']}/watch/providers"
        )
    elif media_type == "series":
        endpoint = f"tv/{tmdb_id_match['tmdb_id']}/watch/providers"
    elif media_type == "episode":
        series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
        season_num = tmdb_id_match.get("season_num")

        if not series_tmdb_id or season_num is None:
            raise ValueError(
                "Episode watch providers require series_tmdb_id and "
                "season_num."
            )

        endpoint = (
            f"tv/{series_tmdb_id}/season/{season_num}/watch/providers"
        )
    else:
        raise ValueError(f"Unsupported media_type: {media_type}")

    watch_provider_data = client.get_json(endpoint)
    return _format_watch_providers(watch_provider_data, country_code)


def _format_watch_providers(watch_provider_data, country_code):
    providers_by_region = (
        watch_provider_data.get("results", {}).get(country_code, {})
    )
    formatted_providers = []
    seen = set()

    for access_type in WATCH_PROVIDER_ACCESS_TYPES:
        for provider in providers_by_region.get(access_type, []):
            provider_tmdb_id = provider.get("provider_id")
            provider_name = provider.get("provider_name")

            if not provider_tmdb_id or not provider_name:
                continue

            key = (provider_tmdb_id, country_code, access_type)

            if key in seen:
                continue

            seen.add(key)
            formatted_providers.append({
                "provider_tmdb_id": provider_tmdb_id,
                "provider_name": provider_name,
                "country_code": country_code,
                "access_type": access_type,
            })

    return formatted_providers


def _unwrap_resolved_match(tmdb_id_match):
    if tmdb_id_match.get("status"):
        if (
            tmdb_id_match.get("status") != "resolved"
            or not tmdb_id_match.get("match")
        ):
            raise ValueError(
                "get_tmdb_media_watch_providers requires a resolved "
                "TMDB match."
            )

        return tmdb_id_match["match"]

    return tmdb_id_match


def _resolve_client(client):
    return client if client is not None else get_default_client()

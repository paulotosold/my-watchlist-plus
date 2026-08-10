"""Public facade for the application's TMDB integration."""

from .client import TmdbClient
from .freshness import current_freshness_timestamp
from .metadata import (
    get_tmdb_media_metadata,
    get_tmdb_media_series_view,
    get_tmdb_series_episode_metadata_list,
)
from .posters import (
    build_tmdb_image_url,
    get_tmdb_media_posters,
    get_tmdb_movie_posters,
    get_tmdb_series_primary_season_posters,
)
from .providers import (
    get_tmdb_media_watch_providers,
    get_tmdb_movie_watch_providers,
)
from .refresh import get_tmdb_metadata_refresh_snapshot
from .search import (
    find_tmdb_match_by_imdb_id,
    search_tmdb_title_candidates,
)


__all__ = [
    "TmdbClient",
    "build_tmdb_image_url",
    "current_freshness_timestamp",
    "find_tmdb_match_by_imdb_id",
    "get_tmdb_media_metadata",
    "get_tmdb_media_posters",
    "get_tmdb_media_series_view",
    "get_tmdb_media_watch_providers",
    "get_tmdb_metadata_refresh_snapshot",
    "get_tmdb_movie_posters",
    "get_tmdb_movie_watch_providers",
    "get_tmdb_series_episode_metadata_list",
    "get_tmdb_series_primary_season_posters",
    "search_tmdb_title_candidates",
]

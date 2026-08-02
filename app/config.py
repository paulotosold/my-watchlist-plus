import os
from pathlib import Path
import tomllib

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = BASE_DIR / ".env"
SETTINGS_PATH = BASE_DIR / "settings.toml"

DEFAULT_SETTINGS = {
    "tmdb": {
        "language": "en-US",
        "watch_region": "AT",
        "poster_size": "w500",
        "max_posters_per_media": 1,
    },
    "watch_providers": {
        "access_types": ["flatrate", "rent", "buy"],
        "subscribed_flatrate_provider_names": [],
    },
}

load_dotenv(ENV_PATH)

TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(f"Missing {name} in {ENV_PATH}")

    return value


def _load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return DEFAULT_SETTINGS

    with SETTINGS_PATH.open("rb") as settings_file:
        settings = tomllib.load(settings_file)

    return _merge_settings(DEFAULT_SETTINGS, settings)


def _merge_settings(defaults: dict, overrides: dict) -> dict:
    merged = defaults.copy()

    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_settings(merged[key], value)
        else:
            merged[key] = value

    return merged


SETTINGS = _load_settings()

TMDB_LANGUAGE = SETTINGS["tmdb"].get("language", "en-US")
TMDB_WATCH_REGION = SETTINGS["tmdb"].get("watch_region", "AT")
TMDB_POSTER_SIZE = SETTINGS["tmdb"].get("poster_size", "w500")
TMDB_MAX_POSTERS_PER_MEDIA = SETTINGS["tmdb"].get("max_posters_per_media", 1)
WATCH_PROVIDER_ACCESS_TYPES = SETTINGS["watch_providers"].get(
    "access_types",
    ["flatrate", "rent", "buy"],
)
SUBSCRIBED_FLATRATE_PROVIDER_NAMES = SETTINGS["watch_providers"].get(
    "subscribed_flatrate_provider_names",
    [],
)

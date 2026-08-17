"""Canonical filesystem locations used across the application."""

from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent
ASSETS_DIR = APP_DIR / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
OVERLAYS_DIR = ASSETS_DIR / "overlays"
DATA_DIR = PROJECT_ROOT / "data"
MEDIA_POSTERS_DIR = DATA_DIR / "media_posters"


__all__ = [
    "APP_DIR",
    "ASSETS_DIR",
    "DATA_DIR",
    "ICONS_DIR",
    "MEDIA_POSTERS_DIR",
    "OVERLAYS_DIR",
    "PROJECT_ROOT",
]

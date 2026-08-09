from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = APP_DIR.parent

DETAIL_ICON_DIR = APP_DIR / "assets"
POSTER_DIR = PROJECT_DIR / "data" / "media_posters"

DETAIL_ICON_BUTTON_SIZE = 20
DETAIL_ICON_SIZE = 18
DETAIL_BUTTON_WIDTH = 100
DETAILS_BACKGROUND_COLOR = "#f1f1f1"

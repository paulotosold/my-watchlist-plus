"""Domain helpers for user-owned media data and draft edits."""

from .lists import (
    DUPLICATE_LIST_NAME_ERROR,
    EMPTY_LIST_NAME_ERROR,
    is_duplicate_list_name,
    normalize_list_description,
    normalize_list_name,
    validate_list_name,
)
from .notes import (
    EMPTY_NOTE_ERROR,
    apply_note_result,
    normalize_note_text,
    validate_note_text,
)
from .watch_history import (
    apply_watch_entry_result,
    episode_key,
    get_series_episodes,
    is_episode_available,
    make_draft_id,
    normalize_watch_date,
    validate_watch_dates,
    watched_episode_keys,
)
from .watch_history_formatters import (
    build_series_watch_history_lines,
    build_watch_history_display_entries,
    build_watch_history_display_lines,
    earliest_created_at,
    format_date_range,
    format_episode_ranges,
    format_watch_history_entry,
    parse_date,
    watch_history_sort_key,
)
from .watch_states import (
    VALID_WATCH_STATES_BY_MEDIA_TYPE,
    validate_watch_state,
)


__all__ = [
    "DUPLICATE_LIST_NAME_ERROR",
    "EMPTY_LIST_NAME_ERROR",
    "EMPTY_NOTE_ERROR",
    "VALID_WATCH_STATES_BY_MEDIA_TYPE",
    "apply_note_result",
    "apply_watch_entry_result",
    "build_series_watch_history_lines",
    "build_watch_history_display_entries",
    "build_watch_history_display_lines",
    "earliest_created_at",
    "episode_key",
    "format_date_range",
    "format_episode_ranges",
    "format_watch_history_entry",
    "get_series_episodes",
    "is_duplicate_list_name",
    "is_episode_available",
    "make_draft_id",
    "normalize_list_description",
    "normalize_list_name",
    "normalize_note_text",
    "normalize_watch_date",
    "parse_date",
    "validate_list_name",
    "validate_note_text",
    "validate_watch_dates",
    "validate_watch_state",
    "watch_history_sort_key",
    "watched_episode_keys",
]

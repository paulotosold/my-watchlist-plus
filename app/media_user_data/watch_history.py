from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from uuid import uuid4


DATE_FORMAT = "%Y-%m-%d"


def normalize_watch_date(value):
    text = (value or "").strip()

    if not text:
        return None, None

    try:
        parsed = datetime.strptime(text, DATE_FORMAT).date()
    except ValueError:
        return None, "Use YYYY-MM-DD."

    if parsed.strftime(DATE_FORMAT) != text:
        return None, "Use YYYY-MM-DD."

    return text, None


def validate_watch_dates(date_earliest, date_latest):
    earliest, earliest_error = normalize_watch_date(date_earliest)

    if earliest_error:
        return {
            "is_valid": False,
            "date_earliest": None,
            "date_latest": None,
            "error": earliest_error,
            "error_type": "invalid_format",
        }

    latest, latest_error = normalize_watch_date(date_latest)

    if latest_error:
        return {
            "is_valid": False,
            "date_earliest": None,
            "date_latest": None,
            "error": latest_error,
            "error_type": "invalid_format",
        }

    if earliest is not None and latest is not None and latest < earliest:
        return {
            "is_valid": False,
            "date_earliest": earliest,
            "date_latest": latest,
            "error": "Latest date must be on or after earliest date.",
            "error_type": "invalid_range",
        }

    return {
        "is_valid": True,
        "date_earliest": earliest,
        "date_latest": latest,
        "error": None,
        "error_type": None,
    }


def is_episode_available(episode, today=None):
    release_date = (episode or {}).get("release_date")

    if not isinstance(release_date, str):
        return False

    try:
        released_on = datetime.strptime(release_date, DATE_FORMAT).date()
    except ValueError:
        return False

    if released_on.strftime(DATE_FORMAT) != release_date:
        return False

    return released_on <= (today or date.today())


def apply_watch_entry_result(media_draft, entry, result):
    action = result.get("action")

    if action == "delete":
        remove_watch_entry(media_draft, entry)
        return

    if action != "save":
        raise ValueError(f"Unsupported watch entry action: {action}")

    metadata = media_draft.get("metadata") or {}

    if metadata.get("media_type") != "series":
        save_media_watch_entry(media_draft, entry, result)
        return

    selected_episodes = sorted(
        result.get("selected_episodes") or [],
        key=lambda item: episode_sort_key(item),
    )

    if selected_episodes:
        remove_watch_entry(media_draft, entry)
        save_series_episode_watch_entry(media_draft, entry, result, selected_episodes)
        return

    save_series_media_watch_entry(media_draft, entry, result)


def save_media_watch_entry(media_draft, entry, result):
    watch_history = ensure_user_watch_history(media_draft)
    event = build_media_event(result)
    index = get_media_watch_history_index(entry, watch_history)

    if index is None:
        watch_history.append(event)
        return

    existing = deepcopy(watch_history[index])
    update_media_event_dates(existing, result)
    watch_history[index] = existing


def save_series_media_watch_entry(media_draft, entry, result):
    watch_history = ensure_user_watch_history(media_draft)
    event = build_media_event(result)

    if entry and entry.get("kind") == "media_event":
        index = get_media_watch_history_index(entry, watch_history)

        if index is not None:
            existing = deepcopy(watch_history[index])
            update_media_event_dates(existing, result)
            watch_history[index] = existing
            return

    remove_watch_entry(media_draft, entry)
    watch_history.append(event)


def save_series_episode_watch_entry(
    media_draft,
    entry,
    result,
    selected_episodes,
):
    episode_watch_history = ensure_series_episode_watch_history(media_draft)
    original_by_key = {
        episode_key(episode): episode
        for episode in (entry or {}).get("episodes", [])
    }
    timestamp = current_draft_timestamp()

    for episode in selected_episodes:
        key = episode_key(episode)
        original = original_by_key.get(key, {})
        row = {
            "series_id": (
                episode.get("series_id")
                or original.get("series_id")
                or media_draft.get("media_id")
            ),
            "episode_id": episode.get("episode_id") or original.get("episode_id"),
            "tmdb_id": episode.get("tmdb_id") or original.get("tmdb_id"),
            "season_num": episode.get("season_num") or original.get("season_num"),
            "episode_num": episode.get("episode_num") or original.get("episode_num"),
            "date_earliest": result.get("date_earliest"),
            "date_latest": result.get("date_latest"),
            "created_at": original.get("created_at") or timestamp,
        }

        if original.get("watch_history_id") is not None:
            row["watch_history_id"] = original["watch_history_id"]
        else:
            row["draft_id"] = original.get("draft_id") or make_draft_id()

        episode_watch_history.append(row)


def remove_watch_entry(media_draft, entry):
    if not entry:
        return

    if entry.get("kind") == "episode_group":
        remove_episode_group_watch_entry(media_draft, entry)
        return

    remove_media_watch_entry(media_draft, entry)


def remove_media_watch_entry(media_draft, entry):
    watch_history = ensure_user_watch_history(media_draft)
    index = get_media_watch_history_index(entry, watch_history)

    if index is not None:
        del watch_history[index]


def remove_episode_group_watch_entry(media_draft, entry):
    episode_watch_history = ensure_series_episode_watch_history(media_draft)
    watch_history_ids = set(entry.get("watch_history_ids") or [])
    draft_ids = set(entry.get("draft_ids") or [])
    original_keys = {
        episode_key(episode)
        for episode in entry.get("episodes", [])
    }
    original_dates = (entry.get("date_earliest"), entry.get("date_latest"))

    kept_rows = []

    for row in episode_watch_history:
        row_id = row.get("watch_history_id")
        draft_id = row.get("draft_id")

        if row_id is not None and row_id in watch_history_ids:
            continue

        if draft_id is not None and draft_id in draft_ids:
            continue

        if (
            row_id is None
            and draft_id is None
            and episode_key(row) in original_keys
            and (row.get("date_earliest"), row.get("date_latest")) == original_dates
        ):
            continue

        kept_rows.append(row)

    episode_watch_history[:] = kept_rows


def build_media_event(result):
    return {
        "draft_id": result.get("draft_id") or make_draft_id(),
        "date_earliest": result.get("date_earliest"),
        "date_latest": result.get("date_latest"),
        "created_at": result.get("created_at") or current_draft_timestamp(),
    }


def update_media_event_dates(event, result):
    event["date_earliest"] = result.get("date_earliest")
    event["date_latest"] = result.get("date_latest")

    if not event.get("created_at"):
        event["created_at"] = result.get("created_at") or current_draft_timestamp()


def get_media_watch_history_index(entry, watch_history):
    if not entry:
        return None

    index = entry.get("watch_history_index")

    if index is not None and 0 <= index < len(watch_history):
        return index

    watch_history_id = entry.get("watch_history_id")

    if watch_history_id is not None:
        for current_index, event in enumerate(watch_history):
            if event.get("id") == watch_history_id:
                return current_index

    draft_id = (entry.get("watch_history") or {}).get("draft_id")

    if draft_id is not None:
        for current_index, event in enumerate(watch_history):
            if event.get("draft_id") == draft_id:
                return current_index

    return None


def ensure_user_watch_history(media_draft):
    user_data = media_draft.setdefault("user_data", {})
    return user_data.setdefault("watch_history", [])


def ensure_series_episode_watch_history(media_draft):
    series_view = media_draft.setdefault("series_view", {})
    return series_view.setdefault("episode_watch_history", [])


def episode_key(episode):
    return (
        episode.get("season_num"),
        episode.get("episode_num"),
    )


def episode_sort_key(episode):
    season_num, episode_num = episode_key(episode)
    return (
        season_num or 0,
        episode_num or 0,
    )


def watched_episode_keys(media_draft, excluded_entry=None):
    excluded_watch_history_ids = set((excluded_entry or {}).get("watch_history_ids") or [])
    excluded_draft_ids = set((excluded_entry or {}).get("draft_ids") or [])
    excluded_episode_keys = selected_episode_keys(excluded_entry)
    excluded_dates = (
        (excluded_entry or {}).get("date_earliest"),
        (excluded_entry or {}).get("date_latest"),
    )
    watched_keys = set()

    for row in (
        (media_draft.get("series_view") or {})
        .get("episode_watch_history", [])
    ):
        key = episode_key(row)

        if key == (None, None):
            continue

        if row.get("watch_history_id") in excluded_watch_history_ids:
            continue

        if row.get("draft_id") in excluded_draft_ids:
            continue

        if (
            not row.get("watch_history_id")
            and not row.get("draft_id")
            and key in excluded_episode_keys
            and (row.get("date_earliest"), row.get("date_latest")) == excluded_dates
        ):
            continue

        watched_keys.add(key)

    return watched_keys


def selected_episode_keys(entry):
    return {
        episode_key(episode)
        for episode in (entry or {}).get("episodes", [])
        if episode_key(episode) != (None, None)
    }


def get_series_episodes(media_draft):
    return sorted(
        (media_draft.get("series_view") or {}).get("episodes", []),
        key=lambda item: episode_sort_key(item),
    )


def make_draft_id():
    return uuid4().hex


def current_draft_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

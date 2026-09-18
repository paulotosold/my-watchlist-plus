from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
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


def media_item(media_draft):
    metadata = media_draft.get("metadata") or {}
    details = metadata.get("episode_details") or {}
    return {
        "draft_id": make_draft_id(),
        "media_id": media_draft.get("media_id"),
        "media_type": metadata.get("media_type"),
        "tmdb_id": metadata.get("tmdb_id"),
        "title": metadata.get("title"),
        "release_date": metadata.get("release_date"),
        "series_id": ((media_draft.get("series_view") or {}).get("series_id")
                      if metadata.get("media_type") == "episode" else None),
        "season_num": details.get("season_num"),
        "episode_num": details.get("episode_num"),
    }


def entry_identity(entry):
    return ("id", entry["id"]) if entry.get("id") is not None else ("draft_id", entry.get("draft_id"))


def apply_watch_entry_result(media_draft, entry, result):
    if result.get("action") not in {"save", "delete"}:
        raise ValueError(f"Unsupported watch entry action: {result.get('action')}")
    history = media_draft.setdefault("user_data", {}).setdefault("watch_history", [])
    index = None
    if entry is not None:
        index = next((n for n, e in enumerate(history) if entry_identity(e) == entry_identity(entry)), None)
        if index is None:
            raise ValueError("Watch history entry is no longer in this draft.")
    if result["action"] == "delete":
        if index is not None:
            del history[index]
        return
    validation = validate_watch_dates(result.get("date_earliest"), result.get("date_latest"))
    if not validation['is_valid']:
        raise ValueError(validation['error'])
    event = deepcopy(history[index]) if index is not None else {
        "draft_id": make_draft_id(), "created_at": current_draft_timestamp(), "updated_at": None,
    }
    selected = result.get("selected_episodes") or []
    metadata = media_draft.get("metadata") or {}
    series_context = metadata.get("media_type") == "series" or (
        entry is not None and metadata.get("media_type") == "episode" and media_draft.get("series_view"))
    if selected:
        items = []
        old_by_media = {i.get("media_id"): i for i in event.get("items", []) if i.get("media_id") is not None}
        old_by_tmdb = {i.get("tmdb_id"): i for i in event.get("items", []) if i.get("tmdb_id") is not None}
        for episode in sorted(selected, key=episode_sort_key):
            mid = episode.get("media_id") or episode.get("episode_id")
            original = old_by_media.get(mid) or old_by_tmdb.get(episode.get("tmdb_id")) or {}
            item = {k: episode.get(k) for k in ("tmdb_id", "series_id", "season_num", "episode_num", "title", "release_date")}
            item.update(media_id=mid, media_type="episode")
            if original.get("id") is not None:
                item["id"] = original["id"]
            else:
                item["draft_id"] = original.get("draft_id") or make_draft_id()
            items.append(item)
    elif series_context and metadata.get("media_type") == "episode":
        context = media_draft["series_view"]
        items = [media_item({"media_id": context["series_id"], "metadata": context["metadata"]})]
    else:
        items = [media_item(media_draft)]
        previous = next((i for i in event.get("items", []) if i.get("media_id") == items[0].get("media_id")
                         and i.get("tmdb_id") == items[0].get("tmdb_id")), None)
        if previous:
            items = [deepcopy(previous)]
    event.update(date_earliest=validation["date_earliest"], date_latest=validation["date_latest"], items=items)
    if index is None:
        history.append(event)
    else:
        history[index] = event


def episode_key(episode):
    return (episode.get("season_num"), episode.get("episode_num"))


def episode_sort_key(episode):
    return tuple(value or 0 for value in episode_key(episode))


def watched_episode_keys(media_draft, excluded_entry=None):
    # Counts outside this draft's history are read-only context; draft entries
    # themselves are the sole editable source of truth.
    watched = {episode_key(e) for e in get_series_episodes(media_draft)
               if e.get("external_history_count", 0) > 0}
    excluded = entry_identity(excluded_entry) if excluded_entry else None
    for event in (media_draft.get("user_data") or {}).get("watch_history", []):
        if excluded is not None and entry_identity(event) == excluded:
            continue
        watched.update(episode_key(i) for i in event.get("items", []) if i.get("media_type") == "episode")
    return watched


def selected_episode_keys(entry):
    return {episode_key(i) for i in (entry or {}).get("items", []) if i.get("media_type") == "episode"}


def get_series_episodes(media_draft):
    return sorted((media_draft.get("series_view") or {}).get("episodes", []), key=episode_sort_key)


def make_draft_id():
    return uuid4().hex


def current_draft_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

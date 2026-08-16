"""Apply persistence and metadata-refresh results to live media drafts."""

from __future__ import annotations

from copy import deepcopy


def apply_inserted_ids_to_draft(media_draft, save_result):
    """Apply post-commit IDs without ever exposing rolled-back IDs to a draft."""
    _ensure_cabinet_order(media_draft)
    mappings = save_result.get("inserted_ids_by_draft_id") or {}
    _apply_event_ids(
        (media_draft.get("user_data") or {}).get("watch_history", []),
        mappings.get("media_watch_history", {}),
        id_key="id",
    )
    _apply_event_ids(
        (media_draft.get("user_data") or {}).get("notes", []),
        mappings.get("notes", {}),
        id_key="id",
    )
    _apply_event_ids(
        ((media_draft.get("series_view") or {}).get(
            "episode_watch_history",
            [],
        )),
        mappings.get("series_episode_watch_history", {}),
        id_key="watch_history_id",
    )
    return media_draft


def merge_metadata_refresh(media_draft, refresh_payload):
    """Return a catalog-refreshed draft while preserving all user-owned data."""
    merged = deepcopy(media_draft)
    _ensure_cabinet_order(merged)
    snapshot = refresh_payload.get("snapshot") or {}
    refresh_result = refresh_payload.get("refresh_result") or {}
    refreshed_metadata = refresh_result.get("metadata") or snapshot.get("metadata")

    if refreshed_metadata:
        merged["metadata"] = _merge_metadata_freshness(
            merged.get("metadata") or {},
            refreshed_metadata,
        )

    if merged.get("media_id") is None and snapshot:
        merged["_metadata_refresh_snapshot"] = deepcopy(snapshot)

    if (merged.get("metadata") or {}).get("media_type") != "series":
        return merged

    catalog = refresh_result.get("series_catalog")

    if catalog is None:
        catalog = _series_catalog_from_snapshot(snapshot, merged.get("media_id"))

    current_series_view = merged.get("series_view") or {}
    episodes = deepcopy((catalog or {}).get("episodes") or [])
    episode_history = deepcopy(
        current_series_view.get("episode_watch_history") or []
    )
    unresolved_history = _normalize_episode_history(episode_history, episodes)

    if merged.get("media_id") is None and unresolved_history:
        raise ValueError(
            "Metadata refresh would orphan an unsaved episode watch entry."
        )
    merged["series_view"] = {
        **current_series_view,
        "summary": deepcopy((catalog or {}).get("summary") or {}),
        "episodes": episodes,
        "episode_watch_history": episode_history,
    }
    return merged


def _ensure_cabinet_order(media_draft):
    user_data = media_draft.get("user_data")

    if user_data is None:
        user_data = {}
        media_draft["user_data"] = user_data

    user_data.setdefault("cabinet_order", None)


def _apply_event_ids(events, mapping, id_key):
    for event in events or []:
        draft_id = event.get("draft_id")

        if draft_id is None or draft_id not in mapping:
            continue

        event[id_key] = mapping[draft_id]
        event.pop("draft_id", None)


def _merge_metadata_freshness(current, refreshed):
    merged = deepcopy(refreshed)

    for key in (
        "last_tmdb_posters_checked_at",
        "last_tmdb_watch_providers_checked_at",
    ):
        if merged.get(key) is None and current.get(key) is not None:
            merged[key] = current[key]

    return merged


def _series_catalog_from_snapshot(snapshot, series_id):
    episodes = []

    for metadata in snapshot.get("regular_episodes") or []:
        details = metadata.get("episode_details") or {}
        episodes.append({
            "series_id": series_id,
            "episode_id": metadata.get("media_id"),
            "tmdb_id": metadata.get("tmdb_id"),
            "season_num": details.get("season_num"),
            "episode_num": details.get("episode_num"),
            "title": metadata.get("title"),
            "release_date": metadata.get("release_date"),
        })

    return {
        "summary": deepcopy(snapshot.get("series_summary") or {}),
        "episodes": episodes,
    }


def _normalize_episode_history(history, episodes):
    by_episode_id = {
        item.get("episode_id"): item
        for item in episodes
        if item.get("episode_id") is not None
    }
    by_tmdb_id = {
        item.get("tmdb_id"): item
        for item in episodes
        if item.get("tmdb_id") is not None
    }

    unresolved = []

    for event in history:
        episode = by_episode_id.get(event.get("episode_id"))

        if episode is None:
            episode = by_tmdb_id.get(event.get("tmdb_id"))

        if episode is None:
            unresolved.append(event)
            continue

        for key in (
            "series_id",
            "episode_id",
            "tmdb_id",
            "season_num",
            "episode_num",
        ):
            if key in episode:
                event[key] = episode.get(key)

    return unresolved

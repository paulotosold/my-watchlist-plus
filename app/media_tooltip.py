"""Consistent catalog titles and years for poster tooltips."""

from app.media_user_data.watch_history_formatters import parse_date


def format_media_tooltip(
    title,
    media_type,
    release_date=None,
    *,
    first_air_date=None,
    last_air_date=None,
    series_title=None,
    season_num=None,
    episode_num=None,
):
    title = title or ("Untitled episode" if media_type == "episode" else "Untitled")
    if media_type == "episode" and series_title:
        code = (
            f" S{season_num}E{episode_num}"
            if season_num is not None and episode_num is not None else ""
        )
        title = f"{series_title}{code}: {title}"
    dates = (
        (first_air_date or release_date, last_air_date)
        if media_type == "series" else (release_date,)
    )
    years = sorted({parsed.year for value in dates if (parsed := parse_date(value))})
    if not years:
        return title
    year_label = str(years[0]) if len(years) == 1 else f"{years[0]}-{years[-1]}"
    return f"{title} ({year_label})"


def media_draft_tooltip(media_draft):
    metadata = media_draft.get("metadata") or {}
    summary = (media_draft.get("series_view") or {}).get("summary") or {}
    episode = metadata.get("episode_details") or {}
    return format_media_tooltip(
        metadata.get("title"),
        metadata.get("media_type"),
        metadata.get("release_date"),
        first_air_date=summary.get("first_air_date"),
        last_air_date=summary.get("last_air_date"),
        series_title=episode.get("series_title"),
        season_num=episode.get("season_num"),
        episode_num=episode.get("episode_num"),
    )

from datetime import datetime, timezone


def current_freshness_timestamp() -> str:
    """Return the UTC timestamp format stored in media freshness columns."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

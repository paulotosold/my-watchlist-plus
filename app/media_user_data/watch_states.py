VALID_WATCH_STATES_BY_MEDIA_TYPE = {
    "movie": frozenset({
        "to_watch",
        "watched",
        "not_interested",
    }),
    "series": frozenset({
        "to_watch",
        "watched",
        "not_interested",
        "dropped",
    }),
    "episode": frozenset({
        "to_watch",
        "watched",
        "not_interested",
    }),
}


def validate_watch_state(media_type, watch_state):
    if media_type not in VALID_WATCH_STATES_BY_MEDIA_TYPE:
        raise ValueError(f"Unsupported media_type: {media_type}")

    if watch_state is None:
        return None

    allowed_states = VALID_WATCH_STATES_BY_MEDIA_TYPE[media_type]

    if watch_state not in allowed_states:
        raise ValueError(
            f"Unsupported watch_state {watch_state!r} for media_type {media_type!r}."
        )

    return watch_state

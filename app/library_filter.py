DEFAULT_FILTER_TEXT = "All released titles marked To Watch, in random order"

DEFAULT_FILTER_INTENT = {
    "watch_state": {
        "include": ["to_watch"],
    },
    "release_date": {
        "on_or_before": "today",
        "exclude_null": True,
    },
    "order_by": [
        {"field": "random"},
    ],
}

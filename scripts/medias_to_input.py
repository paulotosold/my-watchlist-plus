"""Example inputs; each nested items collection describes one viewing action.

Populate user_data.watch_history on the corresponding MediaDraft before saving.
For a complete-series episode entry, enumerate its resolved catalogue episodes
as items instead of using an implicit "all" or watched_episodes flag.
"""
from app.media_user_data.watch_history import make_draft_id


def viewing(earliest, latest, *items):
    return {
        "draft_id": make_draft_id(),
        "date_earliest": earliest,
        "date_latest": latest,
        "items": [{"draft_id": make_draft_id(), **item} for item in items],
    }


medias_to_input = [
    {
        "imdb_id": "tt0133093", # The Matrix
        "tmdb_id": 603,
        "media_type": "movie",
        "watch_state": "watched",
        "impression": "very_good",
        "is_cabinet_worthy": True,
        "cabinet_order": None,
        "watch_history": [
            viewing("1999-05-01", "1999-06-30", {"tmdb_id": 603, "media_type": "movie"}),
            viewing("2014-11-02", "2014-11-02", {"tmdb_id": 603, "media_type": "movie"}),
            viewing("2019-10-05", "2019-10-05", {"tmdb_id": 603, "media_type": "movie"}),
        ],
        "notes": [],
        "lists": [],
    },
    {
        "imdb_id": "tt28069611",  # Star Wars: Starfighter (to be released)
        "watch_state": "to_watch",
        "impression": None,
        "is_cabinet_worthy": None,
        "cabinet_order": None,
        "watch_history": [],
        "notes": [],
        "lists": ["ver com o benji"],
    },
    {
        "imdb_id": "tt1535108",  # Elysium
        "watch_state": "watched",
        "impression": "regret_watching",
        "is_cabinet_worthy": None,
        "cabinet_order": None,
        "watch_history": [
            viewing("2021-07-24", "2021-07-24", {"tmdb_id": 68724, "media_type": "movie"})
        ],
        "notes": [],
        "lists": [],
    },
    {
        "imdb_id": "tt14688458",  # Silo
        "watch_state": "to_watch",
        "impression": None,
        "is_cabinet_worthy": None,
        "cabinet_order": None,
        "watch_history": [
            viewing("2026-05-16", "2026-05-16", *[
                {"tmdb_id": tmdb_id, "media_type": "episode"}
                for tmdb_id in (2964686, 4281661, 4281667)  # S1:E1-3
            ])
        ],
        "notes": [],
        "lists": [],
    },
    {
        "imdb_id": "tt0094582",  # Wonder Years
        "watch_state": "watched",
        # Example without episode detail. To record every episode, build one
        # entry with an explicit item for each resolved catalogue episode.
        # TMDB identity: https://www.themoviedb.org/tv/4500-the-wonder-years
        "impression": "very_good",
        "is_cabinet_worthy": True,
        "cabinet_order": None,
        "watch_history": [
            viewing("1993-01-01", "1996-12-31", {"tmdb_id": 4500, "media_type": "series"})
        ],
        "notes": [],
        "lists": ["ver com o benji (+12)"],
    },



]

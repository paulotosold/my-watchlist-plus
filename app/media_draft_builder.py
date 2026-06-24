import app.media_repository as media_repo
from db.connection import get_connection
import app.tmdb_fetcher

def build_media_draft_from_db(conn, media_from_db):
    metadata = media_repo.get_db_media_metadata(conn, media_from_db)
    watch_providers = media_repo.get_db_media_watch_providers(conn, metadata)
    posters = media_repo.get_db_media_posters(conn, metadata)
    user_data = media_repo.get_db_media_user_data(conn, metadata)

    return {
            "media_id": media_from_db["id"],
            "metadata": metadata,
            "watch_providers": watch_providers,
            "posters": posters,
            "user_data": user_data
        }

def build_media_draft_from_tmdb(imdb_id):
    tmdb_match = app.tmdb_fetcher.find_tmdb_match_by_imdb_id(imdb_id)

    if tmdb_match["status"] != "resolved":
        raise ValueError(tmdb_match.get("reason") or "TMDB match was not resolved.")

    media_draft = build_media_draft_from_tmdb_match(tmdb_match)
    metadata = media_draft["metadata"]

    if not metadata.get("imdb_id"):
        metadata["imdb_id"] = imdb_id

    return media_draft


def build_media_draft_from_tmdb_match(tmdb_match):
    metadata = app.tmdb_fetcher.get_tmdb_media_metadata(tmdb_match)

    watch_providers = app.tmdb_fetcher.get_tmdb_media_watch_providers(tmdb_match)
    posters = app.tmdb_fetcher.get_tmdb_media_posters(tmdb_match)
    user_data = app.tmdb_fetcher.get_tmdb_media_user_data(tmdb_match)

    return {
        "media_id": None,
        "metadata": metadata,
        "watch_providers": watch_providers,
        "posters": posters,
        "user_data": user_data,
    }


def _get_media_metadata(media_type, tmdb_id):
    if media_type == "movie":
        # if tmdb_id is in db:
        #  return get_movie_infos(tmdb_id)
        # else:
        return app.tmdb_fetcher.get_tmdb_movie_metadata(tmdb_id)

    elif media_type == "series":
        return None

    elif media_type == "episode":
        return None

def _get_media_posters(media_type, tmdb_id):
    if media_type == "movie":
        return app.tmdb_fetcher.get_tmdb_movie_posters(tmdb_id)

    elif media_type == "series":
        return None

    elif media_type == "episode":
        return None

def _get_media_watch_providers(media_type, tmdb_id):
    if media_type == "movie":
        movie_watch_providers = app.tmdb_fetcher.get_tmdb_movie_watch_providers(tmdb_id)

    elif media_type == "series":
        return None

    elif media_type == "episode":
        return None

def _get_user_data(tmdb_id, intent):
    #check for user data in db
    new_user_data = intent["user_data"]

    return {
        "watch_state": new_user_data["watch_state"],
        "impression": new_user_data.get("impression"),
        "is_collection_pick": new_user_data["is_collection_pick"],
        "watch_history": new_user_data.get(
            "watch_history",
            new_user_data.get("watch_events", []),
        ),
        "notes": new_user_data["notes"],
        "lists": new_user_data["lists"]
    }

def build_movie_draft(metadata, posters, watch_providers):
    media_drafts = []

def build_media_drafts(matches_by_intent):
    media_drafts = []

    for match in matches_by_intent:
        media_type = match["match"]["media_type"]
        tmdb_id = match["match"]["tmdb_id"]

        media_draft = {
            "metadata": _get_media_metadata(media_type, tmdb_id),
            "posters": _get_media_posters(media_type, tmdb_id),
            "watch_providers": _get_media_watch_providers(media_type, tmdb_id),
            "user_data": _get_user_data(tmdb_id, match["intent"]),
        }

        print("media_draft:")
        print(media_draft)

        media_drafts.append(media_draft)

    return media_drafts


    # for match_package in candidate_match_results:
    #     tmdb_id = match_package["tmdb_id"]
    #     media_type = match_package["media_type"]
    #
    #     with get_connection() as conn:
    #         db_metadata = media_repository.find_metadata_by_tmdb_id(conn, tmdb_id, media_type)
    #         db_posters = media_repository.find_posters_by_tmdb_id(conn, tmdb_id, media_type)
    #
    #
    #
    #
    #
    #     media_draft = build_media_draft(
    #
    #         input_query=input_query,
    #
    #         intent_info=match_package["intent_info"],
    #
    #         match_result=match_package["match_result"],
    #
    #     )
    #
    #     media_drafts.append(media_draft)

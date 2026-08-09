from PySide6.QtWidgets import QMessageBox

import app.media_repository as media_repo
from app.media_draft import (
    build_media_draft_from_db,
    build_media_draft_from_tmdb,
    build_media_draft_from_tmdb_match,
)
from app.tmdb import search_tmdb_title_candidates
from db.connection import get_connection

from .imdb_resolver import is_imdb_title_id, resolve_imdb_id_from_query
from .selection_dialog import MatchSelectionDialog


def confirm_llm_cost(parent) -> bool:
    result = QMessageBox.question(
        parent,
        "Confirm AI Lookup",
        (
            "This will use an AI lookup that may incur API costs.\n\n"
            "Do you want to continue?"
        ),
        QMessageBox.Ok | QMessageBox.Cancel,
        QMessageBox.Cancel,
    )

    return result == QMessageBox.Ok


def resolve_media_draft_from_query(parent, media_query):
    media_query = (media_query or "").strip()

    while True:
        if not media_query:
            _warn_empty_query(parent)
            return None

        outcome = resolve_media_query_without_llm(parent, media_query)

        if outcome["status"] == "resolved":
            return outcome["media_draft"]

        if outcome["status"] == "error":
            return None

        if outcome["status"] == "no_match":
            return resolve_media_draft_with_llm(parent, media_query)

        matches = outcome.get("matches") or []

        if len(matches) == 1:
            return _build_media_draft_from_candidate_or_warn(
                parent,
                matches[0],
            )

        if not matches:
            return resolve_media_draft_with_llm(parent, media_query)

        dialog = MatchSelectionDialog(
            parent=parent,
            query=media_query,
            candidates=matches,
        )
        dialog.exec()
        result = dialog.result_payload
        status = result.get("status")

        if status == "selected":
            return _build_media_draft_from_candidate_or_warn(
                parent,
                result["candidate"],
            )

        if status == "restart":
            media_query = (result.get("query") or "").strip()
            continue

        return None


def resolve_media_query_without_llm(parent, media_query):
    """Resolve an IMDb ID or return organic TMDB title-search results."""
    media_query = (media_query or "").strip()

    if not media_query:
        _warn_empty_query(parent)
        return {"status": "error"}

    if is_imdb_title_id(media_query):
        return {
            "status": "resolved",
            "media_draft": resolve_media_draft_from_imdb_id(media_query),
        }

    try:
        matches = search_tmdb_title_candidates(media_query)
    except Exception as exc:
        message = f"TMDB title search failed.\n\n{exc}"
        QMessageBox.warning(
            parent,
            "Find Media",
            message,
        )
        return {
            "status": "error",
            "message": message,
            "message_shown": True,
        }

    if not matches:
        return {"status": "no_match"}

    return {"status": "matches", "matches": matches}


def resolve_media_draft_with_llm(parent, media_query):
    media_query = (media_query or "").strip()

    if not media_query:
        _warn_empty_query(parent)
        return None

    if not confirm_llm_cost(parent):
        return None

    result = resolve_imdb_id_from_query(media_query)

    if result["status"] != "resolved":
        QMessageBox.warning(
            parent,
            "Find Media",
            result["followup_question"] or result["reason"],
        )
        return None

    return resolve_media_draft_from_imdb_id(result["imdb_id"])


def resolve_media_draft_from_imdb_id(imdb_id):
    imdb_id = (imdb_id or "").strip()

    with get_connection() as conn:
        media_from_db = media_repo.get_media_by_imdb_id(conn, imdb_id)

        if media_from_db:
            return build_media_draft_from_db(conn, media_from_db)

    return build_media_draft_from_tmdb(imdb_id)


def build_media_draft_from_candidate(candidate):
    media_id = candidate.get("media_id")
    media_type = candidate.get("media_type")
    tmdb_id = candidate.get("tmdb_id")

    if media_type not in {"movie", "series"}:
        raise ValueError("Title candidate requires a movie or series media type.")

    if candidate.get("source") == "db" or media_id is not None:
        if media_id is None:
            raise ValueError("Local title candidate requires media_id.")

        with get_connection() as conn:
            media_from_db = media_repo.get_media_by_id(conn, media_id)

            if media_from_db:
                return build_media_draft_from_db(conn, media_from_db)

        raise ValueError("The selected local media is no longer available.")

    if tmdb_id is None:
        raise ValueError("Remote title candidate requires tmdb_id.")

    with get_connection() as conn:
        media_from_db = media_repo.get_media_by_tmdb_id(
            conn,
            tmdb_id,
            media_type,
        )

        if media_from_db:
            return build_media_draft_from_db(conn, media_from_db)

    return build_media_draft_from_tmdb_match({
        "media_type": media_type,
        "tmdb_id": tmdb_id,
    })


def _build_media_draft_from_candidate_or_warn(parent, candidate):
    try:
        return build_media_draft_from_candidate(candidate)
    except Exception as exc:
        QMessageBox.warning(
            parent,
            "Find Media",
            f"Could not load the selected media details.\n\n{exc}",
        )
        return None


def _warn_empty_query(parent):
    QMessageBox.warning(
        parent,
        "Find Media",
        "Enter an IMDb ID, title, or media description first.",
    )

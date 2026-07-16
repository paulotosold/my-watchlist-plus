import re

from PySide6.QtWidgets import QMessageBox

import app.media_repository as media_repo
from app.imdb_id_resolver import resolve_imdb_id_from_query
from app.media_draft_builder import build_media_draft_from_db, build_media_draft_from_tmdb
from db.connection import get_connection


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

    if not media_query:
        QMessageBox.warning(
            parent,
            "Find Media",
            "Enter an IMDb ID or media description first.",
        )
        return None

    if re.fullmatch(r"tt\d{7,10}", media_query):
        imdb_id = media_query
    else:
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

        imdb_id = result["imdb_id"]

    with get_connection() as conn:
        media_from_db = media_repo.get_media_by_imdb_id(conn, imdb_id)

        if media_from_db:
            return build_media_draft_from_db(conn, media_from_db)

    return build_media_draft_from_tmdb(imdb_id)

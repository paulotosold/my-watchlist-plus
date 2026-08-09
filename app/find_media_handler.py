from app.media_details import open_media_details_dialog
from app.media_lookup import resolve_media_draft_from_query


def handle_find_media_input(parent, media_query):
    media_draft = resolve_media_draft_from_query(parent, media_query)

    if media_draft is None:
        return {"status": "cancelled"}

    return open_media_details_dialog(parent, media_draft, media_query=media_query)

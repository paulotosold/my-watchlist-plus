from app.media_details_dialog import open_media_details_dialog
from app.media_lookup import resolve_media_draft_from_query


def handle_media_input(parent, input_query):
    media_draft = resolve_media_draft_from_query(parent, input_query)

    if media_draft is None:
        return {"status": "cancelled"}

    return open_media_details_dialog(parent, media_draft, input_query=input_query)

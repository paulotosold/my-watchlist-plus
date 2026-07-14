from __future__ import annotations

from copy import deepcopy
from uuid import uuid4


EMPTY_NOTE_ERROR = "Note cannot be empty."


def normalize_note_text(value):
    if not isinstance(value, str):
        return ""

    return value.strip()


def validate_note_text(value):
    normalized = normalize_note_text(value)

    if not normalized:
        raise ValueError(EMPTY_NOTE_ERROR)

    return normalized


def apply_note_result(media_draft, entry, result):
    action = result.get("action")
    notes = ensure_user_notes(media_draft)

    if action == "delete":
        note_index = get_note_index(entry, notes)

        if note_index is not None:
            del notes[note_index]

        return

    if action != "save":
        raise ValueError(f"Unsupported note action: {action}")

    note_text = validate_note_text(result.get("note"))
    note_index = get_note_index(entry, notes)

    if entry is None:
        notes.append({
            "draft_id": uuid4().hex,
            "note": note_text,
        })
        return

    if note_index is None:
        raise ValueError("Note entry no longer exists.")

    updated_note = deepcopy(notes[note_index])
    updated_note["note"] = note_text
    notes[note_index] = updated_note


def get_note_index(entry, notes):
    if not entry:
        return None

    note_index = entry.get("note_index")

    if note_index is not None and 0 <= note_index < len(notes):
        return note_index

    note_id = entry.get("id")

    if note_id is not None:
        for index, note in enumerate(notes):
            if note.get("id") == note_id:
                return index

    draft_id = entry.get("draft_id")

    if draft_id is not None:
        for index, note in enumerate(notes):
            if note.get("draft_id") == draft_id:
                return index

    return None


def ensure_user_notes(media_draft):
    user_data = media_draft.setdefault("user_data", {})
    return user_data.setdefault("notes", [])

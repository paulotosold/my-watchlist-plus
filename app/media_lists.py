from __future__ import annotations


EMPTY_LIST_NAME_ERROR = "List name cannot be empty."
DUPLICATE_LIST_NAME_ERROR = "A list with this name already exists."


def normalize_list_name(value):
    if not isinstance(value, str):
        return ""

    return value.strip()


def validate_list_name(value):
    normalized = normalize_list_name(value)

    if not normalized:
        raise ValueError(EMPTY_LIST_NAME_ERROR)

    return normalized


def normalize_list_description(value):
    if not isinstance(value, str):
        return None

    normalized = value.strip()
    return normalized or None


def is_duplicate_list_name(value, lists, current_list_id=None):
    normalized = normalize_list_name(value)

    if not normalized:
        return False

    return any(
        list_item.get("id") != current_list_id
        and normalize_list_name(list_item.get("name")) == normalized
        for list_item in lists or []
    )

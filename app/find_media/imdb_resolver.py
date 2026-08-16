from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from app.config import require_env


IMDB_TITLE_ID_PATTERN = re.compile(r"^tt\d{7,10}$")

IMDB_ID_RESOLUTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "status": {
            "type": "string",
            "enum": ["resolved", "needs_followup", "no_match"],
        },
        "imdb_id": {
            "type": ["string", "null"],
            "description": "The IMDb title ID, such as tt0093773.",
        },
        "media_type": {
            "type": ["string", "null"],
            "enum": ["movie", "series", "episode", None],
        },
        "title": {
            "type": ["string", "null"],
        },
        "year": {
            "type": ["integer", "null"],
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "followup_question": {
            "type": ["string", "null"],
        },
        "reason": {
            "type": "string",
        },
    },
    "required": [
        "status",
        "imdb_id",
        "media_type",
        "title",
        "year",
        "confidence",
        "followup_question",
        "reason",
    ],
}


def is_imdb_title_id(value: str) -> bool:
    if not isinstance(value, str):
        return False

    return bool(IMDB_TITLE_ID_PATTERN.fullmatch(value.strip()))


def resolve_imdb_id_from_query(input_query: str) -> dict[str, Any]:
    """
    Resolve a natural-language user query to an IMDb title ID.

    Returns:
        {
            "status": "resolved" | "needs_followup" | "no_match",
            "imdb_id": "tt..." | None,
            "media_type": "movie" | "series" | "episode" | None,
            "title": str | None,
            "year": int | None,
            "confidence": float,
            "followup_question": str | None,
            "reason": str,
        }
    """

    client = OpenAI(api_key=require_env("OPENAI_API_KEY"))

    prompt = build_imdb_id_resolution_prompt(input_query)

    response = client.responses.create(
        model="gpt-5.6-luna",
        reasoning={"effort": "none"},
        tools=[
            {
                "type": "web_search",
                "search_context_size": "low",
            }
        ],
        tool_choice="required",
        input=[
            {
                "role": "system",
                "content": (
                    "You identify the IMDb title ID for exactly one movie, TV series, "
                    "or TV episode mentioned by the user. Use web search when needed. "
                    "Return only structured JSON matching the schema."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "imdb_id_resolution",
                "strict": True,
                "schema": IMDB_ID_RESOLUTION_SCHEMA,
            }
        },
    )

    result = json.loads(response.output_text)

    return validate_imdb_id_resolution(result)


def build_imdb_id_resolution_prompt(input_query: str) -> str:
    return f"""
User input:
{input_query!r}

Task:
Identify the single IMDb title ID for the media item mentioned by the user.

Important:
- Return an IMDb title ID only, meaning an ID that starts with "tt".
- Do not return IMDb person IDs, which start with "nm".
- Do not return IMDb company IDs, character IDs, or any other external ID.
- If the user mentions a movie, resolve the movie IMDb title ID.
- If the user mentions a TV series, resolve the series IMDb title ID.
- If the user clearly mentions a specific episode, resolve the episode IMDb title ID.
- If the user says "first movie", "original movie", or equivalent, prefer the original/earliest feature film in the franchise.
- If the user says "second movie", prefer the second released feature film in the franchise.
- If the user says "new one", "latest", or equivalent, prefer the newest relevant title.
- If the user uses a localized, translated, misspelled, partial, or informal title, infer the likely intended title.
- If multiple titles are genuinely plausible and you cannot confidently choose one, return status = "needs_followup".
- If no plausible title can be identified, return status = "no_match".

Output rules:
- For status = "resolved", imdb_id must be a valid IMDb title ID like "tt0093773".
- For status = "resolved", confidence should usually be >= 0.85.
- For status = "needs_followup" or "no_match", imdb_id must be null.
- followup_question must be null when status = "resolved".
- followup_question should be a concise question when status = "needs_followup".
- reason should briefly explain why this IMDb ID was selected.
""".strip()


def validate_imdb_id_resolution(result: dict[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    imdb_id = result.get("imdb_id")

    if status == "resolved":
        if not is_imdb_title_id(imdb_id):
            return {
                "status": "no_match",
                "imdb_id": None,
                "media_type": None,
                "title": None,
                "year": None,
                "confidence": 0,
                "followup_question": None,
                "reason": (
                    "The model returned status='resolved', but the IMDb ID was missing "
                    "or did not match the expected IMDb title ID format."
                ),
            }

        result["imdb_id"] = imdb_id.strip()
        result["followup_question"] = None
        return result

    result["imdb_id"] = None

    if status == "no_match":
        result["followup_question"] = None

    return result

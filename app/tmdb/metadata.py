"""Fetch and normalize TMDB movie, series, and episode metadata."""

from .client import get_default_client


def _tmdb_get(endpoint, params=None, *, client=None):
    client = client or get_default_client()

    if params is None:
        return client.get_json(endpoint)

    return client.get_json(endpoint, params=params)


TMDB_GENRE_SCOPES = {
    28: "movie",
    12: "movie",
    10759: "series",
    16: "movie_series",
    35: "movie_series",
    80: "movie_series",
    99: "movie_series",
    18: "movie_series",
    10751: "movie_series",
    14: "movie",
    36: "movie",
    27: "movie",
    10762: "series",
    10402: "movie",
    9648: "movie_series",
    10763: "series",
    10764: "series",
    10749: "movie",
    878: "movie",
    10765: "series",
    10766: "series",
    10770: "movie",
    10767: "series",
    53: "movie",
    10752: "movie",
    10768: "series",
    37: "movie_series",
}

WRITER_JOBS = {"Writer", "Screenplay", "Teleplay", "Story"}


def _clean_date(value):
    return value or None


def _clean_runtime(value):
    if value is None or value <= 0:
        return None

    return value


def _format_genres(genres, media_type):
    fallback_scope = "series" if media_type == "episode" else media_type

    return [
        {
            "tmdb_id": genre["id"],
            "name": genre["name"],
            "tmdb_scope": TMDB_GENRE_SCOPES.get(genre["id"], fallback_scope),
        }
        for genre in genres
        if genre.get("id") and genre.get("name")
    ]


def _format_spoken_languages(spoken_languages):
    return [
        {
            "code": language["iso_639_1"],
            "name": language.get("english_name") or language.get("name"),
        }
        for language in spoken_languages
        if language.get("iso_639_1")
    ]


def _format_origin_language(language_code, spoken_languages):
    if not language_code:
        return None

    for language in spoken_languages:
        if language["code"] == language_code:
            return language

    return {
        "code": language_code,
        "name": None,
    }


def _format_production_countries(countries):
    return [
        {
            "code": country["iso_3166_1"],
            "name": country["name"],
        }
        for country in countries
        if country.get("iso_3166_1") and country.get("name")
    ]


def _format_production_companies(companies):
    return [
        {
            "tmdb_id": company["id"],
            "name": company["name"],
        }
        for company in companies
        if company.get("id") and company.get("name")
    ]


def _format_people(people):
    formatted_people = []
    seen = set()

    for person in people:
        tmdb_id = person.get("id")
        name = person.get("name")

        if not tmdb_id or not name or tmdb_id in seen:
            continue

        seen.add(tmdb_id)
        formatted_people.append({
            "tmdb_id": tmdb_id,
            "name": name,
        })

    return formatted_people


def _format_crew(crew, jobs, include_job=False):
    formatted_crew = []
    seen = set()

    for person in crew:
        job = person.get("job")
        tmdb_id = person.get("id")
        name = person.get("name")

        if job not in jobs or not tmdb_id or not name:
            continue

        key = (tmdb_id, job if include_job else None)

        if key in seen:
            continue

        seen.add(key)

        formatted_person = {
            "tmdb_id": tmdb_id,
            "name": name,
        }

        if include_job:
            formatted_person["job"] = job

        formatted_crew.append(formatted_person)

    return formatted_crew


def _format_cast(cast):
    formatted_cast = []
    seen = set()

    for person in cast:
        tmdb_id = person.get("id")
        name = person.get("name")
        character = person.get("character")

        if not tmdb_id or not name:
            continue

        key = (tmdb_id, character)

        if key in seen:
            continue

        seen.add(key)
        formatted_cast.append({
            "tmdb_id": tmdb_id,
            "name": name,
            "character": character,
            "cast_order": person.get("order"),
        })

    return formatted_cast

def get_tmdb_media_metadata(tmdb_id_match, *, client=None):
    tmdb_id_match = _unwrap_resolved_tmdb_match(
        tmdb_id_match,
        "get_tmdb_media_metadata",
    )
    client = client or get_default_client()

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        metadata = _get_tmdb_movie_metadata(tmdb_id_match["tmdb_id"], client)

    elif media_type == "series":
        metadata = _get_tmdb_series_metadata(tmdb_id_match["tmdb_id"], client)

    elif media_type == "episode":
        metadata = _get_tmdb_episode_metadata(tmdb_id_match, client)

    else:
        raise ValueError(f"Unsupported media_type: {media_type}")

    return metadata


def _unwrap_resolved_tmdb_match(tmdb_id_match, caller_name):
    if not isinstance(tmdb_id_match, dict):
        raise ValueError(f"{caller_name} requires a TMDB match.")

    if tmdb_id_match.get("status"):
        if (
            tmdb_id_match.get("status") != "resolved"
            or not tmdb_id_match.get("match")
        ):
            raise ValueError(f"{caller_name} requires a resolved TMDB match.")

        return tmdb_id_match["match"]

    return tmdb_id_match


def get_tmdb_media_series_view(tmdb_id_match, *, client=None):
    tmdb_id_match = _unwrap_resolved_tmdb_match(
        tmdb_id_match,
        "get_tmdb_media_series_view",
    )

    if tmdb_id_match["media_type"] != "series":
        return None

    client = client or get_default_client()
    series_tmdb_id = tmdb_id_match["tmdb_id"]
    series_details = _tmdb_get(f"tv/{series_tmdb_id}", client=client)

    return {
        "summary": _format_tmdb_series_summary(series_details),
        "episodes": _format_tmdb_series_episodes(
            series_tmdb_id,
            series_details,
            client,
        ),
    }


def _format_tmdb_series_episodes(series_tmdb_id, series_details, client):
    return [
        {
            "series_id": None,
            "episode_id": None,
            "tmdb_id": match.get("tmdb_id"),
            "season_num": match.get("season_num"),
            "episode_num": match.get("episode_num"),
            "title": match.get("title"),
            "release_date": _clean_date(match.get("release_date")),
        }
        for match in get_tmdb_series_episode_matches(
            series_tmdb_id,
            client=client,
            series_details=series_details,
        )
    ]


def _format_tmdb_series_summary(series_details):
    return {
        "season_count": series_details.get("number_of_seasons"),
        "episode_count": series_details.get("number_of_episodes"),
        "first_air_date": _clean_date(series_details.get("first_air_date")),
        "last_air_date": _clean_date(series_details.get("last_air_date")),
        "total_runtime_min": None,
        "avg_episode_runtime_min": None,
    }


def _get_tmdb_movie_metadata(tmdb_id, client):
    movie_details = _tmdb_get(f"movie/{tmdb_id}", client=client)
    movie_credits = _tmdb_get(f"movie/{tmdb_id}/credits", client=client)

    return _format_tmdb_movie_metadata(movie_details, movie_credits)


def _format_tmdb_movie_metadata(movie_details, movie_credits):
    spoken_languages = _format_spoken_languages(
        movie_details.get("spoken_languages", [])
    )

    return {
        "tmdb_id": movie_details["id"],
        "imdb_id": movie_details.get("imdb_id"),
        "media_type": "movie",
        "title": movie_details["title"],
        "original_title": movie_details["original_title"],
        "production_status": movie_details.get("status"),
        "release_date": _clean_date(movie_details.get("release_date")),
        "runtime_min": _clean_runtime(movie_details.get("runtime")),

        "genres": _format_genres(movie_details.get("genres", []), "movie"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            movie_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            movie_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            movie_details.get("production_companies", [])
        ),
        "directors": _format_crew(movie_credits.get("crew", []), {"Director"}),
        "creators": [],
        "writers": _format_crew(
            movie_credits.get("crew", []),
            WRITER_JOBS,
            include_job=True,
        ),
        "actors": _format_cast(movie_credits.get("cast", [])),

        "episode_details": None,
    }


def _get_tmdb_series_metadata(tmdb_id, client):
    series_details = _tmdb_get(f"tv/{tmdb_id}", client=client)
    series_ids = _tmdb_get(f"tv/{tmdb_id}/external_ids", client=client)
    series_credits = _tmdb_get(f"tv/{tmdb_id}/credits", client=client)

    return _format_tmdb_series_metadata(
        series_details,
        series_ids,
        series_credits,
    )


def _format_tmdb_series_metadata(
    series_details,
    series_ids,
    series_credits,
):
    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )

    return {
        "tmdb_id": series_details["id"],
        "imdb_id": series_ids.get("imdb_id"),
        "media_type": "series",
        "title": series_details["name"],
        "original_title": series_details["original_name"],
        "production_status": series_details.get("status"),
        "release_date": _clean_date(series_details.get("first_air_date")),
        "runtime_min": None,

        "genres": _format_genres(series_details.get("genres", []), "series"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            series_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            series_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            series_details.get("production_companies", [])
        ),
        "directors": _format_crew(series_credits.get("crew", []), {"Director"}),
        "creators": _format_people(series_details.get("created_by", [])),
        "writers": _format_crew(
            series_credits.get("crew", []),
            WRITER_JOBS,
            include_job=True,
        ),
        "actors": _format_cast(series_credits.get("cast", [])),

        "episode_details": None,
    }


def _get_tmdb_episode_metadata(tmdb_id_match, client):
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")
    episode_num = tmdb_id_match.get("episode_num")

    if not series_tmdb_id or season_num is None or episode_num is None:
        raise ValueError(
            "Episode TMDB metadata requires series_tmdb_id, season_num, "
            "and episode_num."
        )

    series_details = _tmdb_get(f"tv/{series_tmdb_id}", client=client)
    series_ids = _tmdb_get(
        f"tv/{series_tmdb_id}/external_ids",
        client=client,
    )
    episode_details = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}",
        client=client,
    )
    episode_ids = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}/external_ids",
        client=client,
    )
    episode_credits = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}/credits",
        client=client,
    )

    return _format_tmdb_episode_metadata(
        series_details=series_details,
        series_ids=series_ids,
        episode_details=episode_details,
        episode_ids=episode_ids,
        episode_credits=episode_credits,
        season_num=season_num,
        episode_num=episode_num,
    )


def _format_tmdb_episode_metadata(
    series_details,
    series_ids,
    episode_details,
    episode_ids,
    episode_credits,
    season_num,
    episode_num,
):
    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )
    episode_cast = (
        episode_credits.get("cast", [])
        + episode_credits.get("guest_stars", [])
    )

    return {
        "tmdb_id": episode_details["id"],
        "imdb_id": episode_ids.get("imdb_id"),
        "media_type": "episode",
        "title": episode_details.get("name"),
        "original_title": episode_details.get("name"),
        "production_status": series_details.get("status"),
        "release_date": _clean_date(episode_details.get("air_date")),
        "runtime_min": _clean_runtime(episode_details.get("runtime")),

        "genres": _format_genres(series_details.get("genres", []), "series"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            series_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            series_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            series_details.get("production_companies", [])
        ),
        "directors": _format_crew(episode_credits.get("crew", []), {"Director"}),
        "creators": _format_people(series_details.get("created_by", [])),
        "writers": _format_crew(
            episode_credits.get("crew", []),
            WRITER_JOBS,
            include_job=True,
        ),
        "actors": _format_cast(episode_cast),

        "episode_details": {
            "series_tmdb_id": series_details["id"],
            "series_imdb_id": series_ids.get("imdb_id"),
            "series_title": series_details.get("name"),
            "season_num": season_num,
            "episode_num": episode_num,
        },
    }

def get_tmdb_series_episode_matches(
    series_tmdb_id,
    *,
    client=None,
    series_details=None,
):
    client = client or get_default_client()

    if series_details is None:
        series_details = _tmdb_get(f"tv/{series_tmdb_id}", client=client)
    episode_matches = []

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}",
            client=client,
        )

        for episode in season_details.get("episodes", []):
            episode_num = episode.get("episode_number")
            episode_tmdb_id = episode.get("id")

            if episode_num is None or episode_tmdb_id is None:
                continue

            episode_matches.append({
                "media_type": "episode",
                "tmdb_id": episode_tmdb_id,
                "title": episode.get("name"),
                "release_date": episode.get("air_date"),
                "series_tmdb_id": series_tmdb_id,
                "season_num": season_num,
                "episode_num": episode_num,
            })

    return sorted(
        episode_matches,
        key=lambda match: (match["season_num"], match["episode_num"]),
    )


def get_tmdb_series_episode_metadata_list(
    series_tmdb_id,
    include_episode_imdb_ids=True,
    *,
    checked_at,
    client=None,
):
    client = client or get_default_client()
    series_details = _tmdb_get(f"tv/{series_tmdb_id}", client=client)
    series_ids = _tmdb_get(
        f"tv/{series_tmdb_id}/external_ids",
        client=client,
    )

    spoken_languages = _format_spoken_languages(
        series_details.get("spoken_languages", [])
    )
    episode_metadata_list = []

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}",
            client=client,
        )

        for episode in season_details.get("episodes", []):
            episode_metadata = _format_series_episode_seed_metadata(
                series_details=series_details,
                series_ids=series_ids,
                spoken_languages=spoken_languages,
                episode=episode,
                include_episode_imdb_id=include_episode_imdb_ids,
                checked_at=checked_at,
                client=client,
            )

            if episode_metadata is not None:
                episode_metadata_list.append(episode_metadata)

    return sorted(
        episode_metadata_list,
        key=lambda metadata: (
            metadata["episode_details"]["season_num"],
            metadata["episode_details"]["episode_num"],
        ),
    )


def _format_series_episode_seed_metadata(
    series_details,
    series_ids,
    spoken_languages,
    episode,
    include_episode_imdb_id,
    checked_at,
    client=None,
):
    episode_tmdb_id = episode.get("id")
    season_num = episode.get("season_number")
    episode_num = episode.get("episode_number")

    if episode_tmdb_id is None or season_num is None or episode_num is None:
        return None

    title = episode.get("name") or f"Episode {episode_num}"
    imdb_id = None

    if include_episode_imdb_id:
        episode_ids = _tmdb_get(
            "tv/{series_tmdb_id}/season/{season_num}/episode/"
            "{episode_num}/external_ids".format(
                series_tmdb_id=series_details["id"],
                season_num=season_num,
                episode_num=episode_num,
            ),
            client=client,
        )
        imdb_id = episode_ids.get("imdb_id")

    return {
        "tmdb_id": episode_tmdb_id,
        "imdb_id": imdb_id,
        "media_type": "episode",
        "title": title,
        "original_title": title,
        "production_status": series_details.get("status"),
        "release_date": _clean_date(episode.get("air_date")),
        "runtime_min": _clean_runtime(episode.get("runtime")),

        "genres": _format_genres(series_details.get("genres", []), "series"),
        "spoken_languages": spoken_languages,
        "origin_language": _format_origin_language(
            series_details.get("original_language"),
            spoken_languages,
        ),
        "production_countries": _format_production_countries(
            series_details.get("production_countries", [])
        ),
        "production_companies": _format_production_companies(
            series_details.get("production_companies", [])
        ),
        "directors": [],
        "creators": _format_people(series_details.get("created_by", [])),
        "writers": [],
        "actors": [],

        "episode_details": {
            "series_tmdb_id": series_details["id"],
            "series_imdb_id": series_ids.get("imdb_id"),
            "series_title": series_details.get("name"),
            "season_num": season_num,
            "episode_num": episode_num,
        },
        "last_tmdb_metadata_checked_at": checked_at,
        "last_tmdb_posters_checked_at": None,
        "last_tmdb_watch_providers_checked_at": None,
    }

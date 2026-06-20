import requests

from app.config import (
    TMDB_LANGUAGE,
    TMDB_WATCH_REGION,
    WATCH_PROVIDER_ACCESS_TYPES,
    require_env,
)

TMDB_READ_ACCESS_TOKEN = require_env("TMDB_READ_ACCESS_TOKEN")
#from helpers import format_filename
#from helpers import clear_folder_images_temp

headers = {
    "accept": "application/json",
    "Authorization": f"Bearer {TMDB_READ_ACCESS_TOKEN}"
}

def _get_genre_names(genre_codes):
    genres = {
        28: 'Action',
        12: 'Adventure',
        10759: 'Action & Adventure',
        16: 'Animation',
        35: 'Comedy',
        80: 'Crime',
        99: 'Documentary',
        18: 'Drama',
        10751: 'Family',
        14: 'Fantasy',
        36: 'History',
        27: 'Horror',
        10762: 'Kids',
        10402: 'Music',
        9648: 'Mystery',
        10763: 'News',
        10764: 'Reality',
        10749: 'Romance',
        878: 'Science Fiction',
        10765: 'Sci-Fi & Fantasy',
        10766: 'Soap',
        10770: 'TV Movie',
        10767: 'Talk',
        53: 'Thriller',
        10752: 'War',
        10768: 'War & Politics',
        37: 'Western',
    }

    return [genres[code] for code in genre_codes if code in genres]

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


def _tmdb_get(endpoint, params=None):
    url = f"https://api.themoviedb.org/3/{endpoint.lstrip('/')}"
    response = requests.get(
        url,
        headers=headers,
        params=params or {"language": TMDB_LANGUAGE},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


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


def _format_watch_providers(watch_provider_data, country_code):
    providers_by_region = watch_provider_data.get("results", {}).get(country_code, {})
    formatted_providers = []
    seen = set()

    for access_type in WATCH_PROVIDER_ACCESS_TYPES:
        for provider in providers_by_region.get(access_type, []):
            provider_tmdb_id = provider.get("provider_id")
            provider_name = provider.get("provider_name")

            if not provider_tmdb_id or not provider_name:
                continue

            key = (provider_tmdb_id, country_code, access_type)

            if key in seen:
                continue

            seen.add(key)
            formatted_providers.append({
                "provider_tmdb_id": provider_tmdb_id,
                "provider_name": provider_name,
                "country_code": country_code,
                "access_type": access_type,
            })

    return formatted_providers


def _format_tmdb_posters(
    image_data,
    scope,
    original_language=None,
    series_tmdb_id=None,
    season_num=None,
):
    formatted_posters = []
    seen = set()

    for poster in image_data.get("posters", []):
        file_path = poster.get("file_path")

        if (
            not file_path
            or poster.get("iso_639_1") not in {"en", None, original_language}
            or not 0.64 <= poster.get("aspect_ratio", 0) <= 0.72
            or poster.get("width", 0) < 500
            or poster.get("height", 0) < 750
        ):
            continue

        filename = file_path.removeprefix("/")

        if filename in seen:
            continue

        seen.add(filename)
        formatted_posters.append({
            "scope": scope,
            "filename": filename,
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False,
            "series_tmdb_id": series_tmdb_id,
            "season_num": season_num,
        })

    return formatted_posters


def _tmdb_image_params(original_language=None):
    include_image_languages = ["en", "null"]

    if original_language and original_language not in include_image_languages:
        include_image_languages.append(original_language)

    return {
        "language": TMDB_LANGUAGE,
        "include_image_language": ",".join(include_image_languages),
    }


# -----------------------------------------------------------------------

def find_tmdb_match_by_imdb_id(imdb_id):
    url = f"https://api.themoviedb.org/3/find/{imdb_id.strip()}"
    params = {
        "external_source": "imdb_id",
        "language": TMDB_LANGUAGE,
    }

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()

    result = response.json()

    candidates = []

    for movie in result.get("movie_results", []):
        candidates.append({
            "media_type": "movie",
            "tmdb_id": movie["id"],
            "title": movie.get("title"),
            "release_date": movie.get("release_date"),
        })

    for series in result.get("tv_results", []):
        candidates.append({
            "media_type": "series",
            "tmdb_id": series["id"],
            "title": series.get("name"),
            "release_date": series.get("first_air_date"),
        })

    for episode in result.get("tv_episode_results", []):
        candidates.append({
            "media_type": "episode",
            "tmdb_id": episode["id"],
            "title": episode.get("name"),
            "release_date": episode.get("air_date"),
            "series_tmdb_id": episode.get("show_id"),
            "season_num": episode.get("season_number"),
            "episode_num": episode.get("episode_number"),
        })

    if len(candidates) == 1:
        return {
            "status": "resolved",
            "match": candidates[0],
        }

    if len(candidates) > 1:
        return {
            "status": "ambiguous",
            "match": None,
            "reason": "IMDb ID matched multiple TMDB media categories.",
            "candidates": candidates,
        }

    return {
        "status": "not_found",
        "match": None,
        "reason": "IMDb ID did not match any TMDB movie, series, or episode.",
    }

# -----------------------------------------------------------------------

def get_tmdb_movie_metadata(tmdb_id):
    return _get_tmdb_movie_metadata(tmdb_id)


def get_tmdb_media_metadata(tmdb_id_match):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_metadata requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        return _get_tmdb_movie_metadata(tmdb_id_match["tmdb_id"])

    if media_type == "series":
        return _get_tmdb_series_metadata(tmdb_id_match["tmdb_id"])

    if media_type == "episode":
        return _get_tmdb_episode_metadata(tmdb_id_match)

    raise ValueError(f"Unsupported media_type: {media_type}")


def _get_tmdb_movie_metadata(tmdb_id):
    movie_details = _tmdb_get(f"movie/{tmdb_id}")
    movie_credits = _tmdb_get(f"movie/{tmdb_id}/credits")

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

        "series_summary": None,
        "episode_details": None,
    }


def _get_tmdb_series_metadata(tmdb_id):
    series_details = _tmdb_get(f"tv/{tmdb_id}")
    series_ids = _tmdb_get(f"tv/{tmdb_id}/external_ids")
    series_credits = _tmdb_get(f"tv/{tmdb_id}/credits")

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

        "series_summary": {
            "season_count": series_details.get("number_of_seasons"),
            "episode_count": series_details.get("number_of_episodes"),
            "first_air_date": _clean_date(series_details.get("first_air_date")),
            "last_air_date": _clean_date(series_details.get("last_air_date")),
            "total_runtime_min": None,
        },
        "episode_details": None,
    }


def _get_tmdb_episode_metadata(tmdb_id_match):
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")
    episode_num = tmdb_id_match.get("episode_num")

    if not series_tmdb_id or season_num is None or episode_num is None:
        raise ValueError(
            "Episode TMDB metadata requires series_tmdb_id, season_num, "
            "and episode_num."
        )

    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    series_ids = _tmdb_get(f"tv/{series_tmdb_id}/external_ids")
    episode_details = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}"
    )
    episode_ids = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}/external_ids"
    )
    episode_credits = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/episode/{episode_num}/credits"
    )

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

        "series_summary": None,
        "episode_details": {
            "series_tmdb_id": series_details["id"],
            "series_imdb_id": series_ids.get("imdb_id"),
            "series_title": series_details.get("name"),
            "season_num": season_num,
            "episode_num": episode_num,
        },
    }


def get_tmdb_movie_watch_providers(tmdb_id, country_code=TMDB_WATCH_REGION):
    return get_tmdb_media_watch_providers({
        "media_type": "movie",
        "tmdb_id": tmdb_id,
    }, country_code=country_code)


def get_tmdb_media_watch_providers(tmdb_id_match, country_code=TMDB_WATCH_REGION):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_watch_providers requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        watch_provider_data = _tmdb_get(
            f"movie/{tmdb_id_match['tmdb_id']}/watch/providers"
        )

    elif media_type == "series":
        watch_provider_data = _tmdb_get(
            f"tv/{tmdb_id_match['tmdb_id']}/watch/providers"
        )

    elif media_type == "episode":
        series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
        season_num = tmdb_id_match.get("season_num")

        if not series_tmdb_id or season_num is None:
            raise ValueError(
                "Episode watch providers require series_tmdb_id and season_num."
            )

        watch_provider_data = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}/watch/providers"
        )

    else:
        raise ValueError(f"Unsupported media_type: {media_type}")

    return _format_watch_providers(watch_provider_data, country_code)

def get_tmdb_movie_posters(tmdb_id):
    return get_tmdb_media_posters({
        "media_type": "movie",
        "tmdb_id": tmdb_id,
    })


def get_tmdb_media_posters(tmdb_id_match):
    if tmdb_id_match.get("status"):
        if tmdb_id_match.get("status") != "resolved" or not tmdb_id_match.get("match"):
            raise ValueError(
                "get_tmdb_media_posters requires a resolved TMDB match."
            )

        tmdb_id_match = tmdb_id_match["match"]

    media_type = tmdb_id_match["media_type"]

    if media_type == "movie":
        return _get_tmdb_movie_posters(tmdb_id_match["tmdb_id"])

    if media_type == "series":
        return _get_tmdb_series_posters(tmdb_id_match["tmdb_id"])

    if media_type == "episode":
        return _get_tmdb_episode_posters(tmdb_id_match)

    raise ValueError(f"Unsupported media_type: {media_type}")


def get_tmdb_media_user_data(tmdb_id_match=None):
    return {
        "watch_state": "to_watch",
        "rating": None,
        "is_collection_pick": None,
        "watch_history": [],
        "notes": [],
        "lists": [],
    }


def get_tmdb_series_episode_matches(series_tmdb_id):
    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    episode_matches = []

    for season in series_details.get("seasons", []):
        season_num = season.get("season_number")

        if season_num is None or season_num < 1:
            continue

        if season.get("episode_count") == 0:
            continue

        season_details = _tmdb_get(
            f"tv/{series_tmdb_id}/season/{season_num}"
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
):
    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    series_ids = _tmdb_get(f"tv/{series_tmdb_id}/external_ids")

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
            f"tv/{series_tmdb_id}/season/{season_num}"
        )

        for episode in season_details.get("episodes", []):
            episode_metadata = _format_series_episode_seed_metadata(
                series_details=series_details,
                series_ids=series_ids,
                spoken_languages=spoken_languages,
                episode=episode,
                include_episode_imdb_id=include_episode_imdb_ids,
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
            )
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

        "series_summary": None,
        "episode_details": {
            "series_tmdb_id": series_details["id"],
            "series_imdb_id": series_ids.get("imdb_id"),
            "series_title": series_details.get("name"),
            "season_num": season_num,
            "episode_num": episode_num,
        },
    }


def _get_tmdb_movie_posters(tmdb_id):
    movie_details = _tmdb_get(f"movie/{tmdb_id}")
    original_language = movie_details.get("original_language")
    movie_images = _tmdb_get(
        f"movie/{tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return _format_tmdb_posters(
        movie_images,
        scope="media",
        original_language=original_language,
    )


def _get_tmdb_series_posters(tmdb_id):
    series_details = _tmdb_get(f"tv/{tmdb_id}")
    original_language = series_details.get("original_language")
    series_images = _tmdb_get(
        f"tv/{tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return _format_tmdb_posters(
        series_images,
        scope="media",
        original_language=original_language,
    )


def _get_tmdb_episode_posters(tmdb_id_match):
    series_tmdb_id = tmdb_id_match.get("series_tmdb_id")
    season_num = tmdb_id_match.get("season_num")

    if not series_tmdb_id or season_num is None:
        raise ValueError(
            "Episode posters require series_tmdb_id and season_num."
        )

    series_details = _tmdb_get(f"tv/{series_tmdb_id}")
    original_language = series_details.get("original_language")
    season_images = _tmdb_get(
        f"tv/{series_tmdb_id}/season/{season_num}/images",
        params=_tmdb_image_params(original_language),
    )
    series_images = _tmdb_get(
        f"tv/{series_tmdb_id}/images",
        params=_tmdb_image_params(original_language),
    )

    return (
        _format_tmdb_posters(
            season_images,
            scope="season",
            original_language=original_language,
            series_tmdb_id=series_tmdb_id,
            season_num=season_num,
        )
        + _format_tmdb_posters(
            series_images,
            scope="series",
            original_language=original_language,
            series_tmdb_id=series_tmdb_id,
            season_num=None,
        )
    )




def get_tmdb_infos(tmdb_id, media_type):
    if media_type == "episode":
        raise ValueError(
            "Episode metadata requires a resolved TMDB match with "
            "series_tmdb_id, season_num, and episode_num."
        )

    return get_tmdb_media_metadata({
        "media_type": media_type,
        "tmdb_id": tmdb_id,
    })

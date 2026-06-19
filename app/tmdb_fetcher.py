import json
import requests

from app.config import require_env

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
        params=params or {"language": "en-US"},
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


# -----------------------------------------------------------------------

def find_tmdb_match_by_imdb_id(imdb_id):
    url = f"https://api.themoviedb.org/3/find/{imdb_id.strip()}"
    params = {
        "external_source": "imdb_id",
        "language": "en-US",
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
    episode_run_time = series_details.get("episode_run_time") or []
    runtime_min = _clean_runtime(episode_run_time[0]) if episode_run_time else None

    return {
        "tmdb_id": series_details["id"],
        "imdb_id": series_ids.get("imdb_id"),
        "media_type": "series",
        "title": series_details["name"],
        "original_title": series_details["original_name"],
        "production_status": series_details.get("status"),
        "release_date": _clean_date(series_details.get("first_air_date")),
        "runtime_min": runtime_min,

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


def get_tmdb_movie_watch_providers(tmdb_id, country_code="AT"):
    url_movie_watch_providers = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"
    response_movie_watch_providers = requests.get(url_movie_watch_providers, headers=headers)
    movie_watch_providers = json.loads(response_movie_watch_providers.text)

    return [
        {
            "provider_tmdb_id": provider["provider_id"],
            "provider_name": provider["provider_name"],
            "country_code": country_code,
        }
        for provider in (
            movie_watch_providers.get("results", {}).get(country_code, {}).get("flatrate", [])
        )
    ]

def get_tmdb_movie_posters(tmdb_id):
    url_movie_details = f"https://api.themoviedb.org/3/movie/{tmdb_id}?language=en-US"
    response_movie_details = requests.get(url_movie_details, headers=headers)
    movie_details = json.loads(response_movie_details.text)

    url_movie_images = f"https://api.themoviedb.org/3/movie/{tmdb_id}/images"
    response_movie_images = requests.get(url_movie_images, headers=headers)
    movie_images = json.loads(response_movie_images.text)

    return [
        {
            "file_name": poster["file_path"].removeprefix("/"),
            "source": "tmdb",
            "curation_status": "pending",
            "is_default": False
        }
        for poster in movie_images.get("posters", [])
        if poster.get("file_path")
           and poster.get("iso_639_1") in {"en", None, movie_details.get("original_language")}
           and 0.64 <= poster.get("aspect_ratio", 0) <= 0.72
           and poster.get("width", 0) >= 500
           and poster.get("height", 0) >= 750
    ]




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


#test_infos = get_tmdb_infos(194662, "movie")
#print(len(test_infos["poster_filenames"]))
#print(test_infos["poster_filenames"])
#print(test_infos)

#############################################

# def get_series_id(imdb_id):
#     url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
#     response = requests.get(url, headers=headers)
#     initial_data = json.loads(response.text)
#
#     return initial_data["tv_episode_results"][0]["show_id"]
#
# def get_watch_providers(media_type, tmdb_id, imdb_id):
#     if media_type == "series" or media_type == "episode":
#         if media_type == "episode":
#             tmdb_id = get_series_id(imdb_id)
#         media_type = "tv"
#     else:
#         media_type = "movie"
#
#     print(media_type, tmdb_id)
#
#     url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}/watch/providers"
#     response_watch_providers = requests.get(url, headers=headers)
#     watch_providers_data = json.loads(response_watch_providers.text)
#     print(watch_providers_data)
#
#     my_watch_providers = {"Amazon Prime Video", "Apple TV+", "Disney Plus", "Netflix"}
#     watch_providers_list = []
#     if "AT" in watch_providers_data["results"] and "flatrate" in watch_providers_data["results"]["AT"]:
#         watch_providers_list = [
#             provider["provider_name"]
#             for provider in watch_providers_data["results"]["AT"]["flatrate"]
#             if provider["provider_name"] in my_watch_providers
#         ]
#
#     watch_providers_text = ", ".join(watch_providers_list) if watch_providers_list else "Not in your streaming catalog."
#
#     return watch_providers_text
#
# def reset_tmdb_infos():
#     for key_field in tmdb_infos:
#         if key_field == "duration" or "watched_seasons":
#             tmdb_infos[key_field] = []
#         else:
#             tmdb_infos[key_field] = ""
#
# def get_tmdb_infos(imdb_id):
#     reset_tmdb_infos() #melhor criar um get_tmdb_infos() p retornar sempre um dict novo e não ficar reutilizando esse mesmo aqui?
#
#     url = f"https://api.themoviedb.org/3/find/{imdb_id}?external_source=imdb_id"
#     response = requests.get(url, headers=headers)
#     initial_data = json.loads(response.text)
#
#     if initial_data["movie_results"]: #tem q incluir de colocar os ids do tmdb tb!
#         load_tmdb_infos_with_movie_values(initial_data["movie_results"][0])
#     elif initial_data["tv_results"]:
#         load_tmdb_infos_with_series_values(initial_data["tv_results"][0])
#     elif initial_data["tv_episode_results"]:
#         load_tmdb_infos_with_episode_values(initial_data["tv_episode_results"][0])
#     else:
#         return None
#
#     return tmdb_infos
#
# def preload_poster_images(posters_to_download):
#     clear_folder_images_temp()
#
#     start_path = "https://image.tmdb.org/t/p/w780" # size options: w92, w154, w185, w342, w500, w780, original
#     for index, poster_path in enumerate(posters_to_download):
#         url = start_path + poster_path
#         try:
#             response = requests.get(url)
#             response.raise_for_status()
#
#             images_temp_path = os.path.join("images", "_images_temp")
#             file_name = format_filename(tmdb_infos["title"])
#             file_extension = os.path.splitext(poster_path)[1]
#             file_path = os.path.join(images_temp_path, f"temp_{file_name}{index}{file_extension}")
#             with open(file_path, "wb") as file:
#                 file.write(response.content)
#
#         except Exception as e:
#             print(f"Error downloading from {url}: {e}")
#
# #######################################################################################################################
# # movie:
# def load_tmdb_infos_with_movie_values(initial_data):
#     tmdb_id = initial_data["id"]
#     detailed_data, credits_data, posters_data = get_more_movie_data(tmdb_id)
#
#     # media type:
#     tmdb_infos["media_type"] = "movie"
#     # tmdb id:
#     tmdb_infos["tmdb_id"] = tmdb_id
#     # title:
#     tmdb_infos["title"] = initial_data["title"]
#     # year:
#     tmdb_infos["year"] = initial_data["release_date"][:4]
#     # duration:
#     tmdb_infos["duration"] = [[int(detailed_data["runtime"])]]
#     # genre:
#     genres_list = [genre["name"] for genre in detailed_data["genres"]]
#     tmdb_infos["genre"] = ", ".join(genres_list)
#     # director_creator:
#     director_creators_list = [credit["name"] for credit in credits_data["crew"] if credit["job"] == "Director"]
#     if len(director_creators_list) > 3:
#         tmdb_infos["director_creator"] = "various"
#     else:
#         tmdb_infos["director_creator"] = ", ".join(director_creators_list)
#     # cast:
#     cast_list = [credit["name"] for credit in credits_data["cast"]]
#     if len(cast_list) > 6:
#         cast_list = cast_list[:6]
#     tmdb_infos["cast"] = ", ".join(cast_list)
#
#     # posters download:
#     posters_to_download = [poster["file_path"] for poster in posters_data["posters"]]
#     threading.Thread(target=lambda: preload_poster_images(posters_to_download)).start()
#
# def get_more_movie_data(tmdb_id):
#     url_details = f"https://api.themoviedb.org/3/movie/{tmdb_id}?language=en-US"
#     response_details = requests.get(url_details, headers=headers)
#     detailed_data = json.loads(response_details.text)
#
#     url_credits = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?language=en-US"
#     response_credits = requests.get(url_credits, headers=headers)
#     credits_data = json.loads(response_credits.text)
#
#     original_language = detailed_data["original_language"]
#     url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/images?include_image_language=en%2C{original_language}"
#     response_posters = requests.get(url, headers=headers)
#     posters_data = json.loads(response_posters.text)
#
#     return detailed_data, credits_data, posters_data
#
# #######################################################################################################################
# # series:
# def load_tmdb_infos_with_series_values(initial_data):
#     tmdb_id = initial_data["id"]
#     detailed_data, seasons_data, credits_data, posters_data = get_more_series_data(tmdb_id)
#
#     # media type:
#     tmdb_infos["media_type"] = "series"
#     # tmdb id:
#     tmdb_infos["tmdb_id"] = tmdb_id
#     # title:
#     tmdb_infos["title"] = initial_data["name"]
#     # year:
#     first_air_date = detailed_data["first_air_date"][:4]
#     last_air_date = detailed_data["last_air_date"][:4]
#     print(f"first_air_date = {type(detailed_data['first_air_date'][:4])}")
#     if first_air_date != last_air_date:
#         text_for_year = f"{first_air_date}-{last_air_date}"
#     else:
#         text_for_year = f"{first_air_date}"
#     tmdb_infos["year"] = text_for_year
#     # duration:
#     durations = []
#     for season_index, season in enumerate(seasons_data):
#         if season["episodes"]:
#             durations.append([])
#             for episode in season["episodes"]:
#                 if episode["runtime"] is None:
#                     durations[season_index].append(0)
#                 else:
#                     durations[season_index].append(episode["runtime"])
#     tmdb_infos["duration"] = durations
#     # genre:
#     genres_list = [genre["name"] for genre in detailed_data["genres"]]
#     tmdb_infos["genre"] = ", ".join(genres_list)
#     # director_creator:
#     director_creators_list = [profile["name"] for profile in detailed_data["created_by"]]
#     if len(director_creators_list) > 3:
#         tmdb_infos["director_creator"] = "various"
#     else:
#         tmdb_infos["director_creator"] = ", ".join(director_creators_list)
#     # cast:
#     cast_list = [credit["name"] for credit in credits_data["cast"]]
#     if len(cast_list) > 6:
#         cast_list = cast_list[:6]
#     tmdb_infos["cast"] = ", ".join(cast_list)
#     # watched seasons:
#     for season in seasons_data:
#         if season["episodes"]:
#             tmdb_infos["watched_seasons"].append(False)
#
#     # posters download:
#     posters_to_download = [poster["file_path"] for poster in posters_data["posters"]]
#     threading.Thread(target=lambda: preload_poster_images(posters_to_download)).start()
#
# def get_more_series_data(tmdb_id):
#     url_details = f"https://api.themoviedb.org/3/tv/{tmdb_id}?language=en-US"
#     response_details = requests.get(url_details, headers=headers)
#     detailed_data = json.loads(response_details.text)
#
#     seasons_data = []
#     for i in range(detailed_data["number_of_seasons"]):
#         url_season = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{i+1}?language=en-US"
#         response_season = requests.get(url_season, headers=headers)
#         season_data = json.loads(response_season.text)
#         seasons_data.append(season_data)
#     print(seasons_data)
#
#     url_credits = f"https://api.themoviedb.org/3/tv/{tmdb_id}/credits?language=en-US"
#     response_credits = requests.get(url_credits, headers=headers)
#     credits_data = json.loads(response_credits.text)
#
#     original_language = detailed_data["original_language"]
#     url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/images?include_image_language=en%2C{original_language}"
#     response_posters = requests.get(url, headers=headers)
#     posters_data = json.loads(response_posters.text)
#
#     return detailed_data, seasons_data, credits_data, posters_data
#
# #######################################################################################################################
# # episode:
# def load_tmdb_infos_with_episode_values(initial_data):
#     tmdb_id = initial_data["id"]
#     show_id = initial_data["show_id"]
#     season_number = initial_data["season_number"]
#     episode_number = initial_data["episode_number"]
#     detailed_data, show_infos_data, credits_data, image_data = get_more_episode_data(tmdb_id, show_id, season_number, episode_number)
#
#     # media type:
#     tmdb_infos["media_type"] = "episode"
#     # tmdb id:
#     tmdb_infos["tmdb_id"] = tmdb_id
#     # title:
#     episode_title = initial_data["name"]
#     show_name = show_infos_data["name"]
#     tmdb_infos["title"] = f"{show_name} – S{str(season_number).zfill(2)}E{str(episode_number).zfill(2)}: {episode_title}"
#     # year:
#     tmdb_infos["year"] = initial_data["air_date"][:4]
#     # duration:
#     tmdb_infos["duration"] = [[int(detailed_data["runtime"])]]
#     # genre:
#     genres_list = [genre["name"] for genre in show_infos_data["genres"]]
#     tmdb_infos["genre"] = ", ".join(genres_list)
#     # director_creator:
#     director_creators_list = [credit["name"] for credit in credits_data["crew"] if credit["job"] == "Director"]
#     if len(director_creators_list) > 3:
#         tmdb_infos["director_creator"] = "various"
#     else:
#         tmdb_infos["director_creator"] = ", ".join(director_creators_list)
#     # cast:
#     cast_list = [credit["name"] for credit in credits_data["guest_stars"] if credit["known_for_department"] == "Acting"]
#     if len(cast_list) > 6:
#         cast_list = cast_list[:6]
#     tmdb_infos["cast"] = ", ".join(cast_list)
#
#     # images download:
#     images_to_download = [image["file_path"] for image in image_data["stills"]]
#     threading.Thread(target=lambda: preload_poster_images(images_to_download)).start()
#
# def get_more_episode_data(tmdb_id, show_id, season_number, episode_number):
#     url_details = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season_number}/episode/{episode_number}?language=en-US"
#     response_details = requests.get(url_details, headers=headers)
#     detailed_data = json.loads(response_details.text)
#
#     url_show_infos = f"https://api.themoviedb.org/3/tv/{show_id}?language=en-US"
#     response_show_infos = requests.get(url_show_infos, headers=headers)
#     show_infos_data = json.loads(response_show_infos.text)
#
#     url_credits = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season_number}/episode/{episode_number}/credits?language=en-US"
#     response_credits = requests.get(url_credits, headers=headers)
#     credits_data = json.loads(response_credits.text)
#
#     #original_language = detailed_data["original_language"] #só tem stills em geral e null na language...
#     url_images = f"https://api.themoviedb.org/3/tv/{show_id}/season/{season_number}/episode/{episode_number}/images"
#     response_images = requests.get(url_images, headers=headers)
#     image_data = json.loads(response_images.text)
#
#     return detailed_data, show_infos_data, credits_data, image_data

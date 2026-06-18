import json
import os
import requests
import threading

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

# SEARCH -----------------------------------------------------------------------
def search_movie_candidates(search_title, max_candidates=10):
    url = "https://api.themoviedb.org/3/search/movie"

    params = {
        "query": search_title,
        "include_adult": "false",
        "language": "en-US",
        "page": 1,
    }

    response = requests.get(url, headers=headers, params=params, timeout=15)
    response.raise_for_status()

    data = response.json()

    candidates = []

    for result in data.get("results", [])[:max_candidates]:
        candidate = {
            "tmdb_id": result.get("id"),
            "title": result.get("title"),
            "original_title": result.get("original_title"),
            "release_date": result.get("release_date"),
            "genres": _get_genre_names(genre_codes=result.get("genre_ids", [])),
            "overview": result.get("overview"),
        }

        candidates.append(candidate)

    return candidates

# def search_media_candidates(media_intent):
#     media_type = media_intent.get("media_type")
#
#     if media_type is None:
#         return None
#
#     search_title = ((media_intent.get(media_type) or {}).get("title") or {}).get("search")
#
#     if media_type == "movie" and search_title is not None:
#         return _search_movie_candidates(search_title)
#
#     elif media_type == "series" and search_title is not None:
#         return _search_series_candidates(search_title)
#
#     elif media_type == "episode":
#         series_title = ((media_intent.get("series") or {}).get("title") or {}).get("search")
#         if series_title is None:
#             return None
#         else:
#             return _search_episode_candidates(series_title)
#
#     else:
#         return None
#
# def _search_movie_candidates(search_title):
#     url = "https://api.themoviedb.org/3/search/movie"
#     params = {
#         "query": search_title,
#         "include_adult": "false",
#         "language": "en-US",
#         "page": 1,
#     }
#     response = requests.get(url, headers=headers, params=params)
#     data = response.json()
#     return data["results"]
#
# def _search_series_candidates(search_title):
#     return []
#
# def _search_episode_candidates(search_title):
#     return []

# -----------------------------------------------------------------------

def get_tmdb_movie_metadata(tmdb_id):
    url_movie_details = f"https://api.themoviedb.org/3/movie/{tmdb_id}?language=en-US"
    response_movie_details = requests.get(url_movie_details, headers=headers)
    movie_details = json.loads(response_movie_details.text)

    url_movie_credits = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?language=en-US"
    response_movie_credits = requests.get(url_movie_credits, headers=headers)
    movie_credits = json.loads(response_movie_credits.text)

    return {
        "tmdb_id": movie_details["id"],
        "imdb_id": movie_details.get("imdb_id"),
        "media_type": "movie",
        "title": movie_details["title"],
        "original_title": movie_details["original_title"],
        "production_status": movie_details.get("status"),
        "release_date": movie_details.get("release_date"),
        "runtime_min": movie_details.get("runtime"),
        "genres": [
            genre["id"]
            for genre in movie_details["genres"]
        ],

        "spoken_languages": [
            spoken_language["iso_639_1"]
            for spoken_language in movie_details["spoken_languages"]
        ],
        "origin_language": movie_details["original_language"],
        "production_countries": [
            production_country["iso_3166_1"]
            for production_country in movie_details["production_countries"]
        ],
        "production_companies": [
            {
                "company_tmdb_id": production_company["id"],
                "name": production_company["name"]
            }
            for production_company in movie_details["production_companies"]
        ],
        "directors": [
            {
                "people_tmdb_id": crew["id"],
                "name": crew["name"],
            }
            for crew in movie_credits.get("crew", [])
            if crew.get("job") == "Director"
        ],
        "writers": [
            {
                "people_tmdb_id": crew["id"],
                "name": crew["name"],
                "job": crew["job"],
            }
            for crew in movie_credits.get("crew", [])
            if crew.get("job") in ["Writer", "Screenplay", "Teleplay", "Story"]
        ],
        "actors": [
            {
                "people_tmdb_id": cast["id"],
                "name":  cast["name"],
                "character": cast.get("character"),
                "cast_order": cast.get("order")
            }
            for cast in movie_credits.get("cast", [])
        ],
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




#def get_tmdb_metadata(tmdb_id, media_type):
#    pass

#def get_tmdb_watch_providers(tmdb_id, media_type):
#    pass

#def get_tmdb_posters(tmdb_id, media_type):
#    pass

def get_tmdb_infos(tmdb_id, media_type): #melhor get_tmdb_metadata(tmdb_id, media_type) e separar a parte dos posters? tb o watch_providers separado p eventualmente tb deixar atualizar dentro do movie card?
    if media_type == "movie":
        url_movie_details = f"https://api.themoviedb.org/3/movie/{tmdb_id}?language=en-US"
        response_movie_details = requests.get(url_movie_details, headers=headers)
        movie_details = json.loads(response_movie_details.text)

        url_movie_images = f"https://api.themoviedb.org/3/movie/{tmdb_id}/images"
        response_movie_images = requests.get(url_movie_images, headers=headers)
        movie_images = json.loads(response_movie_images.text)

        url_movie_watch_providers = f"https://api.themoviedb.org/3/movie/{tmdb_id}/watch/providers"
        response_movie_watch_providers = requests.get(url_movie_watch_providers, headers=headers)
        movie_watch_providers = json.loads(response_movie_watch_providers.text)

        url_movie_credits = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?language=en-US"
        response_movie_credits = requests.get(url_movie_credits, headers=headers)
        movie_credits = json.loads(response_movie_credits.text)

        return get_tmdb_movie_metadata(movie_details, movie_images, movie_watch_providers, movie_credits)

    elif media_type == "series":
        url_series_details = f"https://api.themoviedb.org/3/tv/{tmdb_id}?language=en-US"
        response_series_details = requests.get(url_series_details, headers=headers)
        series_details = json.loads(response_series_details.text)

        url_series_ids = f"https://api.themoviedb.org/3/tv/{tmdb_id}/external_ids"
        response_series_ids = requests.get(url_series_ids, headers=headers)
        series_ids = json.loads(response_series_ids.text)

        #f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/3/images"
        #f"https://api.themoviedb.org/3/tv/{tmdb_id}/images"
        #f"https://api.themoviedb.org/3/movie/{tmdb_id}/images"
        url_series_images = f"https://api.themoviedb.org/3/tv/{tmdb_id}/images"
        response_series_images = requests.get(url_series_images, headers=headers)
        series_images = json.loads(response_series_images.text)

        url_series_watch_providers = f"https://api.themoviedb.org/3/tv/{tmdb_id}/watch/providers"
        response_series_watch_providers = requests.get(url_series_watch_providers, headers=headers)
        series_watch_providers = json.loads(response_series_watch_providers.text)

        url_series_credits = f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits?language=en-US"
        response_series_credits = requests.get(url_series_credits, headers=headers)
        series_credits = json.loads(response_series_credits.text)

        return get_tmdb_movie_metadata(series_details, series_ids, series_images, series_watch_providers, series_credits)

    elif media_type == "episode":
        return None
    else:
        return "type not found"



def get_tmdb_series_infos(series_details, series_ids, series_images, series_watch_providers, series_credits):
    return {
        "tmdb_id": series_details["id"],
        "imdb_id": series_ids.get("imdb_id"),
        "media_type": "series",
        "title": series_details["name"],
        "original_title": series_details["original_name"],
        "first_air_date": series_details.get("first_air_date") or None,
        "last_air_date": series_details.get("last_air_date") or None,
        "season_count": series_details.get("number_of_seasons") or None,
        "episode_count": series_details.get("number_of_episodes") or None,
        "genres": [
            genre["id"]
            for genre in series_details["genres"]
        ],
        "poster_filenames": [
            poster["file_path"].removeprefix("/")
            for poster in series_images.get("posters", [])
            if poster.get("file_path")
                and poster.get("iso_639_1") in {"en", None, series_details.get("original_language")}
                and 0.64 <= poster.get("aspect_ratio", 0) <= 0.72
                and poster.get("width", 0) >= 500
                and poster.get("height", 0) >= 750
        ],
        "streaming_providers": [
            {
                "provider_tmdb_id": provider["provider_id"],
                "provider_name": provider["provider_name"],
                "country_code": "AT",
            }
            for provider in (
                series_watch_providers.get("results", {}).get("AT", {}).get("flatrate", [])
            )
        ],
        "spoken_languages": [
            spoken_language["iso_639_1"]
            for spoken_language in series_details["spoken_languages"]
        ],
        "production_countries": [
            production_country["iso_3166_1"]
            for production_country in series_details["production_countries"]
        ],
        "production_companies": [
            {
                "company_tmdb_id": production_company["id"],
                "name": production_company["name"]
            }
            for production_company in series_details["production_companies"]
        ],
        "creators": [
            {
                "people_tmdb_id": creator["id"],
                "name": creator["name"],
            }
            for creator in series_details["created_by"]
        ],
    }


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

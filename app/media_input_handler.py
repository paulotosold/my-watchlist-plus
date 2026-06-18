import re
from PySide6.QtWidgets import QMessageBox

import app.media_repository as media_repo
from app.imdb_id_resolver import resolve_imdb_id_from_query
import app.tmdb_fetcher
import app.media_draft_builder
from app.media_draft_builder import build_media_drafts
from app.media_details_dialog import open_media_details_dialog
from db.connection import get_connection
from app.media_draft_builder import build_media_draft_from_db, build_media_draft_from_tmdb

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

def handle_media_input(parent, input_query):
    if re.fullmatch(r"tt\d{7,10}", input_query.strip()):
        imdb_id = input_query.strip()

    else:
        if not confirm_llm_cost(parent):
            return

        result = resolve_imdb_id_from_query(input_query)
        print(result)

        if result["status"] != "resolved":
            # depois você pode trocar isso por outra janelinha
            print(result["followup_question"] or result["reason"])
            return

        imdb_id = result["imdb_id"]

    print("imdb_id:")
    print(imdb_id)

    with get_connection() as conn:
        media_from_db = media_repo.get_media_by_imdb_id(conn, imdb_id)

        if media_from_db:
            media_draft = build_media_draft_from_db(conn, media_from_db)

        else:
            media_draft = build_media_draft_from_tmdb(imdb_id)

    open_media_details_dialog(parent, media_draft, input_query=input_query)






    #input do usuário
    #é um imdb id? pula o llm call
    #não é um imdb id? faz um llm call com web search p descobrir o imdb id
    #o imdb id está no db? pega as infos do db
    #o imdb id não está no db? pega as infos da api do tmdb
    #carrega a página de edit




    #media_drafts = build_media_drafts(matches_by_intent)
    #print("media_drafts:")
    #print(media_drafts)

    #confirmed_drafts = open_media_details_dialog(parent, media_drafts)
    #print("confirmed_drafts:")
    #print(confirmed_drafts)

    #medias = []
    #for match_result in candidate_match_results:
        #media_infos = get_media_infos_from_db(match_result["tmdb_id"])
        #if media_infos is None:
        #    media_infos = tmdb_fetcher.get_media_infos(match_result["tmdb_id"])

        #media_infos = tmdb_fetcher.get_tmdb_infos(match_result["tmdb_id"], "movie")
        #medias.append(media_infos)


    #open_media_details_dialog(input_query, extracted_intents, medias)


    #final_medias = []
    #for tmdb_candidate in media_candidates:
    #    best_candidate = #call llm p resolver o melhor candidate baseado na busca e no input do user
    #    final_medias.append(best_candidate)

    #for final_media in final_medias:
    #    if final_media is not resolved:
    #        show alert_with_hints(final_medias)
    #    else:
    #        show edit window_with_tabs(final_medias)


#handle_media_input("tt1832355 – adicione esse título aqui do imdb p a minha watchlist")
#handle_media_input("fiz uma maratona e assisti ontem os filmes I, II e III do star wars ontem com o benji e muita pipoca!")
#handle_media_input(None, "assisti ontem o filme dos goonies e o primeiro filme do predador")
#handle_media_input("assisti o filme dos goonies um dia lá trás nos anos 90... me marcou muito. fico pensando o q o benji iria achar... será q envelheceu bem?")
#handle_media_input("assisti o episódio nosedive do black mirror na semana passada.")
#handle_media_input("watched the movie hail mary project yesterday in the theater. great movie!")
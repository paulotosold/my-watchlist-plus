import os
from contextlib import nullcontext
import unittest
from unittest.mock import MagicMock, call, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

import app.media_lookup as media_lookup


class MediaLookupRoutingTests(unittest.TestCase):
    def test_empty_input_warns_before_any_lookup(self):
        with patch.object(
            media_lookup.QMessageBox,
            "warning",
        ) as warning, patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
        ) as deterministic_lookup, patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(None, "   ")

        self.assertIsNone(result)
        self.assertIn("title", warning.call_args.args[2])
        deterministic_lookup.assert_not_called()
        llm_lookup.assert_not_called()

    def test_imdb_id_bypasses_title_search(self):
        draft = {"media_id": 1}

        with patch.object(
            media_lookup,
            "resolve_media_draft_from_imdb_id",
            return_value=draft,
        ) as imdb_lookup, patch.object(
            media_lookup,
            "search_tmdb_title_candidates",
        ) as tmdb_lookup:
            outcome = media_lookup.resolve_media_query_without_llm(
                None,
                " tt1234567 ",
            )

        self.assertEqual(
            outcome,
            {"status": "resolved", "media_draft": draft},
        )
        imdb_lookup.assert_called_once_with("tt1234567")
        tmdb_lookup.assert_not_called()

    def test_non_imdb_input_returns_all_organic_tmdb_results(self):
        candidates = [
            self._candidate(30, "movie"),
            self._candidate(10, "movie"),
            self._candidate(20, "series"),
        ]

        with patch.object(
            media_lookup,
            "search_tmdb_title_candidates",
            return_value=candidates,
        ) as tmdb_lookup:
            outcome = media_lookup.resolve_media_query_without_llm(
                None,
                "Star Wars: Test",
            )

        self.assertEqual(
            outcome,
            {"status": "matches", "matches": candidates},
        )
        tmdb_lookup.assert_called_once_with("Star Wars: Test")

    def test_no_tmdb_results_returns_no_match(self):
        with patch.object(
            media_lookup,
            "search_tmdb_title_candidates",
            return_value=[],
        ) as tmdb_lookup:
            outcome = media_lookup.resolve_media_query_without_llm(
                None,
                "unknown title",
            )

        self.assertEqual(outcome, {"status": "no_match"})
        tmdb_lookup.assert_called_once_with("unknown title")

    def test_zero_tmdb_results_falls_back_to_llm(self):
        draft = {"media_id": None, "metadata": {"title": "Resolved"}}

        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            return_value={"status": "no_match"},
        ), patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
            return_value=draft,
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(
                None,
                "a vague description",
            )

        self.assertIs(result, draft)
        llm_lookup.assert_called_once_with(None, "a vague description")

    def test_llm_result_reuses_the_imdb_workflow(self):
        draft = {"media_id": None}
        resolution = {
            "status": "resolved",
            "imdb_id": "tt1234567",
            "followup_question": None,
            "reason": "resolved",
        }

        with patch.object(
            media_lookup,
            "confirm_llm_cost",
            return_value=True,
        ), patch.object(
            media_lookup,
            "resolve_imdb_id_from_query",
            return_value=resolution,
        ) as llm_resolver, patch.object(
            media_lookup,
            "resolve_media_draft_from_imdb_id",
            return_value=draft,
        ) as imdb_lookup:
            result = media_lookup.resolve_media_draft_with_llm(
                None,
                "the one with the fox",
            )

        self.assertIs(result, draft)
        llm_resolver.assert_called_once_with("the one with the fox")
        imdb_lookup.assert_called_once_with("tt1234567")

    def test_one_title_match_builds_only_that_candidate(self):
        candidate = self._candidate(10, "movie")
        draft = {"media_id": None}

        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            return_value={"status": "matches", "matches": [candidate]},
        ), patch.object(
            media_lookup,
            "build_media_draft_from_candidate",
            return_value=draft,
        ) as build_draft, patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(
                None,
                "Robin Hood",
            )

        self.assertIs(result, draft)
        build_draft.assert_called_once_with(candidate)
        llm_lookup.assert_not_called()

    def test_multiple_matches_open_selection_and_build_selected_candidate(self):
        first = self._candidate(10, "movie")
        selected = self._candidate(20, "series")
        draft = {"media_id": None}
        dialog = MagicMock()
        dialog.result_payload = {
            "status": "selected",
            "candidate": selected,
        }

        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            return_value={"status": "matches", "matches": [first, selected]},
        ), patch.object(
            media_lookup,
            "MatchSelectionDialog",
            return_value=dialog,
        ) as dialog_class, patch.object(
            media_lookup,
            "build_media_draft_from_candidate",
            return_value=draft,
        ) as build_draft, patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(
                "parent",
                "Robin Hood",
            )

        self.assertIs(result, draft)
        dialog_class.assert_called_once()
        self.assertEqual(dialog_class.call_args.kwargs["query"], "Robin Hood")
        self.assertEqual(
            dialog_class.call_args.kwargs["candidates"],
            [first, selected],
        )
        self.assertNotIn("lookup_callback", dialog_class.call_args.kwargs)
        dialog.exec.assert_called_once_with()
        build_draft.assert_called_once_with(selected)
        llm_lookup.assert_not_called()

    def test_restart_reruns_full_pipeline_with_refined_query(self):
        matches = [
            self._candidate(10, "movie"),
            self._candidate(20, "series"),
        ]
        refined_candidate = self._candidate(30, "movie")
        draft = {"media_id": None}
        dialog = MagicMock()
        dialog.result_payload = {
            "status": "restart",
            "query": "Refined Title",
        }

        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            side_effect=[
                {"status": "matches", "matches": matches},
                {"status": "matches", "matches": [refined_candidate]},
            ],
        ) as deterministic_lookup, patch.object(
            media_lookup,
            "build_media_draft_from_candidate",
            return_value=draft,
        ) as build_draft, patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup, patch.object(
            media_lookup,
            "MatchSelectionDialog",
            return_value=dialog,
        ):
            result = media_lookup.resolve_media_draft_from_query(
                None,
                "Robin Hood",
            )

        self.assertIs(result, draft)
        self.assertEqual(
            deterministic_lookup.call_args_list,
            [
                call(None, "Robin Hood"),
                call(None, "Refined Title"),
            ],
        )
        build_draft.assert_called_once_with(refined_candidate)
        llm_lookup.assert_not_called()

    def test_restarted_no_match_uses_refined_query_for_llm(self):
        matches = [
            self._candidate(10, "movie"),
            self._candidate(20, "series"),
        ]
        draft = {"media_id": None}
        dialog = MagicMock()
        dialog.result_payload = {
            "status": "restart",
            "query": "the one with the fox",
        }

        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            side_effect=[
                {"status": "matches", "matches": matches},
                {"status": "no_match"},
            ],
        ), patch.object(
            media_lookup,
            "MatchSelectionDialog",
            return_value=dialog,
        ), patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
            return_value=draft,
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(
                None,
                "Robin Hood",
            )

        self.assertIs(result, draft)
        llm_lookup.assert_called_once_with(None, "the one with the fox")

    def test_tmdb_failure_stops_before_llm(self):
        with patch.object(
            media_lookup,
            "search_tmdb_title_candidates",
            side_effect=RuntimeError("offline"),
        ), patch.object(
            media_lookup.QMessageBox,
            "warning",
        ) as warning, patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup:
            outcome = media_lookup.resolve_media_query_without_llm(
                None,
                "Robin Hood",
            )

        self.assertEqual(outcome["status"], "error")
        self.assertTrue(outcome["message_shown"])
        self.assertIn("offline", warning.call_args.args[2])
        llm_lookup.assert_not_called()

    def test_technical_error_outcome_never_falls_back_to_llm(self):
        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            return_value={"status": "error"},
        ), patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(
                None,
                "Robin Hood",
            )

        self.assertIsNone(result)
        llm_lookup.assert_not_called()

    def test_local_candidate_builds_by_media_id(self):
        candidate = self._candidate(
            10,
            "movie",
            source="db",
            media_id=4,
        )
        media_row = {"id": 4, "tmdb_id": 10, "media_type": "movie"}
        draft = {"media_id": 4}
        connection = object()

        with patch.object(
            media_lookup,
            "get_connection",
            side_effect=lambda: nullcontext(connection),
        ), patch.object(
            media_lookup.media_repo,
            "get_media_by_id",
            return_value=media_row,
        ) as get_by_id, patch.object(
            media_lookup.media_repo,
            "get_media_by_tmdb_id",
        ) as get_by_tmdb, patch.object(
            media_lookup,
            "build_media_draft_from_db",
            return_value=draft,
        ) as build_db:
            result = media_lookup.build_media_draft_from_candidate(candidate)

        self.assertIs(result, draft)
        get_by_id.assert_called_once_with(connection, 4)
        get_by_tmdb.assert_not_called()
        build_db.assert_called_once_with(connection, media_row)

    def test_remote_candidate_rechecks_db_before_tmdb_draft(self):
        candidate = self._candidate(10, "series")
        media_row = {"id": 4, "tmdb_id": 10, "media_type": "series"}
        draft = {"media_id": 4}
        connection = object()

        with patch.object(
            media_lookup,
            "get_connection",
            side_effect=lambda: nullcontext(connection),
        ), patch.object(
            media_lookup.media_repo,
            "get_media_by_tmdb_id",
            return_value=media_row,
        ) as get_by_tmdb, patch.object(
            media_lookup,
            "build_media_draft_from_db",
            return_value=draft,
        ) as build_db, patch.object(
            media_lookup,
            "build_media_draft_from_tmdb_match",
        ) as build_tmdb:
            result = media_lookup.build_media_draft_from_candidate(candidate)

        self.assertIs(result, draft)
        get_by_tmdb.assert_called_once_with(connection, 10, "series")
        build_db.assert_called_once_with(connection, media_row)
        build_tmdb.assert_not_called()

    def test_remote_candidate_builds_from_tmdb_when_still_unsaved(self):
        candidate = self._candidate(10, "movie")
        draft = {"media_id": None}
        connection = object()

        with patch.object(
            media_lookup,
            "get_connection",
            side_effect=lambda: nullcontext(connection),
        ), patch.object(
            media_lookup.media_repo,
            "get_media_by_tmdb_id",
            return_value=None,
        ), patch.object(
            media_lookup,
            "build_media_draft_from_tmdb_match",
            return_value=draft,
        ) as build_tmdb:
            result = media_lookup.build_media_draft_from_candidate(candidate)

        self.assertIs(result, draft)
        build_tmdb.assert_called_once_with({
            "media_type": "movie",
            "tmdb_id": 10,
        })

    def test_selected_candidate_load_failure_does_not_call_llm(self):
        candidate = self._candidate(10, "movie")

        with patch.object(
            media_lookup,
            "resolve_media_query_without_llm",
            return_value={"status": "matches", "matches": [candidate]},
        ), patch.object(
            media_lookup,
            "build_media_draft_from_candidate",
            side_effect=RuntimeError("metadata unavailable"),
        ), patch.object(
            media_lookup.QMessageBox,
            "warning",
        ) as warning, patch.object(
            media_lookup,
            "resolve_media_draft_with_llm",
        ) as llm_lookup:
            result = media_lookup.resolve_media_draft_from_query(
                None,
                "Robin Hood",
            )

        self.assertIsNone(result)
        self.assertIn("metadata unavailable", warning.call_args.args[2])
        llm_lookup.assert_not_called()

    @staticmethod
    def _candidate(
        tmdb_id,
        media_type,
        *,
        source="tmdb",
        media_id=None,
    ):
        return {
            "source": source,
            "media_id": media_id,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "imdb_id": None,
            "title": "Robin Hood",
            "original_title": "Robin Hood",
            "release_date": "2025-01-01",
            "poster_path": None,
        }


if __name__ == "__main__":
    unittest.main()

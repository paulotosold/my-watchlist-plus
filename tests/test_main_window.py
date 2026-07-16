import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TMDB_READ_ACCESS_TOKEN", "test-token")
os.environ.setdefault("OPENAI_API_KEY", "test-key")

from app.library_filter import DEFAULT_FILTER_TEXT
from app.main_window import MainWindow


class MainWindowInputTests(unittest.TestCase):
    def test_exact_default_filter_replaces_and_refreshes_filtered_media(self):
        replacement = object()
        harness = SimpleNamespace(
            filtered_media=object(),
            refresh_media_view=Mock(),
        )

        with patch(
            "app.main_window.FilteredMedia",
            return_value=replacement,
        ) as filtered_media_factory, patch("builtins.print") as print_mock:
            MainWindow.on_filter_input(harness, DEFAULT_FILTER_TEXT)

        filtered_media_factory.assert_called_once_with()
        print_mock.assert_not_called()
        self.assertIs(harness.filtered_media, replacement)
        harness.refresh_media_view.assert_called_once_with()

    def test_any_other_filter_text_is_only_printed(self):
        for filter_text in (
            "",
            DEFAULT_FILTER_TEXT.lower(),
            f" {DEFAULT_FILTER_TEXT}",
            f"{DEFAULT_FILTER_TEXT} ",
            "movies directed by Jane Campion",
        ):
            with self.subTest(filter_text=filter_text):
                current_filtered_media = object()
                harness = SimpleNamespace(
                    filtered_media=current_filtered_media,
                    refresh_media_view=Mock(),
                )

                with (
                    patch("app.main_window.FilteredMedia") as factory,
                    patch("builtins.print") as print_mock,
                ):
                    MainWindow.on_filter_input(harness, filter_text)

                print_mock.assert_called_once_with(
                    "Filter Library:",
                    filter_text,
                )
                factory.assert_not_called()
                self.assertIs(harness.filtered_media, current_filtered_media)
                harness.refresh_media_view.assert_not_called()

    def test_find_media_refreshes_only_after_saved_or_deleted(self):
        for status, should_refresh in (
            ("saved", True),
            ("deleted", True),
            ("cancelled", False),
        ):
            with self.subTest(status=status):
                harness = SimpleNamespace(refresh_media_view=Mock())

                with patch(
                    "app.main_window.handle_find_media_input",
                    return_value={"status": status},
                ) as handler:
                    MainWindow.on_find_media_input(harness, "tt1234567")

                handler.assert_called_once_with(harness, "tt1234567")

                if should_refresh:
                    harness.refresh_media_view.assert_called_once_with()
                else:
                    harness.refresh_media_view.assert_not_called()


if __name__ == "__main__":
    unittest.main()

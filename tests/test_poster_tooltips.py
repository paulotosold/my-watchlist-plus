import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyle, QToolTip, QWidget

from app.cabinet.card import CabinetCard
from app.watchlist.card import MediaCard
from app.history.grid import HistoryPosterImage
from test_history_grid import make_entry


class PosterTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def test_both_card_types_format_refresh_and_clear_tooltips(self):
        cases = [
            ({"media_type": "movie", "title": "Movie", "release_date": "2023-01-01"}, None, "Movie (2023)"),
            ({"media_type": "movie", "title": "Movie", "release_date": "invalid"}, None, "Movie"),
            ({"media_type": "series", "title": "Series", "release_date": "2020-01-01"},
             {"summary": {"first_air_date": "2021-01-01", "last_air_date": "2030-01-01"}}, "Series (2021-2030)"),
            ({"media_type": "series", "title": "Series", "release_date": "2021-01-01"}, None, "Series (2021)"),
            ({"media_type": "series", "title": "Series"}, {"summary": None}, "Series"),
            ({"media_type": "series", "title": "Series"},
             {"summary": {"first_air_date": "2021-01-01", "last_air_date": "2021-12-01"}}, "Series (2021)"),
            ({"media_type": "episode", "title": "Pilot", "release_date": "2022-01-01",
              "episode_details": {"series_title": "Series", "season_num": 0, "episode_num": 1}},
             None, "Series S0E1: Pilot (2022)"),
            ({"media_type": "episode", "title": None,
              "episode_details": {"series_title": "Series"}}, None, "Series: Untitled episode"),
        ]
        for card_class in (CabinetCard, MediaCard):
            card = card_class()
            try:
                for metadata, series_view, expected in cases:
                    with self.subTest(card=card_class.__name__, expected=expected):
                        card.init_card_session(None, {
                            "media_id": 1, "metadata": metadata, "series_view": series_view,
                        })
                        self.assertEqual(card.toolTip(), expected)
                card.clear_card()
                self.assertEqual(card.toolTip(), "")
                card.init_card_session(None)
                self.assertEqual(card.toolTip(), "")
            finally:
                card.close()
                card.deleteLater()

    def test_every_poster_waits_two_seconds_including_after_visible_tooltip(self):
        window = QWidget()
        window.resize(800, 350)
        window.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips)
        cards = []
        for index, cls in enumerate((CabinetCard, MediaCard, HistoryPosterImage)):
            if cls is HistoryPosterImage:
                card = cls(make_entry(index + 1, title="History tooltip"), window)
            else:
                card = cls(window)
                card.init_card_session(None, {"media_id": index + 1, "metadata": {"title": cls.__name__}})
            card.setFixedSize(160, 240)
            card.move(20 + index * 240, 20)
            cards.append(card)
        window.show()
        window.activateWindow()
        self.application.processEvents()
        try:
            for card in cards:
                surfaces = [card, *card.findChildren(QWidget)]
                for surface in surfaces:
                    self.assertEqual(surface.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay, None, surface), 2000)
                    self.assertEqual(surface.style().styleHint(QStyle.StyleHint.SH_ToolTip_FallAsleepDelay, None, surface), 0)
                QTest.mouseMove(card, QPoint(80, 120))
                QTest.qWait(1700)
                self.assertNotEqual(QToolTip.text(), card.toolTip())
                QTest.qWait(450)
                self.assertEqual(QToolTip.text(), card.toolTip())
                self.assertTrue(QToolTip.isVisible())
        finally:
            QToolTip.hideText()
            window.close()
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()

import unittest
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from app.media_user_data.watch_history import current_draft_timestamp, validate_watch_dates
from app.media_user_data.watch_history_formatters import (
    build_watch_history_display_entries,
    estimate_watch_history_sort_date,
    format_watch_history_entry,
    resolve_watch_interval,
    sort_watch_history_entries,
    watch_history_sort_key,
)


class WatchHistoryTemporalTests(unittest.TestCase):
    def test_boundary_sources_anchors_and_labels(self):
        cases = [
            ("2026-08-03", "2026-08-20", "date_earliest", "date_latest", 11.5, 2, "Aug 2026"),
            ("2026-08-03", None, "date_earliest", "created_at", 3, 1, "~Aug 2026"),
            (None, "2026-08-20", "release_date", "date_latest", 10.5, 1, "~Aug 2026"),
            (None, None, "release_date", "created_at", 1, 0, "~Aug 2026"),
            ("2026-08-20", "2026-08-20", "date_earliest", "date_latest", 20, 3, "20 Aug 2026, Thu"),
        ]
        for earliest, latest, source_a, source_b, day, specificity, label in cases:
            with self.subTest(earliest=earliest, latest=latest):
                event = dict(date_earliest=earliest, date_latest=latest, created_at="2026-08-20 23:59:59")
                interval = resolve_watch_interval(event, "2026-08-01")
                self.assertEqual((interval.earliest_source, interval.latest_source), (source_a, source_b))
                self.assertEqual(interval.anchor, date(2026, 8, 1).toordinal() + day - 1)
                self.assertEqual(interval.specificity, specificity)
                self.assertEqual(interval.label, label)
                self.assertEqual(format_watch_history_entry(event, "2026-08-01"), label)
                self.assertEqual(estimate_watch_history_sort_date(event, "2026-08-01"),
                                 (interval.anchor, specificity))
                with self.assertRaises(FrozenInstanceError):
                    interval.earliest = date.today()

    def test_created_at_changes_label_but_not_lower_bound_anchor(self):
        for earliest in (None, "2024-01-01"):
            event = dict(date_earliest=earliest, created_at="2025-01-01")
            first = resolve_watch_interval(event, "2001-10-11")
            later = resolve_watch_interval({**event, "created_at": "2026-08-16"}, "2001-10-11")
            self.assertEqual(first.anchor, later.anchor)
            self.assertNotEqual(first.label, later.label)
        self.assertEqual(later.label, "~2024-2026")

    def test_equal_boundaries_keep_original_specificity_and_approximation(self):
        for earliest, latest, specificity in [("2026-08-20", "2026-08-20", 3),
                                              ("2026-08-20", None, 1),
                                              (None, "2026-08-20", 1), (None, None, 0)]:
            with self.subTest(earliest=earliest, latest=latest):
                interval = resolve_watch_interval(
                    dict(date_earliest=earliest, date_latest=latest, created_at="2026-08-20"),
                    "2026-08-20",
                )
                self.assertEqual(interval.anchor, date(2026, 8, 20).toordinal())
                self.assertEqual(interval.specificity, specificity)
                self.assertEqual(interval.label, ("" if specificity == 3 else "~") + "20 Aug 2026, Thu")

    def test_missing_and_contradictory_boundaries_collapse_without_extra_specificity(self):
        cases = [
            ({"date_earliest": "2026-08-20"}, None, "date_earliest", 1),
            ({"date_earliest": "2026-08-20", "created_at": "2020-01-01"}, None, "date_earliest", 1),
            ({"date_latest": "2026-08-20", "created_at": "2030-01-01"}, None, "date_latest", 1),
            ({"date_latest": "2026-08-20"}, "2030-01-01", "date_latest", 1),
            ({"created_at": "2026-08-20"}, None, "created_at", 0),
            ({}, "2026-08-20", "release_date", 0),
            ({"created_at": "2020-01-01"}, "2026-08-20", "release_date", 0),
            ({"created_at": "invalid"}, "2026-08-20", "release_date", 0),
            ({"created_at": "2026-08-20"}, "invalid", "created_at", 0),
        ]
        for event, release, source, specificity in cases:
            with self.subTest(event=event, release=release):
                interval = resolve_watch_interval(event, release)
                self.assertEqual(interval.earliest, date(2026, 8, 20))
                self.assertEqual(interval.latest, interval.earliest)
                self.assertEqual((interval.earliest_source, interval.latest_source), (source, source))
                self.assertEqual(interval.specificity, specificity)
                self.assertEqual(interval.label, "~20 Aug 2026, Thu")

    def test_unknown_dates_sort_last_stably(self):
        unknown = resolve_watch_interval({"created_at": "invalid"}, "invalid")
        self.assertEqual(unknown.label, "~unknown date")
        self.assertEqual(unknown.anchor, 0)
        self.assertIsNone(unknown.earliest_source)
        events = [{"id": 1}, {"id": 3}, {"id": 2, "date_earliest": "1900-01-01"}]
        self.assertEqual([e["id"] for e in sort_watch_history_entries(events)], [2, 3, 1])

    def test_each_descending_tie_breaker(self):
        # All anchors are Jan 2. Specificity must beat timestamp and identity.
        events = [
            dict(id=1, date_earliest="2026-01-02", date_latest="2026-01-02", created_at="2026-01-03"),
            dict(id=2, date_earliest="2026-01-01", date_latest="2026-01-03", created_at="2026-01-04"),
            dict(id=3, date_earliest="2026-01-02", created_at="2026-01-05"),
            dict(id=4, created_at="2026-01-06"),
        ]
        self.assertEqual([e["id"] for e in sort_watch_history_entries(events, "2026-01-02")], [1, 2, 3, 4])
        base = dict(date_earliest="2026-01-02", date_latest="2026-01-02")
        events = [dict(base, id=9, created_at="2026-01-03T00:30:00+02:00"),
                  dict(base, id=2, created_at="2026-01-02T23:00:00Z"),
                  dict(base, id=3, created_at="2026-01-02T23:00:00Z")]
        self.assertEqual([e["id"] for e in sort_watch_history_entries(events)], [3, 2, 9])
        drafts = [dict(base, draft_id="a"), dict(base, draft_id="b")]
        self.assertEqual([e["draft_id"] for e in sort_watch_history_entries(drafts)], ["b", "a"])

    def test_fractional_anchor_sorts_between_adjacent_days(self):
        events = [dict(id=1, date_earliest="2026-01-01", date_latest="2026-01-01"),
                  dict(id=2, date_earliest="2026-01-01", date_latest="2026-01-02"),
                  dict(id=3, date_earliest="2026-01-02", date_latest="2026-01-02")]
        self.assertEqual([e["id"] for e in sort_watch_history_entries(events)], [3, 2, 1])

    def test_stored_calendar_day_and_updated_at_independence(self):
        event = dict(date_earliest="2025-12-31", created_at="2026-01-01T00:30:00+02:00")
        self.assertEqual(resolve_watch_interval(event).latest, date(2026, 1, 1))
        edited = dict(event, updated_at="2099-01-01")
        self.assertEqual(resolve_watch_interval(event), resolve_watch_interval(edited))
        self.assertEqual(watch_history_sort_key(event), watch_history_sort_key(edited))

    def test_reject_invalid_explicit_dates_and_accept_future_dates(self):
        for event in ({"date_earliest": "2026-02-30"}, {"date_latest": "2026-1-2"},
                      {"date_earliest": "2026-01-01T12:00:00"},
                      {"date_earliest": "2026-02-01", "date_latest": "2026-01-01"}):
            with self.subTest(event=event), self.assertRaises(ValueError):
                resolve_watch_interval(event)
        self.assertTrue(validate_watch_dates("2099-01-01", None)["is_valid"])
        interval = resolve_watch_interval(dict(date_earliest="2099-01-01", created_at="2026-01-01"))
        self.assertEqual(interval.anchor, date(2099, 1, 1).toordinal())

    def test_episode_release_is_selected_by_episode_order_not_date(self):
        items = [dict(media_type="episode", season_num=2, episode_num=1, release_date="2000-01-01"),
                 dict(media_type="episode", season_num=1, episode_num=4, release_date="2020-01-01")]
        event = dict(items=items, created_at="2026-01-01")
        interval = resolve_watch_interval(event, "1990-01-01")
        self.assertEqual(interval.label, "~2020-2026")
        items[1]["release_date"] = "2021-01-01"
        self.assertEqual(resolve_watch_interval(event).anchor, date(2021, 1, 1).toordinal())
        items[1]["release_date"] = None
        self.assertEqual(resolve_watch_interval(event, "1990-01-01").earliest, date(2026, 1, 1))

    def test_group_ranges_and_single_episode_use_own_release(self):
        for numbers, label in [([(1, 4)], "S1:E4"), ([(1, 4), (1, 5), (1, 6)], "S1:E4-6"),
                               ([(1, 1), (1, 2), (1, 4)], "S1:E1-2, S1:E4"),
                               ([(1, 1), (1, 2), (2, 1)], "S1:E1-2, S2:E1")]:
            with self.subTest(numbers=numbers):
                event = dict(id=1, created_at="2026-01-01", items=[
                    dict(media_type="episode", season_num=s, episode_num=e, release_date="2024-01-01")
                    for s, e in reversed(numbers)])
                draft = dict(metadata=dict(media_type="series", release_date="2000-01-01"),
                             user_data=dict(watch_history=[event, dict(event, id=2)]))
                entries = build_watch_history_display_entries(draft)
                self.assertEqual([e["id"] for e in entries], [2, 1])
                self.assertEqual(entries[0]["text"], f"~2024-2026 · {label}")

    def test_draft_creation_uses_utc_when_local_calendar_day_differs(self):
        local = datetime(2026, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=2)))
        with patch("app.media_user_data.watch_history.datetime") as clock:
            clock.now.return_value = local.astimezone(timezone.utc)
            self.assertEqual(current_draft_timestamp(), "2025-12-31 22:30:00")
            clock.now.assert_called_once_with(timezone.utc)

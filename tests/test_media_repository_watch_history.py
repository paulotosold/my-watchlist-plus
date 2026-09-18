from copy import deepcopy
from datetime import date
import sqlite3
import unittest

from app import media_repository as repo
from app.media_draft import build_media_draft_from_db, apply_inserted_ids_to_draft
from app.media_user_data.watch_history import apply_watch_entry_result
from app.media_user_data.watch_history_formatters import build_watch_history_display_entries
from app.history.repository import load_default_history_entries
from db.connection import apply_database_schema
from history_fixtures import entry, insert_entry


class MediaRepositoryWatchHistoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.conn.execute('PRAGMA foreign_keys=ON')
        apply_database_schema(self.conn)
        self.movie = self.media(1, 'movie')
        self.series = self.media(2, 'series')
        self.other_series = self.media(3, 'series')
        self.episodes = [self.episode(10+n, self.series, n) for n in range(1, 5)]
        self.other_episode = self.episode(20, self.other_series, 1)
        self.conn.commit()

    def tearDown(self):
        self.assertEqual(self.conn.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.conn.close()

    def media(self, tid, kind):
        return self.conn.execute('INSERT INTO media(tmdb_id, media_type, title) VALUES (?, ?, ?)',
                                 (tid, kind, f'{kind} {tid}')).lastrowid

    def episode(self, tid, series, number):
        mid = self.media(tid, 'episode')
        self.conn.execute('INSERT INTO episode_details VALUES (?, ?, 1, ?)', (mid, series, number))
        return mid

    def read(self, media=None):
        return repo.load_history_entries(self.conn, media)

    def save(self, media, baseline, current):
        with self.conn:
            result = repo.apply_history_delta(self.conn, media, baseline, current)
        return result

    def assert_no_orphans(self):
        self.assertEqual(self.conn.execute('''SELECT id FROM watch_history_entry e WHERE NOT EXISTS
            (SELECT 1 FROM watch_history_item i WHERE i.entry_id=e.id)''').fetchall(), [])

    def test_create_single_group_and_separate_identical_dates(self):
        a, b = self.episodes[:2]
        entries = [entry(a, b), entry(a), entry(b), entry(self.series)]
        self.save(self.series, [], entries)
        saved = self.read(self.series)
        self.assertEqual(len(saved), 4)
        self.assertEqual(sorted(len(e['items']) for e in saved), [1, 1, 1, 2])
        self.assertEqual(len(load_default_history_entries(self.conn)), 4)
        self.assert_no_orphans()

    def test_temporal_projection_matches_details_in_series_and_episode_contexts(self):
        a, b = self.episodes[:2]
        self.conn.execute("UPDATE media SET release_date = '2000-01-01' WHERE id = ?", (self.series,))
        self.conn.execute("UPDATE media SET release_date = '2024-01-01' WHERE id = ?", (a,))
        self.conn.execute("UPDATE media SET release_date = '2023-01-01' WHERE id = ?", (b,))
        ids = [insert_entry(self.conn, [b, a], lo, hi, "2026-01-01 12:00:00")
               for lo, hi in [(None, None), ("2025-01-01", None),
                              (None, "2025-01-01"), ("2025-01-01", "2025-01-01")]]
        # A distinct viewing with the same members and date pair stays distinct.
        ids.append(insert_entry(self.conn, [a, b], created_at="2026-01-01 12:00:00"))
        for release in ("2024-01-01", "2022-01-01", None):
            self.conn.execute("UPDATE media SET release_date = ? WHERE id = ?", (release, a))
            history = load_default_history_entries(self.conn)
            self.assertEqual(len(history), len(ids))
            undated = next(e for e in history if e.entry_id == ids[0])
            self.assertEqual(undated.sort_key[0], date.fromisoformat(release or "2026-01-01").toordinal())
            self.assertEqual(undated.release_date, release)
            for media_id in (self.series, a, b):
                with self.subTest(release=release, media_id=media_id):
                    draft = build_media_draft_from_db(self.conn, repo.get_media_by_id(self.conn, media_id))
                    details = build_watch_history_display_entries(draft)
                    self.assertEqual([e.entry_id for e in history], [e['id'] for e in details])
                    for card, row in zip(history, details):
                        self.assertEqual(card.formatted_date, row['text'].split(' · ')[0])
                        self.assertEqual(card.sort_key, row['sort_key'])

    def test_edit_dates_membership_and_conversion_preserve_identity(self):
        self.save(self.series, [], [entry(self.series)])
        first = self.read(self.series)[0]
        identity = (first['id'], first['created_at'])
        for members in [self.episodes[:3], self.episodes[2:], [self.series], [self.episodes[0]]]:
            baseline = self.read(self.series)
            desired = deepcopy(baseline)
            desired[0]['items'] = [{'media_id': m} for m in members]
            desired[0]['date_earliest'] = '2025-01-01'
            self.save(self.series, baseline, desired)
            saved = self.read(self.series)[0]
            self.assertEqual((saved['id'], saved['created_at']), identity)
            self.assertEqual({i['media_id'] for i in saved['items']}, set(members))
            self.assertIsNotNone(saved['updated_at'])
            self.assert_no_orphans()

    def test_retained_members_keep_item_ids_and_noop_keeps_timestamps(self):
        self.save(self.series, [], [entry(*self.episodes[:2])])
        baseline = self.read(self.series)
        old_ids = {i['media_id']: i['id'] for i in baseline[0]['items']}
        desired = deepcopy(baseline)
        desired[0]['items'].append({'media_id': self.episodes[2]})
        self.save(self.series, baseline, desired)
        saved = self.read(self.series)
        self.assertTrue(all(i['id'] == old_ids[i['media_id']] for i in saved[0]['items'] if i['media_id'] in old_ids))
        result = self.save(self.series, saved, deepcopy(saved))
        self.assertEqual(saved, self.read(self.series))
        self.assertFalse(any(result['counts'].values()))

    def test_invalid_compositions_and_dates_roll_back_complete_operation(self):
        cases = [entry(), entry(self.movie, self.series), entry(self.series, self.episodes[0]),
                 entry(self.episodes[0], self.other_episode), entry(self.episodes[0], self.episodes[0]),
                 entry(self.series, date_earliest='2025-02-30'),
                 entry(self.series, date_earliest='2025-05-02', date_latest='2025-05-01')]
        for invalid in cases:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                repo.apply_history_delta(self.conn, self.series, [], [entry(self.series), invalid])
            self.assertEqual(self.read(), [])
            self.assert_no_orphans()

    def test_schema_checks_composition_dates_and_unique(self):
        eid = insert_entry(self.conn, [self.series])
        for mid in [self.series, self.movie, self.episodes[0]]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute('INSERT INTO watch_history_item(entry_id, media_id) VALUES (?, ?)', (eid, mid))
        for invalid in ['2025-02-30', '2025-13-01', '2025-1-1', 'xxxx-xx-xx']:
            with self.assertRaises(sqlite3.IntegrityError):
                self.conn.execute('INSERT INTO watch_history_entry(date_earliest) VALUES (?)', (invalid,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute('INSERT INTO watch_history_item(entry_id, media_id) VALUES (9999, ?)', (self.movie,))

    def test_delete_entry_and_item_and_media_cascades(self):
        eid = insert_entry(self.conn, self.episodes[:2])
        self.conn.execute('DELETE FROM media WHERE id=?', (self.episodes[0],))
        self.assertEqual([i['media_id'] for i in self.read()[0]['items']], [self.episodes[1]])
        self.conn.execute('DELETE FROM watch_history_item WHERE entry_id=?', (eid,))
        self.assertEqual(self.read(), [])
        self.assert_no_orphans()
        eid = insert_entry(self.conn, self.episodes[2:])
        self.conn.execute('DELETE FROM watch_history_entry WHERE id=?', (eid,))
        self.assertEqual(self.conn.execute('SELECT * FROM watch_history_item').fetchall(), [])
        eid = insert_entry(self.conn, [self.movie])
        self.conn.execute('DELETE FROM media WHERE id=?', (self.movie,))
        self.assert_no_orphans()

    def test_rewatch_removal_preserves_watched_until_last_entry(self):
        a = self.episodes[0]
        self.save(self.series, [], [entry(a), entry(a, self.episodes[1])])
        baseline = self.read(self.series)
        self.save(self.series, baseline, baseline[1:])
        self.assertEqual(repo.get_media_state(self.conn, a)['watch_state'], 'watched')
        self.save(self.series, self.read(self.series), [])
        self.assertIsNone(repo.get_media_state(self.conn, a)['watch_state'])

    def test_concurrent_group_edit_from_episode_conflicts_and_preserves_new_entries(self):
        a, b = self.episodes[:2]
        self.save(self.series, [], [entry(a, b)])
        baseline = self.read(a)
        self.assertEqual(len(baseline[0]['items']), 2)
        changed = deepcopy(baseline)
        changed[0]['items'] = changed[0]['items'][1:]
        self.save(a, baseline, changed)
        self.assertEqual(self.read(a), [])
        stale = deepcopy(baseline)
        stale[0]['date_earliest'] = '2025-01-01'
        with self.assertRaises(repo.ConcurrentEditError):
            self.save(self.series, baseline, stale)
        self.save(self.series, [], [entry(a)])
        self.assertEqual(len(self.read(self.series)), 2)

    def test_group_membership_change_conflicts_with_delete(self):
        self.save(self.series, [], [entry(*self.episodes[:2])])
        baseline = self.read(self.series)
        changed = deepcopy(baseline)
        changed[0]['items'].append({'media_id': self.episodes[2]})
        self.save(self.series, baseline, changed)
        with self.assertRaises(repo.ConcurrentEditError):
            self.save(self.series, baseline, [])
        self.assertEqual(len(self.read(self.series)[0]['items']), 3)

    def test_foreign_entry_and_media_identity_are_rejected(self):
        self.save(self.other_series, [], [entry(self.other_episode)])
        with self.assertRaises(ValueError):
            self.save(self.series, [], self.read(self.other_series))
        bad = entry(self.episodes[0]); bad['items'][0]['tmdb_id'] = 9999
        with self.assertRaises(ValueError):
            self.save(self.series, [], [bad])

    def test_draft_reconciliation_publishes_entries_items_and_timestamps(self):
        new = entry(*self.episodes[:2], draft_id='entry-new')
        draft = {'user_data': {'watch_history': [new]}}
        before = deepcopy(draft)
        result = self.save(self.series, [], [new])
        self.assertEqual(draft, before)
        self.assertEqual(len(result['inserted_ids_by_draft_id']['watch_history_items']), 2)
        apply_inserted_ids_to_draft(draft, result)
        self.assertEqual(draft['user_data']['watch_history'], self.read(self.series))
        self.assertNotIn('draft_id', draft['user_data']['watch_history'][0])

    def test_episode_draft_and_editor_preserve_complete_group(self):
        a, b = self.episodes[:2]
        self.save(self.series, [], [entry(a, b)])
        draft = build_media_draft_from_db(self.conn, repo.get_media_by_id(self.conn, a))
        original = deepcopy(draft['user_data']['watch_history'][0])
        self.assertNotIn('episode_watch_history', draft['series_view'])
        display = build_watch_history_display_entries(draft)[0]
        self.assertEqual(len(display['items']), 2)
        apply_watch_entry_result(draft, display, {'action': 'save', 'date_earliest': '2025-01-01',
            'selected_episodes': draft['series_view']['episodes'][1:3]})
        changed = draft['user_data']['watch_history'][0]
        self.assertEqual(changed['id'], original['id'])
        self.assertEqual(changed['created_at'], original['created_at'])
        self.save(a, [original], [changed])
        self.assertEqual(self.read(a), [])
        self.assertEqual(len(self.read(b)[0]['items']), 2)

    def test_full_save_resolves_tmdb_items(self):
        new = entry(self.episodes[0]); new['items'] = [{'tmdb_id': 11, 'media_type': 'episode'}]
        repo.sync_history(self.conn, self.series, [new])
        self.assertEqual(self.read()[0]['items'][0]['media_id'], self.episodes[0])

    def test_deleting_series_in_sql_cascades_to_episode_items(self):
        insert_entry(self.conn, self.episodes)
        insert_entry(self.conn, [self.series])
        self.conn.execute('DELETE FROM media WHERE id=?', (self.series,))
        self.assertEqual(self.read(), [])
        self.assert_no_orphans()
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM episode_details WHERE series_id=?',
                                          (self.series,)).fetchone()[0], 0)

    def test_failed_incremental_save_rolls_back_scalar_changes_and_ids(self):
        draft = build_media_draft_from_db(self.conn, repo.get_media_by_id(self.conn, self.movie))
        changed = deepcopy(draft)
        changed['user_data']['impression'] = 'good'
        changed['user_data']['watch_history'] = [entry(self.movie), entry(self.other_episode)]
        before = deepcopy(changed)
        with self.assertRaises(ValueError):
            repo.apply_media_user_changes(self.conn, self.movie, draft, changed)
        self.assertEqual(changed, before)
        self.assertIsNone(repo.get_media_state(self.conn, self.movie)['impression'])
        self.assertEqual(self.read(), [])
        self.assert_no_orphans()

    def test_external_history_count_and_draft_edits_color_other_episodes(self):
        from app.media_user_data.watch_history import watched_episode_keys
        a, b, c = self.episodes[:3]
        self.save(self.series, [], [entry(a, b), entry(b), entry(c)])
        draft = build_media_draft_from_db(self.conn, repo.get_media_by_id(self.conn, a))
        self.assertEqual(len(draft['user_data']['watch_history']), 1)
        group = draft['user_data']['watch_history'][0]
        self.assertEqual(watched_episode_keys(draft, group), {(1, 2), (1, 3)})
        apply_watch_entry_result(draft, group, {'action': 'delete'})
        self.assertEqual(watched_episode_keys(draft), {(1, 2), (1, 3)})

    def test_csv_repeats_full_group_by_identity_and_keeps_rewatches(self):
        from scripts.export_watchlist_csv import collect_watchlist_rows
        import json
        a, b = self.episodes[:2]
        self.save(self.series, [], [entry(a, b), entry(a, b)])
        rows = collect_watchlist_rows(self.conn)
        histories = [json.loads(r['watch_history']) for r in rows]
        self.assertEqual(len(histories), 2)
        self.assertEqual(histories[0], histories[1])
        self.assertEqual(len({e['id'] for e in histories[0]}), 2)
        self.assertTrue(all(len(e['items']) == 2 for e in histories[0]))

    def test_new_database_has_only_definitive_history_schema(self):
        names = {r[0] for r in self.conn.execute('SELECT name FROM sqlite_master')}
        self.assertIn('watch_history_entry', names)
        self.assertIn('watch_history_item', names)
        self.assertNotIn('watch_history', names)
        self.assertNotIn('series_episode_watch_history', names)


if __name__ == '__main__':
    unittest.main()

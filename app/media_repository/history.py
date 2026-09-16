"""Atomic persistence of complete logical watch-history entries.

Callers own the transaction. Savepoints roll back a failed operation without
committing unrelated work; returned identities are published only after commit.
"""
from contextlib import contextmanager
from copy import deepcopy
from uuid import uuid4

from app.media_user_data.watch_history import validate_watch_dates
from .errors import ConcurrentEditError


@contextmanager
def history_savepoint(conn):
    if not conn.in_transaction:
        conn.execute('BEGIN')
    name = 'history_' + uuid4().hex
    conn.execute(f'SAVEPOINT {name}')
    try:
        yield
    except Exception:
        conn.execute(f'ROLLBACK TO {name}')
        raise
    finally:
        conn.execute(f'RELEASE {name}')


def load_history_entries(conn, media_id=None, *, include_series_episodes=True, entry_id=None):
    conditions, params = [], []
    if entry_id is not None:
        conditions.append('e.id = ?')
        params.append(entry_id)
    if media_id is not None:
        conditions.append('''EXISTS (SELECT 1 FROM watch_history_item member
            WHERE member.entry_id = e.id AND (member.media_id = ? OR
            (? AND member.media_id IN (SELECT media_id FROM episode_details WHERE series_id = ?))))''')
        params.extend((media_id, include_series_episodes, media_id))
    where = 'WHERE ' + ' AND '.join(conditions) if conditions else ''
    rows = conn.execute(f'''SELECT e.*, i.id AS item_id, i.media_id,
        m.media_type, m.tmdb_id, m.title, m.release_date,
        ed.series_id, ed.season_num, ed.episode_num
        FROM watch_history_entry e JOIN watch_history_item i ON i.entry_id = e.id
        JOIN media m ON m.id = i.media_id
        LEFT JOIN episode_details ed ON ed.media_id = m.id
        {where}
        ORDER BY e.created_at, e.id, ed.season_num, ed.episode_num, i.id''', params)
    entries = {}
    for row in rows:
        entry = entries.setdefault(row['id'], {
            key: row[key] for key in ('id', 'date_earliest', 'date_latest', 'created_at', 'updated_at')
        })
        item = {key: row[key] for key in (
            'media_id', 'media_type', 'tmdb_id', 'title', 'release_date',
            'series_id', 'season_num', 'episode_num')}
        item['id'] = row['item_id']
        entry.setdefault('items', []).append(item)
    return list(entries.values())


def history_ids(conn, media_id):
    return {r[0] for r in conn.execute(
        'SELECT entry_id FROM watch_history_item WHERE media_id = ?', (media_id,))}


def _media(conn, media_id):
    row = conn.execute('''SELECT m.*, ed.series_id FROM media m
        LEFT JOIN episode_details ed ON ed.media_id = m.id WHERE m.id = ?''', (media_id,)).fetchone()
    if row is None:
        raise ValueError(f'media id {media_id} does not exist.')
    return row


def _resolve_items(conn, entry):
    items = deepcopy(entry.get('items') or [])
    if not items:
        raise ValueError('A watch history entry requires at least one item.')
    seen = set()
    for item in items:
        media_id = item.get('media_id')
        if media_id is None:
            row = conn.execute('SELECT id FROM media WHERE tmdb_id = ? AND media_type = ?',
                               (item.get('tmdb_id'), item.get('media_type'))).fetchone()
            if row is None:
                raise ValueError('Could not resolve watch history media item.')
            media_id = row[0]
        media = _media(conn, media_id)
        for key in ('tmdb_id', 'media_type', 'series_id'):
            if item.get(key) is not None and item[key] != media[key]:
                raise ValueError(f'Watch history item {key} does not match media {media_id}.')
        if media_id in seen:
            raise ValueError('Duplicate media in watch history entry.')
        seen.add(media_id)
        item.update(media_id=media_id, media_type=media['media_type'], series_id=media['series_id'])
    if len(items) > 1 and (any(i['media_type'] != 'episode' for i in items)
                          or len({i['series_id'] for i in items}) != 1):
        raise ValueError('Multiple items must be episodes of the same series.')
    if any(i['media_type'] == 'episode' and i['series_id'] is None for i in items):
        raise ValueError('Episode item requires a parent series.')
    return items


def _validate_scope(conn, media_id, items, *, existing=False):
    owner = _media(conn, media_id)
    items = [{**item, 'media_type': actual['media_type'], 'series_id': actual['series_id']}
             for item in items for actual in [_media(conn, item['media_id'])]]
    if owner['media_type'] == 'movie':
        valid = len(items) == 1 and items[0]['media_id'] == media_id
    else:
        series_id = media_id if owner['media_type'] == 'series' else owner['series_id']
        valid = all(i['media_id'] == series_id or
                    (i['media_type'] == 'episode' and i['series_id'] == series_id) for i in items)
        if owner['media_type'] == 'episode' and not existing:
            valid = valid and any(i['media_id'] == media_id for i in items)
    if not valid:
        raise ValueError('Watch history entry does not belong to media context.')


def _values(entry, *, revision=False):
    value = (entry.get('date_earliest'), entry.get('date_latest'),
             tuple(sorted(i['media_id'] for i in entry['items'])))
    if revision:
        value += (entry.get('created_at'), entry.get('updated_at'),
                  tuple(sorted((i.get('id'), i['media_id']) for i in entry['items'])))
    return value


def _indexed(entries):
    indexed, draft_ids = {}, set()
    for entry in entries:
        if entry.get('id') is not None:
            if entry['id'] in indexed:
                raise ValueError('Duplicate watch history entry id.')
            indexed[entry['id']] = entry
        else:
            draft_id = entry.get('draft_id')
            if not draft_id or draft_id in draft_ids:
                raise ValueError('New watch history entries require unique draft_id.')
            draft_ids.add(draft_id)
    return indexed


def _replace_items(conn, entry_id, old_items, desired):
    old = {i['media_id']: i for i in old_items}
    new = {i['media_id']: i for i in desired}
    kept = old.keys() & new.keys()
    if old and not kept:
        # Retain one physical item through conversion, so cleanup cannot delete
        # the entry. There is no incompatible second item during reassignment.
        anchor = next(iter(old.values()))
        conn.execute('DELETE FROM watch_history_item WHERE entry_id = ? AND id != ?',
                     (entry_id, anchor['id']))
        first = next(iter(new))
        conn.execute('UPDATE watch_history_item SET media_id = ? WHERE id = ?',
                     (first, anchor['id']))
        kept = {first}
    else:
        for media_id in old.keys() - new.keys():
            conn.execute('DELETE FROM watch_history_item WHERE id = ?', (old[media_id]['id'],))
    for media_id in new.keys() - kept:
        conn.execute('INSERT INTO watch_history_item(entry_id, media_id) VALUES (?, ?)',
                     (entry_id, media_id))


def apply_history_delta(conn, media_id, baseline, current):
    """Apply complete-entry deltas without mutating either draft."""
    with history_savepoint(conn):
        return _apply_history_delta(conn, media_id, baseline, current)


def _apply_history_delta(conn, media_id, baseline, current):
    from .user_data import _sync_episode_watch_state_for_history_transition
    baseline_by_id = _indexed(baseline)
    current_by_id = _indexed(current)
    if current_by_id.keys() - baseline_by_id.keys():
        raise ValueError('Watch history id was not part of the baseline.')
    before = {}
    entry_map, item_map, persisted = {}, {}, {}
    counts = dict(watch_history_inserted=0, watch_history_updated=0, watch_history_deleted=0)
    item_drafts = set()

    def remember(items):
        for item in items:
            mid = item['media_id']
            before.setdefault(mid, history_ids(conn, mid))

    for original in current:
        entry = deepcopy(original)
        entry['items'] = _resolve_items(conn, entry)
        entry_id = entry.get('id')
        _validate_scope(conn, media_id, entry['items'], existing=entry_id is not None)
        dates = validate_watch_dates(entry.get('date_earliest'), entry.get('date_latest'))
        if not dates['is_valid']:
            raise ValueError(dates['error'])
        for item in entry['items']:
            draft_id = item.get('draft_id')
            if draft_id:
                if draft_id in item_drafts:
                    raise ValueError('Duplicate watch history item draft_id.')
                item_drafts.add(draft_id)
        if entry_id is None:
            if any(item.get('id') is not None for item in entry['items']):
                raise ValueError('New entries cannot claim persisted item ids.')
            remember(entry['items'])
            entry_id = conn.execute('''INSERT INTO watch_history_entry(date_earliest, date_latest)
                VALUES (?, ?)''', (entry.get('date_earliest'), entry.get('date_latest'))).lastrowid
            _replace_items(conn, entry_id, [], entry['items'])
            entry_map[entry['draft_id']] = entry_id
            counts['watch_history_inserted'] += 1
        else:
            base = baseline_by_id[entry_id]
            base_items = {i.get('id'): i['media_id'] for i in base['items'] if i.get('id') is not None}
            for item in entry['items']:
                if item.get('id') is not None and base_items.get(item['id']) != item['media_id']:
                    raise ValueError('Watch history item id does not match its baseline association.')
            _validate_scope(conn, media_id, base['items'])
            changed = _values(entry) != _values(base)
            stored = load_history_entries(conn, entry_id=entry_id)
            if not changed:
                continue
            if not stored or _values(stored[0], revision=True) != _values(base, revision=True):
                raise ConcurrentEditError(f'Watch history entry {entry_id} changed concurrently.')
            remember(stored[0]['items'])
            remember(entry['items'])
            _replace_items(conn, entry_id, stored[0]['items'], entry['items'])
            conn.execute('''UPDATE watch_history_entry SET date_earliest = ?, date_latest = ?,
                updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?''',
                         (entry.get('date_earliest'), entry.get('date_latest'), entry_id))
            counts['watch_history_updated'] += 1
        saved = load_history_entries(conn, entry_id=entry_id)[0]
        persisted[entry_id] = saved
        saved_by_media = {i['media_id']: i for i in saved['items']}
        for item in entry['items']:
            if item.get('draft_id'):
                item_map[item['draft_id']] = saved_by_media[item['media_id']]['id']

    for entry_id in baseline_by_id.keys() - current_by_id.keys():
        base = baseline_by_id[entry_id]
        _validate_scope(conn, media_id, base['items'])
        stored = load_history_entries(conn, entry_id=entry_id)
        if not stored:
            raise ConcurrentEditError(f'Watch history entry {entry_id} was deleted concurrently.')
        if _values(stored[0], revision=True) != _values(base, revision=True):
            raise ConcurrentEditError(f'Watch history entry {entry_id} changed before deletion.')
        remember(stored[0]['items'])
        conn.execute('DELETE FROM watch_history_entry WHERE id = ?', (entry_id,))
        counts['watch_history_deleted'] += 1
    for mid, ids in before.items():
        _sync_episode_watch_state_for_history_transition(conn, mid, ids, history_ids(conn, mid))
    return {'inserted_ids_by_draft_id': {'watch_history_entries': entry_map, 'watch_history_items': item_map},
            'persisted_watch_history': persisted, 'counts': counts}


def sync_history(conn, media_id, entries):
    """Full initial save; existing interactive drafts must use a baseline delta."""
    current = deepcopy(entries)
    for entry in current:
        if entry.get('id') is None:
            entry.setdefault('draft_id', uuid4().hex)
    result = apply_history_delta(conn, media_id, load_history_entries(conn, media_id), current)
    return result

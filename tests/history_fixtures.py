"""Explicit entry/item fixtures for history tests."""
from uuid import uuid4


def entry(*media_ids, date_earliest=None, date_latest=None, draft_id=None):
    return {'draft_id': draft_id or uuid4().hex,
            'date_earliest': date_earliest, 'date_latest': date_latest,
            'items': [{'media_id': mid, 'draft_id': uuid4().hex} for mid in media_ids]}


def insert_entry(conn, media_ids, earliest=None, latest=None, created_at=None):
    columns = 'date_earliest, date_latest'
    values = [earliest, latest]
    if created_at is not None:
        columns += ', created_at'
        values.append(created_at)
    eid = conn.execute(f'INSERT INTO watch_history_entry({columns}) VALUES ({",".join("?" for _ in values)})', values).lastrowid
    conn.executemany('INSERT INTO watch_history_item(entry_id, media_id) VALUES (?, ?)',
                     [(eid, mid) for mid in media_ids])
    return eid

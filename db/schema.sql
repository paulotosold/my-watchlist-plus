-- ----------------------------------------------------------
-- media table
CREATE TABLE IF NOT EXISTS media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    tmdb_id INTEGER NOT NULL,
    imdb_id TEXT,
    media_type TEXT NOT NULL,
    title TEXT NOT NULL,
    original_title TEXT,
    production_status TEXT,
    release_date TEXT,
    runtime_min INTEGER,
    last_tmdb_metadata_checked_at TEXT,
    last_tmdb_posters_checked_at TEXT,
    last_tmdb_watch_providers_checked_at TEXT,

    UNIQUE (tmdb_id, media_type),
    UNIQUE (imdb_id),

    CHECK (media_type IN ('movie', 'series', 'episode')),
    CHECK (
        release_date IS NULL
        OR (
            release_date = date(release_date)
            AND release_date GLOB '????-??-??'
        )
    ),
    CHECK (runtime_min IS NULL OR runtime_min >= 0)
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- episode_details table
CREATE TABLE IF NOT EXISTS episode_details (
    media_id INTEGER PRIMARY KEY,
    series_id INTEGER NOT NULL,
    season_num INTEGER NOT NULL,
    episode_num INTEGER NOT NULL,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (series_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    UNIQUE (series_id, season_num, episode_num),

    CHECK (season_num >= 1),
    CHECK (episode_num >= 1)
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- series_summary view
CREATE VIEW IF NOT EXISTS series_summary AS
SELECT
    s.id AS series_id,
    s.title AS series_title,

    COUNT(DISTINCT ed.season_num) AS season_count,
    COUNT(ed.media_id) AS episode_count,

    MIN(e.release_date) AS first_air_date,
    MAX(e.release_date) AS last_air_date,

    COALESCE(SUM(e.runtime_min), 0) AS total_runtime_min,
    CASE
        WHEN COUNT(ed.media_id) = 0 THEN NULL
        ELSE CAST(
            ROUND(
                1.0 * COALESCE(SUM(e.runtime_min), 0) / COUNT(ed.media_id)
            ) AS INTEGER
        )
    END AS avg_episode_runtime_min

FROM media s

LEFT JOIN episode_details ed
    ON ed.series_id = s.id

LEFT JOIN media e
    ON e.id = ed.media_id

WHERE s.media_type = 'series'

GROUP BY
    s.id,
    s.title;
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_posters table
CREATE TABLE IF NOT EXISTS media_posters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    media_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'other',
    curation_status TEXT NOT NULL DEFAULT 'pending',
    is_default INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    UNIQUE (media_id, filename),

    CHECK (source IN ('tmdb', 'user', 'other')),
    CHECK (curation_status IN ('pending', 'selected', 'discarded', 'failed')),
    CHECK (is_default IN (0, 1)),
    CHECK (
        is_default = 0
        OR curation_status = 'selected'
    )
);

-- only one default poster is allowed per media item
CREATE UNIQUE INDEX IF NOT EXISTS uq_media_posters_one_default
ON media_posters (media_id)
WHERE is_default = 1;
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- season_posters table
CREATE TABLE IF NOT EXISTS season_posters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    series_id INTEGER NOT NULL,
    season_num INTEGER NOT NULL,
    filename TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'other',
    curation_status TEXT NOT NULL DEFAULT 'pending',
    is_default INTEGER NOT NULL DEFAULT 0,

    FOREIGN KEY (series_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    UNIQUE (series_id, season_num, filename),

    CHECK (season_num >= 1),
    CHECK (source IN ('tmdb', 'user', 'other')),
    CHECK (curation_status IN ('pending', 'selected', 'discarded', 'failed')),
    CHECK (is_default IN (0, 1)),
    CHECK (
        is_default = 0
        OR curation_status = 'selected'
    )
);

-- only one default poster is allowed per season
CREATE UNIQUE INDEX IF NOT EXISTS uq_season_posters_one_default
ON season_posters (series_id, season_num)
WHERE is_default = 1;
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_notes table
CREATE TABLE IF NOT EXISTS media_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    media_id INTEGER NOT NULL,
    note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_media_notes_media_id
    ON media_notes (media_id);

CREATE TRIGGER IF NOT EXISTS trg_media_notes_validate_insert
BEFORE INSERT ON media_notes
WHEN length(trim(
    NEW.note,
    ' ' || char(9) || char(10) || char(11) || char(12) || char(13)
)) = 0
BEGIN
    SELECT RAISE(ABORT, 'media note cannot be empty');
END;

CREATE TRIGGER IF NOT EXISTS trg_media_notes_validate_update
BEFORE UPDATE OF note ON media_notes
WHEN length(trim(
    NEW.note,
    ' ' || char(9) || char(10) || char(11) || char(12) || char(13)
)) = 0
BEGIN
    SELECT RAISE(ABORT, 'media note cannot be empty');
END;
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_state table
CREATE TABLE IF NOT EXISTS media_state (
    media_id INTEGER PRIMARY KEY,

    watch_state TEXT,
    impression TEXT,
    is_cabinet_worthy INTEGER,
    cabinet_order INTEGER DEFAULT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    CHECK (
        watch_state IS NULL
        OR watch_state IN (
            'to_watch',
            'watched',
            'not_interested',
            'dropped'
        )
    ),

    CHECK (
        impression IS NULL
        OR impression IN (
            'very_good',
            'good',
            'meh',
            'not_for_me',
            'regret_watching'
        )
    ),

    CHECK (is_cabinet_worthy IS NULL OR is_cabinet_worthy IN (0, 1)),
    CHECK (cabinet_order IS NULL OR is_cabinet_worthy IS 1)
);

CREATE TRIGGER IF NOT EXISTS trg_media_state_validate_insert
BEFORE INSERT ON media_state
WHEN NEW.watch_state IS NOT NULL
AND NOT EXISTS (
    SELECT 1
    FROM media m
    WHERE m.id = NEW.media_id
      AND (
          (
              m.media_type = 'movie'
              AND NEW.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested'
              )
          )
          OR (
              m.media_type = 'series'
              AND NEW.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested',
                  'dropped'
              )
          )
          OR (
              m.media_type = 'episode'
              AND NEW.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested'
              )
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid watch_state for media_type');
END;

CREATE TRIGGER IF NOT EXISTS trg_media_state_validate_update
BEFORE UPDATE OF media_id, watch_state ON media_state
WHEN NEW.watch_state IS NOT NULL
AND NOT EXISTS (
    SELECT 1
    FROM media m
    WHERE m.id = NEW.media_id
      AND (
          (
              m.media_type = 'movie'
              AND NEW.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested'
              )
          )
          OR (
              m.media_type = 'series'
              AND NEW.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested',
                  'dropped'
              )
          )
          OR (
              m.media_type = 'episode'
              AND NEW.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested'
              )
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'invalid watch_state for media_type');
END;

CREATE TRIGGER IF NOT EXISTS trg_media_validate_watch_state_after_type_change
BEFORE UPDATE OF media_type ON media
WHEN EXISTS (
    SELECT 1
    FROM media_state ms
    WHERE ms.media_id = OLD.id
      AND ms.watch_state IS NOT NULL
      AND NOT (
          (
              NEW.media_type = 'movie'
              AND ms.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested'
              )
          )
          OR (
              NEW.media_type = 'series'
              AND ms.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested',
                  'dropped'
              )
          )
          OR (
              NEW.media_type = 'episode'
              AND ms.watch_state IN (
                  'to_watch',
                  'watched',
                  'not_interested'
              )
          )
      )
)
BEGIN
    SELECT RAISE(ABORT, 'media_type is incompatible with watch_state');
END;
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- Logical history records and their media associations.
CREATE TABLE IF NOT EXISTS watch_history_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date_earliest TEXT,
    date_latest TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,
    CHECK (date_earliest IS NULL OR (
        date(date_earliest, '+0 days') IS NOT NULL
        AND date_earliest = date(date_earliest, '+0 days')
        AND date_earliest GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    )),
    CHECK (date_latest IS NULL OR (
        date(date_latest, '+0 days') IS NOT NULL
        AND date_latest = date(date_latest, '+0 days')
        AND date_latest GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
    )),
    CHECK (date_earliest IS NULL OR date_latest IS NULL
           OR date_latest >= date_earliest)
);

CREATE TABLE IF NOT EXISTS watch_history_item (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_id INTEGER NOT NULL REFERENCES watch_history_entry(id) ON DELETE CASCADE,
    media_id INTEGER NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    UNIQUE (entry_id, media_id)
);
CREATE INDEX IF NOT EXISTS idx_watch_history_item_media_id
ON watch_history_item(media_id);

CREATE TRIGGER IF NOT EXISTS trg_watch_history_item_validate_insert
BEFORE INSERT ON watch_history_item
BEGIN
    SELECT RAISE(ABORT, 'invalid watch history composition')
    WHERE NOT EXISTS (
        SELECT 1 FROM media m
        LEFT JOIN episode_details ed ON ed.media_id = m.id
        JOIN media parent ON parent.id = COALESCE(ed.series_id, m.id)
        WHERE m.id = NEW.media_id
          AND (m.media_type != 'episode' OR
               (ed.media_id IS NOT NULL AND parent.media_type = 'series'))
    ) OR EXISTS (
        SELECT 1 FROM watch_history_item i
        JOIN media old_media ON old_media.id = i.media_id
        JOIN media new_media ON new_media.id = NEW.media_id
        LEFT JOIN episode_details old_ed ON old_ed.media_id = i.media_id
        LEFT JOIN episode_details new_ed ON new_ed.media_id = NEW.media_id
        WHERE i.entry_id = NEW.entry_id

          AND (old_media.media_type != 'episode' OR new_media.media_type != 'episode'
               OR old_ed.series_id IS NOT new_ed.series_id)
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_watch_history_item_validate_update
BEFORE UPDATE ON watch_history_item
BEGIN
    SELECT RAISE(ABORT, 'invalid watch history composition')
    WHERE NOT EXISTS (
        SELECT 1 FROM media m
        LEFT JOIN episode_details ed ON ed.media_id = m.id
        JOIN media parent ON parent.id = COALESCE(ed.series_id, m.id)
        WHERE m.id = NEW.media_id
          AND (m.media_type != 'episode' OR
               (ed.media_id IS NOT NULL AND parent.media_type = 'series'))
    ) OR EXISTS (
        SELECT 1 FROM watch_history_item i
        JOIN media old_media ON old_media.id = i.media_id
        JOIN media new_media ON new_media.id = NEW.media_id
        LEFT JOIN episode_details old_ed ON old_ed.media_id = i.media_id
        LEFT JOIN episode_details new_ed ON new_ed.media_id = NEW.media_id
        WHERE i.entry_id = NEW.entry_id
          AND i.id != OLD.id
          AND (old_media.media_type != 'episode' OR new_media.media_type != 'episode'
               OR old_ed.series_id IS NOT new_ed.series_id)
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_watch_history_item_cleanup_delete
AFTER DELETE ON watch_history_item
BEGIN
    DELETE FROM watch_history_entry WHERE id = OLD.entry_id
    AND NOT EXISTS (SELECT 1 FROM watch_history_item WHERE entry_id = OLD.entry_id);
    UPDATE watch_history_entry SET updated_at = strftime('%Y-%m-%d %H:%M:%f', 'now')
    WHERE id = OLD.entry_id;
END;

CREATE TRIGGER IF NOT EXISTS trg_watch_history_item_cleanup_move
AFTER UPDATE OF entry_id ON watch_history_item
WHEN OLD.entry_id != NEW.entry_id
BEGIN
    DELETE FROM watch_history_entry WHERE id = OLD.entry_id
    AND NOT EXISTS (SELECT 1 FROM watch_history_item WHERE entry_id = OLD.entry_id);
END;
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- Deleting a series removes its episode catalogue and all affected memberships.
CREATE TRIGGER IF NOT EXISTS trg_media_delete_series_episodes
BEFORE DELETE ON media WHEN OLD.media_type = 'series'
BEGIN
    DELETE FROM media WHERE id IN (
        SELECT media_id FROM episode_details WHERE series_id = OLD.id
    );
END;

CREATE TRIGGER IF NOT EXISTS trg_episode_details_validate_history_move
BEFORE UPDATE OF series_id ON episode_details
WHEN NEW.series_id != OLD.series_id
BEGIN
    SELECT RAISE(ABORT, 'cannot move an episode out of its history group')
    WHERE EXISTS (
        SELECT 1 FROM watch_history_item own
        JOIN watch_history_item sibling ON sibling.entry_id = own.entry_id AND sibling.id != own.id
        JOIN episode_details ed ON ed.media_id = sibling.media_id
        WHERE own.media_id = OLD.media_id AND ed.series_id != NEW.series_id
    );
END;

-- media_watch_providers table
CREATE TABLE IF NOT EXISTS media_watch_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    media_id INTEGER NOT NULL,
    provider_tmdb_id INTEGER NOT NULL,
    provider_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    access_type TEXT NOT NULL,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    UNIQUE (media_id, provider_tmdb_id, country_code, access_type),

    CHECK (country_code GLOB '[A-Z][A-Z]'),
    CHECK (access_type IN ('flatrate', 'rent', 'buy'))
);

CREATE INDEX IF NOT EXISTS idx_media_watch_providers_media_id
ON media_watch_providers (media_id);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- lists table
CREATE TABLE IF NOT EXISTS lists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT NOT NULL,
    description TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,

    UNIQUE (name),

    CHECK (length(trim(name)) > 0),
    CHECK (
        updated_at IS NULL
        OR updated_at >= created_at
    )
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- genres table
CREATE TABLE IF NOT EXISTS genres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    tmdb_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    tmdb_scope TEXT NOT NULL,

    UNIQUE (tmdb_id, tmdb_scope),

    CHECK (length(trim(name)) > 0),
    CHECK (tmdb_scope IN ('movie', 'series', 'movie_series'))
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- languages table
CREATE TABLE IF NOT EXISTS languages (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,

    CHECK (code GLOB '[a-z][a-z]'),
    CHECK (length(trim(name)) > 0)
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- countries table
CREATE TABLE IF NOT EXISTS countries (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,

    CHECK (code GLOB '[A-Z][A-Z]'),
    CHECK (length(trim(name)) > 0)
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- companies table
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    tmdb_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,

    CHECK (length(trim(name)) > 0)
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- people table
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    tmdb_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,

    CHECK (length(trim(name)) > 0)
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_lists table
CREATE TABLE IF NOT EXISTS media_lists (
    media_id INTEGER NOT NULL,
    list_id INTEGER NOT NULL,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (media_id, list_id),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (list_id)
        REFERENCES lists(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_genres table
CREATE TABLE IF NOT EXISTS media_genres (
    media_id INTEGER NOT NULL,
    genre_id INTEGER NOT NULL,

    PRIMARY KEY (media_id, genre_id),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (genre_id)
        REFERENCES genres(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_spoken_languages table
CREATE TABLE IF NOT EXISTS media_spoken_languages (
    media_id INTEGER NOT NULL,
    language_code TEXT NOT NULL,

    PRIMARY KEY (media_id, language_code),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (language_code)
        REFERENCES languages(code)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_origin_language table
CREATE TABLE IF NOT EXISTS media_origin_language (
    media_id INTEGER PRIMARY KEY,
    language_code TEXT NOT NULL,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (language_code)
        REFERENCES languages(code)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_production_countries table
CREATE TABLE IF NOT EXISTS media_production_countries (
    media_id INTEGER NOT NULL,
    country_code TEXT NOT NULL,

    PRIMARY KEY (media_id, country_code),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (country_code)
        REFERENCES countries(code)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_production_companies table
CREATE TABLE IF NOT EXISTS media_production_companies (
    media_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL,

    PRIMARY KEY (media_id, company_id),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_directors table
CREATE TABLE IF NOT EXISTS media_directors (
    media_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,

    PRIMARY KEY (media_id, person_id),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (person_id)
        REFERENCES people(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_creators table
CREATE TABLE IF NOT EXISTS media_creators (
    media_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,

    PRIMARY KEY (media_id, person_id),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (person_id)
        REFERENCES people(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_writers table
CREATE TABLE IF NOT EXISTS media_writers (
    media_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    job TEXT NOT NULL,

    PRIMARY KEY (media_id, person_id, job),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (person_id)
        REFERENCES people(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_actors table
CREATE TABLE IF NOT EXISTS media_actors (
    media_id INTEGER NOT NULL,
    person_id INTEGER NOT NULL,
    character TEXT,
    cast_order INTEGER,

    PRIMARY KEY (media_id, person_id),

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    FOREIGN KEY (person_id)
        REFERENCES people(id)
        ON DELETE CASCADE
);
-- ----------------------------------------------------------

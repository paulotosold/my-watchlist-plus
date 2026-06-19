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

    COUNT(DISTINCT ed.season_num) AS season_count,
    COUNT(ed.media_id) AS episode_count,

    MIN(e.release_date) AS first_air_date,
    MAX(e.release_date) AS last_air_date,

    COALESCE(SUM(e.runtime_min), 0) AS total_runtime_min

FROM media s

LEFT JOIN episode_details ed
    ON ed.series_id = s.id

LEFT JOIN media e
    ON e.id = ed.media_id

WHERE s.media_type = 'series'

GROUP BY s.id;
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
-- raw_input_history table (only confirmed inputs are recorded)
CREATE TABLE IF NOT EXISTS raw_input_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    user_input TEXT NOT NULL,
    media_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE SET NULL
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- user_notes table
CREATE TABLE IF NOT EXISTS user_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    media_id INTEGER NOT NULL,
    user_note TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_notes_media_id
    ON user_notes (media_id);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_state table
CREATE TABLE IF NOT EXISTS media_state (
    media_id INTEGER PRIMARY KEY,

    watch_state TEXT NOT NULL,
    rating INTEGER,
    is_collection_pick INTEGER,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    CHECK (watch_state IN (
        'suggested',
        'to_watch',
        'watched',
        'watching',
        'not_interested',
        'dropped'
    )),

    CHECK (rating IS NULL OR rating BETWEEN 0 AND 10),

    CHECK (is_collection_pick IS NULL OR is_collection_pick IN (0, 1))
);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- watch_history table
CREATE TABLE IF NOT EXISTS watch_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    media_id INTEGER NOT NULL,
    date_earliest TEXT,
    date_latest TEXT,

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT,

    FOREIGN KEY (media_id)
        REFERENCES media(id)
        ON DELETE CASCADE,

    CHECK (
        date_earliest IS NULL
        OR (
            date_earliest = date(date_earliest)
            AND date_earliest GLOB '????-??-??'
        )
    ),

    CHECK (
        date_latest IS NULL
        OR (
            date_latest = date(date_latest)
            AND date_latest GLOB '????-??-??'
        )
    ),

    CHECK (
        date_earliest IS NULL
        OR date_latest IS NULL
        OR date_latest >= date_earliest
    )
);

CREATE INDEX IF NOT EXISTS idx_watch_history_media_id
ON watch_history (media_id);
-- ----------------------------------------------------------

-- ----------------------------------------------------------
-- media_watch_providers table
CREATE TABLE IF NOT EXISTS media_watch_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    media_id INTEGER NOT NULL,
    provider_tmdb_id INTEGER NOT NULL,
    provider_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    access_type TEXT NOT NULL,

    checked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

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

    entry_note TEXT,
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

CREATE TABLE IF NOT EXISTS patch_sessions (
    id                  TEXT PRIMARY KEY,
    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
    title               TEXT NOT NULL,
    subsystem           TEXT DEFAULT 'ASoC',
    kernel_version      TEXT,
    source_path         TEXT,
    llm_model           TEXT,
    max_rounds          INTEGER DEFAULT 5,
    input_type          TEXT,
    original_patch      TEXT NOT NULL,
    final_patch         TEXT,
    verdict             TEXT DEFAULT 'IN_PROGRESS',
    total_rounds        INTEGER DEFAULT 0,
    total_issues_found  INTEGER DEFAULT 0,
    total_issues_fixed  INTEGER DEFAULT 0,
    submission_status   TEXT DEFAULT 'PENDING',
    submission_target   TEXT,
    submission_url      TEXT,
    kb_contributed      BOOLEAN DEFAULT 0,
    interrupt_count     INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS session_rounds (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES patch_sessions(id),
    round_number    INTEGER NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    issues_found    INTEGER DEFAULT 0,
    issues_fixed    INTEGER DEFAULT 0,
    improvement_pct REAL DEFAULT 0.0,
    chanakya_input  TEXT,
    chanakya_output TEXT,
    aryabhata_input TEXT,
    aryabhata_output TEXT,
    round_diff      TEXT,
    duration_secs   REAL,
    verdict         TEXT
);

CREATE TABLE IF NOT EXISTS session_messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES patch_sessions(id),
    round_id    TEXT REFERENCES session_rounds(id),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    agent       TEXT NOT NULL,
    msg_type    TEXT NOT NULL,
    content     TEXT NOT NULL,
    metadata    TEXT
);

CREATE TABLE IF NOT EXISTS session_references (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES patch_sessions(id),
    round_id    TEXT REFERENCES session_rounds(id),
    source      TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    author      TEXT,
    date        TEXT,
    similarity  REAL,
    subsystem   TEXT,
    summary     TEXT
);

CREATE TABLE IF NOT EXISTS session_exports (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES patch_sessions(id),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    export_type TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_size   INTEGER
);

CREATE INDEX IF NOT EXISTS idx_sessions_subsystem ON patch_sessions(subsystem);
CREATE INDEX IF NOT EXISTS idx_sessions_verdict ON patch_sessions(verdict);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON patch_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_messages_session ON session_messages(session_id);
CREATE INDEX IF NOT EXISTS idx_rounds_session ON session_rounds(session_id);

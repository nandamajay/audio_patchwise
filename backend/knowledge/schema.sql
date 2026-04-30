CREATE TABLE IF NOT EXISTS sessions (
    session_id    TEXT PRIMARY KEY,
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    patch_input   TEXT,
    context       TEXT,
    config        TEXT,
    current_round INTEGER DEFAULT 0,
    max_rounds    INTEGER DEFAULT 5,
    conversation  TEXT,
    issues_found  TEXT,
    final_patch   TEXT,
    review_report TEXT,
    verdict       TEXT,
    submission    TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON sessions(created_at DESC);

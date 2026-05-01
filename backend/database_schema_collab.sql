-- Collaborative mode tables
CREATE TABLE IF NOT EXISTS collab_sessions (
    id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    session_id    TEXT NOT NULL,
    share_token   TEXT UNIQUE NOT NULL,
    owner_id      TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'co_reviewer',
    expires_at    TEXT,
    password_hash TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collab_comments (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL,
    user_id     TEXT NOT NULL,
    username    TEXT NOT NULL,
    message_ref TEXT,
    comment     TEXT NOT NULL,
    role        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS collab_pins (
    id          TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(8)))),
    session_id  TEXT NOT NULL,
    message_ref TEXT NOT NULL,
    pinned_by   TEXT NOT NULL,
    note        TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_collab_session ON collab_sessions(session_id);
CREATE INDEX IF NOT EXISTS idx_collab_comments ON collab_comments(session_id);

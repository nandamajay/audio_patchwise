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

CREATE TABLE IF NOT EXISTS subsystem_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subsystem TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    rule_content TEXT NOT NULL,
    confidence REAL DEFAULT 0.5,
    source TEXT DEFAULT 'learned',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fix_patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subsystem TEXT DEFAULT 'alsa-asoc',
    issue_type TEXT NOT NULL,
    issue_context TEXT,
    fix_applied TEXT NOT NULL,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(issue_type, fix_applied)
);

CREATE TABLE IF NOT EXISTS maintainer_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maintainer_email TEXT NOT NULL,
    preference_type TEXT NOT NULL,
    preference_detail TEXT,
    confidence REAL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cover_letter_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subsystem TEXT NOT NULL,
    template_content TEXT NOT NULL,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_weights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    vote TEXT NOT NULL,
    weight_delta REAL DEFAULT 0.0,
    feedback_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS patch_version_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    chain_data TEXT NOT NULL,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lkml_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL UNIQUE,
    subject TEXT,
    author TEXT,
    date TEXT,
    subsystem TEXT,
    thread_url TEXT,
    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lkml_seed_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subsystem TEXT NOT NULL,
    patches_count INTEGER DEFAULT 0,
    last_seeded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;

-- Long-term persistence for learner progress.
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    target_lang TEXT NOT NULL DEFAULT 'spanish',
    gender TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS lesson_progress (
    user_id TEXT NOT NULL,
    lesson_id TEXT NOT NULL,
    language TEXT NOT NULL,
    status TEXT NOT NULL,           -- 'started' | 'completed'
    score REAL,
    completed_at TEXT,
    PRIMARY KEY (user_id, lesson_id)
);

CREATE TABLE IF NOT EXISTS vocab_mastery (
    user_id TEXT NOT NULL,
    language TEXT NOT NULL,
    word TEXT NOT NULL,
    -- SM-2 fields
    interval_days REAL NOT NULL DEFAULT 0,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    repetitions INTEGER NOT NULL DEFAULT 0,
    due_at TEXT NOT NULL,
    correct_count INTEGER NOT NULL DEFAULT 0,
    incorrect_count INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, language, word)
);

CREATE TABLE IF NOT EXISTS mistakes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    language TEXT NOT NULL,
    lesson_id TEXT,
    expected TEXT,
    got TEXT,
    error_type TEXT,                -- 'gender' | 'verb_form' | 'vocab' | 'pronunciation' | 'other'
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at TEXT,
    summary TEXT
);

CREATE INDEX IF NOT EXISTS idx_vocab_due ON vocab_mastery(user_id, due_at);
CREATE INDEX IF NOT EXISTS idx_mistakes_user ON mistakes(user_id, created_at);

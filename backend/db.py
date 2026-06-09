from __future__ import annotations

import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS manual_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    input_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(session_date, input_type)
);

CREATE TABLE IF NOT EXISTS session_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL UNIQUE,
    timeframe_context_json TEXT,
    levels_json TEXT,
    volatility_json TEXT,
    calendar_json TEXT,
    overnight_json TEXT,
    qqq_nq_ratio REAL,
    volatility_indication_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    scenario_number INTEGER NOT NULL,
    setup_type TEXT NOT NULL,
    rationale TEXT NOT NULL,
    targets TEXT NOT NULL,
    invalidated_if TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(session_date, scenario_number)
);

CREATE TABLE IF NOT EXISTS session_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    indicators_json TEXT NOT NULL,
    regime_name TEXT,
    regime_confidence REAL,
    regime_details_json TEXT,
    setup_score REAL,
    score_breakdown_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date_time ON session_snapshots(session_date, snapshot_time);

CREATE TABLE IF NOT EXISTS market_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    conditions_json TEXT NOT NULL,
    characteristics TEXT NOT NULL,
    risk_adjustments_json TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    parent_regime TEXT DEFAULT '',
    subtype TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scoring_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    condition_json TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tagged_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_datetime TEXT NOT NULL,
    exit_datetime TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    quantity INTEGER DEFAULT 1,
    pnl REAL DEFAULT 0.0,
    net_pnl REAL DEFAULT 0.0,
    tags_json TEXT NOT NULL DEFAULT '{}',
    tags_auto INTEGER DEFAULT 1,
    snapshot_id INTEGER REFERENCES session_snapshots(id),
    import_hash TEXT UNIQUE,
    exported_to_dashboard INTEGER DEFAULT 0,
    base_symbol TEXT DEFAULT '',
    commission REAL DEFAULT 0.0,
    max_open_profit REAL DEFAULT 0.0,
    max_open_loss REAL DEFAULT 0.0,
    duration_seconds REAL DEFAULT 0.0,
    fill_count INTEGER DEFAULT 1,
    point_value REAL DEFAULT 1.0,
    tick_size REAL DEFAULT 0.01,
    tick_value REAL DEFAULT 0.01,
    note TEXT DEFAULT '',
    setup_tag TEXT DEFAULT '',
    key_indicators_tags TEXT DEFAULT '',
    scoring_criteria_tags TEXT DEFAULT '',
    additional_tag TEXT DEFAULT '',
    setup_rating REAL DEFAULT 0.0,
    comments TEXT DEFAULT '',
    is_merged INTEGER DEFAULT 0,
    merge_source_ids TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tagged_session ON tagged_trades(session_date);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS active_setup_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    setup_type TEXT NOT NULL,
    marked_at TEXT DEFAULT (datetime('now'))
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA_SQL)
    # Migrate existing databases that predate new columns
    _add_column_if_missing(conn, "session_data", "volatility_indication_json", "TEXT")
    _add_column_if_missing(conn, "session_data", "nq_last_price", "REAL")
    _add_column_if_missing(conn, "scenarios", "invalidated_if", "TEXT NOT NULL DEFAULT ''")
    _migrate_scenarios_table(conn)
    _migrate_regime_rules_to_market_scenarios(conn)
    _add_setup_type_to_scoring_criteria(conn)
    _add_column_if_missing(conn, "tagged_trades", "base_symbol", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "commission", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "tagged_trades", "max_open_profit", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "tagged_trades", "max_open_loss", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "tagged_trades", "duration_seconds", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "tagged_trades", "fill_count", "INTEGER DEFAULT 1")
    _add_column_if_missing(conn, "tagged_trades", "point_value", "REAL DEFAULT 1.0")
    _add_column_if_missing(conn, "tagged_trades", "tick_size", "REAL DEFAULT 0.01")
    _add_column_if_missing(conn, "tagged_trades", "tick_value", "REAL DEFAULT 0.01")
    _add_column_if_missing(conn, "tagged_trades", "note", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "setup_tag", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "key_indicators_tags", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "scoring_criteria_tags", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "additional_tag", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "setup_rating", "REAL DEFAULT 0.0")
    _add_column_if_missing(conn, "tagged_trades", "comments", "TEXT DEFAULT ''")
    _add_column_if_missing(conn, "tagged_trades", "is_merged", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "tagged_trades", "merge_source_ids", "TEXT DEFAULT ''")
    conn.commit()

    # Seed initial feature store data
    from backend.feature_store.seed_scenarios import seed_market_scenarios, seed_scoring_criteria
    seed_market_scenarios(conn)
    seed_scoring_criteria(conn)


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    col_type: str,
) -> None:
    existing = {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")


def _migrate_scenarios_table(conn: sqlite3.Connection) -> None:
    """Recreate scenarios table if it has the old schema (location column or CHECK constraint)."""
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(scenarios)").fetchall()
    }
    if not columns or "location" in columns:
        conn.execute("DROP TABLE IF EXISTS scenarios")
        conn.executescript("""
CREATE TABLE IF NOT EXISTS scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    scenario_number INTEGER NOT NULL,
    setup_type TEXT NOT NULL,
    rationale TEXT NOT NULL,
    targets TEXT NOT NULL,
    invalidated_if TEXT NOT NULL DEFAULT '',
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(session_date, scenario_number)
);
""")


def _migrate_regime_rules_to_market_scenarios(conn: sqlite3.Connection) -> None:
    """Migrate legacy `regime_rules` table to `market_scenarios`.

    If the old `regime_rules` table exists its rows are copied into
    `market_scenarios` with `is_active = 0` so they don't pollute the
    active scenario list.  The old table is then dropped.
    """
    # Check whether the legacy table still exists.
    legacy_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='regime_rules'"
    ).fetchone()
    if not legacy_exists:
        return

    # Ensure the destination table exists (schema may have just been created).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_scenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            conditions_json TEXT NOT NULL,
            characteristics TEXT NOT NULL,
            risk_adjustments_json TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            parent_regime TEXT DEFAULT '',
            subtype TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Copy all rows, marking them inactive so they don't conflict.
    conn.execute("""
        INSERT OR IGNORE INTO market_scenarios
            (name, conditions_json, characteristics, risk_adjustments_json,
             is_active, created_at, updated_at)
        SELECT
            name, conditions_json, characteristics, risk_adjustments_json,
            0, created_at, updated_at
        FROM regime_rules
    """)

    conn.execute("DROP TABLE regime_rules")


def _add_setup_type_to_scoring_criteria(conn: sqlite3.Connection) -> None:
    """Add the nullable `setup_type` column to `scoring_criteria` if absent."""
    _add_column_if_missing(conn, "scoring_criteria", "setup_type", "TEXT")

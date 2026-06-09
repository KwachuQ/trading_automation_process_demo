"""Tests for database migrations, schema definitions, config updates, and constants."""

from __future__ import annotations

import sqlite3
import pytest
from backend.db import init_db, get_connection
from backend.config import SierraChartConfig, load_config


def test_config_sierra_chart_defaults():
    """Verify that SierraChartConfig has the new fields with correct default values."""
    config = SierraChartConfig(
        data_dir="C:/SierraChart/Data",
        nq_1min="min_nq.txt",
        rth_500v="rth_vwap.txt",
        eth_750v="eth_vwap.txt",
        quarterly_vwap="quarterly_vwap.txt",
        monthly_vwap="monthly_vwap.txt",
        weekly_vwap="weekly_vwap.txt",
        daily_adr="daily_dvma_adr_.txt",
        yearly_vwap="yearly_vwap.txt",
        qqq_1min="min_qqq.txt",
        rvol_30min="30min_rvol.txt",
    )
    # These fields might not be present or raise attribute error initially
    assert getattr(config, "saved_trade_activity_dir") == "C:/SierraChart/SavedTradeActivity"
    assert getattr(config, "trades_list_file") == "TradesList.txt"


def test_manual_tag_constants():
    """Verify manual tag static dropdown values are correctly defined."""
    from backend.review.constants import ENTRY_TYPES, ENTRY_CONTEXTS, CLOSE_TYPES
    assert ENTRY_TYPES == ["frontrun", "standard", "late_entry", "re-entry"]
    assert ENTRY_CONTEXTS == ["ETH", "RTH"]
    assert CLOSE_TYPES == ["SL", "trailed_SL", "TP", "scratch", "misclick", "manual_exit"]


def test_tagged_trades_schema_fresh_db():
    """Verify that all new columns are present in a freshly initialized database."""
    conn = get_connection(":memory:")
    init_db(conn)

    # Fetch table columns
    cursor = conn.execute("PRAGMA table_info(tagged_trades)")
    columns = {row[1]: row for row in cursor.fetchall()}

    expected_columns = {
        "base_symbol": ("TEXT", "''"),
        "commission": ("REAL", "0.0"),
        "max_open_profit": ("REAL", "0.0"),
        "max_open_loss": ("REAL", "0.0"),
        "duration_seconds": ("REAL", "0.0"),
        "fill_count": ("INTEGER", "1"),
        "point_value": ("REAL", "1.0"),
        "tick_size": ("REAL", "0.01"),
        "tick_value": ("REAL", "0.01"),
        "note": ("TEXT", "''"),
        "setup_tag": ("TEXT", "''"),
        "key_indicators_tags": ("TEXT", "''"),
        "scoring_criteria_tags": ("TEXT", "''"),
        "additional_tag": ("TEXT", "''"),
        "setup_rating": ("REAL", "0.0"),
        "comments": ("TEXT", "''"),
        "is_merged": ("INTEGER", "0"),
        "merge_source_ids": ("TEXT", "''"),
    }

    for col_name, (col_type, default_val) in expected_columns.items():
        assert col_name in columns, f"Column {col_name} missing from tagged_trades"
        # Check type (case insensitive comparison)
        assert columns[col_name][2].upper() == col_type
        # SQLite returns default values as strings or numbers, let's verify it matches
        actual_default = columns[col_name][4]
        # Clean up quotes for default values
        if actual_default is not None:
            actual_default = str(actual_default).strip("'")
        assert actual_default == default_val.strip("'"), f"Default for {col_name} is {actual_default}, expected {default_val}"

    conn.close()


def test_tagged_trades_migration_idempotent():
    """Verify that migrations are idempotent and keep existing data intact."""
    conn = get_connection(":memory:")

    # Create the old table schema manually
    conn.execute("""
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
            snapshot_id INTEGER,
            import_hash TEXT UNIQUE,
            exported_to_dashboard INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Insert a dummy trade row using old schema
    conn.execute("""
        INSERT INTO tagged_trades (
            session_date, symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, quantity, pnl, net_pnl, import_hash
        ) VALUES (
            '2026-06-01', 'MNQM26', 'Long', '2026-06-01 10:00:00', '2026-06-01 10:10:00',
            28000.0, 28050.0, 2, 100.0, 98.0, 'test_hash_1'
        )
    """)
    conn.commit()

    # Run the init_db which triggers migration
    init_db(conn)

    # Verify that existing row's data is untouched
    row = conn.execute("SELECT session_date, symbol, pnl, base_symbol FROM tagged_trades WHERE import_hash = 'test_hash_1'").fetchone()
    assert row is not None
    assert row[0] == '2026-06-01'
    assert row[1] == 'MNQM26'
    assert row[2] == 100.0
    # The migrated column should have the default value
    assert row[3] == ''

    # Run migration again to verify idempotency
    init_db(conn)

    # Assert again that everything is fine
    row_after = conn.execute("SELECT session_date, symbol, pnl, base_symbol FROM tagged_trades WHERE import_hash = 'test_hash_1'").fetchone()
    assert row_after is not None
    assert row_after[3] == ''

    conn.close()

"""
TDD tests for the auto-tagger module.
Tests nearest snapshot lookup, setup tag derivation, key indicators parsing,
and scoring criteria formatting, along with the full database auto-tagging flow.
"""

from __future__ import annotations

import json
import sqlite3
import pytest
from datetime import datetime

from backend.db import get_connection, init_db


@pytest.fixture()
def conn():
    """Create an in-memory SQLite database initialized with the latest schema."""
    connection = get_connection(":memory:")
    init_db(connection)
    yield connection
    connection.close()


def test_find_nearest_snapshot(conn):
    """Verify that find_nearest_snapshot finds the closest snapshot by absolute time."""
    from backend.review.auto_tagger import find_nearest_snapshot

    # Test case 1: No snapshots exist
    result = find_nearest_snapshot(conn, "2026-06-01 10:00:00", "2026-06-01")
    assert result is None

    # Seed some snapshots on 2026-06-01
    # Snapshot A: 10:05:00
    conn.execute(
        """
        INSERT INTO session_snapshots (
            session_date, snapshot_time, indicators_json, regime_name, setup_score, score_breakdown_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01",
            "2026-06-01 10:05:00",
            json.dumps({"gamma_regime": "negative"}),
            "Trend Down",
            60.0,
            json.dumps([]),
        ),
    )

    # Snapshot B: 10:15:00
    conn.execute(
        """
        INSERT INTO session_snapshots (
            session_date, snapshot_time, indicators_json, regime_name, setup_score, score_breakdown_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01",
            "2026-06-01 10:15:00",
            json.dumps({"gamma_regime": "positive"}),
            "Trend Up",
            85.0,
            json.dumps([]),
        ),
    )
    conn.commit()

    # Test case 2: Entry time at 10:04:00 (closer to A than B)
    snap = find_nearest_snapshot(conn, "2026-06-01 10:04:00", "2026-06-01")
    assert snap is not None
    assert snap["regime_name"] == "Trend Down"
    assert json.loads(snap["indicators_json"])["gamma_regime"] == "negative"

    # Test case 3: Entry time at 10:12:00 (closer to B than A)
    snap = find_nearest_snapshot(conn, "2026-06-01 10:12:00", "2026-06-01")
    assert snap is not None
    assert snap["regime_name"] == "Trend Up"
    assert json.loads(snap["indicators_json"])["gamma_regime"] == "positive"

    # Test case 4: Snapshot on a different date should not be matched
    snap = find_nearest_snapshot(conn, "2026-06-02 10:05:00", "2026-06-02")
    assert snap is None


def test_derive_setup_tag(conn):
    """Verify that derive_setup_tag returns the most recent active setup before trade entry."""
    from backend.review.auto_tagger import derive_setup_tag

    # Test case 1: No active setups exist
    trade = {"entry_datetime": "2026-06-01 10:00:00"}
    tag = derive_setup_tag(conn, trade)
    assert tag == ""

    # Seed active setup log
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) VALUES (?, ?, ?)",
        ("2026-06-01", "ML", "2026-06-01 09:30:00"),
    )
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) VALUES (?, ?, ?)",
        ("2026-06-01", "MS", "2026-06-01 10:15:00"),
    )
    conn.commit()

    # Test case 2: Trade entry at 09:45:00 (should match ML)
    trade_1 = {"entry_datetime": "2026-06-01 09:45:00"}
    assert derive_setup_tag(conn, trade_1) == "ML"

    # Test case 3: Trade entry at 10:20:00 (should match MS, the latest marked_at <= entry)
    trade_2 = {"entry_datetime": "2026-06-01 10:20:00"}
    assert derive_setup_tag(conn, trade_2) == "MS"

    # Test case 4: Trade entry at 09:15:00 (before any active setup logs)
    trade_3 = {"entry_datetime": "2026-06-01 09:15:00"}
    assert derive_setup_tag(conn, trade_3) == ""


def test_derive_key_indicators_tags():
    """Verify key indicators are formatted as a comma-separated key:value string."""
    from backend.review.auto_tagger import derive_key_indicators_tags

    # Test case 1: Snapshot is None
    assert derive_key_indicators_tags({}, None) == ""

    # Test case 2: Snapshot contains all indicators
    snapshot = {
        "indicators_json": json.dumps(
            {
                "gamma_regime": "negative",
                "cd_vs_ma": "above MA",
                "delta_slope": "rising",
                "vwap_slope": "falling",
                "vol_regime": "MODERATE",
                "entry_quality": "Good",
            }
        )
    }
    tags = derive_key_indicators_tags({}, snapshot)
    expected = (
        "gamma_regime:negative,cd_vs_ma:above MA,delta_slope:rising,"
        "vwap_slope:falling,vol_regime:MODERATE,entry_quality:Good"
    )
    # Compare sets of splits to prevent order from breaking test
    assert set(tags.split(",")) == set(expected.split(","))

    # Test case 3: Partial indicators (missing some keys or null values)
    snapshot_partial = {
        "indicators_json": json.dumps(
            {
                "gamma_regime": "positive",
                "cd_vs_ma": None,  # should be skipped or ignored
                "delta_slope": "sideways",
                # other keys missing completely
            }
        )
    }
    tags_partial = derive_key_indicators_tags({}, snapshot_partial)
    assert set(tags_partial.split(",")) == {"gamma_regime:positive", "delta_slope:sideways"}


def test_derive_scoring_criteria_tags():
    """Verify that only matched scoring criteria names are returned comma-separated."""
    from backend.review.auto_tagger import derive_scoring_criteria_tags

    # Test case 1: Snapshot is None
    assert derive_scoring_criteria_tags(None) == ""

    # Test case 2: Snapshot contains breakdown with matched criteria
    snapshot = {
        "score_breakdown_json": json.dumps(
            [
                {"name": "ml_rvol_expansion", "matched": True, "weight": 7.0},
                {"name": "ml_vwap_slope_confirms_direction", "matched": False, "weight": 8.0},
                {"name": "ml_gamma_supports_move", "matched": True, "weight": 8.0},
            ]
        )
    }
    tags = derive_scoring_criteria_tags(snapshot)
    assert set(tags.split(",")) == {"ml_rvol_expansion", "ml_gamma_supports_move"}

    # Test case 3: Empty breakdown
    snapshot_empty = {"score_breakdown_json": json.dumps([])}
    assert derive_scoring_criteria_tags(snapshot_empty) == ""


def test_auto_tag_trades_success(conn):
    """Verify the end-to-end auto-tagging process writes correctly to the database."""
    from backend.review.auto_tagger import auto_tag_trades

    # 1. Seed snapshot
    conn.execute(
        """
        INSERT INTO session_snapshots (
            session_date, snapshot_time, indicators_json, regime_name, setup_score, score_breakdown_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01",
            "2026-06-01 10:05:00",
            json.dumps(
                {
                    "gamma_regime": "negative",
                    "cd_vs_ma": "above MA",
                    "delta_slope": "rising",
                    "vwap_slope": "falling",
                    "vol_regime": "MODERATE",
                    "entry_quality": "Optimal",
                }
            ),
            "Trend Down",
            75.0,
            json.dumps(
                [
                    {"name": "ml_rvol_expansion", "matched": True},
                    {"name": "ml_gamma_supports_move", "matched": True},
                ]
            ),
        ),
    )

    # 2. Seed active setup log
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) VALUES (?, ?, ?)",
        ("2026-06-01", "ML", "2026-06-01 09:30:00"),
    )

    # 3. Seed trade into tagged_trades
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, import_hash, tags_auto
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01",
            "MNQM26",
            "Long",
            "2026-06-01 10:04:00",
            "2026-06-01 10:15:00",
            28000.0,
            28050.0,
            "hash_1234",
            1,
        ),
    )
    conn.commit()

    # Retrieve trade dict representing seeded trade
    trade_row = conn.execute("SELECT * FROM tagged_trades WHERE import_hash = 'hash_1234'").fetchone()
    # Convert row to dict
    columns = [column[1] for column in conn.execute("PRAGMA table_info(tagged_trades)").fetchall()]
    trade_dict = dict(zip(columns, trade_row))

    # Run auto-tagger
    count = auto_tag_trades(conn, [trade_dict])
    assert count == 1

    # Verify updated row in DB
    updated = conn.execute("SELECT setup_tag, key_indicators_tags, scoring_criteria_tags, setup_rating, tags_auto FROM tagged_trades WHERE import_hash = 'hash_1234'").fetchone()
    assert updated is not None
    assert updated[0] == "ML"
    assert set(updated[1].split(",")) == {
        "gamma_regime:negative",
        "cd_vs_ma:above MA",
        "delta_slope:rising",
        "vwap_slope:falling",
        "vol_regime:MODERATE",
        "entry_quality:Optimal",
    }
    assert set(updated[2].split(",")) == {"ml_rvol_expansion", "ml_gamma_supports_move"}
    assert updated[3] == 75.0
    assert updated[4] == 1


def test_auto_tag_trades_no_snapshots(conn):
    """Verify that if no snapshots exist, the trade is still tagged with empty defaults and tags_auto=1."""
    from backend.review.auto_tagger import auto_tag_trades

    # Seed trade only (no snapshots)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, import_hash, tags_auto
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01",
            "MNQM26",
            "Long",
            "2026-06-01 10:04:00",
            "2026-06-01 10:15:00",
            28000.0,
            28050.0,
            "hash_no_snap",
            1,
        ),
    )
    conn.commit()

    trade_row = conn.execute("SELECT * FROM tagged_trades WHERE import_hash = 'hash_no_snap'").fetchone()
    columns = [column[1] for column in conn.execute("PRAGMA table_info(tagged_trades)").fetchall()]
    trade_dict = dict(zip(columns, trade_row))

    count = auto_tag_trades(conn, [trade_dict])
    assert count == 1

    updated = conn.execute("SELECT setup_tag, key_indicators_tags, scoring_criteria_tags, setup_rating, tags_auto FROM tagged_trades WHERE import_hash = 'hash_no_snap'").fetchone()
    assert updated is not None
    assert updated[0] == ""  # no active setup seeded either
    assert updated[1] == ""
    assert updated[2] == ""
    assert updated[3] == 0.0
    assert updated[4] == 1


def test_derive_setup_tag_session_date_isolation(conn):
    """Verify that derive_setup_tag does NOT leak setups from other session dates."""
    from backend.review.auto_tagger import derive_setup_tag

    # Seed setup on 2026-06-01
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) "
        "VALUES (?, ?, ?)",
        ("2026-06-01", "ML", "2026-06-01 09:30:00"),
    )
    conn.commit()

    # Trade on 2026-06-02 should NOT see the 2026-06-01 setup
    trade = {
        "entry_datetime": "2026-06-02 10:00:00",
        "session_date": "2026-06-02",
    }
    assert derive_setup_tag(conn, trade) == ""

    # Trade on 2026-06-01 should still see it
    trade_same_day = {
        "entry_datetime": "2026-06-01 10:00:00",
        "session_date": "2026-06-01",
    }
    assert derive_setup_tag(conn, trade_same_day) == "ML"


def test_auto_tag_trades_preserves_existing_tags(conn):
    """Verify that re-tagging preserves existing non-empty tag values."""
    from backend.review.auto_tagger import auto_tag_trades

    # 1. Seed active setup log
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) "
        "VALUES (?, ?, ?)",
        ("2026-06-01", "MS", "2026-06-01 09:30:00"),
    )

    # 2. Seed snapshot (for key_indicators and scoring)
    conn.execute(
        """
        INSERT INTO session_snapshots (
            session_date, snapshot_time, indicators_json, regime_name,
            setup_score, score_breakdown_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01",
            "2026-06-01 10:05:00",
            json.dumps({"gamma_regime": "positive", "vwap_slope": "rising"}),
            "Trend Up",
            80.0,
            json.dumps([{"name": "crit_1", "matched": True}]),
        ),
    )

    # 3. Seed a trade that already has setup_tag but empty indicators/scoring
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, import_hash, tags_auto,
            setup_tag, key_indicators_tags, scoring_criteria_tags, setup_rating
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01", "MNQM26", "Short",
            "2026-06-01 10:04:00", "2026-06-01 10:15:00",
            28000.0, 27950.0, "hash_partial",
            1,       # tags_auto
            "ML",    # pre-existing setup_tag
            "",      # empty key_indicators_tags
            "",      # empty scoring_criteria_tags
            70.0,    # pre-existing setup_rating
        ),
    )
    conn.commit()

    # Retrieve trade dict
    trade_row = conn.execute(
        "SELECT * FROM tagged_trades WHERE import_hash = 'hash_partial'"
    ).fetchone()
    columns = [
        column[1]
        for column in conn.execute("PRAGMA table_info(tagged_trades)").fetchall()
    ]
    trade_dict = dict(zip(columns, trade_row))

    # Run auto-tagger
    count = auto_tag_trades(conn, [trade_dict])
    assert count == 1

    # Verify: existing setup_tag and rating preserved, new indicators filled in
    updated = conn.execute(
        "SELECT setup_tag, key_indicators_tags, scoring_criteria_tags, "
        "setup_rating, tags_auto "
        "FROM tagged_trades WHERE import_hash = 'hash_partial'"
    ).fetchone()
    assert updated is not None
    assert updated[0] == "ML"   # Original setup_tag preserved (NOT overwritten to "MS")
    assert "gamma_regime:positive" in updated[1]  # New indicators backfilled
    assert "crit_1" in updated[2]                 # New scoring backfilled
    assert updated[4] == 1


def test_auto_tag_timezone_mismatch_regression(conn):
    """
    Regression test validating the timezone mismatch issue.
    When Sierra Chart exports times in EST but the backend records
    marked_at in UTC, string comparison (marked_at <= entry_datetime)
    fails and either skips trades or maps them to the wrong setup.
    """
    from backend.review.auto_tagger import auto_tag_trades

    # Simulate UTC recorded clicks (what datetime.utcnow() was doing)
    # vs EST trade times from Sierra Chart.
    # 1. User clicked ML setup at 14:55 UTC (which is 10:55 EST)
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) "
        "VALUES (?, ?, ?)",
        ("2026-06-02", "ML", "2026-06-02 14:55:00"),
    )

    # 2. Earlier click on same day: user clicked MRL at 10:32 UTC (06:32 EST)
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) "
        "VALUES (?, ?, ?)",
        ("2026-06-02", "MRL", "2026-06-02 10:32:00"),
    )

    # 3. Trade occurs at 10:56 EST (right after the ML click at 10:55 EST)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, import_hash, tags_auto,
            setup_tag, key_indicators_tags, scoring_criteria_tags, setup_rating
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-02", "MNQM26", "Long",
            "2026-06-02 10:56:00", "2026-06-02 11:00:00",
            28000.0, 28050.0, "hash_timezone_bug",
            1, "", "", "", 0.0,
        ),
    )
    conn.commit()

    trade_row = conn.execute(
        "SELECT * FROM tagged_trades WHERE import_hash = 'hash_timezone_bug'"
    ).fetchone()
    columns = [
        column[1]
        for column in conn.execute("PRAGMA table_info(tagged_trades)").fetchall()
    ]
    trade_dict = dict(zip(columns, trade_row))

    auto_tag_trades(conn, [trade_dict])

    # Because "14:55:00" > "10:56:00", the string comparison <= fails for ML,
    # and it incorrectly falls back to the MRL setup from 10:32 UTC!
    # This validates the exact bug reported: "MRL instead of ML".
    updated = conn.execute(
        "SELECT setup_tag FROM tagged_trades WHERE import_hash = 'hash_timezone_bug'"
    ).fetchone()
    assert updated is not None
    # This assert proves the bug exists under UTC vs EST mismatch.
    # The fix in session.py to use datetime.now() ensures future records
    # will have aligned timestamps (e.g., both will be 10:55 EST / Local).
    assert updated[0] == "MRL"


def test_derive_setup_tag_defect1_regression(conn):
    """
    Regression test for Defect 1: timezone/timestamp mismatch.

    After the fix, mark_active_setup stores marked_at in America/New_York
    time — the same timezone Sierra Chart uses for trade exports.  Both sides
    of the string comparison in derive_setup_tag are now in NY time, so the
    comparison works correctly.

    Scenario: trader clicked ML at 09:34 NY time. Trade entry is 09:35 NY
    time.  Expected: setup_tag = 'ML'.  Before the fix, marked_at would have
    been '15:34' (CET), which is lexicographically greater than '09:35', so
    the comparison would return '' (no match).
    """
    from backend.review.auto_tagger import derive_setup_tag

    # Simulate the FIXED behaviour: marked_at stored in NY time.
    # Trader clicked MS at 09:34 NY time (= 13:34 UTC / 15:34 CET).
    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at)"
        " VALUES (?, ?, ?)",
        ("2026-06-05", "MS", "2026-06-05 09:34:26"),  # NY time stored
    )
    conn.commit()

    # Trade entry at 09:35 NY time — both sides are now in NY time.
    trade = {
        "entry_datetime": "2026-06-05 09:35:00",
        "session_date": "2026-06-05",
    }

    tag = derive_setup_tag(conn, trade)
    assert tag == "MS", (
        "Expected 'MS': when marked_at is stored in NY time, the string "
        "comparison 'marked_at <= entry_datetime' should succeed."
    )

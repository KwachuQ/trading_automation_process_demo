"""
Tests for the Review API router endpoints.
Follows PEP 8 styling and implements test-first logic.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db import get_connection, init_db
from backend.main import app
from backend.state import app_state

# Real tab-separated header from Sierra Chart
HEADER = (
    "Symbol\tTrade Type\tEntry DateTime\tExit DateTime\tEntry Price\tExit Price\t"
    "Trade Quantity\tMax Open Quantity\tMax Closed Quantity\tProfit/Loss (C)\t"
    "Cumulative Profit/Loss (C)\tFlatToFlat Profit/Loss (C)\t"
    "FlatToFlat Max Open Profit (C)\tFlatToFlat Max Open Loss (C)\t"
    "Max Open Profit (C)\tMax Open Loss (C)\tEntry Efficiency\tExit Efficiency\t"
    "Total Efficiency\tCommission (C)\tHigh Price While Open\tLow Price While Open\t"
    "Note\tOpen Position Quantity\tClose Position Quantity\tDuration\tAccount\t"
    "Highest Cumulative P/L (C)\tLowest Cumulative P/L (C)\tMaximum Runup (C)\t"
    "Maximum Drawdown (C)"
)

# Sample F2F trade rows for test imports
SAMPLE_ROWS = [
    # MNQ Group (F2F 1)
    "MNQH26 (19850621)\tLong\t2026-02-10  14:09:50.516 BP\t2026-02-10  14:09:50.516\t15000.00\t15000.00\t1\t1\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00%\t0.00%\t0.00%\t0.52\t15000.00\t15000.00\tParent order\t1\t0\t00:00:00\t12345\t0.00\t0.00\t0.00\t0.00",
    "MNQH26 (19850621)\tLong\t2026-02-10  14:10:00.000\t2026-02-10  14:10:00.000\t15010.00\t15010.00\t1\t2\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00%\t0.00%\t0.00%\t0.52\t15010.00\t15010.00\tParent order\t2\t0\t00:00:10\t12345\t0.00\t0.00\t0.00\t0.00",
    "MNQH26 (19850621)\tShort\t2026-02-10  14:11:17.343\t2026-02-10  14:11:17.343 EP\t15050.00\t15050.00\t2\t2\t2\t160.00\t160.00\t160.00 F\t170.00\t-10.00\t170.00\t-10.00\t90.00%\t90.00%\t90.00%\t1.04\t15060.00\t14995.00\tDescriptive Exit\t0\t2\t00:01:26\t12345\t160.00\t-10.00\t170.00\t-10.00",
]


@pytest.fixture()
def client(tmp_path: Path):
    """
    Set up a test Client with an in-memory or temp SQLite database
    and temporary config state.
    """
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    app_state["db_path"] = db_path
    app_state["config"] = _make_config(tmp_path)
    yield TestClient(app, raise_server_exceptions=True), db_path, tmp_path


def _make_config(tmp_path: Path):
    """
    Return a mock/minimal Config-like object with necessary structure.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        sierra_chart=SimpleNamespace(
            saved_trade_activity_dir=str(tmp_path),
            trades_list_file="TradesList.txt",
        )
    )


@pytest.fixture()
def temp_trades_file(tmp_path: Path) -> Path:
    """
    Creates a temporary TradesList.txt file with sample data.
    """
    file_path = tmp_path / "TradesList.txt"
    content = HEADER + "\n" + "\n".join(SAMPLE_ROWS) + "\n"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def test_get_constants(client):
    """
    Test GET /api/review/constants returns static tag categories.
    """
    c, _, _ = client
    resp = c.get("/api/review/constants")
    assert resp.status_code == 200
    data = resp.json()
    assert "entry_type" in data
    assert "entry_direct_context" in data
    assert "close_type" in data
    assert "frontrun" in data["entry_type"]
    assert "ETH" in data["entry_direct_context"]
    assert "SL" in data["close_type"]


def test_import_trades_endpoint(client, temp_trades_file):
    """
    Test POST /api/review/import parses and auto-tags imported trades.
    """
    c, db_path, _ = client

    # We must seed a snapshot close to 2026-02-10 14:09:50 for auto-tagger to find it
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO session_snapshots (
            session_date, snapshot_time, indicators_json, regime_name,
            regime_confidence, setup_score, score_breakdown_json
        ) VALUES (
            '2026-02-10', '2026-02-10 14:10:00',
            '{"gamma_regime": "positive", "cd_vs_ma": "above", "delta_slope": "rising", "vwap_slope": "rising", "vol_regime": "high", "entry_quality": "Optimal"}',
            'continuation_up', 0.85, 75.0,
            '[{"name": "test_criterion", "matched": true}]'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO active_setup_log (session_date, setup_type, marked_at)
        VALUES ('2026-02-10', 'ML', '2026-02-10 14:05:00')
        """
    )
    conn.commit()
    conn.close()

    resp = c.post(f"/api/review/import?file_path={temp_trades_file}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["imported"] == 1
    assert data["skipped"] == 0
    assert data["total"] == 1
    assert len(data["trades"]) == 1

    imported_trade = data["trades"][0]
    assert imported_trade["symbol"] == "MNQH26"
    assert imported_trade["setup_tag"] == "ML"
    assert imported_trade["setup_rating"] == pytest.approx(75.0)
    assert "gamma_regime:positive" in imported_trade["key_indicators_tags"]
    assert "test_criterion" in imported_trade["scoring_criteria_tags"]


def test_import_trades_uses_default_config_path(client, temp_trades_file):
    """
    Test POST /api/review/import defaults to the config's trade file path.
    """
    c, _, _ = client

    # We patch import_trades to verify the correct path is passed
    with patch("backend.routers.review.import_trades") as mock_import, \
         patch("backend.routers.review.auto_tag_trades") as mock_tag:
        mock_import.return_value = {"imported": 0, "skipped": 0, "total": 0}
        mock_tag.return_value = 0

        resp = c.post("/api/review/import")
        assert resp.status_code == 200
        mock_import.assert_called_once()
        called_path = mock_import.call_args[0][0]
        assert "TradesList.txt" in str(called_path)


def test_get_trades_by_date(client):
    """
    Test GET /api/review/trades retrieves trades by session_date.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash
        ) VALUES (
            '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:15:00', 15000.0, 15020.0, 1, 40.0, 39.0, 'hash123'
        )
        """
    )
    conn.commit()
    conn.close()

    # Query with explicit date
    resp = c.get("/api/review/trades?session_date=2026-06-01")
    assert resp.status_code == 200
    trades = resp.json()
    assert len(trades) == 1
    assert trades[0]["symbol"] == "MNQH26"
    assert trades[0]["session_date"] == "2026-06-01"

    # Query with default (today) should return 0 if today is not 2026-06-01
    from datetime import date
    today = date.today().isoformat()
    if today != "2026-06-01":
        resp_today = c.get("/api/review/trades")
        assert resp_today.status_code == 200
        assert len(resp_today.json()) == 0


def test_get_trade_by_id(client):
    """
    Test GET /api/review/trades/{id} and returning a single trade.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    cursor = conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash
        ) VALUES (
            '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:15:00', 15000.0, 15020.0, 1, 40.0, 39.0, 'hash123'
        )
        """
    )
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()

    resp = c.get(f"/api/review/trades/{trade_id}")
    assert resp.status_code == 200
    trade = resp.json()
    assert trade["id"] == trade_id
    assert trade["symbol"] == "MNQH26"

    # Test non-existent trade ID returns 404
    resp_404 = c.get("/api/review/trades/99999")
    assert resp_404.status_code == 404


def test_patch_trade_updates_fields_and_sets_tags_auto(client):
    """
    Test PATCH /api/review/trades/{id} partially updates fields and sets tags_auto=0.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    cursor = conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash, tags_auto, setup_tag, comments, setup_rating
        ) VALUES (
            '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:15:00', 15000.0, 15020.0, 1, 40.0, 39.0, 'hash123',
            1, 'ML', 'Initial comment', 70.0
        )
        """
    )
    trade_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Update only some fields (setup_tag and comments)
    update_data = {
        "setup_tag": "MRL",
        "comments": "Updated comment",
        "setup_rating": 85.0,
    }
    resp = c.patch(f"/api/review/trades/{trade_id}", json=update_data)
    assert resp.status_code == 200
    updated_trade = resp.json()
    assert updated_trade["id"] == trade_id
    assert updated_trade["setup_tag"] == "MRL"
    assert updated_trade["comments"] == "Updated comment"
    assert updated_trade["setup_rating"] == pytest.approx(85.0)
    # Check that tags_auto has been updated to 0
    assert updated_trade["tags_auto"] == 0

    # Verify database directly
    conn = get_connection(db_path)
    row = conn.execute(
        "SELECT setup_tag, comments, tags_auto FROM tagged_trades WHERE id = ?",
        (trade_id,),
    ).fetchone()
    conn.close()
    assert row[0] == "MRL"
    assert row[1] == "Updated comment"
    assert row[2] == 0

    # Try updating non-existent trade returns 404
    resp_404 = c.patch("/api/review/trades/99999", json={"setup_tag": "MS"})
    assert resp_404.status_code == 404


def test_get_stats_route(client):
    """
    Test GET /api/review/stats calculates and returns stats and charts.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash, duration_seconds
        ) VALUES (
            '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:15:00', 15000.0, 15020.0, 1, 40.0, 39.0, 'hash1', 900.0
        )
        """
    )
    conn.commit()
    conn.close()

    resp = c.get("/api/review/stats?session_date=2026-06-01")
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert "charts" in data
    assert data["stats"]["summary"]["total_trades"] == 1
    assert data["stats"]["summary"]["total_pnl"] == 39.0


def test_get_stats_by_tag_route(client):
    """
    Test GET /api/review/stats-by-tag groups stats by unique tag values.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash, setup_tag
        ) VALUES (
            '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:15:00', 15000.0, 15020.0, 1, 40.0, 39.0, 'hash1', 'ML'
        )
        """
    )
    conn.commit()
    conn.close()

    resp = c.get("/api/review/stats-by-tag?tag_column=setup_tag&session_date=2026-06-01")
    assert resp.status_code == 200
    data = resp.json()
    assert "ML" in data
    assert data["ML"]["summary"]["total_trades"] == 1


def test_merge_trades_route(client):
    """
    Test POST /api/review/trades/merge successfully combines multiple trades.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            id, session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash, setup_tag
        ) VALUES (
            10, '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:05:00', 15000.0, 15010.0, 1, 20.0, 19.0, 'hash1', 'ML'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO tagged_trades (
            id, session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash, setup_tag
        ) VALUES (
            11, '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:10:00',
            '2026-06-01 10:15:00', 15010.0, 15020.0, 1, 20.0, 19.0, 'hash2', 'MS'
        )
        """
    )
    conn.commit()
    conn.close()

    resp = c.post("/api/review/trades/merge", json={"trade_ids": [10, 11]})
    assert resp.status_code == 200
    data = resp.json()
    assert "merged_trade" in data
    assert "stats" in data
    assert data["merged_trade"]["PnL"] == 40.0
    assert data["merged_trade"]["Size"] == 2
    assert data["merged_trade"]["Setup Tag"] == "ML"  # Preserved from first trade


def test_delete_trade_route(client):
    """
    Test DELETE /api/review/trades/{id} deletes the trade and returns updated stats.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            id, session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash
        ) VALUES (
            10, '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:05:00', 15000.0, 15010.0, 1, 20.0, 19.0, 'hash1'
        )
        """
    )
    conn.commit()
    conn.close()

    resp = c.delete("/api/review/trades/10")
    assert resp.status_code == 200
    data = resp.json()
    assert "stats" in data
    assert data["stats"]["stats"]["summary"]["total_trades"] == 0

    # Verify directly from DB
    conn = get_connection(db_path)
    row = conn.execute("SELECT 1 FROM tagged_trades WHERE id = 10").fetchone()
    assert row is None
    conn.close()


def test_recalculate_commissions_route(client):
    """
    Test POST /api/review/recalculate-commissions triggers commission updates.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, commission, net_pnl,
            import_hash
        ) VALUES (
            '2026-06-01', 'MNQH26', 'MNQ', 'Long', '2026-06-01 10:00:00',
            '2026-06-01 10:05:00', 15000.0, 15010.0, 1, 20.0, 0.0, 20.0, 'hash1'
        )
        """
    )
    conn.commit()
    conn.close()

    resp = c.post("/api/review/recalculate-commissions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] == 1
    assert "stats" in data


# ---------------------------------------------------------------------------
# Tests for the date-range filter fix on GET /api/review/trades
# ---------------------------------------------------------------------------

def _seed_trade(conn, trade_id: int, session_date: str, import_hash: str) -> None:
    """
    Helper: insert a minimal valid tagged_trades row for the given date.
    Kept DRY so all range tests share the same seed logic.
    """
    conn.execute(
        """
        INSERT INTO tagged_trades (
            id, session_date, symbol, base_symbol, direction, entry_datetime,
            exit_datetime, entry_price, exit_price, quantity, pnl, net_pnl,
            import_hash
        ) VALUES (?, ?, 'MNQH26', 'MNQ', 'Long',
                  ? || ' 10:00:00', ? || ' 10:15:00',
                  15000.0, 15020.0, 1, 40.0, 39.0, ?)
        """,
        (trade_id, session_date, session_date, session_date, import_hash),
    )


def test_list_trades_date_range_returns_all_trades_within_bounds(client):
    """
    Root-cause fix regression test:
    GET /api/review/trades?date_from=...&date_to=... must return every trade
    whose session_date falls within the inclusive range and exclude trades
    that fall outside.

    Seed three trades across three different dates:
      - 2026-06-01  (inside range)
      - 2026-06-04  (inside range)
      - 2026-06-10  (outside range, after date_to)
    Querying date_from=2026-06-01&date_to=2026-06-07 must return 2 trades.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    _seed_trade(conn, 1, "2026-06-01", "hash_a")
    _seed_trade(conn, 2, "2026-06-04", "hash_b")
    _seed_trade(conn, 3, "2026-06-10", "hash_c")
    conn.commit()
    conn.close()

    resp = c.get("/api/review/trades?date_from=2026-06-01&date_to=2026-06-07")
    assert resp.status_code == 200
    trades = resp.json()

    returned_dates = {t["session_date"] for t in trades}
    assert returned_dates == {"2026-06-01", "2026-06-04"}, (
        "Only dates within the range should be returned"
    )
    assert len(trades) == 2


def test_list_trades_date_range_is_inclusive_on_both_bounds(client):
    """
    The BETWEEN clause must include trades on the exact boundary dates
    (date_from itself and date_to itself).
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    _seed_trade(conn, 10, "2026-06-01", "hash_start")  # exactly on date_from
    _seed_trade(conn, 11, "2026-06-07", "hash_end")    # exactly on date_to
    _seed_trade(conn, 12, "2026-06-08", "hash_after")  # one day after date_to
    conn.commit()
    conn.close()

    resp = c.get("/api/review/trades?date_from=2026-06-01&date_to=2026-06-07")
    assert resp.status_code == 200
    trades = resp.json()

    returned_ids = {t["id"] for t in trades}
    assert 10 in returned_ids, "Trade on date_from should be included"
    assert 11 in returned_ids, "Trade on date_to should be included"
    assert 12 not in returned_ids, "Trade after date_to should be excluded"


def test_list_trades_session_date_still_works_without_range_params(client):
    """
    Backwards-compatibility check: the original ?session_date=... param must
    still work exactly as before the fix — returning only that single day.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    _seed_trade(conn, 20, "2026-06-01", "hash_today")
    _seed_trade(conn, 21, "2026-06-02", "hash_tomorrow")
    conn.commit()
    conn.close()

    resp = c.get("/api/review/trades?session_date=2026-06-01")
    assert resp.status_code == 200
    trades = resp.json()

    assert len(trades) == 1
    assert trades[0]["session_date"] == "2026-06-01", (
        "Single-day session_date query must not leak into adjacent dates"
    )


def test_bulk_delete_trades_route(client):
    """
    Test POST /api/review/trades/bulk-delete successfully deletes multiple trades.
    """
    c, db_path, _ = client
    conn = get_connection(db_path)
    # Seed three trades across different session dates
    _seed_trade(conn, 30, "2026-06-01", "hash_30")
    _seed_trade(conn, 31, "2026-06-01", "hash_31")
    _seed_trade(conn, 32, "2026-06-02", "hash_32")
    conn.commit()
    conn.close()

    # Bulk delete trade 30 and 31
    resp = c.post("/api/review/trades/bulk-delete", json={"trade_ids": [30, 31]})
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    assert 30 in data["trade_ids"]
    assert 31 in data["trade_ids"]

    # Verify directly from DB that 30 and 31 are gone, but 32 remains
    conn = get_connection(db_path)
    remaining = conn.execute("SELECT id FROM tagged_trades ORDER BY id").fetchall()
    remaining_ids = [row[0] for row in remaining]
    assert remaining_ids == [32]
    conn.close()


def test_bulk_delete_trades_validation(client):
    """
    Test POST /api/review/trades/bulk-delete returns 400 when trade_ids is empty.
    """
    c, _, _ = client
    resp = c.post("/api/review/trades/bulk-delete", json={"trade_ids": []})
    assert resp.status_code == 400




"""Tests for stats computation and trade management.

Verifies summary statistics, chart data preparation, tag-based grouping,
and DB operations (merge, delete, commission recalculation).
"""

from __future__ import annotations

import json
import sqlite3
import pytest

from backend.db import get_connection, init_db
from backend.review.stats import (
    compute_stats,
    compute_stats_by_tag,
    prepare_charts_data,
)
from backend.review.trade_manager import (
    delete_trade,
    merge_trades,
    recalculate_commissions,
)


@pytest.fixture
def sample_trades() -> list[dict]:
    """Provide 5 sample trades with known metrics for statistics testing."""
    return [
        # Win, long, Day 1
        {
            "id": 1,
            "session_date": "2026-06-01",
            "symbol": "MNQM26",
            "direction": "Long",
            "entry_datetime": "2026-06-01 10:00:00",
            "exit_datetime": "2026-06-01 10:02:00",
            "entry_price": 28000.0,
            "exit_price": 28050.0,
            "quantity": 2,
            "pnl": 100.0,
            "commission": 2.08,
            "net_pnl": 97.92,
            "max_open_profit": 120.0,
            "max_open_loss": -10.0,
            "duration_seconds": 120.0,
            "setup_tag": "ML",
            "key_indicators_tags": "gamma:positive",
            "comments": "Great entry",
            "note": "First trade",
            "tags_json": "{}",
            "tags_auto": 1,
            "snapshot_id": 10,
            "exported_to_dashboard": 0,
        },
        # Loss, short, Day 1
        {
            "id": 2,
            "session_date": "2026-06-01",
            "symbol": "MNQM26",
            "direction": "Short",
            "entry_datetime": "2026-06-01 11:00:00",
            "exit_datetime": "2026-06-01 11:00:30",
            "entry_price": 28060.0,
            "exit_price": 28070.0,
            "quantity": 1,
            "pnl": -20.0,
            "commission": 1.04,
            "net_pnl": -21.04,
            "max_open_profit": 5.0,
            "max_open_loss": -25.0,
            "duration_seconds": 30.0,
            "setup_tag": "MS",
            "key_indicators_tags": "gamma:negative",
            "comments": "Bad timing",
            "note": "Second trade",
            "tags_json": "{}",
            "tags_auto": 1,
            "snapshot_id": 11,
            "exported_to_dashboard": 0,
        },
        # Win, long, Day 1
        {
            "id": 3,
            "session_date": "2026-06-01",
            "symbol": "MNQM26",
            "direction": "Long",
            "entry_datetime": "2026-06-01 13:00:00",
            "exit_datetime": "2026-06-01 13:05:00",
            "entry_price": 28020.0,
            "exit_price": 28045.0,
            "quantity": 1,
            "pnl": 50.0,
            "commission": 1.04,
            "net_pnl": 48.96,
            "max_open_profit": 60.0,
            "max_open_loss": -5.0,
            "duration_seconds": 300.0,
            "setup_tag": "ML",
            "key_indicators_tags": "gamma:positive",
            "comments": "Nice follow through",
            "note": "Third trade",
            "tags_json": "{}",
            "tags_auto": 1,
            "snapshot_id": 12,
            "exported_to_dashboard": 0,
        },
        # Loss, short, Day 2
        {
            "id": 4,
            "session_date": "2026-06-02",
            "symbol": "NQM26",
            "direction": "Short",
            "entry_datetime": "2026-06-02 09:45:00",
            "exit_datetime": "2026-06-02 09:45:10",
            "entry_price": 28100.0,
            "exit_price": 28115.0,
            "quantity": 1,
            "pnl": -300.0,
            "commission": 2.36,
            "net_pnl": -302.36,
            "max_open_profit": 10.0,
            "max_open_loss": -350.0,
            "duration_seconds": 10.0,
            "setup_tag": "MS",
            "key_indicators_tags": "gamma:negative",
            "comments": "Stopped out quickly",
            "note": "Fourth trade",
            "tags_json": "{}",
            "tags_auto": 1,
            "snapshot_id": 13,
            "exported_to_dashboard": 0,
        },
        # Win, long, Day 2
        {
            "id": 5,
            "session_date": "2026-06-02",
            "symbol": "MNQM26",
            "direction": "Long",
            "entry_datetime": "2026-06-02 14:00:00",
            "exit_datetime": "2026-06-02 14:01:00",
            "entry_price": 28000.0,
            "exit_price": 28080.0,
            "quantity": 1,
            "pnl": 160.0,
            "commission": 1.04,
            "net_pnl": 158.96,
            "max_open_profit": 180.0,
            "max_open_loss": -15.0,
            "duration_seconds": 60.0,
            "setup_tag": "ML",
            "key_indicators_tags": "gamma:positive",
            "comments": "Strong bounce",
            "note": "Fifth trade",
            "tags_json": "{}",
            "tags_auto": 1,
            "snapshot_id": 14,
            "exported_to_dashboard": 0,
        },
    ]


def test_compute_stats(sample_trades):
    """Verify that compute_stats correctly calculates all summary, duration, daily, and direction metrics."""
    res = compute_stats(sample_trades)

    summary = res["summary"]
    # Total net PnL: 97.92 - 21.04 + 48.96 - 302.36 + 158.96 = -17.56
    assert summary["total_pnl"] == -17.56
    # Total gross PnL = Total net + Total fees = -17.56 + 7.56 = -10.0
    assert summary["gross_pnl"] == -10.0
    # Total commissions: 2.08 + 1.04 + 1.04 + 2.36 + 1.04 = 7.56
    assert summary["total_fees"] == 7.56
    # Win rate: 3 wins (net_pnl > 0: id 1, 3, 5) out of 5 trades = 60.0%
    assert summary["win_rate"] == 60.0
    assert summary["total_trades"] == 5
    # Gross profit: 97.92 + 48.96 + 158.96 = 305.84
    # Gross loss: 21.04 + 302.36 = 323.40
    # Profit factor: 305.84 / 323.40 = 0.95
    assert summary["profit_factor"] == 0.95
    # Expected value: -17.56 / 5 = -3.512 -> round to 2 decimals = -3.51
    assert summary["expected_value"] == -3.51
    # Avg win: 305.84 / 3 = 101.946 -> round to 2 decimals = 101.95
    assert summary["avg_win"] == 101.95
    # Avg loss: -323.40 / 2 = -161.70
    assert summary["avg_loss"] == -161.70
    # Best trade (net PnL): 158.96 (from trade 5)
    assert summary["best_trade"] == 158.96
    # Worst trade (net PnL): -302.36 (from trade 4)
    assert summary["worst_trade"] == -302.36
    # Commission per trade = 7.56 / 5 = 1.512 -> round to 2 decimals = 1.51
    assert summary["commission_per_trade"] == 1.51

    duration = res["duration"]
    # Total duration = 120 + 30 + 300 + 10 + 60 = 520
    # Avg duration = 520 / 5 = 104.0
    assert duration["avg_duration"] == 104.0
    # Avg win duration = (120 + 300 + 60) / 3 = 160.0
    assert duration["avg_win_duration"] == 160.0
    # Avg loss duration = (30 + 10) / 2 = 20.0
    assert duration["avg_loss_duration"] == 20.0

    daily = res["daily"]
    # Day 1: 97.92 (win) - 21.04 (loss) + 48.96 (win) = 125.84 (net PnL) -> winning day
    # Day 2: -302.36 (loss) + 158.96 (win) = -143.40 (net PnL) -> losing day
    # Day win rate: 1 winning day out of 2 = 50.0%
    assert daily["day_win_rate"] == 50.0
    assert daily["best_day"] == 125.84
    assert daily["worst_day"] == -143.40
    # Day 1 has 3 trades, Day 2 has 2 trades. Most active day trades = 3
    assert daily["most_active_day_trades"] == 3
    # best_day / total_pnl = 125.84 / -17.56 -> since total_pnl is negative, it returns 0.0
    assert daily["best_day_pct_total"] == 0.0

    direction = res["direction"]
    # Longs: 3 (id 1, 3, 5) out of 5 = 60.0%
    # Shorts: 2 (id 2, 4) out of 5 = 40.0%
    assert direction["long_pct"] == 60.0
    assert direction["short_pct"] == 40.0


def test_prepare_charts_data(sample_trades):
    """Verify that prepare_charts_data constructs correct sorted daily series and duration buckets."""
    res = prepare_charts_data(sample_trades)

    daily_pnl = res["daily_pnl"]
    assert len(daily_pnl) == 2
    assert daily_pnl[0]["Date"] == "2026-06-01"
    assert daily_pnl[0]["DailyPnL"] == 125.84
    assert daily_pnl[0]["CumulativePnL"] == 125.84
    assert daily_pnl[1]["Date"] == "2026-06-02"
    assert daily_pnl[1]["DailyPnL"] == -143.40
    assert daily_pnl[1]["CumulativePnL"] == -17.56

    distribution = res["duration_distribution"]
    # Duration buckets:
    # Under 15 sec: id 4 (10 sec) -> count=1
    # 15-45 sec: id 2 (30 sec) -> count=1
    # 45 sec - 1 min: None -> count=0
    # 1 min - 2 min: id 1 (120 sec) -> wait, range is min <= dur < max, so 60 <= 120 < 120 is False. 120 goes to '2 min - 5 min' bucket: 120 <= 120 < 300.
    # So 1 min - 2 min has count=1 (id 5: 60 sec, 60 <= 60 < 120).
    # 2 min - 5 min has count=2 (id 1: 120 sec, id 3: 300 sec is 300 <= 300 < 600? Yes, so id 3 is in 5-10 min bucket).
    # Let's count them:
    # id 4 (10s): 'Under 15 sec' (0-15s) -> count 1, win_rate 0.0
    # id 2 (30s): '15-45 sec' (15-45s) -> count 1, win_rate 0.0
    # id 5 (60s): '1 min - 2 min' (60-120s) -> count 1, win_rate 100.0
    # id 1 (120s): '2 min - 5 min' (120-300s) -> count 1, win_rate 100.0
    # id 3 (300s): '5 min - 10 min' (300-600s) -> count 1, win_rate 100.0

    buckets_by_range = {d["range"]: d for d in distribution}
    assert buckets_by_range["Under 15 sec"]["count"] == 1
    assert buckets_by_range["Under 15 sec"]["win_rate"] == 0.0

    assert buckets_by_range["15-45 sec"]["count"] == 1
    assert buckets_by_range["15-45 sec"]["win_rate"] == 0.0

    assert buckets_by_range["1 min - 2 min"]["count"] == 1
    assert buckets_by_range["1 min - 2 min"]["win_rate"] == 100.0

    assert buckets_by_range["2 min - 5 min"]["count"] == 1
    assert buckets_by_range["2 min - 5 min"]["win_rate"] == 100.0

    assert buckets_by_range["5 min - 10 min"]["count"] == 1
    assert buckets_by_range["5 min - 10 min"]["win_rate"] == 100.0

    scatter = res["duration_scatter"]
    # Check that scatter data size is correct
    assert len(scatter) == 5
    assert scatter[0] == {"Duration": 120.0, "NetPnL": 97.92}


def test_compute_stats_by_tag(sample_trades):
    """Verify that compute_stats_by_tag groups trades and computes statistics per group."""
    res = compute_stats_by_tag(sample_trades, "setup_tag")
    assert len(res) == 2
    assert "ML" in res
    assert "MS" in res

    ml_stats = res["ML"]
    # ML trades are id 1, 3, 5 (all wins)
    assert ml_stats["summary"]["total_trades"] == 3
    assert ml_stats["summary"]["win_rate"] == 100.0

    ms_stats = res["MS"]
    # MS trades are id 2, 4 (all losses)
    assert ms_stats["summary"]["total_trades"] == 2
    assert ms_stats["summary"]["win_rate"] == 0.0


def test_compute_stats_empty():
    """Verify that computing stats on empty trade lists returns a zeroed structure safely."""
    res = compute_stats([])
    assert res["summary"]["total_trades"] == 0
    assert res["summary"]["total_pnl"] == 0.0
    assert res["duration"]["avg_duration"] == 0.0


def test_trade_manager_operations():
    """Verify database trade operations: merge, delete, and recalculate commissions."""
    conn = get_connection(":memory:")
    init_db(conn)

    # Insert 3 sample trades
    conn.execute(
        """
        INSERT INTO tagged_trades (
            id, session_date, symbol, base_symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, quantity, pnl, commission, net_pnl,
            max_open_profit, max_open_loss, duration_seconds, note, fill_count,
            setup_tag, key_indicators_tags, scoring_criteria_tags, additional_tag,
            setup_rating, comments, import_hash
        ) VALUES (
            1, '2026-06-01', 'MNQM26', 'MNQ', 'Long', '2026-06-01 10:00:00', '2026-06-01 10:02:00',
            28000.0, 28050.0, 2, 100.0, 0.0, 100.0,
            120.0, -10.0, 120.0, 'First', 2,
            'ML', 'gamma:positive', 'RuleA', 'frontrun',
            85.0, 'Nice entry', 'hash1'
        )
        """
    )
    conn.execute(
        """
        INSERT INTO tagged_trades (
            id, session_date, symbol, base_symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, quantity, pnl, commission, net_pnl,
            max_open_profit, max_open_loss, duration_seconds, note, fill_count,
            setup_tag, key_indicators_tags, scoring_criteria_tags, additional_tag,
            setup_rating, comments, import_hash
        ) VALUES (
            2, '2026-06-01', 'MNQM26', 'MNQ', 'Long', '2026-06-01 10:05:00', '2026-06-01 10:07:00',
            28040.0, 28060.0, 1, 40.0, 0.0, 40.0,
            50.0, -5.0, 120.0, 'Second', 1,
            'MS', 'gamma:negative', 'RuleB', 'standard',
            50.0, 'Ok entry', 'hash2'
        )
        """
    )
    conn.commit()

    # Recalculate commissions:
    # Trade 1: MNQ quantity=2 -> CPS=0.52 -> commission = 0.52 * 2 * 2 = 2.08 -> net_pnl = 97.92
    # Trade 2: MNQ quantity=1 -> CPS=0.52 -> commission = 0.52 * 2 * 1 = 1.04 -> net_pnl = 38.96
    res = recalculate_commissions(conn)
    assert res["updated"] == 2

    # Verify updated values in DB
    row1 = conn.execute("SELECT commission, net_pnl FROM tagged_trades WHERE id = 1").fetchone()
    assert row1[0] == 2.08
    assert row1[1] == 97.92

    row2 = conn.execute("SELECT commission, net_pnl FROM tagged_trades WHERE id = 2").fetchone()
    assert row2[0] == 1.04
    assert row2[1] == 38.96

    # Merge Trades 1 and 2:
    # Quantity: 2 + 1 = 3
    # PnL: 100.0 + 40.0 = 140.0
    # Commission: 2.08 + 1.04 = 3.12
    # Net PnL: 97.92 + 38.96 = 136.88
    # Max open profit: max(120.0, 50.0) = 120.0
    # Max open loss: min(-10.0, -5.0) = -10.0
    # Duration: 120.0 + 120.0 = 240.0
    # Fills: 2 + 1 = 3
    # Tags from first (Trade 1): setup_tag='ML', comments='Nice entry', rating=85.0
    merged = merge_trades(conn, [1, 2])
    assert merged is not None
    assert merged["quantity"] == 3
    assert merged["pnl"] == 140.0
    assert merged["commission"] == 3.12
    assert merged["net_pnl"] == 136.88
    assert merged["max_open_profit"] == 120.0
    assert merged["max_open_loss"] == -10.0
    assert merged["duration_seconds"] == 240.0
    assert merged["fill_count"] == 3
    assert merged["setup_tag"] == "ML"
    assert merged["comments"] == "Nice entry"
    assert merged["setup_rating"] == 85.0
    assert merged["is_merged"] == 1
    assert merged["import_hash"] is None

    # Check that original trades 1 and 2 are deleted
    rem1 = conn.execute("SELECT 1 FROM tagged_trades WHERE id = 1").fetchone()
    rem2 = conn.execute("SELECT 1 FROM tagged_trades WHERE id = 2").fetchone()
    assert rem1 is None
    assert rem2 is None

    # Delete the merged trade
    merged_id = merged["id"]
    del_res = delete_trade(conn, merged_id)
    assert del_res is True

    rem_merged = conn.execute("SELECT 1 FROM tagged_trades WHERE id = ?", (merged_id,)).fetchone()
    assert rem_merged is None

    conn.close()

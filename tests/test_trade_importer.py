"""
Tests for the Sierra Chart TradesList importer.
"""

from __future__ import annotations

import os
import sqlite3
import pytest
from pathlib import Path
from backend.db import get_connection, init_db
from backend.review.trade_importer import parse_sierra_trades, import_trades

# Real tab-separated header
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

# 6 sample fill rows forming 2 F2F groups
# Group 1: 3 rows for MNQH26 (representing a single F2F trade)
# Fill 1: entry, qty 1, Profit/Loss 0
# Fill 2: scale in, qty 1, Profit/Loss 0
# Fill 3: exit, qty 2, Profit/Loss 150.00, is_f2f_end (FlatToFlat Profit/Loss ends with F)
# Group 2: 3 rows for NQH26 (representing a single F2F trade)
# Fill 4: entry, qty 1
# Fill 5: entry, qty 1
# Fill 6: exit, qty 2, Profit/Loss -200.00, is_f2f_end (FlatToFlat Profit/Loss ends with F)

SAMPLE_ROWS = [
    # MNQ Group (F2F 1)
    "MNQH26 (19850621)\tLong\t2026-02-10  14:09:50.516 BP\t2026-02-10  14:09:50.516\t15000.00\t15000.00\t1\t1\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00%\t0.00%\t0.00%\t0.52\t15000.00\t15000.00\tParent order\t1\t0\t00:00:00\t12345\t0.00\t0.00\t0.00\t0.00",
    "MNQH26 (19850621)\tLong\t2026-02-10  14:10:00.000\t2026-02-10  14:10:00.000\t15010.00\t15010.00\t1\t2\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00%\t0.00%\t0.00%\t0.52\t15010.00\t15010.00\tParent order\t2\t0\t00:00:10\t12345\t0.00\t0.00\t0.00\t0.00",
    "MNQH26 (19850621)\tShort\t2026-02-10  14:11:17.343\t2026-02-10  14:11:17.343 EP\t15050.00\t15050.00\t2\t2\t2\t160.00\t160.00\t160.00 F\t170.00\t-10.00\t170.00\t-10.00\t90.00%\t90.00%\t90.00%\t1.04\t15060.00\t14995.00\tDescriptive Exit\t0\t2\t00:01:26\t12345\t160.00\t-10.00\t170.00\t-10.00",

    # NQ Group (F2F 2)
    "NQH26\tShort\t2026-02-11  09:30:15.000 BP\t2026-02-11  09:30:15.000\t16000.00\t16000.00\t1\t1\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00%\t0.00%\t0.00%\t1.18\t16000.00\t16000.00\tParent order\t1\t0\t00:00:00\t12345\t0.00\t0.00\t0.00\t0.00",
    "NQH26\tShort\t2026-02-11  09:31:00.000\t2026-02-11  09:31:00.000\t16010.00\t16010.00\t1\t2\t0\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00\t0.00%\t0.00%\t0.00%\t1.18\t16010.00\t16010.00\tParent order\t2\t0\t00:00:45\t12345\t0.00\t0.00\t0.00\t0.00",
    "NQH26\tLong\t2026-02-11  09:35:30.000\t2026-02-11  09:35:30.000 EP\t15980.00\t15980.00\t2\t2\t2\t40.00\t40.00\t40.00 F\t60.00\t-20.00\t60.00\t-20.00\t80.00%\t80.00%\t80.00%\t2.36\t16020.00\t15970.00\tParent order\t0\t2\t00:05:15\t12345\t40.00\t-20.00\t60.00\t-20.00",
]

@pytest.fixture
def temp_trades_file(tmp_path) -> Path:
    """Creates a temporary TradesList.txt file with sample data."""
    file_path = tmp_path / "TradesList.txt"
    content = HEADER + "\n" + "\n".join(SAMPLE_ROWS) + "\n"
    file_path.write_text(content, encoding="utf-8")
    return file_path

@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Provides an in-memory SQLite connection with initialized schema."""
    conn = get_connection(":memory:")
    init_db(conn)
    return conn

def test_parse_sierra_trades(temp_trades_file):
    """Test that parse_sierra_trades correctly parses and aggregates F2F trades."""
    trades = parse_sierra_trades(temp_trades_file)
    assert len(trades) == 2

    # Verify MNQ trade details
    mnq_trade = trades[0]
    assert mnq_trade["symbol"] == "MNQH26"
    assert mnq_trade["base_symbol"] == "MNQ"
    assert mnq_trade["direction"] == "Long"
    assert mnq_trade["entry_datetime"] == "2026-02-10 14:09:50"
    assert mnq_trade["exit_datetime"] == "2026-02-10 14:11:17"
    assert mnq_trade["entry_price"] == pytest.approx(15000.00)
    assert mnq_trade["exit_price"] == pytest.approx(15050.00)
    assert mnq_trade["quantity"] == 2
    assert mnq_trade["pnl"] == pytest.approx(160.00)
    assert mnq_trade["commission"] == pytest.approx(2.08)  # 2.08 from fills
    assert mnq_trade["net_pnl"] == pytest.approx(mnq_trade["pnl"] - mnq_trade["commission"])
    assert mnq_trade["max_open_profit"] == pytest.approx(170.00)
    assert mnq_trade["max_open_loss"] == pytest.approx(-10.00)
    assert mnq_trade["duration_seconds"] == pytest.approx(86.0)
    assert mnq_trade["note"] == "Descriptive Exit"
    assert mnq_trade["fill_count"] == 3
    assert mnq_trade["point_value"] == 2.0
    assert mnq_trade["tick_size"] == 0.25
    assert mnq_trade["tick_value"] == 0.50
    assert "import_hash" in mnq_trade
    assert len(mnq_trade["import_hash"]) == 64

    # Verify NQ trade details
    nq_trade = trades[1]
    assert nq_trade["symbol"] == "NQH26"
    assert nq_trade["base_symbol"] == "NQ"
    assert nq_trade["direction"] == "Short"
    assert nq_trade["entry_datetime"] == "2026-02-11 09:30:15"
    assert nq_trade["exit_datetime"] == "2026-02-11 09:35:30"
    assert nq_trade["entry_price"] == pytest.approx(16000.00)
    assert nq_trade["exit_price"] == pytest.approx(15980.00)
    assert nq_trade["quantity"] == 2
    assert nq_trade["pnl"] == pytest.approx(40.00)
    # Commission from file is 1.18 + 1.18 + 2.36 = 4.72
    assert nq_trade["commission"] == pytest.approx(4.72)
    assert nq_trade["net_pnl"] == pytest.approx(nq_trade["pnl"] - nq_trade["commission"])
    assert nq_trade["max_open_profit"] == pytest.approx(60.00)
    assert nq_trade["max_open_loss"] == pytest.approx(-20.00)
    assert nq_trade["duration_seconds"] == pytest.approx(315.0)
    assert nq_trade["note"] == "Parent order"
    assert nq_trade["fill_count"] == 3
    assert nq_trade["point_value"] == 20.0
    assert nq_trade["tick_size"] == 0.25
    assert nq_trade["tick_value"] == 5.00

def test_import_trades_success_and_deduplication(temp_trades_file, db_conn):
    """Test importing trades, deduping duplicate imports, and deriving session_date."""
    # First import should import all 2 trades
    result = import_trades(str(temp_trades_file), db_conn)
    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert result["total"] == 2

    # Check rows in DB
    rows = db_conn.execute(
        "SELECT session_date, symbol, base_symbol, direction, entry_datetime, exit_datetime, "
        "entry_price, exit_price, quantity, pnl, commission, net_pnl, max_open_profit, "
        "max_open_loss, duration_seconds, fill_count, point_value, tick_size, tick_value, "
        "note, import_hash, setup_tag FROM tagged_trades ORDER BY entry_datetime"
    ).fetchall()

    assert len(rows) == 2

    # Derived session date from YYYY-MM-DD
    assert rows[0][0] == "2026-02-10"  # MNQ
    assert rows[0][1] == "MNQH26"
    assert rows[0][2] == "MNQ"
    assert rows[0][21] == ""  # setup_tag should be empty on import

    assert rows[1][0] == "2026-02-11"  # NQ
    assert rows[1][1] == "NQH26"
    assert rows[1][2] == "NQ"

    # Second import of the same file should import 0 and skip 2
    result2 = import_trades(str(temp_trades_file), db_conn)
    assert result2["imported"] == 0
    assert result2["skipped"] == 2
    assert result2["total"] == 2

    # Row count remains 2
    count = db_conn.execute("SELECT COUNT(*) FROM tagged_trades").fetchone()[0]
    assert count == 2

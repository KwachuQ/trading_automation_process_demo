"""
Tests for Plan vs Execution comparison logic and endpoint.
Adheres to PEP 8 styling and implements test-first TDD logic.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.db import get_connection, init_db
from backend.review.plan_vs_execution import compare_plan_vs_execution
from backend.main import app
from backend.state import app_state


@pytest.fixture()
def client(tmp_path: Path):
    """
    Set up a test client with an in-memory/temp SQLite database
    and temporary config state.
    """
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    app_state["db_path"] = db_path
    
    # Minimal config structure matching other tests
    from types import SimpleNamespace
    app_state["config"] = SimpleNamespace(
        sierra_chart=SimpleNamespace(
            saved_trade_activity_dir=str(tmp_path),
            trades_list_file="TradesList.txt",
        )
    )
    
    yield TestClient(app, raise_server_exceptions=True), db_path


def test_compare_plan_vs_execution_logic(client):
    """
    Verify the business logic of compare_plan_vs_execution with seeded data.
    """
    _, db_path = client
    conn = get_connection(db_path)
    try:
        session_date = "2026-06-01"

        # 1. Seed scenarios
        conn.execute(
            """
            INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
            VALUES (?, 1, 'ML', 'Buy the dip', 'VAH', '')
            """,
            (session_date,),
        )
        conn.execute(
            """
            INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
            VALUES (?, 2, 'MS', 'Short the breakdown', 'VAL', '')
            """,
            (session_date,),
        )

        # 2. Seed trades
        # Trade 1: Aligned ML
        conn.execute(
            """
            INSERT INTO tagged_trades (
                session_date, symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, pnl, net_pnl, setup_tag, import_hash
            ) VALUES (?, 'MNQ', 'Long', '2026-06-01 10:00:00', '2026-06-01 10:15:00',
                      15000.0, 15020.0, 40.0, 39.0, 'ML', 'hash1')
            """,
            (session_date,),
        )
        # Trade 2: Unaligned MS (Setup tag MS, but Long direction instead of Short!)
        conn.execute(
            """
            INSERT INTO tagged_trades (
                session_date, symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, pnl, net_pnl, setup_tag, import_hash
            ) VALUES (?, 'MNQ', 'Long', '2026-06-01 10:20:00', '2026-06-01 10:30:00',
                      15000.0, 15020.0, 40.0, 39.0, 'MS', 'hash2')
            """,
            (session_date,),
        )
        # Trade 3: Aligned MS
        conn.execute(
            """
            INSERT INTO tagged_trades (
                session_date, symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, pnl, net_pnl, setup_tag, import_hash
            ) VALUES (?, 'MNQ', 'Short', '2026-06-01 10:35:00', '2026-06-01 10:45:00',
                      15020.0, 15000.0, 40.0, 39.0, 'MS', 'hash3')
            """,
            (session_date,),
        )
        # Trade 4: Unplanned MRS (no MRS scenario seeded for the day)
        conn.execute(
            """
            INSERT INTO tagged_trades (
                session_date, symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, pnl, net_pnl, setup_tag, import_hash
            ) VALUES (?, 'MNQ', 'Short', '2026-06-01 11:00:00', '2026-06-01 11:10:00',
                      15020.0, 15000.0, 40.0, 39.0, 'MRS', 'hash4')
            """,
            (session_date,),
        )
        conn.commit()

        # Run comparison logic
        res = compare_plan_vs_execution(conn, session_date)

        # Check general structure
        assert "scenarios" in res
        assert "unplanned_trades" in res
        assert "summary" in res

        # Validate summary
        summary = res["summary"]
        assert summary["total_trades"] == 4
        assert summary["aligned_count"] == 2      # Trade 1 (ML/Long) & Trade 3 (MS/Short)
        assert summary["unaligned_count"] == 1    # Trade 2 (MS/Long)
        assert summary["unplanned_count"] == 1    # Trade 4 (MRS/Short)

        # Validate scenarios breakdown
        sc_list = res["scenarios"]
        assert len(sc_list) == 2

        # Scenario 1 (ML)
        s1 = [s for s in sc_list if s["setup_type"] == "ML"][0]
        assert s1["rationale"] == "Buy the dip"
        assert s1["targets"] == "VAH"
        assert len(s1["aligned_trades"]) == 1
        assert s1["aligned_trades"][0]["import_hash"] == "hash1"
        assert len(s1["unaligned_trades"]) == 0

        # Scenario 2 (MS)
        s2 = [s for s in sc_list if s["setup_type"] == "MS"][0]
        assert s2["rationale"] == "Short the breakdown"
        assert s2["targets"] == "VAL"
        assert len(s2["aligned_trades"]) == 1
        assert s2["aligned_trades"][0]["import_hash"] == "hash3"
        assert len(s2["unaligned_trades"]) == 1
        assert s2["unaligned_trades"][0]["import_hash"] == "hash2"

        # Validate unplanned trades
        unplanned = res["unplanned_trades"]
        assert len(unplanned) == 1
        assert unplanned[0]["import_hash"] == "hash4"

    finally:
        conn.close()


def test_compare_plan_vs_execution_no_scenarios(client):
    """
    Test comparison logic when no scenarios are set up for the date.
    All trades should be classified as unplanned.
    """
    _, db_path = client
    conn = get_connection(db_path)
    try:
        session_date = "2026-06-02"

        # Seed 1 trade
        conn.execute(
            """
            INSERT INTO tagged_trades (
                session_date, symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, pnl, net_pnl, setup_tag, import_hash
            ) VALUES (?, 'MNQ', 'Long', '2026-06-02 10:00:00', '2026-06-02 10:15:00',
                      15000.0, 15020.0, 40.0, 39.0, 'ML', 'hash5')
            """,
            (session_date,),
        )
        conn.commit()

        res = compare_plan_vs_execution(conn, session_date)

        assert len(res["scenarios"]) == 0
        assert len(res["unplanned_trades"]) == 1
        assert res["unplanned_trades"][0]["import_hash"] == "hash5"

        summary = res["summary"]
        assert summary["total_trades"] == 1
        assert summary["aligned_count"] == 0
        assert summary["unaligned_count"] == 0
        assert summary["unplanned_count"] == 1

    finally:
        conn.close()


def test_compare_plan_vs_execution_api_endpoint(client):
    """
    Test the GET /api/review/plan-vs-execution endpoint using the TestClient.
    """
    c, db_path = client

    # Seed data
    conn = get_connection(db_path)
    session_date = "2026-06-03"
    conn.execute(
        """
        INSERT INTO scenarios (session_date, scenario_number, setup_type, rationale, targets, invalidated_if)
        VALUES (?, 1, 'ML', 'Buy the dip', 'VAH', '')
        """,
        (session_date,),
    )
    conn.execute(
        """
        INSERT INTO tagged_trades (
            session_date, symbol, direction, entry_datetime, exit_datetime,
            entry_price, exit_price, pnl, net_pnl, setup_tag, import_hash
        ) VALUES (?, 'MNQ', 'Long', '2026-06-03 10:00:00', '2026-06-03 10:15:00',
                  15000.0, 15020.0, 40.0, 39.0, 'ML', 'hash6')
        """,
        (session_date,),
    )
    conn.commit()
    conn.close()

    # Call with query parameter
    resp = c.get(f"/api/review/plan-vs-execution?session_date={session_date}")
    assert resp.status_code == 200
    data = resp.json()
    assert "scenarios" in data
    assert "unplanned_trades" in data
    assert "summary" in data

    sc_list = data["scenarios"]
    assert len(sc_list) == 1
    assert sc_list[0]["setup_type"] == "ML"
    assert len(sc_list[0]["aligned_trades"]) == 1
    assert sc_list[0]["aligned_trades"][0]["import_hash"] == "hash6"

    summary = data["summary"]
    assert summary["total_trades"] == 1
    assert summary["aligned_count"] == 1
    assert summary["unplanned_count"] == 0

    # Call without parameter (uses default date)
    resp_default = c.get("/api/review/plan-vs-execution")
    assert resp_default.status_code == 200
    data_default = resp_default.json()
    assert "summary" in data_default

"""
Plan vs Execution comparison logic.
Provides functions to compare pre-session scenarios against actual trades.
Adheres to PEP 8 styling guidelines and is fully commented.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List


def _get_implied_direction(setup_type: str) -> str:
    """
    Map a setup type (ML, MRL, MS, MRS) to its implied trade direction.

    - ML (Market Long) and MRL (Market Reversal Long) imply 'Long'.
    - MS (Market Short) and MRS (Market Reversal Short) imply 'Short'.
    """
    if setup_type in ("ML", "MRL"):
        return "Long"
    elif setup_type in ("MS", "MRS"):
        return "Short"
    return ""


def compare_plan_vs_execution(
    conn: sqlite3.Connection,
    session_date: str,
) -> Dict[str, Any]:
    """
    Compare actual F2F trades against pre-session scenarios for a given date.

    Returns a structured dictionary:
    {
        "scenarios": [
            {
                "setup_type": str,
                "rationale": str,
                "targets": str,
                "aligned_trades": list[dict],
                "unaligned_trades": list[dict]
            }
        ],
        "unplanned_trades": list[dict],
        "summary": {
            "total_trades": int,
            "aligned_count": int,
            "unaligned_count": int,
            "unplanned_count": int
        }
    }
    """
    # Save original row factory and enforce sqlite3.Row for dict conversion
    orig_row_factory = conn.row_factory
    conn.row_factory = sqlite3.Row

    try:
        # 1. Fetch scenarios for the specified session_date ordered by scenario_number
        scenarios_cursor = conn.execute(
            """
            SELECT setup_type, rationale, targets
            FROM scenarios
            WHERE session_date = ?
            ORDER BY scenario_number
            """,
            (session_date,),
        )
        scenarios = [
            {
                "setup_type": row["setup_type"],
                "rationale": row["rationale"],
                "targets": row["targets"],
                "aligned_trades": [],
                "unaligned_trades": [],
            }
            for row in scenarios_cursor.fetchall()
        ]

        # Create a set of setup types that are part of today's plan
        planned_setup_types = {s["setup_type"] for s in scenarios}

        # 2. Fetch tagged trades for the specified session_date ordered by entry_datetime
        trades_cursor = conn.execute(
            """
            SELECT *
            FROM tagged_trades
            WHERE session_date = ?
            ORDER BY entry_datetime
            """,
            (session_date,),
        )
        trades = [dict(row) for row in trades_cursor.fetchall()]

        # 3. Classify trades into aligned, unaligned, and unplanned
        unplanned_trades: List[Dict[str, Any]] = []
        aligned_count = 0
        unaligned_count = 0

        for trade in trades:
            setup_tag = trade.get("setup_tag", "")

            if setup_tag not in planned_setup_types:
                # Trade did not match any of the planned setup types for the day
                unplanned_trades.append(trade)
            else:
                # Trade matches a planned setup type; classify as aligned or unaligned
                implied_direction = _get_implied_direction(setup_tag)
                is_aligned = (trade.get("direction") == implied_direction)

                if is_aligned:
                    aligned_count += 1
                else:
                    unaligned_count += 1

                # Distribute trade record into all matching scenarios in the list
                for scenario in scenarios:
                    if scenario["setup_type"] == setup_tag:
                        if is_aligned:
                            scenario["aligned_trades"].append(trade)
                        else:
                            scenario["unaligned_trades"].append(trade)

        # 4. Build and return final response structure
        return {
            "scenarios": scenarios,
            "unplanned_trades": unplanned_trades,
            "summary": {
                "total_trades": len(trades),
                "aligned_count": aligned_count,
                "unaligned_count": unaligned_count,
                "unplanned_count": len(unplanned_trades),
            },
        }

    finally:
        # Restore original row factory
        conn.row_factory = orig_row_factory

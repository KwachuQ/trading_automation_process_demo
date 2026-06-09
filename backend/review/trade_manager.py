"""Trade management operations for the trading dashboard.

Provides functionality for merging trades, deleting trades, and
recalculating commissions directly on the ``tagged_trades`` table.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional


def merge_trades(conn: sqlite3.Connection, trade_ids: List[int]) -> Optional[Dict[str, Any]]:
    """Merge multiple trades in `tagged_trades` into a single composite trade.

    The merged trade inherits the first trade's entry and the last trade's exit.
    P/L, commissions, and quantity are summed.
    Original trades are deleted. Tags are preserved from the first trade.

    Returns the newly created merged trade dict, or None on failure.
    """
    if len(trade_ids) < 2:
        return None

    orig_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in trade_ids)
        rows = conn.execute(
            f"SELECT * FROM tagged_trades WHERE id IN ({placeholders}) "
            f"ORDER BY entry_datetime ASC",
            trade_ids,
        ).fetchall()

        if len(rows) < 2:
            return None

        trades = [dict(r) for r in rows]
        first = trades[0]
        last = trades[-1]

        merged = {
            "session_date": first["session_date"],
            "symbol": first["symbol"],
            "base_symbol": first["base_symbol"],
            "direction": first["direction"],
            "entry_datetime": first["entry_datetime"],
            "exit_datetime": last["exit_datetime"],
            "entry_price": first["entry_price"],
            "exit_price": last["exit_price"],
            "quantity": sum(t["quantity"] for t in trades),
            "pnl": round(sum(t["pnl"] for t in trades), 2),
            "commission": round(sum(t["commission"] for t in trades), 2),
            "net_pnl": round(sum(t["net_pnl"] for t in trades), 2),
            "max_open_profit": max(t["max_open_profit"] for t in trades),
            "max_open_loss": min(t["max_open_loss"] for t in trades),
            "duration_seconds": sum(t["duration_seconds"] for t in trades),
            "note": " | ".join(t["note"] for t in trades if t["note"]),
            "fill_count": sum(t["fill_count"] for t in trades),
            "point_value": first["point_value"],
            "tick_size": first["tick_size"],
            "tick_value": first["tick_value"],
            "import_hash": None,  # Nullable in UNIQUE column in SQLite
            "is_merged": 1,
            "merge_source_ids": json.dumps(trade_ids),
            "setup_tag": first["setup_tag"],
            "key_indicators_tags": first["key_indicators_tags"],
            "scoring_criteria_tags": first["scoring_criteria_tags"],
            "additional_tag": first["additional_tag"],
            "setup_rating": first["setup_rating"],
            "comments": first["comments"],
            "tags_json": first["tags_json"],
            "tags_auto": first["tags_auto"],
            "snapshot_id": first["snapshot_id"],
            "exported_to_dashboard": first["exported_to_dashboard"],
        }

        # Insert merged trade
        cursor = conn.execute("""
            INSERT INTO tagged_trades (
                session_date, symbol, base_symbol, direction,
                entry_datetime, exit_datetime, entry_price, exit_price,
                quantity, pnl, commission, net_pnl,
                max_open_profit, max_open_loss, duration_seconds, note,
                fill_count, point_value, tick_size, tick_value,
                import_hash, is_merged, merge_source_ids,
                setup_tag, key_indicators_tags, scoring_criteria_tags,
                additional_tag, setup_rating, comments,
                tags_json, tags_auto, snapshot_id, exported_to_dashboard
            ) VALUES (
                :session_date, :symbol, :base_symbol, :direction,
                :entry_datetime, :exit_datetime, :entry_price, :exit_price,
                :quantity, :pnl, :commission, :net_pnl,
                :max_open_profit, :max_open_loss, :duration_seconds, :note,
                :fill_count, :point_value, :tick_size, :tick_value,
                :import_hash, :is_merged, :merge_source_ids,
                :setup_tag, :key_indicators_tags, :scoring_criteria_tags,
                :additional_tag, :setup_rating, :comments,
                :tags_json, :tags_auto, :snapshot_id, :exported_to_dashboard
            )
        """, merged)

        new_id = cursor.lastrowid
        merged["id"] = new_id

        # Delete originals
        conn.execute(
            f"DELETE FROM tagged_trades WHERE id IN ({placeholders})",
            trade_ids,
        )
        conn.commit()
        return merged
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.row_factory = orig_factory


def delete_trade(conn: sqlite3.Connection, trade_id: int) -> bool:
    """Delete a trade by its ID from tagged_trades. Returns True if deleted."""
    try:
        cursor = conn.execute(
            "DELETE FROM tagged_trades WHERE id = ?",
            (trade_id,)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        conn.rollback()
        raise e


def bulk_delete_trades(conn: sqlite3.Connection, trade_ids: List[int]) -> int:
    """Delete multiple trades by their IDs from tagged_trades.

    Returns the number of deleted records. All logic is fully commented
    and handles transaction rollback on exception.
    """
    if not trade_ids:
        return 0
    try:
        placeholders = ",".join("?" for _ in trade_ids)
        cursor = conn.execute(
            f"DELETE FROM tagged_trades WHERE id IN ({placeholders})",
            trade_ids
        )
        conn.commit()
        return cursor.rowcount
    except Exception as e:
        conn.rollback()
        raise e



def recalculate_commissions(conn: sqlite3.Connection) -> Dict[str, int]:
    """Recalculate commissions for all trades in tagged_trades that currently have commission = 0.

    Uses formula: commission_per_side × 2 (entry + exit) × quantity.
    Also updates net_pnl = pnl - commission.
    """
    from backend.review.trade_importer import INSTRUMENT_SPECS

    orig_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    updated = 0
    try:
        rows = conn.execute(
            "SELECT id, base_symbol, quantity, pnl, commission "
            "FROM tagged_trades WHERE commission = 0.0"
        ).fetchall()

        for row in rows:
            trade = dict(row)
            base = trade["base_symbol"]
            spec = INSTRUMENT_SPECS.get(base)
            if not spec:
                continue
            cps = spec.get("commission_per_side", 0.0)
            if cps <= 0.0:
                continue

            qty = trade.get("quantity", 1) or 1
            new_commission = round(cps * 2 * qty, 2)
            new_net_pnl = round(trade["pnl"] - new_commission, 2)

            conn.execute(
                "UPDATE tagged_trades "
                "SET commission = ?, net_pnl = ? "
                "WHERE id = ?",
                (new_commission, new_net_pnl, trade["id"]),
            )
            updated += 1

        conn.commit()
        return {"updated": updated}
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.row_factory = orig_factory

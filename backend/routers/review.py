"""
Review API endpoints.
Provides trade importing, tagging, and management features.
All logic is fully commented and adheres to PEP 8 styling.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import date
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException

from backend.db import get_connection
from backend.review.constants import CLOSE_TYPES, ENTRY_CONTEXTS, ENTRY_TYPES
from backend.review.trade_importer import import_trades, parse_sierra_trades
from backend.review.auto_tagger import auto_tag_trades
from backend.review.plan_vs_execution import compare_plan_vs_execution
from backend.review.stats import compute_stats, prepare_charts_data, compute_stats_by_tag
from backend.review.trade_manager import (
    merge_trades,
    delete_trade,
    bulk_delete_trades,
    recalculate_commissions,
)
from backend.state import app_state
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/review", tags=["review"])


def _get_conn() -> sqlite3.Connection:
    """Helper to get a database connection from active app state."""
    db_path: str = app_state["db_path"]
    return get_connection(db_path)


# ---------------------------------------------------------------------------
# Pydantic Schema Definitions
# ---------------------------------------------------------------------------

class TaggedTradeResponse(BaseModel):
    """Schema representing a complete record in the tagged_trades table."""
    id: int
    session_date: str
    symbol: str
    direction: str
    entry_datetime: str
    exit_datetime: str
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    net_pnl: float
    tags_json: str
    tags_auto: int
    snapshot_id: Optional[int] = None
    import_hash: Optional[str] = None
    exported_to_dashboard: int
    base_symbol: str
    commission: float
    max_open_profit: float
    max_open_loss: float
    duration_seconds: float
    fill_count: int
    point_value: float
    tick_size: float
    tick_value: float
    note: str
    setup_tag: str
    key_indicators_tags: str
    scoring_criteria_tags: str
    additional_tag: str
    setup_rating: float
    comments: str
    created_at: str


class ImportResponse(BaseModel):
    """Schema representing response after importing trade logs."""
    imported: int
    skipped: int
    total: int
    trades: List[TaggedTradeResponse]


class TradeUpdateRequest(BaseModel):
    """Schema representing partial tag updates on a trade."""
    setup_tag: Optional[str] = None
    key_indicators_tags: Optional[str] = None
    scoring_criteria_tags: Optional[str] = None
    additional_tag: Optional[str] = None
    setup_rating: Optional[float] = None
    comments: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/constants")
async def get_constants() -> dict[str, list[str]]:
    """
    Fetch static dropdown category lists for trade review manual tagging.
    """
    return {
        "entry_type": ENTRY_TYPES,
        "entry_direct_context": ENTRY_CONTEXTS,
        "close_type": CLOSE_TYPES,
    }


@router.post("/import", response_model=ImportResponse)
async def import_trades_endpoint(file_path: Optional[str] = None) -> ImportResponse:
    """
    Trigger parser and auto-tagger for Trade log file from Sierra Chart.
    Defaults to configured directory/filename if file_path query parameter is not provided.
    """
    config = app_state["config"]

    if file_path is None:
        saved_dir = getattr(config.sierra_chart, "saved_trade_activity_dir", "")
        filename = getattr(config.sierra_chart, "trades_list_file", "TradesList.txt")
        file_path = os.path.join(saved_dir, filename)

    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        # 1. Parse and insert new trades into database
        stats = import_trades(file_path, conn)

        # 2. Query trades eligible for auto-tagging:
        #    - At least one tag field is still empty (OR logic allows
        #      partial re-tagging when new data becomes available)
        #    - Only auto-tagged trades (tags_auto = 1); skip manually tagged
        new_trades_cursor = conn.execute(
            """
            SELECT * FROM tagged_trades
            WHERE (setup_tag = '' OR key_indicators_tags = ''
                   OR scoring_criteria_tags = '')
              AND tags_auto = 1
            """
        )
        new_trades = [dict(row) for row in new_trades_cursor.fetchall()]

        # 3. Run auto-tagger on eligible trades
        if new_trades:
            auto_tag_trades(conn, new_trades)

        # 4. Fetch updated database records for parsed trade list
        parsed_trades = parse_sierra_trades(file_path)
        parsed_hashes = [t["import_hash"] for t in parsed_trades]

        trades_to_return = []
        if parsed_hashes:
            placeholders = ",".join("?" for _ in parsed_hashes)
            imported_rows = conn.execute(
                f"""
                SELECT * FROM tagged_trades
                WHERE import_hash IN ({placeholders})
                ORDER BY entry_datetime
                """,
                parsed_hashes,
            ).fetchall()
            trades_to_return = [dict(row) for row in imported_rows]

        return ImportResponse(
            imported=stats["imported"],
            skipped=stats["skipped"],
            total=stats["total"],
            trades=trades_to_return,
        )
    finally:
        conn.close()


@router.get("/trades", response_model=List[TaggedTradeResponse])
async def list_trades(
    session_date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[TaggedTradeResponse]:
    """
    Retrieve all flat-to-flat tagged trades.

    Filtering priority:
    1. If ``date_from`` and ``date_to`` are both supplied, return all trades
       whose ``session_date`` falls within the inclusive range.
    2. If only ``session_date`` is supplied, return trades for that single day.
    3. If nothing is supplied, default to today's date.
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        if date_from and date_to:
            # Range query — covers multiple session dates
            rows = conn.execute(
                """
                SELECT * FROM tagged_trades
                WHERE session_date BETWEEN ? AND ?
                ORDER BY entry_datetime
                """,
                (date_from, date_to),
            ).fetchall()
        else:
            # Single-day fallback (original behaviour)
            query_date = session_date or date.today().isoformat()
            rows = conn.execute(
                """
                SELECT * FROM tagged_trades
                WHERE session_date = ?
                ORDER BY entry_datetime
                """,
                (query_date,),
            ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.get("/trades/{id}", response_model=TaggedTradeResponse)
async def get_trade(id: int) -> TaggedTradeResponse:
    """
    Retrieve a single trade record by its unique database ID.
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM tagged_trades WHERE id = ?",
            (id,),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Trade with ID {id} not found.",
            )
        return dict(row)
    finally:
        conn.close()


@router.patch("/trades/{id}", response_model=TaggedTradeResponse)
async def patch_trade(id: int, body: TradeUpdateRequest) -> TaggedTradeResponse:
    """
    Partially update tag details on an existing trade record.
    Marks tags_auto = 0 to denote manual override/correction.
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        # Verify the trade exists in database
        exists = conn.execute(
            "SELECT id FROM tagged_trades WHERE id = ?",
            (id,),
        ).fetchone()
        if not exists:
            raise HTTPException(
                status_code=404,
                detail=f"Trade with ID {id} not found.",
            )

        update_fields = []
        params = []
        tag_changed = False

        # Extract only provided update keys
        for key, val in body.model_dump(exclude_unset=True).items():
            update_fields.append(f"{key} = ?")
            params.append(val)
            tag_changed = True

        if not update_fields:
            # No fields provided in body; return unchanged record
            row = conn.execute(
                "SELECT * FROM tagged_trades WHERE id = ?",
                (id,),
            ).fetchone()
            return dict(row)

        if tag_changed:
            # Set manual tagging override marker
            update_fields.append("tags_auto = ?")
            params.append(0)

        params.append(id)
        query = f"UPDATE tagged_trades SET {', '.join(update_fields)} WHERE id = ?"
        conn.execute(query, params)
        conn.commit()

        # Retrieve and return updated record
        updated = conn.execute(
            "SELECT * FROM tagged_trades WHERE id = ?",
            (id,),
        ).fetchone()
        return dict(updated)
    finally:
        conn.close()


@router.get("/plan-vs-execution")
async def get_plan_vs_execution(
    session_date: Optional[str] = None,
) -> dict[str, Any]:
    """
    Overlay actual trades against pre-session scenarios to assess plan adherence.
    Defaults to today's date if session_date query parameter is not provided.
    """
    query_date = session_date or date.today().isoformat()
    conn = _get_conn()
    try:
        return compare_plan_vs_execution(conn, query_date)
    finally:
        conn.close()


class MergeRequest(BaseModel):
    """Request schema for merging multiple trades."""
    trade_ids: List[int]


class BulkDeleteRequest(BaseModel):
    """Request schema for bulk deleting multiple trades."""
    trade_ids: List[int]


# ---------------------------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------------------------

def _format_trade_for_frontend(t: dict[str, Any]) -> dict[str, Any]:
    """Map a single database row from tagged_trades to the frontend trade shape."""
    entry_dt = t.get("entry_datetime", "")
    day = entry_dt.split(" ")[0] if entry_dt else ""

    return {
        "_row_id": t.get("id"),
        "id": t.get("id"),
        "Symbol": t.get("symbol", ""),
        "Direction": t.get("direction", ""),
        "Date": entry_dt,
        "EntryDate": entry_dt,
        "ExitDate": t.get("exit_datetime", ""),
        "EntryPrice": t.get("entry_price", 0.0),
        "ExitPrice": t.get("exit_price", 0.0),
        "PnL": t.get("pnl", 0.0),
        "NetPnL": t.get("net_pnl", 0.0),
        "Fees": t.get("commission", 0.0),
        "Size": t.get("quantity", 1),
        "Duration": t.get("duration_seconds", 0.0),
        "Day": day,
        "Setup Tag": t.get("setup_tag", ""),
        "Key Indicators": t.get("key_indicators_tags", ""),
        "Scoring Criteria": t.get("scoring_criteria_tags", ""),
        "Additional Tag": t.get("additional_tag", ""),
        "Setup Rating": t.get("setup_rating") or 0.0,
        "Comments": t.get("comments", ""),
        "Note": t.get("note", ""),
        "FillCount": t.get("fill_count", 1),
        "MaxOpenProfit": t.get("max_open_profit", 0.0),
        "MaxOpenLoss": t.get("max_open_loss", 0.0),
        "PointValue": t.get("point_value", 1.0),
        "TickSize": t.get("tick_size", 0.01),
        "TickValue": t.get("tick_value", 0.01),
        "isMerged": bool(t.get("is_merged", 0)),
        "Date_Obj": day,
    }


# ---------------------------------------------------------------------------
# Statistics and Chart Endpoints
# ---------------------------------------------------------------------------

@router.get("/stats")
async def get_stats(
    session_date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    """
    Compute and return summary statistics and chart-ready data structures.
    Supports filtering by specific session_date or a custom date range.
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT * FROM tagged_trades WHERE session_date BETWEEN ? AND ? ORDER BY entry_datetime ASC",
                (date_from, date_to),
            ).fetchall()
        elif session_date:
            rows = conn.execute(
                "SELECT * FROM tagged_trades WHERE session_date = ? ORDER BY entry_datetime ASC",
                (session_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tagged_trades ORDER BY entry_datetime ASC"
            ).fetchall()

        trades = [dict(row) for row in rows]
        stats = compute_stats(trades)
        charts = prepare_charts_data(trades)
        return {"stats": stats, "charts": charts}
    finally:
        conn.close()


@router.get("/stats-by-tag")
async def get_stats_by_tag(
    tag_column: str = "setup_tag",
    session_date: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict[str, Any]:
    """
    Compute and return statistics grouped by unique values in a specific tag column.
    """
    allowed_columns = {
        "setup_tag", "key_indicators_tags", "scoring_criteria_tags",
        "additional_tag", "tags_auto", "exported_to_dashboard"
    }
    if tag_column not in allowed_columns:
        raise HTTPException(status_code=400, detail="Invalid tag column requested.")

    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        if date_from and date_to:
            rows = conn.execute(
                "SELECT * FROM tagged_trades WHERE session_date BETWEEN ? AND ? ORDER BY entry_datetime ASC",
                (date_from, date_to),
            ).fetchall()
        elif session_date:
            rows = conn.execute(
                "SELECT * FROM tagged_trades WHERE session_date = ? ORDER BY entry_datetime ASC",
                (session_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tagged_trades ORDER BY entry_datetime ASC"
            ).fetchall()

        trades = [dict(row) for row in rows]
        stats_by_tag = compute_stats_by_tag(trades, tag_column)
        return stats_by_tag
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Trade Management Endpoints
# ---------------------------------------------------------------------------

@router.post("/trades/merge")
async def merge_trades_endpoint(body: MergeRequest) -> dict[str, Any]:
    """
    Merge multiple trades into a single composite trade and return the merged
    trade along with updated stats for that session date.
    """
    if len(body.trade_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="At least 2 trade IDs are required for merging."
        )

    conn = _get_conn()
    try:
        merged = merge_trades(conn, body.trade_ids)
        if merged is None:
            raise HTTPException(
                status_code=400,
                detail="Could not merge — trades not found."
            )

        # Fetch remaining trades for that date to compute updated stats
        session_date = merged["session_date"]
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM tagged_trades WHERE session_date = ? ORDER BY entry_datetime ASC",
            (session_date,),
        ).fetchall()
        trades = [dict(row) for row in rows]
        stats = compute_stats(trades)
        charts = prepare_charts_data(trades)

        return {
            "message": "Trades merged successfully.",
            "merged_trade": _format_trade_for_frontend(merged),
            "stats": {"stats": stats, "charts": charts}
        }
    finally:
        conn.close()


@router.delete("/trades/{id}")
async def delete_trade_endpoint(id: int) -> dict[str, Any]:
    """
    Delete a trade by its unique database ID and return updated stats for its session date.
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        # Fetch trade session date before deletion
        row = conn.execute(
            "SELECT session_date FROM tagged_trades WHERE id = ?",
            (id,),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Trade with ID {id} not found."
            )
        session_date = row["session_date"]

        delete_trade(conn, id)

        # Retrieve remaining trades for that session date to compute updated stats
        rows = conn.execute(
            "SELECT * FROM tagged_trades WHERE session_date = ? ORDER BY entry_datetime ASC",
            (session_date,),
        ).fetchall()
        trades = [dict(r) for r in rows]
        stats = compute_stats(trades)
        charts = prepare_charts_data(trades)

        return {
            "message": "Trade deleted successfully.",
            "trade_id": id,
            "stats": {"stats": stats, "charts": charts}
        }
    finally:
        conn.close()


@router.post("/trades/bulk-delete")
async def bulk_delete_trades_endpoint(body: BulkDeleteRequest) -> dict[str, Any]:
    """
    Delete multiple trades by their database IDs. All logic handles
    transaction boundaries and is fully commented.
    """
    if not body.trade_ids:
        raise HTTPException(
            status_code=400,
            detail="At least one trade ID is required for bulk deletion."
        )

    conn = _get_conn()
    try:
        count = bulk_delete_trades(conn, body.trade_ids)
        return {
            "message": f"Successfully deleted {count} trade(s).",
            "trade_ids": body.trade_ids,
            "count": count
        }
    finally:
        conn.close()


@router.post("/recalculate-commissions")
async def recalculate_commissions_endpoint() -> dict[str, Any]:
    """
    Recalculate commissions for all trades in tagged_trades with zero commission.
    Returns the count of updated trades along with updated global stats.
    """
    conn = _get_conn()
    conn.row_factory = sqlite3.Row
    try:
        result = recalculate_commissions(conn)

        # Retrieve all trades to get updated stats
        rows = conn.execute(
            "SELECT * FROM tagged_trades ORDER BY entry_datetime ASC"
        ).fetchall()
        trades = [dict(r) for r in rows]
        stats = compute_stats(trades)
        charts = prepare_charts_data(trades)

        return {
            "message": f"Recalculated commissions for {result['updated']} trades.",
            "updated": result["updated"],
            "stats": {"stats": stats, "charts": charts}
        }
    finally:
        conn.close()

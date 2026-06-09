"""
backend/review/auto_tagger.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Auto-tagging system for flat-to-flat (F2F) trades.
Derives setup tag, key indicator tags, scoring criteria tags, and setup rating
from session snapshots and feature store setup logs active at trade entry time.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional

# Set up logger matching the project's standard
logger = logging.getLogger(__name__)


def find_nearest_snapshot(
    conn: sqlite3.Connection,
    entry_datetime: str,
    session_date: str,
) -> Optional[Dict[str, Any]]:
    """
    Find the session snapshot closest in time to the trade's entry datetime.

    Filters by the matching session date and orders by absolute difference
    in time using SQLite's julianday function.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active SQLite database connection.
    entry_datetime : str
        The entry datetime of the trade (e.g., '2026-06-01 10:04:00').
    session_date : str
        The date of the session (e.g., '2026-06-01').

    Returns
    -------
    dict | None
        Dictionary of snapshot fields if a match is found, otherwise None.
    """
    query = """
        SELECT id, session_date, snapshot_time, indicators_json,
               regime_name, regime_confidence, setup_score, score_breakdown_json
        FROM session_snapshots
        WHERE session_date = ?
        ORDER BY ABS(julianday(snapshot_time) - julianday(?))
        LIMIT 1
    """
    try:
        row = conn.execute(query, (session_date, entry_datetime)).fetchone()
        if not row:
            return None

        return {
            "id": row[0],
            "session_date": row[1],
            "snapshot_time": row[2],
            "indicators_json": row[3],
            "regime_name": row[4],
            "regime_confidence": row[5],
            "setup_score": row[6],
            "score_breakdown_json": row[7],
        }
    except Exception as exc:
        logger.error(
            f"Error finding nearest snapshot for {entry_datetime} "
            f"on {session_date}: {exc}",
            exc_info=True,
        )
        return None


def derive_setup_tag(conn: sqlite3.Connection, trade: Dict[str, Any]) -> str:
    """
    Query the active setup log for the most recent active setup before trade entry.

    Filters by session_date to prevent cross-day leakage of setup tags.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active SQLite database connection.
    trade : dict
        Normalized trade dictionary.

    Returns
    -------
    str
        The setup tag (e.g. 'ML', 'MS', 'MRL', 'MRS') or empty string if none exists.
    """
    entry_dt = trade.get("entry_datetime")
    if not entry_dt:
        return ""

    # Extract session_date from the trade, or derive from entry_datetime
    session_date = trade.get("session_date")
    if not session_date:
        session_date = entry_dt.split(" ")[0]

    query = """
        SELECT setup_type
        FROM active_setup_log
        WHERE session_date = ?
          AND marked_at <= ?
        ORDER BY marked_at DESC
        LIMIT 1
    """
    try:
        row = conn.execute(query, (session_date, entry_dt)).fetchone()
        return row[0] if row else ""
    except Exception as exc:
        logger.error(
            f"Error deriving setup tag for entry {entry_dt}: {exc}",
            exc_info=True,
        )
        return ""


def derive_key_indicators_tags(
    trade: Dict[str, Any],
    snapshot: Optional[Dict[str, Any]],
) -> str:
    """
    Extract key indicator values from snapshot's indicators_json.

    Formats them as a comma-separated list of key:value pairs.
    Indicators: gamma_regime, cd_vs_ma, delta_slope, vwap_slope, vol_regime, entry_quality.

    Parameters
    ----------
    trade : dict
        Normalized trade dictionary (unused but kept for signature flexibility).
    snapshot : dict | None
        The closest session snapshot dictionary.

    Returns
    -------
    str
        Comma-separated key:value string of indicator values.
    """
    if not snapshot:
        return ""

    indicators_raw = snapshot.get("indicators_json")
    if not indicators_raw:
        return ""

    try:
        if isinstance(indicators_raw, str):
            indicators = json.loads(indicators_raw)
        else:
            indicators = indicators_raw
    except Exception as exc:
        logger.error(f"Error parsing indicators JSON: {exc}")
        return ""

    if not isinstance(indicators, dict):
        return ""

    keys_to_extract = [
        "gamma_regime",
        "cd_vs_ma",
        "delta_slope",
        "vwap_slope",
        "vol_regime",
        "entry_quality",
    ]

    parts = []
    for key in keys_to_extract:
        val = indicators.get(key)
        if val is not None and val != "":
            parts.append(f"{key}:{val}")

    return ",".join(parts)


def derive_scoring_criteria_tags(snapshot: Optional[Dict[str, Any]]) -> str:
    """
    Parse the snapshot's score breakdown to find all matched criteria.

    Parameters
    ----------
    snapshot : dict | None
        The closest session snapshot dictionary.

    Returns
    -------
    str
        Comma-separated string of matched scoring criteria names.
    """
    if not snapshot:
        return ""

    breakdown_raw = snapshot.get("score_breakdown_json")
    if not breakdown_raw:
        return ""

    try:
        if isinstance(breakdown_raw, str):
            breakdown = json.loads(breakdown_raw)
        else:
            breakdown = breakdown_raw
    except Exception as exc:
        logger.error(f"Error parsing score breakdown JSON: {exc}")
        return ""

    if not isinstance(breakdown, list):
        return ""

    matched_names = []
    for criterion in breakdown:
        if isinstance(criterion, dict):
            name = criterion.get("name")
            matched = criterion.get("matched")
            if name and (matched is True or str(matched).lower() == "true"):
                matched_names.append(name)

    return ",".join(matched_names)


def auto_tag_trades(conn: sqlite3.Connection, trades: List[Dict[str, Any]]) -> int:
    """
    Perform end-to-end auto-tagging for a list of trades, updating the database.

    Parameters
    ----------
    conn : sqlite3.Connection
        Active SQLite database connection.
    trades : list[dict]
        List of trade dictionaries to auto-tag.

    Returns
    -------
    int
        The count of successfully tagged trades.
    """
    tagged_count = 0

    for trade in trades:
        entry_dt = trade.get("entry_datetime")
        if not entry_dt:
            logger.warning("Skipping trade auto-tagging: entry_datetime is missing")
            continue

        session_date = trade.get("session_date")
        if not session_date:
            session_date = entry_dt.split(" ")[0]

        # 1. Find closest snapshot in time
        snapshot = find_nearest_snapshot(conn, entry_dt, session_date)

        # 2. Derive all required tags
        setup_tag = derive_setup_tag(conn, trade)
        key_indicators_tags = derive_key_indicators_tags(trade, snapshot)
        scoring_criteria_tags = derive_scoring_criteria_tags(snapshot)

        setup_rating = 0.0
        if snapshot and snapshot.get("setup_score") is not None:
            try:
                setup_rating = float(snapshot["setup_score"])
            except (TypeError, ValueError):
                pass

        # Only overwrite tag fields that are currently empty in the trade.
        # This allows partial re-tagging without losing previously set values.
        existing_setup = trade.get("setup_tag", "")
        existing_indicators = trade.get("key_indicators_tags", "")
        existing_scoring = trade.get("scoring_criteria_tags", "")
        existing_rating = trade.get("setup_rating", 0.0)

        final_setup = setup_tag if (not existing_setup and setup_tag) else existing_setup
        final_indicators = (
            key_indicators_tags
            if (not existing_indicators and key_indicators_tags)
            else existing_indicators
        )
        final_scoring = (
            scoring_criteria_tags
            if (not existing_scoring and scoring_criteria_tags)
            else existing_scoring
        )
        final_rating = (
            setup_rating
            if (existing_rating == 0.0 and setup_rating != 0.0)
            else existing_rating
        )

        # 3. Update the database row in tagged_trades
        trade_id = trade.get("id")
        import_hash = trade.get("import_hash")

        try:
            if trade_id is not None:
                conn.execute(
                    """
                    UPDATE tagged_trades
                    SET setup_tag = ?,
                        key_indicators_tags = ?,
                        scoring_criteria_tags = ?,
                        setup_rating = ?,
                        tags_auto = 1
                    WHERE id = ?
                    """,
                    (
                        final_setup,
                        final_indicators,
                        final_scoring,
                        final_rating,
                        trade_id,
                    ),
                )
                tagged_count += 1
            elif import_hash is not None:
                conn.execute(
                    """
                    UPDATE tagged_trades
                    SET setup_tag = ?,
                        key_indicators_tags = ?,
                        scoring_criteria_tags = ?,
                        setup_rating = ?,
                        tags_auto = 1
                    WHERE import_hash = ?
                    """,
                    (
                        final_setup,
                        final_indicators,
                        final_scoring,
                        final_rating,
                        import_hash,
                    ),
                )
                tagged_count += 1
            else:
                logger.warning(
                    f"Skipping DB update: both 'id' and 'import_hash' are "
                    f"missing in trade: {trade}"
                )
        except Exception as exc:
            logger.error(f"Failed to update database for trade: {exc}", exc_info=True)

    try:
        conn.commit()
    except Exception as exc:
        logger.error(f"Failed to commit transaction: {exc}", exc_info=True)

    return tagged_count

"""
Sierra Chart TradesList parser and importer.

Reads tab-delimited TradesList exports from Sierra Chart and aggregates
individual fills into flat-to-flat (F2F) trades, then imports them into
the local SQLite database, ensuring deduplication.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Set up logging matching the project's standard
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract specification registry
# ---------------------------------------------------------------------------
INSTRUMENT_SPECS: Dict[str, Dict[str, float]] = {
    "MNQ": {
        "point_value": 2.0,
        "tick_size": 0.25,
        "tick_value": 0.50,
        "commission_per_side": 0.52,
    },
    "NQ": {
        "point_value": 20.0,
        "tick_size": 0.25,
        "tick_value": 5.00,
        "commission_per_side": 1.18,
    },
    "MES": {
        "point_value": 5.0,
        "tick_size": 0.25,
        "tick_value": 1.25,
        "commission_per_side": 0.52,
    },
    "ES": {
        "point_value": 50.0,
        "tick_size": 0.25,
        "tick_value": 12.50,
        "commission_per_side": 1.18,
    },
    "MCL": {
        "point_value": 100.0,
        "tick_size": 0.01,
        "tick_value": 1.00,
        "commission_per_side": 0.52,
    },
    "CL": {
        "point_value": 1000.0,
        "tick_size": 0.01,
        "tick_value": 10.00,
        "commission_per_side": 1.18,
    },
}


def _extract_base_symbol(raw_symbol: str) -> str:
    """
    Extract the base instrument code from a Sierra Chart symbol string.

    Sierra Chart symbols follow the pattern: BASE + MONTH_CODE + YEAR
    where MONTH_CODE is a single letter (F-Z) and YEAR is 2 digits.

    Examples:
        'MNQH26 (19850621)' -> 'MNQ'
        'MNQH26'            -> 'MNQ'
        'NQH26 (19850621)'  -> 'NQ'
        'NQH26'             -> 'NQ'
        'ESZ25'             -> 'ES'
    """
    # Strip any account suffix like ' (19850621)'
    symbol = raw_symbol.split("(")[0].strip()

    # Strip contract month code (single letter) + 2-digit year from end
    # Month codes: F G H J K M N Q U V X Z
    match = re.match(r"^(.+?)[FGHJKMNQUVXZ]\d{2}$", symbol)
    if match:
        return match.group(1)

    # Fallback: try matching against known instrument prefixes
    for prefix in sorted(INSTRUMENT_SPECS.keys(), key=len, reverse=True):
        if symbol.startswith(prefix):
            return prefix

    return symbol


def _get_instrument_spec(raw_symbol: str) -> Dict[str, float]:
    """Return the instrument specification for a given raw Sierra symbol."""
    base = _extract_base_symbol(raw_symbol)
    return INSTRUMENT_SPECS.get(base, {
        "point_value": 1.0,
        "tick_size": 0.01,
        "tick_value": 0.01,
        "commission_per_side": 0.0,
    })


def _clean_datetime(raw: str) -> str:
    """
    Strip Sierra-specific suffixes (BP, EP) from datetime strings.

    '2026-02-10  14:09:50.516 BP' -> '2026-02-10 14:09:50'
    '2026-02-10  14:11:17.343'    -> '2026-02-10 14:11:17'
    """
    # Remove BP / EP markers
    cleaned = re.sub(r"\s+(BP|EP)\s*$", "", raw.strip())
    # Collapse double spaces
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    # Strip sub-second precision for cleaner display
    cleaned = re.sub(r"\.\d+$", "", cleaned)
    return cleaned


def _clean_numeric(raw: Any) -> Optional[float]:
    """
    Parse a numeric field, stripping any non-numeric suffixes like ' F'.

    '1200.00 F' -> 1200.0
    '-3.50'     -> -3.5
    ''          -> None
    """
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    cleaned = re.sub(r"\s+[A-Z]$", "", raw_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_duration(raw: str) -> float:
    """
    Parse a duration string 'HH:MM:SS' into seconds.

    '00:01:26' -> 86.0
    """
    if not raw or not raw.strip():
        return 0.0
    parts = raw.strip().split(":")
    try:
        if len(parts) == 3:
            return (float(parts[0]) * 3600
                    + float(parts[1]) * 60
                    + float(parts[2]))
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
    except ValueError:
        pass
    return 0.0


def _compute_import_hash(trade: Dict[str, Any]) -> str:
    """
    Compute a deterministic hash for duplicate detection.

    Uses symbol + entry_datetime + exit_datetime + pnl.
    """
    raw = (
        f"{trade['symbol']}|{trade['entry_datetime']}|"
        f"{trade['exit_datetime']}|{trade['pnl']}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_trade_from_group(group: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build a normalised trade dict from a group of fills."""
    first = group[0]
    last = group[-1]

    # Symbol: use the first fill's raw symbol (may have account suffix)
    raw_symbol = first["symbol_raw"]
    # Propagate the full symbol from the first record that has it
    # (subsequent fills may omit the account suffix)
    for fill in group:
        if "(" in fill["symbol_raw"]:
            raw_symbol = fill["symbol_raw"]
            break

    # Clean symbol: remove account suffix for display
    display_symbol = raw_symbol.split("(")[0].strip()
    base_symbol = _extract_base_symbol(raw_symbol)
    spec = _get_instrument_spec(raw_symbol)

    # F2F P/L from the last fill's column
    f2f_pnl = _clean_numeric(last["f2f_pnl_raw"]) or 0.0

    # Max open quantity (peak size during the trade)
    max_qty = max(f.get("max_open_quantity", 1) or 1 for f in group)

    # Total commission across all fills (from the file)
    file_commission = sum(f.get("commission", 0) or 0 for f in group)

    # If the file provides zero commission, calculate from instrument spec.
    # Commission = commission_per_side × 2 sides (entry + exit) × quantity
    commission_per_side = spec.get("commission_per_side", 0.0)
    if file_commission == 0.0 and commission_per_side > 0.0:
        total_commission = round(
            commission_per_side * 2 * (max_qty or 1), 2,
        )
    else:
        total_commission = file_commission

    # Duration from the last fill
    duration = _parse_duration(last["duration_raw"])

    # We take the first fill's entry and last fill's exit for the trade
    entry_dt = _clean_datetime(first["entry_datetime_raw"])
    exit_dt = _clean_datetime(last["exit_datetime_raw"])

    # Entry price from first fill, exit price from last fill
    entry_price = first["entry_price"] or 0.0
    exit_price = last["exit_price"] or 0.0

    # Max open profit/loss from F2F columns
    max_open_profit = last.get("max_open_profit")
    if max_open_profit is None:
        max_open_profit = 0.0
    max_open_loss = last.get("max_open_loss")
    if max_open_loss is None:
        max_open_loss = 0.0

    # Note
    note = first["note"] or ""
    # Prefer the note from last fill if first is generic
    if last["note"] and last["note"] != "Parent order":
        note = last["note"]
    elif first["note"] == "Parent order" and len(group) > 1:
        # Check other fills for a more descriptive note
        for fill in group:
            if fill["note"] and fill["note"] != "Parent order":
                note = fill["note"]
                break

    trade: Dict[str, Any] = {
        "symbol": display_symbol,
        "base_symbol": base_symbol,
        "direction": first["trade_type"],
        "entry_datetime": entry_dt,
        "exit_datetime": exit_dt,
        "entry_price": round(entry_price, 6),
        "exit_price": round(exit_price, 6),
        "quantity": int(max_qty),
        "pnl": round(f2f_pnl, 2),
        "commission": round(total_commission, 2),
        "net_pnl": round(f2f_pnl - total_commission, 2),
        "max_open_profit": round(max_open_profit or 0.0, 2),
        "max_open_loss": round(max_open_loss or 0.0, 2),
        "duration_seconds": round(duration, 2),
        "note": note,
        "fill_count": len(group),
        "point_value": spec["point_value"],
        "tick_size": spec["tick_size"],
        "tick_value": spec["tick_value"],
    }

    trade["import_hash"] = _compute_import_hash(trade)
    return trade


def _aggregate_f2f(fills: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aggregate individual fills into flat-to-flat trade groups.

    A F2F group ends when the fill's FlatToFlat Profit/Loss column
    contains the ' F' suffix.
    """
    trades: List[Dict[str, Any]] = []
    current_group: List[Dict[str, Any]] = []

    for fill in fills:
        current_group.append(fill)

        if fill["is_f2f_end"]:
            trade = _build_trade_from_group(current_group)
            trades.append(trade)
            current_group = []

    # Handle any remaining fills without an F marker
    # (incomplete F2F — treat as standalone trade)
    if current_group:
        trade = _build_trade_from_group(current_group)
        trades.append(trade)

    return trades


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_sierra_trades(source: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Parse a Sierra Chart TradesList export file and return a list of
    flat-to-flat trade dictionaries.

    Parameters
    ----------
    source : str | Path
        File path containing the TradesList data.

    Returns
    -------
    list[dict]
        Each dict contains normalised trade fields ready for DB insertion.

    Raises
    ------
    ValueError
        If the file cannot be parsed or contains no valid trades.
    """
    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()

    if not lines:
        raise ValueError("Empty file — no data to parse.")

    # Parse header row
    header = lines[0].split("\t")
    header = [h.strip() for h in header]

    # Build column index map
    col_idx: Dict[str, int] = {}
    for i, col_name in enumerate(header):
        col_idx[col_name] = i

    # Required columns check
    required = ["Symbol", "Trade Type", "Entry DateTime", "Exit DateTime",
                "Entry Price", "Exit Price", "FlatToFlat Profit/Loss (C)"]
    missing = [c for c in required if c not in col_idx]
    if missing:
        raise ValueError(
            f"Missing required columns: {', '.join(missing)}. "
            f"Available: {', '.join(header)}"
        )

    # Parse data rows into fill records, skipping blanks and totals
    fills: List[Dict[str, Any]] = []
    for line_num, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        cols = line.split("\t")
        # Skip total/summary rows (no symbol)
        symbol_raw = cols[col_idx["Symbol"]].strip() if len(cols) > col_idx["Symbol"] else ""
        if not symbol_raw:
            continue
        # Skip if the Trade Type is empty (summary row)
        trade_type = cols[col_idx["Trade Type"]].strip() if len(cols) > col_idx["Trade Type"] else ""
        if not trade_type:
            continue

        fill = {
            "symbol_raw": symbol_raw,
            "trade_type": trade_type,
            "entry_datetime_raw": cols[col_idx["Entry DateTime"]].strip(),
            "exit_datetime_raw": cols[col_idx["Exit DateTime"]].strip(),
            "entry_price": _clean_numeric(cols[col_idx["Entry Price"]]),
            "exit_price": _clean_numeric(cols[col_idx["Exit Price"]]),
            "quantity": _clean_numeric(
                cols[col_idx.get("Trade Quantity", col_idx.get("Max Open Quantity", 0))]
            ) or 1.0,
            "max_open_quantity": _clean_numeric(
                cols[col_idx["Max Open Quantity"]]
            ) if "Max Open Quantity" in col_idx else 1.0,
            "pnl": _clean_numeric(cols[col_idx["Profit/Loss (C)"]])
                if "Profit/Loss (C)" in col_idx else 0.0,
            "f2f_pnl_raw": cols[col_idx["FlatToFlat Profit/Loss (C)"]].strip(),
            "commission": _clean_numeric(
                cols[col_idx["Commission (C)"]]
            ) if "Commission (C)" in col_idx else 0.0,
            "max_open_profit": _clean_numeric(
                cols[col_idx["FlatToFlat Max Open Profit (C)"]]
            ) if "FlatToFlat Max Open Profit (C)" in col_idx else 0.0,
            "max_open_loss": _clean_numeric(
                cols[col_idx["FlatToFlat Max Open Loss (C)"]]
            ) if "FlatToFlat Max Open Loss (C)" in col_idx else 0.0,
            "duration_raw": (
                cols[col_idx["Duration"]].strip()
                if "Duration" in col_idx else ""
            ),
            "note": (
                cols[col_idx["Note"]].strip()
                if "Note" in col_idx else ""
            ),
            "entry_efficiency": (
                cols[col_idx["Entry Efficiency"]].strip()
                if "Entry Efficiency" in col_idx else ""
            ),
            "exit_efficiency": (
                cols[col_idx["Exit Efficiency"]].strip()
                if "Exit Efficiency" in col_idx else ""
            ),
            # F2F detection: the last fill of an F2F group has ' F' suffix
            "is_f2f_end": cols[col_idx["FlatToFlat Profit/Loss (C)"]].strip().endswith("F"),
            # BP = Begin Position, EP = End Position
            "is_begin_position": "BP" in cols[col_idx["Entry DateTime"]],
            "is_end_position": "EP" in cols[col_idx["Exit DateTime"]],
        }
        fills.append(fill)

    if not fills:
        raise ValueError("No valid trade fills found in the file.")

    # Group fills into F2F trades
    trades = _aggregate_f2f(fills)
    return trades


def import_trades(file_path: str, conn: sqlite3.Connection) -> dict[str, int]:
    """
    Parse TradesList.txt, deduplicate against DB, and insert new trades.

    Parameters
    ----------
    file_path : str
        Path to Sierra Chart's TradesList.txt file.
    conn : sqlite3.Connection
        Active SQLite database connection.

    Returns
    -------
    dict
        Statistics showing how many trades were imported, skipped, and total:
        {"imported": N, "skipped": M, "total": K}
    """
    logger.info(f"Starting trade import from file: {file_path}")
    try:
        trades = parse_sierra_trades(file_path)
    except FileNotFoundError as e:
        logger.error(f"Trade import failed: file not found at {file_path}")
        raise e
    except Exception as e:
        logger.error(f"Error parsing trade file: {e}", exc_info=True)
        raise e

    imported = 0
    skipped = 0
    total = len(trades)

    for trade in trades:
        import_hash = trade["import_hash"]

        # Check for duplication
        dup = conn.execute(
            "SELECT 1 FROM tagged_trades WHERE import_hash = ?",
            (import_hash,)
        ).fetchone()

        if dup:
            skipped += 1
            continue

        # Derive session_date from entry_datetime (YYYY-MM-DD)
        session_date = trade["entry_datetime"].split(" ")[0]

        # Insert new trade with empty tag columns and base fields populated
        conn.execute(
            """
            INSERT INTO tagged_trades (
                session_date, symbol, base_symbol, direction, entry_datetime, exit_datetime,
                entry_price, exit_price, quantity, pnl, commission, net_pnl,
                max_open_profit, max_open_loss, duration_seconds, note,
                fill_count, point_value, tick_size, tick_value, import_hash,
                tags_json, tags_auto, setup_tag, key_indicators_tags,
                scoring_criteria_tags, additional_tag, setup_rating, comments
            ) VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                '{}', 1, '', '',
                '', '', 0.0, ''
            )
            """,
            (
                session_date,
                trade["symbol"],
                trade["base_symbol"],
                trade["direction"],
                trade["entry_datetime"],
                trade["exit_datetime"],
                trade["entry_price"],
                trade["exit_price"],
                trade["quantity"],
                trade["pnl"],
                trade["commission"],
                trade["net_pnl"],
                trade["max_open_profit"],
                trade["max_open_loss"],
                trade["duration_seconds"],
                trade["note"],
                trade["fill_count"],
                trade["point_value"],
                trade["tick_size"],
                trade["tick_value"],
                import_hash,
            )
        )
        imported += 1

    conn.commit()
    logger.info(f"Trade import finished: {imported} imported, {skipped} skipped, total {total}")
    return {"imported": imported, "skipped": skipped, "total": total}

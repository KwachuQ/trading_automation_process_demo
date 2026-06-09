from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

class SchemaType(Enum):
    VWAP_MULTI = "vwap_multi"
    DAILY_ADR = "daily_adr"
    ONE_MIN = "one_min"
    ETH_RTH_VWAP = "eth_rth_vwap"
    RVOL_30MIN = "rvol_30min"


# ---------------------------------------------------------------------------
# Column name mappings per schema
# ---------------------------------------------------------------------------

# ONE_MIN: files #1 (NQ 1-min) and #12 (QQQ 1-min)
# These files match exactly: 13 columns, no VWAP, no rename needed.
_ONE_MIN_COLS = [
    "Date", "Time", "Open", "High", "Low", "Last", "Volume",
    "# of Trades", "OHLC Avg", "HLC Avg", "HL Avg", "Bid Volume", "Ask Volume",
]
_ONE_MIN_NUMERIC_COLS = [
    "Open", "High", "Low", "Last", "Volume",
    "# of Trades", "OHLC Avg", "HLC Avg", "HL Avg", "Bid Volume", "Ask Volume",
]

# Actual Sierra Chart column names → canonical names used by this module.
# Covers the real export format used by SC as of 2025–2026.
# Columns already using canonical names (Open, High, etc.) are NOT listed here.
_VWAP_ACTUAL_RENAME: dict[str, str] = {
    # Price column: SC real files use "Last" instead of "Close"
    "Last": "Close",
    # Primary VWAP column (volume-bar charts #5/#6/#7/#10)
    "Volume Weighted Average Price": "VWAP",
    # Secondary / fallback VWAP present in all files; ignored if VWAP already mapped
    "ECIVwap": "VWAP",
    # Standard deviation bands (real SC naming)
    "Top Band 1 of Vwap Standard Deviation": "Upper Band 1",
    "Bottom Band 1 of Vwap Standard Deviation": "Lower Band 1",
    "Top Band 2 of Vwap Standard Deviation": "Upper Band 2",
    "Bottom Band 2 of Vwap Standard Deviation": "Lower Band 2",
    "Top Band 3 of Vwap Standard Deviation": "Upper Band 3",
    "Bottom Band 3 of Vwap Standard Deviation": "Lower Band 3",
    "Top Band 4 of Vwap Standard Deviation": "Upper Band 4",
    "Bottom Band 4 of Vwap Standard Deviation": "Lower Band 4",
}

_DAILY_ADR_ACTUAL_RENAME: dict[str, str] = {
    "Last": "Close",
}

# RVOL_30MIN: file 30min_rvol.txt
# 26 columns including Cumulative Volume Ratio and Relative Volume.
_RVOL_30MIN_RENAME: dict[str, str] = {
    "Last": "Close",
}
_RVOL_30MIN_CANONICAL_KEEP = [
    "Open", "High", "Low", "Close", "Volume",
    "Cumulative Volume Ratio", "Relative Volume",
]

# Canonical output columns for each schema (in preferred order).
# Columns absent from the actual file are silently omitted from the result.
_VWAP_CANONICAL_KEEP = [
    "Open", "High", "Low", "Close", "Volume",
    "VWAP",
    "Upper Band 1", "Lower Band 1",
    "Upper Band 2", "Lower Band 2",
    "Upper Band 3", "Lower Band 3",
    "Upper Band 4", "Lower Band 4",
    "Difference", "Avg",
]

_DAILY_ADR_CANONICAL_KEEP = [
    "Open", "High", "Low", "Close", "Volume", "Avg", "ADR",
]

# Legacy column lists kept for _empty_df fallback only -----------------------

_VWAP_MULTI_BASE_COLS = [
    "Date", "Time", "Open", "High", "Low", "Close", "Volume",
    "VWAP",
    "Upper Band 1", "Lower Band 1",
    "Upper Band 2", "Lower Band 2",
    "Upper Band 3", "Lower Band 3",
    "Upper Band 4", "Lower Band 4",
]
_VWAP_MULTI_EXTRA_COLS = ["Difference", "Avg"]
_VWAP_MULTI_NUMERIC_COLS = _VWAP_CANONICAL_KEEP  # same set

_DAILY_ADR_COLS = ["Date", "Time", "Open", "High", "Low", "Close", "Volume", "Avg", "ADR"]
_DAILY_ADR_NUMERIC_COLS = _DAILY_ADR_CANONICAL_KEEP

_ETH_RTH_VWAP_BASE_COLS = _VWAP_MULTI_BASE_COLS
_ETH_RTH_VWAP_NUMERIC_COLS = _VWAP_MULTI_NUMERIC_COLS

# Extended canonical keep for ETH/RTH VWAP files (#3, #4) which contain
# overlay studies that duplicate base-bar column names.  Overlay columns are
# assigned positional aliases by _build_col_index_eth_rth.
_ETH_RTH_VWAP_CANONICAL_KEEP = [
    "Open", "High", "Low", "Close", "Volume",
    "VWAP",
    "Upper Band 1", "Lower Band 1",
    "Upper Band 2", "Lower Band 2",
    "Upper Band 3", "Lower Band 3",
    "Upper Band 4", "Lower Band 4",
    "Avg",
    "delta_open", "delta_high", "delta_low", "delta_close",
    "ha_open", "ha_close",
    "trailing_open", "trailing_high", "trailing_low", "trailing_last",
]


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

def _parse_datetime_index(df: pd.DataFrame) -> pd.DataFrame:
    """Combine Date + Time columns into a DatetimeIndex and drop them."""
    df.index = pd.to_datetime(df["Date"] + " " + df["Time"], errors="coerce")
    df.index.name = "datetime"
    df = df.drop(columns=["Date", "Time"])
    df = df[df.index.notna()]
    return df



def _build_col_index(
    raw_headers: list[str], rename_map: dict[str, str]
) -> dict[str, int]:
    """Return {canonical_name: column_index} from actual file headers.

    First occurrence wins for duplicate canonical names, which handles the
    duplicate 'Volume' column present in DAILY_ADR files.
    """
    seen: set[str] = set()
    col_index: dict[str, int] = {}
    for idx, h in enumerate(raw_headers):
        canonical = rename_map.get(h, h)
        if canonical not in seen:
            col_index[canonical] = idx
            seen.add(canonical)
    return col_index


def _build_col_index_eth_rth(raw_headers: list[str]) -> dict[str, int]:
    """Build column index for ETH/RTH VWAP files with duplicate overlay columns.

    Files #4 (42 cols) and #3 (45 cols) contain overlay studies whose column
    names duplicate the base bar names (Open, High, Low, Close, Last).  The
    standard first-occurrence logic in ``_build_col_index`` silently drops
    them.  This function anchors on the "Text Display" column separator and
    assigns positional aliases to the overlay group that follows.

    Overlay mapping after "Text Display":
      Avg          -- already captured by first-occurrence pass; advanced past
      Line1        -- present in file #4 only; skipped
      Open/High/Low/Close  ->  delta_open / delta_high / delta_low / delta_close
      HA Open / HA Close   ->  ha_open / ha_close
      Open/High/Low/Last   ->  trailing_open / trailing_high / trailing_low / trailing_last

    Falls back to the standard first-occurrence mapping when "Text Display" is
    absent (e.g. simplified test fixtures without the overlay columns).
    """
    # First-occurrence pass using the standard VWAP rename map
    seen: set[str] = set()
    col_index: dict[str, int] = {}
    for idx, h in enumerate(raw_headers):
        canonical = _VWAP_ACTUAL_RENAME.get(h, h)
        if canonical not in seen:
            col_index[canonical] = idx
            seen.add(canonical)

    # Locate the "Text Display" anchor that separates the overlay studies
    try:
        td_pos = raw_headers.index("Text Display")
    except ValueError:
        return col_index  # simple fixture without overlay; standard mapping is correct

    pos = td_pos + 1

    # Skip any intermediate study columns that appear between "Text Display" and
    # the "Avg" marker (e.g. "Bullish Divergence", "Bearish Divergence" in the
    # current file format).  Stop when we reach "Avg", "Line1", or a bare
    # price column ("Open") that marks the start of the delta study group.
    while pos < len(raw_headers) and raw_headers[pos] not in ("Avg", "Line1", "Open"):
        pos += 1

    # "Avg" is already captured from the first-occurrence pass; advance past it
    if pos < len(raw_headers) and raw_headers[pos] == "Avg":
        pos += 1

    # "Line1" is a study separator present only in file #4; skip it
    if pos < len(raw_headers) and raw_headers[pos] == "Line1":
        pos += 1

    # Delta study group: Open, High, Low, Close  →  positional aliases
    for alias in ("delta_open", "delta_high", "delta_low", "delta_close"):
        if pos < len(raw_headers):
            col_index[alias] = pos
            pos += 1

    # Heikin-Ashi study: HA Open, HA Close  →  ha_open, ha_close
    if pos < len(raw_headers) and raw_headers[pos] == "HA Open":
        col_index["ha_open"] = pos
        pos += 1
    if pos < len(raw_headers) and raw_headers[pos] == "HA Close":
        col_index["ha_close"] = pos
        pos += 1

    # Trailing group: Open, High, Low, Last  →  trailing_* aliases
    for alias in ("trailing_open", "trailing_high", "trailing_low", "trailing_last"):
        if pos < len(raw_headers):
            col_index[alias] = pos
            pos += 1

    return col_index


def _parse_header_driven(
    lines: list[str],
    raw_headers: list[str],
    rename_map: dict[str, str],
    keep_canonical: list[str],
    col_index: dict[str, int] | None = None,
) -> pd.DataFrame:
    """Generic header-driven parser for SC files with variable column layouts.

    Reads column positions from the actual file header, applies *rename_map*
    to translate real column names to canonical names, then returns a
    DataFrame containing only the columns listed in *keep_canonical* that
    are actually present in the file.  Rows whose column count differs from
    the header column count are skipped with a WARNING.  Rows where any
    numeric conversion fails are also skipped with a WARNING.

    Args:
        lines: All file lines, header at index 0.
        raw_headers: Stripped tokens from the header line (already split).
        rename_map: Maps actual header name → canonical column name.
        keep_canonical: Canonical names to include in the output DataFrame.

    Returns:
        DataFrame with DatetimeIndex and available keep_canonical columns.
    """
    if col_index is None:
        col_index = _build_col_index(raw_headers, rename_map)
    n_expected = len(raw_headers)
    _non_numeric = {"Date", "Time"}
    numeric_keep = {c for c in keep_canonical if c not in _non_numeric}

    rows: list[dict] = []
    for line_no, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        values = [v.strip() for v in line.split(",")]
        if len(values) != n_expected:
            logger.warning("Column count mismatch at line %d – row skipped", line_no)
            continue

        row: dict = {}
        # Always extract Date and Time so _parse_datetime_index works
        for special in ("Date", "Time"):
            if special in col_index:
                row[special] = values[col_index[special]]

        failed = False
        for canonical in keep_canonical:
            if canonical in _non_numeric:
                continue
            if canonical not in col_index:
                continue
            val = values[col_index[canonical]]
            try:
                row[canonical] = float(val)
            except (ValueError, TypeError):
                logger.warning(
                    "Malformed value in column '%s' at line %d – row skipped",
                    canonical,
                    line_no,
                )
                failed = True
                break
        if failed:
            continue
        rows.append(row)

    if not rows:
        available = [c for c in keep_canonical if c in col_index and c not in _non_numeric]
        return pd.DataFrame(columns=available or [c for c in keep_canonical if c not in _non_numeric])

    df = pd.DataFrame(rows)
    return _parse_datetime_index(df)


def parse_sc_file(path: str, schema: SchemaType) -> pd.DataFrame:
    """Parse a Sierra Chart .txt export file into a DataFrame.

    Args:
        path: Absolute path to the .txt file.
        schema: Which schema variant to use for column mapping.

    Returns:
        DataFrame with a DatetimeIndex and typed numeric columns.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SC file not found: {path}")

    with p.open("r", encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()

    if not lines:
        return _empty_df(schema)

    # Strip whitespace from header, handle possible BOM
    header_line = lines[0].lstrip("\ufeff").strip()
    raw_headers = [h.strip() for h in header_line.split(",")]

    if schema == SchemaType.VWAP_MULTI:
        return _parse_vwap_multi(lines, raw_headers)
    elif schema == SchemaType.DAILY_ADR:
        return _parse_daily_adr(lines, raw_headers)
    elif schema == SchemaType.ONE_MIN:
        return _parse_one_min(lines, raw_headers)
    elif schema == SchemaType.ETH_RTH_VWAP:
        return _parse_eth_rth_vwap(lines, raw_headers)
    elif schema == SchemaType.RVOL_30MIN:
        return _parse_rvol_30min(lines, raw_headers)
    else:
        raise ValueError(f"Unknown schema: {schema}")


def _parse_vwap_multi(lines: list[str], raw_headers: list[str]) -> pd.DataFrame:
    """Parse VWAP_MULTI schema (files #5, #6, #7, #10)."""
    return _parse_header_driven(lines, raw_headers, _VWAP_ACTUAL_RENAME, _VWAP_CANONICAL_KEEP)


def _parse_daily_adr(lines: list[str], raw_headers: list[str]) -> pd.DataFrame:
    """Parse DAILY_ADR schema (file #8)."""
    return _parse_header_driven(lines, raw_headers, _DAILY_ADR_ACTUAL_RENAME, _DAILY_ADR_CANONICAL_KEEP)


def _parse_one_min(lines: list[str], raw_headers: list[str]) -> pd.DataFrame:
    """Parse ONE_MIN schema (files #1 NQ 1-min and #12 QQQ 1-min)."""
    col_names = _ONE_MIN_COLS
    numeric_cols = _ONE_MIN_NUMERIC_COLS

    rows = []
    for line_no, line in enumerate(lines[1:], start=2):
        line = line.strip()
        if not line:
            continue
        values = [v.strip() for v in line.split(",")]
        if len(values) != len(col_names):
            logger.warning("Column count mismatch at line %d – row skipped", line_no)
            continue
        row_dict = dict(zip(col_names, values))
        failed = False
        for col in numeric_cols:
            try:
                row_dict[col] = float(row_dict[col])
            except (ValueError, TypeError):
                logger.warning("Malformed value in column '%s' at line %d – row skipped", col, line_no)
                failed = True
                break
        if failed:
            continue
        rows.append(row_dict)

    if not rows:
        return _empty_df_from_cols(col_names, numeric_cols)

    df = pd.DataFrame(rows)
    return _parse_datetime_index(df)


def _parse_eth_rth_vwap(lines: list[str], raw_headers: list[str]) -> pd.DataFrame:
    """Parse ETH_RTH_VWAP schema (files #3 RTH 500-vol and #4 ETH 750-vol).

    Uses ``_build_col_index_eth_rth`` to handle duplicate column names produced
    by overlay studies.  The canonical keep list is extended with positional
    aliases for the delta study (``delta_close`` = cumulative delta value) and
    Heikin-Ashi study (``ha_open``, ``ha_close``).
    """
    eth_col_index = _build_col_index_eth_rth(raw_headers)
    return _parse_header_driven(
        lines, raw_headers, _VWAP_ACTUAL_RENAME, _ETH_RTH_VWAP_CANONICAL_KEEP,
        col_index=eth_col_index,
    )


def _parse_rvol_30min(lines: list[str], raw_headers: list[str]) -> pd.DataFrame:
    """Parse RVOL_30MIN schema (30min_rvol.txt)."""
    return _parse_header_driven(
        lines, raw_headers, _RVOL_30MIN_RENAME, _RVOL_30MIN_CANONICAL_KEEP
    )


# ---------------------------------------------------------------------------
# Schema auto-detection
# ---------------------------------------------------------------------------

def detect_schema(path: str) -> SchemaType:
    """Infer the SchemaType from the header row of a Sierra Chart .txt export.

    Detection rules (checked in order):
    1. Header contains "ADR"                   → DAILY_ADR
    2. Header contains "# of Trades"            → ONE_MIN   (no VWAP columns)
    3. Header contains "VWAP" + "Volume"
       and column count ≤ 18                   → ETH_RTH_VWAP  (volume-bar intraday)
    4. Otherwise VWAP columns present           → VWAP_MULTI    (daily / high-vol)

    Args:
        path: Path to the .txt file.

    Returns:
        Detected SchemaType.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the schema cannot be detected.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"SC file not found: {path}")

    with p.open("r", encoding="utf-8", errors="replace") as fh:
        first_line = fh.readline().lstrip("\ufeff").strip()

    headers_lower = {h.strip().lower() for h in first_line.split(",")}
    headers_original = first_line
    col_count = len(first_line.split(","))

    if "adr" in headers_lower:
        return SchemaType.DAILY_ADR

    # RVOL 30-min file: has "Cumulative Volume Ratio" column
    if "cumulative volume ratio" in headers_lower:
        return SchemaType.RVOL_30MIN

    has_vwap = any("vwap" in h for h in headers_lower)
    has_volume = "volume" in headers_lower

    if has_vwap and has_volume:
        # Distinguish ETH_RTH_VWAP (#3, #4) from VWAP_MULTI (#5, #6, #7, #10).
        # Real ETH/RTH files contain Heikin Ashi or "Text Display" study columns.
        # Old-format test fixtures use 16 or fewer columns.
        has_heikin_ashi = any(
            kw in h for h in headers_lower for kw in ("ha open", "ha close", "text display")
        )
        if col_count <= 16 or has_heikin_ashi:
            return SchemaType.ETH_RTH_VWAP
        return SchemaType.VWAP_MULTI

    # Check ONE_MIN AFTER VWAP: real #5/#6/#7 have both "# of Trades" and VWAP columns
    if "# of trades" in headers_lower:
        return SchemaType.ONE_MIN

    raise ValueError(f"Cannot detect schema from header: {headers_original!r}")


# ---------------------------------------------------------------------------
# Latest bar
# ---------------------------------------------------------------------------

def get_latest_bar(path: str, schema: SchemaType) -> dict:
    """Return the last row of the file as a dict.

    For DAILY_ADR, also includes computed keys:
      - ``rvol``: last bar Volume / Avg column
      - ``adr``: ADR value from the last row

    Args:
        path: Path to the .txt file.
        schema: Schema variant.

    Returns:
        Dict of all column values from the last row, plus derived keys for DAILY_ADR.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the parsed DataFrame is empty.
    """
    df = parse_sc_file(path, schema)
    if df.empty:
        raise ValueError(f"No data rows found in {path}")

    last = df.iloc[-1].to_dict()
    last["datetime"] = df.index[-1].isoformat()

    if schema == SchemaType.DAILY_ADR:
        avg = last.get("Avg", 0.0) or 0.0
        volume = last.get("Volume", 0.0) or 0.0
        last["rvol"] = (volume / avg) if avg != 0.0 else float("nan")
        last["adr"] = last.get("ADR", float("nan"))

    return last


def get_pre_ultimate_bar(path: str, schema: SchemaType) -> dict:
    """Return the second-to-last row of the file as a dict.

    Used for daily files where the last row is a partial (current day) bar
    and yesterday's completed values are needed instead.

    Args:
        path: Path to the .txt file.
        schema: Schema variant.

    Returns:
        Dict of all column values from the penultimate row.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If fewer than 2 data rows exist.
    """
    df = parse_sc_file(path, schema)
    if len(df) < 2:
        raise ValueError(
            f"Need at least 2 rows for pre-ultimate bar, got {len(df)} in {path}"
        )
    row = df.iloc[-2].to_dict()
    row["datetime"] = df.index[-2].isoformat()
    return row


def get_recent_bars(path: str, schema: SchemaType, n: int) -> pd.DataFrame:
    """Return the last ``n`` rows from the parsed DataFrame.

    If fewer than ``n`` rows exist, all available rows are returned (no error).

    Args:
        path: Path to the .txt file.
        schema: Schema variant.
        n: Maximum number of trailing rows to return.

    Returns:
        DataFrame slice (may be smaller than ``n`` if file has fewer rows).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    df = parse_sc_file(path, schema)
    return df.iloc[-n:] if len(df) >= n else df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_df(schema: SchemaType) -> pd.DataFrame:
    if schema == SchemaType.VWAP_MULTI:
        return _empty_df_from_cols(_VWAP_MULTI_BASE_COLS, _VWAP_MULTI_NUMERIC_COLS)
    elif schema == SchemaType.DAILY_ADR:
        return _empty_df_from_cols(_DAILY_ADR_COLS, _DAILY_ADR_NUMERIC_COLS)
    elif schema == SchemaType.ONE_MIN:
        return _empty_df_from_cols(_ONE_MIN_COLS, _ONE_MIN_NUMERIC_COLS)
    elif schema == SchemaType.ETH_RTH_VWAP:
        return _empty_df_from_cols(_ETH_RTH_VWAP_CANONICAL_KEEP, _ETH_RTH_VWAP_CANONICAL_KEEP)
    elif schema == SchemaType.RVOL_30MIN:
        return _empty_df_from_cols(_RVOL_30MIN_CANONICAL_KEEP, _RVOL_30MIN_CANONICAL_KEEP)
    return pd.DataFrame()


def _empty_df_from_cols(col_names: list[str], numeric_cols: list[str]) -> pd.DataFrame:
    data_cols = [c for c in col_names if c not in ("Date", "Time")]
    df = pd.DataFrame(columns=data_cols)
    df.index.name = "datetime"
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.Series(dtype=float)
    return df

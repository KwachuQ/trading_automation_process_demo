from __future__ import annotations

import pandas as pd


def classify_timeframe(df: pd.DataFrame, n_bars: int = 3) -> dict:
    """Classify trend direction and price band position for a VWAP timeframe.

    Trend direction is derived from the last ``n_bars`` VWAP values:
    - rising   — each bar's VWAP >= previous bar's VWAP (monotonically
                  non-decreasing) OR the net change across the window is
                  strictly positive.
    - falling  — each bar's VWAP <= previous bar's VWAP (monotonically
                  non-increasing) OR the net change is strictly negative.
    - sideways — any other case, including insufficient data.

    Band position compares the latest ``Close`` to the ±1σ VWAP bands.
    In Sierra Chart exports the ±1σ bands are named "Top/Bottom Band 2 of
    Vwap Standard Deviation", which the SC parser renames to "Upper Band 2"
    and "Lower Band 2".  These are the columns used here.

    Args:
        df:     DataFrame produced by ``parse_sc_file`` for a VWAP schema.
                Must have a DatetimeIndex and columns ``VWAP``, ``Close``,
                ``Upper Band 2``, ``Lower Band 2``.
        n_bars: Number of trailing bars to use for trend computation.

    Returns:
        Dict with keys:
            trend         — "rising" | "falling" | "sideways"
            band_position — "imbalance_up" | "inside_value" | "imbalance_down" | None
        Plus all scalar values from the latest bar (float | None each).
    """
    result: dict = {
        "trend": "sideways",
        "band_position": None,
    }

    if df.empty:
        return result

    latest = df.iloc[-1]

    # --- raw latest bar values ---
    for col in df.columns:
        val = latest.get(col)
        try:
            result[col] = float(val) if val is not None else None
        except (TypeError, ValueError):
            result[col] = None

    # --- trend from last n_bars VWAP values ---
    if "VWAP" in df.columns:
        window = df["VWAP"].dropna().iloc[-n_bars:]
        if len(window) >= 2:
            diffs = window.diff().dropna()
            net = float(window.iloc[-1]) - float(window.iloc[0])
            if (diffs > 0).all() or net > 0:
                result["trend"] = "rising"
            elif (diffs < 0).all() or net < 0:
                result["trend"] = "falling"
            # else: sideways (already default, covers flat/mixed)
        # len < 2 → leave as sideways

    # --- band position vs ±1σ (Upper Band 2 / Lower Band 2 in parser output) ---
    try:
        close = float(latest["Close"]) if "Close" in latest.index else None
        upper = float(latest["Upper Band 2"]) if "Upper Band 2" in latest.index else None
        lower = float(latest["Lower Band 2"]) if "Lower Band 2" in latest.index else None
    except (TypeError, ValueError):
        close = upper = lower = None

    if close is not None and upper is not None and lower is not None:
        if close > upper:
            result["band_position"] = "imbalance_up"
        elif close < lower:
            result["band_position"] = "imbalance_down"
        else:
            result["band_position"] = "inside_value"

    return result

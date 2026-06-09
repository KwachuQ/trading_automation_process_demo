from __future__ import annotations

import logging
from datetime import date, datetime, time

import pandas as pd

logger = logging.getLogger(__name__)


def enrich_overnight_assessment(
    overnight_data: dict,
    eth_750v_df: pd.DataFrame,
    daily_df: pd.DataFrame,
    session_date: date | None = None,
) -> dict:
    """Enrich the overnight_json dict with derived boolean flags and range values.

    Takes the overnight_data dict already assembled by the ingestion pipeline
    (containing cumulative_delta, cd_ma, eth_upper_1, eth_lower_1, dvma from
    the ETH 750v #4 and daily #8 files) and adds:

    - cd_above_zero: cumulative_delta > 0
    - cd_above_ma: cumulative_delta > cd_ma
    - price_vs_eth_bands: latest ETH 750v Close vs ±1σ bands
    - volume_ma: alias for dvma (yesterday's completed Avg from daily #8)
    - eth_range: max(High) - min(Low) across ETH session bars (16:00 prev day
                 to 09:29:59 current day). When session_date is provided and
                 eth_750v_df has a DatetimeIndex, bars are filtered to that
                 window. Otherwise all rows in eth_750v_df are used.
    - eth_range_above_adr: eth_range > adr

    Missing keys in overnight_data produce None values for the enriched fields
    without raising.

    Args:
        overnight_data: Dict from ingestion step (b) with raw SC-extracted values.
        eth_750v_df: Parsed DataFrame from the ETH 750v #4 file (recent bars).
                     Should have a DatetimeIndex for time-window filtering.
        daily_df: Parsed DataFrame from the daily #8 file (kept for backward
                  compatibility; no longer used for ETH range).
        session_date: The trading session date (current day). When provided,
                      ETH range is filtered to bars from 16:00 previous calendar
                      day through 09:29:59 of this date.

    Returns:
        New dict merging overnight_data with the enriched keys.
    """
    result = dict(overnight_data)

    # --- Cumulative delta boolean flags ---
    cd = result.get("cumulative_delta")
    cd_ma = result.get("cd_ma")

    result["cd_above_zero"] = bool(cd > 0) if cd is not None else None
    result["cd_above_ma"] = (
        bool(cd > cd_ma) if (cd is not None and cd_ma is not None) else None
    )

    # --- Price position vs ETH ±1σ bands ---
    eth_upper = result.get("eth_upper_1")
    eth_lower = result.get("eth_lower_1")

    price_vs: str | None = None
    if (
        not eth_750v_df.empty
        and "Close" in eth_750v_df.columns
        and eth_upper is not None
        and eth_lower is not None
    ):
        latest_close = float(eth_750v_df.iloc[-1]["Close"])
        if latest_close > eth_upper:
            price_vs = "above +1.0 std ETH"
        elif latest_close < eth_lower:
            price_vs = "below -1.0 std ETH"
        else:
            price_vs = "between ETH bands"
    result["price_vs_eth_bands"] = price_vs

    # --- Volume MA: pre-ultimate Avg from daily #8 (already in overnight_data) ---
    result["volume_ma"] = result.get("dvma")

    # --- ETH range: max(High) - min(Low) over the ETH session window ---
    if (
        not eth_750v_df.empty
        and "High" in eth_750v_df.columns
        and "Low" in eth_750v_df.columns
    ):
        eth_window_df = eth_750v_df
        if session_date is not None and isinstance(eth_750v_df.index, pd.DatetimeIndex):
            from datetime import timedelta
            window_start = datetime.combine(
                session_date - timedelta(days=1), time(16, 0, 0)
            )
            window_end = datetime.combine(session_date, time(15, 59, 59))
            eth_window_df = eth_750v_df[
                (eth_750v_df.index >= window_start)
                & (eth_750v_df.index <= window_end)
            ]

        if not eth_window_df.empty:
            eth_range = float(
                eth_window_df["High"].max() - eth_window_df["Low"].min()
            )
            result["eth_range"] = eth_range
            adr = result.get("adr")
            if adr is not None:
                result["eth_range_above_adr"] = bool(eth_range > adr)
            else:
                result["eth_range_above_adr"] = None
        else:
            result["eth_range"] = None
            result["eth_range_above_adr"] = None
    else:
        result["eth_range"] = None
        result["eth_range_above_adr"] = None

    return result

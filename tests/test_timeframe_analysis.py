"""Tests for timeframe_analysis.py — Task 12."""
from __future__ import annotations

import pandas as pd
import pytest

from backend.ingestion.timeframe_analysis import classify_timeframe


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(
    vwap_values: list[float],
    close: float | None = None,
    upper_band2: float | None = None,
    lower_band2: float | None = None,
) -> pd.DataFrame:
    """Build a minimal VWAP-schema DataFrame for testing."""
    n = len(vwap_values)
    data: dict = {
        "VWAP": vwap_values,
        "Close": [close] * n if close is not None else [None] * n,
        "Upper Band 2": [upper_band2] * n if upper_band2 is not None else [None] * n,
        "Lower Band 2": [lower_band2] * n if lower_band2 is not None else [None] * n,
    }
    index = pd.date_range("2026-04-14 09:30", periods=n, freq="min")
    return pd.DataFrame(data, index=index)


# ---------------------------------------------------------------------------
# Trend classification
# ---------------------------------------------------------------------------

class TestTrendClassification:
    def test_rising_monotonic(self):
        df = _make_df([100.0, 101.0, 102.0], close=102.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "rising"

    def test_rising_net_positive(self):
        # Not strictly monotonic but net positive
        df = _make_df([100.0, 99.5, 102.0], close=102.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "rising"

    def test_falling_monotonic(self):
        df = _make_df([102.0, 101.0, 100.0], close=100.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "falling"

    def test_falling_net_negative(self):
        # Not strictly monotonic but net negative
        df = _make_df([102.0, 102.5, 100.0], close=100.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "falling"

    def test_sideways_flat(self):
        df = _make_df([100.0, 100.0, 100.0], close=100.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "sideways"

    def test_single_bar_defaults_to_sideways(self):
        df = _make_df([100.0], close=100.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "sideways"

    def test_more_bars_than_window_uses_only_last_n(self):
        # 5 bars: first 2 falling, last 3 rising — with n_bars=3 should be rising
        df = _make_df([105.0, 103.0, 100.0, 101.0, 102.0], close=102.0, upper_band2=107.0, lower_band2=95.0)
        result = classify_timeframe(df, n_bars=3)
        assert result["trend"] == "rising"


# ---------------------------------------------------------------------------
# Band position classification
# ---------------------------------------------------------------------------

class TestBandPosition:
    def test_above_upper_band_is_imbalance_up(self):
        df = _make_df([100.0, 101.0, 102.0], close=106.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df)
        assert result["band_position"] == "imbalance_up"

    def test_below_lower_band_is_imbalance_down(self):
        df = _make_df([100.0, 99.0, 98.0], close=94.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df)
        assert result["band_position"] == "imbalance_down"

    def test_between_bands_is_inside_value(self):
        df = _make_df([100.0, 101.0, 102.0], close=101.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df)
        assert result["band_position"] == "inside_value"

    def test_exactly_on_upper_band_is_inside_value(self):
        df = _make_df([100.0, 101.0, 102.0], close=105.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df)
        assert result["band_position"] == "inside_value"

    def test_missing_bands_returns_none(self):
        df = _make_df([100.0, 101.0, 102.0], close=102.0)
        result = classify_timeframe(df)
        assert result["band_position"] is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_df_returns_defaults(self):
        df = pd.DataFrame(columns=["VWAP", "Close", "Upper Band 2", "Lower Band 2"])
        result = classify_timeframe(df)
        assert result["trend"] == "sideways"
        assert result["band_position"] is None

    def test_returns_raw_bar_values(self):
        df = _make_df([100.0, 101.0, 102.0], close=102.5, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df)
        assert result["Close"] == pytest.approx(102.5)
        assert result["VWAP"] == pytest.approx(102.0)
        assert result["Upper Band 2"] == pytest.approx(105.0)
        assert result["Lower Band 2"] == pytest.approx(95.0)

    def test_default_n_bars_is_3(self):
        # Provide 5 bars — confirm n_bars=3 default uses only last 3
        # Last 3 are falling: 102 → 101 → 100
        df = _make_df([99.0, 100.0, 102.0, 101.0, 100.0], close=100.0, upper_band2=105.0, lower_band2=95.0)
        result = classify_timeframe(df)
        assert result["trend"] == "falling"

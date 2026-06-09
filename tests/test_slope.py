"""Tests for slope.py — Theil-Sen + volatility-normalised trend classification."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.ingestion.slope import (
    SlopeConfig,
    TrendResult,
    classify_trend,
    compute_slope,
    compute_trend_score,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Upward-trending NQ-scale series with realistic variation (5 bars)
RISING_5 = [19780.0, 19795.0, 19815.0, 19825.0, 19850.0]

# Downward mirror
FALLING_5 = [19850.0, 19825.0, 19815.0, 19795.0, 19780.0]

# 8-bar clearly rising series used for most classify_trend tests
RISING_8 = [19780.0, 19795.0, 19815.0, 19825.0, 19850.0, 19870.0, 19895.0, 19920.0]

# 8-bar clearly falling series
FALLING_8 = [19920.0, 19895.0, 19870.0, 19850.0, 19825.0, 19815.0, 19795.0, 19780.0]

# Alternating zigzag — no net trend, high volatility relative to slope
# Net drift: +65 pts over 7 steps, but ±20-point noise each bar
# Produces z-score in the dead-band (0.4–1.0) for the default config
MILD_RISING_8 = [19800.0, 19820.0, 19815.0, 19835.0, 19830.0, 19850.0, 19845.0, 19865.0]

_DEFAULT_CFG = SlopeConfig()


# ---------------------------------------------------------------------------
# compute_slope
# ---------------------------------------------------------------------------

class TestComputeSlope:
    def test_rising_series_is_positive(self):
        assert compute_slope(RISING_5) > 0

    def test_falling_series_is_negative(self):
        assert compute_slope(FALLING_5) < 0

    def test_identical_values_returns_zero(self):
        assert compute_slope([19800.0] * 5) == 0.0

    def test_single_value_returns_zero(self):
        assert compute_slope([19800.0]) == 0.0

    def test_empty_input_returns_zero(self):
        assert compute_slope([]) == 0.0

    def test_pandas_series_input(self):
        assert compute_slope(pd.Series(RISING_5)) > 0

    def test_n_bars_trims_to_last_n(self):
        # First 5 values falling, last 3 sharply rising — n_bars=3 should be positive
        combined = FALLING_5 + [19850.0, 19900.0, 19960.0]
        slope_all = compute_slope(combined, n_bars=len(combined))
        slope_last3 = compute_slope(combined, n_bars=3)
        assert slope_last3 > slope_all

    def test_nan_values_excluded(self):
        s = pd.Series([19780.0, float("nan"), 19815.0, float("nan"), 19850.0])
        assert compute_slope(s) > 0

    def test_outlier_robustness_vs_ols(self):
        """Theil-Sen slope should remain close to the clean-data slope even when
        one bar is replaced with a large spike.  OLS would diverge sharply."""
        clean = [19800.0 + i * 10 for i in range(8)]  # clean linear rise
        with_spike = list(clean)
        with_spike[3] = 99999.0  # massive outlier in the middle

        slope_clean = compute_slope(clean)
        slope_spike = compute_slope(with_spike)

        # Both should still be positive (same direction)
        assert slope_clean > 0
        assert slope_spike > 0
        # Spike shouldn't push slope to more than 5× the clean value
        assert slope_spike < slope_clean * 5


# ---------------------------------------------------------------------------
# compute_trend_score
# ---------------------------------------------------------------------------

class TestComputeTrendScore:
    def test_rising_series_gives_positive_score(self):
        score = compute_trend_score(RISING_8, n_bars=8, vol_lookback=8)
        assert score > 0

    def test_falling_series_gives_negative_score(self):
        score = compute_trend_score(FALLING_8, n_bars=8, vol_lookback=8)
        assert score < 0

    def test_flat_series_returns_zero(self):
        """All-equal values produce zero sigma → guarded to return 0.0."""
        assert compute_trend_score([19800.0] * 10, n_bars=8, vol_lookback=8) == 0.0

    def test_single_value_returns_zero(self):
        assert compute_trend_score([19800.0], n_bars=8, vol_lookback=8) == 0.0

    def test_empty_returns_zero(self):
        assert compute_trend_score([], n_bars=8, vol_lookback=8) == 0.0

    def test_clearly_rising_score_exceeds_entry_threshold(self):
        """RISING_8 should produce a score well above the default entry_threshold=1.0."""
        score = compute_trend_score(RISING_8, n_bars=8, vol_lookback=8)
        assert score > _DEFAULT_CFG.entry_threshold

    def test_clearly_falling_score_below_neg_entry_threshold(self):
        score = compute_trend_score(FALLING_8, n_bars=8, vol_lookback=8)
        assert score < -_DEFAULT_CFG.entry_threshold


# ---------------------------------------------------------------------------
# classify_trend
# ---------------------------------------------------------------------------

class TestClassifyTrend:
    def test_returns_trend_result_dataclass(self):
        result = classify_trend(RISING_8, _DEFAULT_CFG)
        assert isinstance(result, TrendResult)
        assert result.label in ("rising", "falling", "sideways")
        assert isinstance(result.short_score, float)
        assert isinstance(result.long_score, float)
        assert 0.0 <= result.confidence <= 1.0

    def test_clearly_rising_gives_rising_label(self):
        result = classify_trend(RISING_8, _DEFAULT_CFG)
        assert result.label == "rising"

    def test_clearly_falling_gives_falling_label(self):
        result = classify_trend(FALLING_8, _DEFAULT_CFG)
        assert result.label == "falling"

    def test_flat_series_gives_sideways(self):
        result = classify_trend([19800.0] * 10, _DEFAULT_CFG)
        assert result.label == "sideways"
        assert result.confidence == 0.0

    def test_empty_input_gives_sideways(self):
        result = classify_trend([], _DEFAULT_CFG)
        assert result.label == "sideways"

    def test_single_value_gives_sideways(self):
        result = classify_trend([19800.0], _DEFAULT_CFG)
        assert result.label == "sideways"

    def test_confidence_nonzero_for_rising(self):
        result = classify_trend(RISING_8, _DEFAULT_CFG)
        assert result.confidence > 0.0

    # ------------------------------------------------------------------
    # Hysteresis tests
    # ------------------------------------------------------------------

    def test_dead_band_stays_rising_with_prev_rising(self):
        """MILD_RISING_8 produces z-scores in the dead-band (below entry_threshold
        but above exit_threshold).  Without prior regime it resolves to sideways;
        with prev_regime='rising' it should stay rising (hysteresis)."""
        # Confirm the fresh-run result is sideways (scores < entry)
        fresh = classify_trend(MILD_RISING_8, _DEFAULT_CFG)
        assert fresh.label == "sideways"

        # With prior rising regime, the same series should stay rising
        held = classify_trend(MILD_RISING_8, _DEFAULT_CFG, prev_regime="rising")
        assert held.label == "rising"

    def test_exits_rising_when_score_drops_below_exit_threshold(self):
        """A flat series produces scores of 0.0, well below exit_threshold=0.4.
        Even with prev_regime='rising', it should exit to sideways."""
        flat = [19800.0] * 12
        result = classify_trend(flat, _DEFAULT_CFG, prev_regime="rising")
        assert result.label == "sideways"

    def test_strong_reversal_overrides_prev_rising(self):
        """A clearly falling series should flip to 'falling' even if the previous
        regime was 'rising' — strong reversals override the dead-band."""
        result = classify_trend(FALLING_8, _DEFAULT_CFG, prev_regime="rising")
        assert result.label == "falling"

    def test_dead_band_stays_falling_with_prev_falling(self):
        """Mirror of the rising dead-band test."""
        mild_falling = list(reversed(MILD_RISING_8))
        fresh = classify_trend(mild_falling, _DEFAULT_CFG)
        assert fresh.label == "sideways"

        held = classify_trend(mild_falling, _DEFAULT_CFG, prev_regime="falling")
        assert held.label == "falling"

    def test_sideways_prev_regime_same_as_none(self):
        """prev_regime='sideways' should behave identically to prev_regime=None."""
        result_none = classify_trend(MILD_RISING_8, _DEFAULT_CFG, prev_regime=None)
        result_sw = classify_trend(MILD_RISING_8, _DEFAULT_CFG, prev_regime="sideways")
        assert result_none.label == result_sw.label


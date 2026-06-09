"""Tests for the session volatility indication engine."""
from __future__ import annotations

import pytest

from backend.ingestion.volatility_engine import (
    classify_adr_trend,
    classify_dvma_trend,
    classify_rvol,
    compute_volatility_indication,
)


class TestClassifyDVMATrend:
    def test_positive_slope_above_threshold_returns_rising(self) -> None:
        assert classify_dvma_trend(1.0) == "rising"

    def test_negative_slope_below_threshold_returns_falling(self) -> None:
        assert classify_dvma_trend(-1.0) == "falling"

    def test_near_zero_slope_returns_sideways(self) -> None:
        assert classify_dvma_trend(0.005) == "sideways"

    def test_exactly_at_threshold_returns_sideways(self) -> None:
        assert classify_dvma_trend(0.010) == "sideways"

    def test_just_above_threshold_returns_rising(self) -> None:
        assert classify_dvma_trend(0.011) == "rising"

    def test_custom_threshold(self) -> None:
        assert classify_dvma_trend(0.3, threshold=0.2) == "rising"
        assert classify_dvma_trend(-0.3, threshold=0.2) == "falling"
        assert classify_dvma_trend(0.1, threshold=0.2) == "sideways"


class TestClassifyADRTrend:
    def test_positive_slope_above_threshold_returns_rising(self) -> None:
        assert classify_adr_trend(1.0) == "rising"

    def test_negative_slope_below_threshold_returns_falling(self) -> None:
        assert classify_adr_trend(-1.0) == "falling"

    def test_near_zero_slope_returns_sideways(self) -> None:
        assert classify_adr_trend(0.010) == "sideways"

    def test_exactly_at_positive_threshold_returns_sideways(self) -> None:
        # Boundary: equal to threshold is NOT above → sideways
        assert classify_adr_trend(0.020) == "sideways"

    def test_just_above_positive_threshold_returns_rising(self) -> None:
        assert classify_adr_trend(0.021) == "rising"

    def test_exactly_at_negative_threshold_returns_sideways(self) -> None:
        assert classify_adr_trend(-0.020) == "sideways"

    def test_just_below_negative_threshold_returns_falling(self) -> None:
        assert classify_adr_trend(-0.021) == "falling"

    def test_custom_threshold(self) -> None:
        assert classify_adr_trend(0.3, threshold=0.2) == "rising"
        assert classify_adr_trend(-0.3, threshold=0.2) == "falling"
        assert classify_adr_trend(0.1, threshold=0.2) == "sideways"


class TestClassifyRVOL:
    def test_value_above_high_threshold_returns_high(self) -> None:
        assert classify_rvol(105.0) == "high"

    def test_value_below_low_threshold_returns_low(self) -> None:
        assert classify_rvol(75.0) == "low"

    def test_value_between_thresholds_returns_normal(self) -> None:
        assert classify_rvol(90.0) == "normal"

    def test_exactly_at_high_threshold_returns_normal(self) -> None:
        # 100.0 is NOT above 100.0 → normal
        assert classify_rvol(100.0) == "normal"

    def test_just_above_high_threshold_returns_high(self) -> None:
        assert classify_rvol(100.1) == "high"

    def test_exactly_at_low_threshold_returns_normal(self) -> None:
        assert classify_rvol(80.0) == "normal"

    def test_just_below_low_threshold_returns_low(self) -> None:
        assert classify_rvol(79.9) == "low"

    def test_custom_thresholds(self) -> None:
        assert classify_rvol(1.5, low_threshold=1.0, high_threshold=2.0) == "normal"
        assert classify_rvol(2.1, low_threshold=1.0, high_threshold=2.0) == "high"
        assert classify_rvol(0.9, low_threshold=1.0, high_threshold=2.0) == "low"


class TestComputeVolatilityIndication:
    """Verify all 5 expectation levels using the 4-factor scoring system.

    Weights: ADR (Rising +2, Sideways 0, Falling -2)
             RVOL (High +2, Normal 0, Low -2)
             Gamma (Negative +2, Mixed 0, Positive -2)
             DVMA (Rising +2, Sideways 0, Falling -2)
    Thresholds: EXTREME ≥6, HIGH ≥3, MODERATE ≥-2, LOW ≥-5, VERY_LOW <-5
    """

    def test_extreme_max_score(self) -> None:
        # Rising(+2) + High(+2) + Negative(+2) + Rising_DVMA(+2) = 8 → EXTREME
        result = compute_volatility_indication(
            adr_slope=1.0, rvol=105.0, gamma="negative", dvma_slope=1.0
        )
        assert result.score == 8
        assert result.expectation == "EXTREME"
        assert result.adr_trend == "rising"
        assert result.rvol_level == "high"
        assert result.gamma_regime == "negative"
        assert result.dvma_trend == "rising"
        assert len(result.description) > 0

    def test_extreme_at_threshold_6(self) -> None:
        # Rising(+2) + High(+2) + Negative(+2) + Sideways(0) = 6 → EXTREME
        result = compute_volatility_indication(
            adr_slope=1.0, rvol=105.0, gamma="negative", dvma_slope=0.0
        )
        assert result.score == 6
        assert result.expectation == "EXTREME"

    def test_very_low_min_score(self) -> None:
        # Falling(-2) + Low(-2) + Positive(-2) + Falling_DVMA(-2) = -8 → VERY_LOW
        result = compute_volatility_indication(
            adr_slope=-1.0, rvol=75.0, gamma="positive", dvma_slope=-1.0
        )
        assert result.score == -8
        assert result.expectation == "VERY_LOW"
        assert result.dvma_trend == "falling"
        assert len(result.description) > 0

    def test_very_low_at_threshold_minus6(self) -> None:
        # Falling(-2) + Low(-2) + Positive(-2) + Sideways(0) = -6 → VERY_LOW
        result = compute_volatility_indication(
            adr_slope=-1.0, rvol=75.0, gamma="positive", dvma_slope=0.0
        )
        assert result.score == -6
        assert result.expectation == "VERY_LOW"

    def test_moderate_zero_score(self) -> None:
        # Sideways(0) + Normal(0) + Mixed(0) + Sideways(0) = 0 → MODERATE
        result = compute_volatility_indication(
            adr_slope=0.0, rvol=90.0, gamma="mixed", dvma_slope=0.0
        )
        assert result.score == 0
        assert result.expectation == "MODERATE"
        assert len(result.description) > 0

    def test_high_at_threshold_3(self) -> None:
        # Rising(+2) + Normal(0) + Mixed(0) + Rising(+2) = 4 → HIGH (≥3)
        result = compute_volatility_indication(
            adr_slope=1.0, rvol=90.0, gamma="mixed", dvma_slope=1.0
        )
        assert result.score == 4
        assert result.expectation == "HIGH"

    def test_high_score_just_below_extreme(self) -> None:
        # Rising(+2) + High(+2) + Mixed(0) + Rising(+2) = 6 - but wait that's EXTREME
        # Rising(+2) + Normal(0) + Negative(+2) + Rising(+2) = 6 → EXTREME
        # Rising(+2) + High(+2) + Mixed(0) + Sideways(0) = 4 → HIGH? No, 4 < 6 → HIGH
        result = compute_volatility_indication(
            adr_slope=1.0, rvol=105.0, gamma="mixed", dvma_slope=0.0
        )
        assert result.score == 4
        assert result.expectation == "HIGH"

    def test_low_score(self) -> None:
        # Falling(-2) + Normal(0) + Mixed(0) + Falling(-2) = -4 → LOW (≥-5)
        result = compute_volatility_indication(
            adr_slope=-1.0, rvol=90.0, gamma="mixed", dvma_slope=-1.0
        )
        assert result.score == -4
        assert result.expectation == "LOW"

    def test_low_at_threshold_minus3(self) -> None:
        # Falling(-2) + Normal(0) + Mixed(0) + Sideways(0) = -2 → MODERATE (≥-2)
        result = compute_volatility_indication(
            adr_slope=-1.0, rvol=90.0, gamma="mixed", dvma_slope=0.0
        )
        assert result.score == -2
        assert result.expectation == "MODERATE"

    def test_low_score_minus4(self) -> None:
        # Sideways(0) + Low(-2) + Positive(-2) + Sideways(0) = -4 → LOW
        result = compute_volatility_indication(
            adr_slope=0.0, rvol=75.0, gamma="positive", dvma_slope=0.0
        )
        assert result.score == -4
        assert result.expectation == "LOW"

    def test_dvma_slope_defaults_to_sideways(self) -> None:
        # dvma_slope not passed → defaults to 0.0 (sideways) → no change from 3-factor zero case
        result = compute_volatility_indication(adr_slope=0.0, rvol=90.0, gamma="mixed")
        assert result.dvma_trend == "sideways"
        assert result.score == 0
        assert result.expectation == "MODERATE"

    def test_description_non_empty_for_all_expectations(self) -> None:
        cases = [
            (1.0, 105.0, "negative", 1.0),   # EXTREME (8)
            (1.0, 90.0, "mixed", 1.0),        # HIGH (4)
            (0.0, 90.0, "mixed", 0.0),        # MODERATE (0)
            (-1.0, 90.0, "mixed", -1.0),      # LOW (-4)
            (-1.0, 75.0, "positive", -1.0),   # VERY_LOW (-8)
        ]
        for adr_slope, rvol, gamma, dvma_slope in cases:
            result = compute_volatility_indication(adr_slope, rvol, gamma, dvma_slope)
            assert result.description, f"Empty description for score={result.score}"

    def test_gamma_case_insensitive(self) -> None:
        result_lower = compute_volatility_indication(1.0, 105.0, "negative", 1.0)
        result_upper = compute_volatility_indication(1.0, 105.0, "Negative", 1.0)
        assert result_lower.score == result_upper.score
        assert result_lower.expectation == result_upper.expectation

    def test_unknown_gamma_defaults_to_mixed(self) -> None:
        result = compute_volatility_indication(0.0, 90.0, "unknown_value", 0.0)
        assert result.gamma_regime == "mixed"
        assert result.score == 0  # sideways(0) + normal(0) + mixed(0) + sideways(0) = 0

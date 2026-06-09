"""Session volatility indication engine.

Combines ADR trend direction, RVOL classification, gamma regime, and DVMA
trend into a single weighted volatility expectation score and maps it to a
named regime.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ADRTrend(str, Enum):
    rising = "rising"
    sideways = "sideways"
    falling = "falling"


class RVOLLevel(str, Enum):
    high = "high"
    normal = "normal"
    low = "low"


class GammaRegime(str, Enum):
    negative = "negative"
    mixed = "mixed"
    positive = "positive"


class DVMATrend(str, Enum):
    rising = "rising"
    sideways = "sideways"
    falling = "falling"


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class VolatilityIndication:
    adr_trend: str
    rvol_level: str
    gamma_regime: str
    dvma_trend: str
    score: int
    expectation: str   # EXTREME | HIGH | MODERATE | LOW | VERY_LOW
    description: str


# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

_ADR_WEIGHTS: dict[str, int] = {
    ADRTrend.rising: 2,
    ADRTrend.sideways: 0,
    ADRTrend.falling: -2,
}

_RVOL_WEIGHTS: dict[str, int] = {
    RVOLLevel.high: 2,
    RVOLLevel.normal: 0,
    RVOLLevel.low: -2,
}

_GAMMA_WEIGHTS: dict[str, int] = {
    GammaRegime.negative: 2,
    GammaRegime.mixed: 0,
    GammaRegime.positive: -2,
}

_DVMA_WEIGHTS: dict[str, int] = {
    DVMATrend.rising: 2,
    DVMATrend.sideways: 0,
    DVMATrend.falling: -2,
}


# ---------------------------------------------------------------------------
# Score → regime
# ---------------------------------------------------------------------------

def _score_to_expectation(score: int) -> str:
    # 4-factor range: -8 to +8
    if score >= 6:
        return "EXTREME"
    if score >= 3:
        return "HIGH"
    if score >= -2:
        return "MODERATE"
    if score >= -5:
        return "LOW"
    return "VERY_LOW"


_DESCRIPTIONS: dict[str, str] = {
    "EXTREME": "Explosive, trend-following, high-risk environment.",
    "HIGH": "Volatile, wide swings, expanding uncertainty.",
    "MODERATE": "Standard active trading conditions, manageable risk.",
    "LOW": "Quiet, contracting range, limited directional conviction.",
    "VERY_LOW": "Extremely stable, very low interest, near-dead market.",
}


# ---------------------------------------------------------------------------
# Public classification helpers
# ---------------------------------------------------------------------------

def classify_dvma_trend(dvma_slope: float, threshold: float = 0.010) -> str:
    """Map a pre-computed DVMA slope float to a trend label.

    Uses the same threshold logic as :func:`classify_adr_trend`.

    Args:
        dvma_slope: Slope value from ``compute_slope`` applied to the Avg
            column of the daily file.
        threshold: Absolute value above which the slope is considered
            directional.

    Returns:
        ``"rising"`` | ``"sideways"`` | ``"falling"``
    """
    if dvma_slope > threshold:
        return DVMATrend.rising.value
    if dvma_slope < -threshold:
        return DVMATrend.falling.value
    return DVMATrend.sideways.value


def classify_adr_trend(adr_slope: float, threshold: float = 0.020) -> str:
    """Map a pre-computed ADR slope float to a trend label.

    Args:
        adr_slope: Slope value from ``compute_slope`` (log-price units/bar).
        threshold: Absolute value above which the slope is considered
            directional.  Defaults to 0.020 (calibrated to n_bars=3 on daily data).

    Returns:
        ``"rising"`` | ``"sideways"`` | ``"falling"``
    """
    if adr_slope > threshold:
        return ADRTrend.rising.value
    if adr_slope < -threshold:
        return ADRTrend.falling.value
    return ADRTrend.sideways.value


def classify_rvol(
    rvol: float,
    low_threshold: float = 80.0,
    high_threshold: float = 100.0,
) -> str:
    """Classify a cumulative volume ratio value.

    Args:
        rvol: Cumulative Volume Ratio (30-min file).
        low_threshold: Values below this are classified as ``"low"``.
        high_threshold: Values above this are classified as ``"high"``.

    Returns:
        ``"high"`` | ``"normal"`` | ``"low"``
    """
    if rvol > high_threshold:
        return RVOLLevel.high.value
    if rvol < low_threshold:
        return RVOLLevel.low.value
    return RVOLLevel.normal.value


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def compute_volatility_indication(
    adr_slope: float,
    rvol: float,
    gamma: str,
    dvma_slope: float = 0.0,
) -> VolatilityIndication:
    """Compute a composite volatility expectation from four inputs.

    Args:
        adr_slope: Pre-computed ADR slope (from ``overnight_json``).
        rvol: Cumulative Volume Ratio from the 30-min SC file.
        gamma: Gamma regime string — ``"positive"``, ``"negative"``, or
            ``"mixed"``.
        dvma_slope: Pre-computed daily volume MA slope (from ``overnight_json``).
            Defaults to ``0.0`` (sideways) when not available.

    Returns:
        :class:`VolatilityIndication` with score, expectation label, and
        market behaviour description.
    """
    adr_trend = classify_adr_trend(adr_slope)
    rvol_level = classify_rvol(rvol)
    dvma_trend = classify_dvma_trend(dvma_slope)

    # Normalise gamma string — accept any capitalisation
    gamma_norm = gamma.lower().strip()
    if gamma_norm not in (GammaRegime.negative, GammaRegime.mixed, GammaRegime.positive):
        gamma_norm = GammaRegime.mixed.value  # safe default

    score = (
        _ADR_WEIGHTS[adr_trend]
        + _RVOL_WEIGHTS[rvol_level]
        + _GAMMA_WEIGHTS[gamma_norm]
        + _DVMA_WEIGHTS[dvma_trend]
    )
    expectation = _score_to_expectation(score)
    description = _DESCRIPTIONS[expectation]

    return VolatilityIndication(
        adr_trend=adr_trend,
        rvol_level=rvol_level,
        gamma_regime=gamma_norm,
        dvma_trend=dvma_trend,
        score=score,
        expectation=expectation,
        description=description,
    )

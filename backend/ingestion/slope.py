from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SlopeConfig:
    """Tunable parameters for trend estimation and classification.

    Defined in this module so the slope utilities are self-contained and
    usable without importing the full application config stack.
    """

    short_window: int = 8
    long_window: int = 21
    vol_lookback: int = 21
    persistence_bars: int = 2
    entry_threshold: float = 1.0
    exit_threshold: float = 0.4


@dataclass(frozen=True)
class DeltaSlopeConfig:
    """Config for the cumulative-delta slope classifier.

    Unlike ``SlopeConfig``, this uses a raw (non-log-transformed) Theil-Sen
    slope compared against absolute thresholds.  This is necessary because
    the cumulative delta MA series can be zero or negative, which makes the
    log-transform in the standard ``classify_trend`` path return 0.0 for the
    entire window — always producing "sideways".

    Attributes:
        n_bars:          Number of trailing bars for slope estimation.
        entry_threshold: Absolute slope value required to enter rising/falling.
        exit_threshold:  Absolute slope value below which the regime exits.
    """

    n_bars: int = 8
    entry_threshold: float = 0.003
    exit_threshold: float = 0.001


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class TrendResult:
    """Output of dual-window trend classification."""

    label: str          # "rising" | "falling" | "sideways"
    short_score: float  # volatility-normalised z-score, short window
    long_score: float   # volatility-normalised z-score, long window
    confidence: float   # 0–1 strength of the classification


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_clean_array(values: pd.Series | list[float]) -> np.ndarray:
    """Return a 1-D float array with NaN and None dropped."""
    if isinstance(values, pd.Series):
        return values.dropna().to_numpy(dtype=float)
    return np.array(
        [v for v in values if v is not None and not np.isnan(float(v))],
        dtype=float,
    )


def _log_array(arr: np.ndarray) -> np.ndarray:
    """Return natural log of arr.  Returns an empty array if any value <= 0."""
    if len(arr) == 0 or np.any(arr <= 0):
        return np.array([], dtype=float)
    return np.log(arr)


def _apply_hysteresis(
    short_score: float,
    long_score: float,
    prev_regime: str | None,
    entry: float,
    exit_: float,
) -> str:
    """Resolve the regime label with entry/exit hysteresis.

    Two separate thresholds prevent flicker: a regime is *entered* only
    when both windows exceed ``entry``, but it is *exited* when either
    window drops below ``exit_``.  The dead-band between the two thresholds
    keeps the label stable during minor pullbacks.
    """
    if prev_regime == "rising":
        # Strong reversal — directly flip to falling
        if short_score < -entry and long_score < -entry:
            return "falling"
        # Exit rising when either window drops below exit threshold
        if short_score < exit_ or long_score < exit_:
            return "sideways"
        return "rising"

    if prev_regime == "falling":
        if short_score > entry and long_score > entry:
            return "rising"
        if short_score > -exit_ or long_score > -exit_:
            return "sideways"
        return "falling"

    # No prior regime (first run) or "sideways" — require both windows to agree
    if short_score > entry and long_score > entry:
        return "rising"
    if short_score < -entry and long_score < -entry:
        return "falling"
    return "sideways"


def _compute_confidence(
    short_score: float,
    long_score: float,
    label: str,
    entry: float,
) -> float:
    """Return a [0, 1] confidence score for the assigned label.

    Confidence reflects how far the *weaker* window is past the entry
    threshold, capped at 1.0.  Returns 0.0 for sideways.
    """
    if label == "sideways":
        return 0.0
    sign = 1.0 if label == "rising" else -1.0
    weak_score = min(sign * short_score, sign * long_score)
    return float(min(1.0, max(0.0, weak_score / entry)))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_slope(values: pd.Series | list[float], n_bars: int = 5) -> float:
    """Estimate trend slope using Theil-Sen regression on log price.

    Operates in log-price space so the result is approximately the average
    per-bar fractional change and is scale-invariant across instruments.
    Theil-Sen is used instead of OLS for robustness against single bad bars
    (e.g. thin pre-market prints, data errors).

    Args:
        values: Price series (values must be positive).
        n_bars: Number of trailing bars to include.

    Returns:
        Slope in log-price units per bar.  Returns 0.0 for degenerate
        inputs (fewer than 2 values, all equal prices, non-positive prices).
    """
    arr = _to_clean_array(values)
    log_arr = _log_array(arr[-n_bars:])
    if len(log_arr) < 2:
        return 0.0
    x = np.arange(len(log_arr), dtype=float)
    result = stats.theilslopes(log_arr, x)
    slope = float(result.slope)
    return 0.0 if abs(slope) < 1e-12 else slope


def compute_trend_score(
    values: pd.Series | list[float],
    n_bars: int,
    vol_lookback: int,
) -> float:
    """Compute a volatility-normalised trend z-score.

    Divides the Theil-Sen log-price slope by the rolling standard deviation
    of log returns.  A score of ±1.0 means the trend is one standard
    deviation above typical noise, making it directly comparable across
    timeframes and instruments.

    Args:
        values: Price series (values must be positive).
        n_bars: Window for slope estimation.
        vol_lookback: Window for volatility estimation.

    Returns:
        Dimensionless z-score.  Returns 0.0 for degenerate inputs.
    """
    arr = _to_clean_array(values)
    slope = compute_slope(arr, n_bars)

    # Use the longer of the two windows for volatility estimation
    vol_arr = _log_array(arr[-max(n_bars, vol_lookback):])
    if len(vol_arr) < 2:
        return 0.0
    log_returns = np.diff(vol_arr)
    if len(log_returns) < 2:
        return 0.0
    sigma = float(np.std(log_returns, ddof=1))
    if sigma < 1e-10:
        return 0.0
    return slope / sigma


def classify_trend(
    values: pd.Series | list[float],
    config: SlopeConfig,
    prev_regime: str | None = None,
) -> TrendResult:
    """Classify trend direction using a dual-window volatility-normalised estimator.

    Applies Theil-Sen regression on log price for both a short and long
    window, normalises each score by rolling volatility, then resolves the
    final label via entry/exit hysteresis.  When the two windows disagree
    the label defaults to "sideways".

    Args:
        values: Price series.
        config: Window sizes and threshold parameters.
        prev_regime: Previously published label for this series (enables
            hysteresis).  Pass ``None`` on first run.

    Returns:
        ``TrendResult`` with label, both scores, and a confidence value.
    """
    short_score = compute_trend_score(values, config.short_window, config.vol_lookback)
    long_score = compute_trend_score(values, config.long_window, config.vol_lookback)

    label = _apply_hysteresis(
        short_score,
        long_score,
        prev_regime,
        config.entry_threshold,
        config.exit_threshold,
    )
    confidence = _compute_confidence(short_score, long_score, label, config.entry_threshold)

    return TrendResult(
        label=label,
        short_score=round(short_score, 6),
        long_score=round(long_score, 6),
        confidence=round(confidence, 6),
    )


def classify_delta_slope(
    values: pd.Series | list[float],
    config: DeltaSlopeConfig,
    prev_regime: str | None = None,
) -> str:
    """Classify cumulative-delta MA trend using raw Theil-Sen slope.

    Operates directly on the additive delta series without log-transforming,
    so it works correctly when the MA passes through zero or goes negative.
    Classification uses simple absolute entry/exit thresholds.

    Args:
        values:      Series of cumulative-delta MA values (``Avg`` column).
        config:      ``DeltaSlopeConfig`` with window size and thresholds.
        prev_regime: Previously published label for hysteresis
                     ("rising" | "falling" | "sideways" | None).

    Returns:
        One of ``"rising"``, ``"falling"``, or ``"sideways"``.
    """
    arr = _to_clean_array(values)
    if len(arr) < 2:
        return "sideways"

    slope = float(np.polyfit(np.arange(len(arr[-config.n_bars:])), arr[-config.n_bars:], 1)[0])

    entry = config.entry_threshold
    exit_ = config.exit_threshold

    # Apply entry/exit hysteresis to avoid flickering at the boundary.
    if prev_regime == "rising":
        if slope < -entry:
            return "falling"
        if slope < exit_:
            return "sideways"
        return "rising"

    if prev_regime == "falling":
        if slope > entry:
            return "rising"
        if slope > -exit_:
            return "sideways"
        return "falling"

    # No prior regime — require the slope to clearly exceed the entry threshold.
    if slope > entry:
        return "rising"
    if slope < -entry:
        return "falling"
    return "sideways"

"""Entry location classification utilities.

Provides a simple classifier that maps a z-score distance from ETH VWAP
to an `entry_quality` label depending on the active setup type.
"""
from __future__ import annotations

from typing import Literal


def classify_entry_quality(z_score: float, setup_type: str) -> str:
    """Classify entry quality from a z-score and setup type.

    Long setups (ML, MRL) expect positive z-scores. Short setups (MS, MRS)
    expect negative z-scores and the ranges are mirrored.

    Returns one of: 'Optimal', 'Good', 'Acceptable', 'Poor', 'Unacceptable'.
    Unknown setup types return 'Unacceptable' as a safe default.
    """
    long_setups = ("ML", "MRL")
    short_setups = ("MS", "MRS")

    if setup_type in long_setups:
        z = z_score
        if 1.0 <= z < 1.2:
            return "Optimal"
        if 1.2 <= z < 1.5:
            return "Good"
        if 1.5 <= z < 1.7:
            return "Acceptable"
        if z >= 1.7:
            return "Poor"
        return "Unacceptable"

    if setup_type in short_setups:
        # For shorts, z_score should be negative; classify by magnitude.
        if z_score >= 0:
            return "Unacceptable"
        z = abs(z_score)
        if 1.0 <= z < 1.2:
            return "Optimal"
        if 1.2 <= z < 1.5:
            return "Good"
        if 1.5 <= z < 1.7:
            return "Acceptable"
        if z >= 1.7:
            return "Poor"
        return "Unacceptable"

    return "Unacceptable"

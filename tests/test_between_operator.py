"""
tests/test_between_operator.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the new 'between' operator range evaluation.
"""

from __future__ import annotations

import pytest

from backend.feature_store.engine import (
    IndicatorSnapshot,
    _evaluate_condition,
)


def test_between_operator_basic_inclusive() -> None:
    """Check that value matches inside integer and float bounds (inclusive)."""
    # 1. Normal value in middle of float range
    snap = IndicatorSnapshot(rvol=150.0)
    assert _evaluate_condition(snap, "rvol", "between", [100.0, 200.0]) is True

    # 2. Inclusive lower bound
    assert _evaluate_condition(snap, "rvol", "between", [150.0, 200.0]) is True

    # 3. Inclusive upper bound
    assert _evaluate_condition(snap, "rvol", "between", [100.0, 150.0]) is True


def test_between_operator_out_of_bounds() -> None:
    """Check that values outside the range are not matched."""
    snap = IndicatorSnapshot(rvol=99.9)
    assert _evaluate_condition(snap, "rvol", "between", [100.0, 200.0]) is False

    snap = IndicatorSnapshot(rvol=200.1)
    assert _evaluate_condition(snap, "rvol", "between", [100.0, 200.0]) is False


def test_between_operator_string_list_compatible() -> None:
    """Verify that comma-separated string bounds are parsed correctly."""
    snap = IndicatorSnapshot(adr=250.0)
    # Comma-separated string format (standard database fallback format)
    assert _evaluate_condition(snap, "adr", "between", "200, 300") is True
    assert _evaluate_condition(snap, "adr", "between", "100.5, 250.0") is True
    assert _evaluate_condition(snap, "adr", "between", "250.0, 400.2") is True
    assert _evaluate_condition(snap, "adr", "between", "100, 200") is False


def test_between_operator_invalid_inputs_graceful() -> None:
    """Check that malformed bounds or non-numeric arguments return False instead of crashing."""
    snap = IndicatorSnapshot(rvol=150.0)

    # 1. Non-numeric values in list
    assert _evaluate_condition(snap, "rvol", "between", ["abc", 200]) is False
    assert _evaluate_condition(snap, "rvol", "between", [100, "xyz"]) is False

    # 2. Too few/many bounds in list
    assert _evaluate_condition(snap, "rvol", "between", [100]) is False
    assert _evaluate_condition(snap, "rvol", "between", [100, 200, 300]) is False

    # 3. Malformed string formats
    assert _evaluate_condition(snap, "rvol", "between", "100") is False
    assert _evaluate_condition(snap, "rvol", "between", "100,abc") is False
    assert _evaluate_condition(snap, "rvol", "between", "100, 200, 300") is False


def test_between_operator_null_safety() -> None:
    """Check that None indicator values gracefully evaluate to False without crashing."""
    snap = IndicatorSnapshot(rvol=None)
    assert _evaluate_condition(snap, "rvol", "between", [100, 200]) is False

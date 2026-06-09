"""
tests/test_setup_scoring.py
Tests for per-setup scoring logic using seeded criteria.
"""

import sqlite3
from pathlib import Path
import pytest

from backend.db import get_connection, init_db
from backend.feature_store.engine import IndicatorSnapshot, score_setup, ScenarioResult
from backend.feature_store.store import get_scoring_criteria_by_setup
from backend.feature_store.seed_scenarios import seed_scoring_criteria

@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test_scoring.db"
    c = get_connection(str(db_path))
    init_db(c)
    seed_scoring_criteria(c)
    return c

def test_ml_scoring_continuation_up(conn: sqlite3.Connection) -> None:
    # ML should score very high (>70) in continuation_up scenario
    criteria = get_scoring_criteria_by_setup(conn, "ML")
    snap = IndicatorSnapshot(
        delta_slope="rising",
        vwap_slope="rising",
        cd_vs_ma="above MA",
        gamma_regime="negative",
        rvol=150,
        vol_regime="HIGH"
    )
    # Include entry quality since new criteria were added for entry location
    snap.entry_quality = "Optimal"
    active_scenario = ScenarioResult(
        scenario_name="continuation_up",
        parent_regime="Trending up",
        subtype="continuation_up",
        confidence=0.9,
        matched_weight=40.0,
        total_weight=50.0,
        characteristics="",
        risk_adjustments={}
    )
    score = score_setup(snap, criteria, active_scenario)
    assert score.total_score > 70, f"Expected high score for ML, got {score.total_score}"

def test_ml_scoring_continuation_down(conn: sqlite3.Connection) -> None:
    # ML should score very low (<30) in continuation_down scenario
    criteria = get_scoring_criteria_by_setup(conn, "ML")
    snap = IndicatorSnapshot(
        delta_slope="falling",
        vwap_slope="falling",
        cd_vs_ma="below MA",
        gamma_regime="negative",
        rvol=150,
        vol_regime="HIGH"
    )
    active_scenario = ScenarioResult(
        scenario_name="continuation_down",
        parent_regime="Trending down",
        subtype="continuation_down",
        confidence=0.9,
        matched_weight=40.0,
        total_weight=50.0,
        characteristics="",
        risk_adjustments={}
    )
    score = score_setup(snap, criteria, active_scenario)
    assert score.total_score < 40, f"Expected low score for ML, got {score.total_score}"

def test_mrl_scoring_countertrend_variation(conn: sqlite3.Connection) -> None:
    # MRL should score moderate in a countertrend variation scenario
    criteria = get_scoring_criteria_by_setup(conn, "MRL")
    snap = IndicatorSnapshot(
        delta_slope="falling",
        vwap_slope="falling",
        gamma_regime="positive",
        vol_regime="MODERATE",
        rvol=110
    )
    active_scenario = ScenarioResult(
        scenario_name="countertrend_variation",
        parent_regime="Normal variation",
        subtype="countertrend_variation",
        confidence=0.7,
        matched_weight=30.0,
        total_weight=50.0,
        characteristics="",
        risk_adjustments={}
    )
    score = score_setup(snap, criteria, active_scenario)
    assert 30 <= score.total_score <= 70, f"Expected moderate score for MRL, got {score.total_score}"

def test_neutral_penalty_reduces_score(conn: sqlite3.Connection) -> None:
    criteria = get_scoring_criteria_by_setup(conn, "ML")
    snap_good = IndicatorSnapshot(
        delta_slope="rising", vwap_slope="rising"
    )
    active_scenario_trend = ScenarioResult(
        scenario_name="continuation_up", parent_regime="Trending up", subtype="continuation", confidence=0.8, matched_weight=0, total_weight=0, characteristics="", risk_adjustments={}
    )
    score_trend = score_setup(snap_good, criteria, active_scenario_trend)
    
    active_scenario_neutral = ScenarioResult(
        scenario_name="sideways_absorption", parent_regime="Neutral", subtype="absorption", confidence=0.8, matched_weight=0, total_weight=0, characteristics="", risk_adjustments={}
    )
    snap_neutral = IndicatorSnapshot(
        delta_slope="rising", vwap_slope="rising", vol_regime="LOW"
    )
    score_neutral = score_setup(snap_neutral, criteria, active_scenario_neutral)
    assert score_neutral.total_score < score_trend.total_score, f"Expected neutral penalty to reduce score. trend: {score_trend.total_score}, neutral: {score_neutral.total_score}"


def test_inactive_criterion_skipped() -> None:
    snap = IndicatorSnapshot(delta_slope="rising")
    from backend.feature_store.store import ScoringCriterion, RuleCondition
    crit = ScoringCriterion(
        id=1, name="test", 
        condition=RuleCondition(indicator="delta_slope", operator="==", value="rising", weight=10.0), 
        weight=10.0, is_active=False
    )
    score = score_setup(snap, [crit])
    assert score.total_score == 0.0
    assert len(score.breakdown) == 0

def test_scenario_attribute_checks() -> None:
    snap = IndicatorSnapshot()
    from backend.feature_store.store import ScoringCriterion, RuleCondition
    active_scenario = ScenarioResult(
        scenario_name="trending_up",
        parent_regime="Trending",
        subtype="up",
        confidence=1.0, matched_weight=1.0, total_weight=1.0, characteristics="", risk_adjustments={}
    )
    criteria = [
        ScoringCriterion(id=1, name="c1", condition=RuleCondition(indicator="scenario_name", operator="==", value="trending_up", weight=1.0), weight=1.0, is_active=True),
        ScoringCriterion(id=2, name="c2", condition=RuleCondition(indicator="scenario_name", operator="!=", value="trending_down", weight=1.0), weight=1.0, is_active=True),
        ScoringCriterion(id=3, name="c3", condition=RuleCondition(indicator="scenario_name", operator="in", value=["abc", "trending_up"], weight=1.0), weight=1.0, is_active=True),
        ScoringCriterion(id=4, name="c4", condition=RuleCondition(indicator="scenario_name", operator="unknown", value="xyz", weight=1.0), weight=1.0, is_active=True),
    ]
    score = score_setup(snap, criteria, active_scenario)
    assert score.total_score == 75.0  # 3 of 4 match, weights are 1.0 each
    assert score.breakdown[0]["matched"] is True
    assert score.breakdown[1]["matched"] is True
    assert score.breakdown[2]["matched"] is True
    assert score.breakdown[3]["matched"] is False

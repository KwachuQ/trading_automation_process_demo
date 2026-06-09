"""tests/test_entry_location.py
Unit tests for entry location classification (Task 54b).
"""
from backend.ingestion.entry_location import classify_entry_quality


def test_classify_long_optimal_good_acceptable_poor_unacceptable():
    assert classify_entry_quality(1.1, "ML") == "Optimal"
    assert classify_entry_quality(1.3, "ML") == "Good"
    assert classify_entry_quality(1.6, "ML") == "Acceptable"
    assert classify_entry_quality(1.8, "ML") == "Poor"
    assert classify_entry_quality(0.9, "ML") == "Unacceptable"


def test_classify_short_optimal_acceptable_unacceptable():
    assert classify_entry_quality(-1.1, "MS") == "Optimal"
    assert classify_entry_quality(-1.6, "MS") == "Acceptable"
    assert classify_entry_quality(0.5, "MS") == "Unacceptable"


def test_unknown_setup_returns_unacceptable():
    assert classify_entry_quality(1.2, "UNKNOWN") == "Unacceptable"


def test_entry_location_criterion_matches_in_scoring(conn_tmp_path=None):
    # Integration-style check: seed criteria and verify ml_entry_location matches
    import sqlite3
    from backend.db import get_connection, init_db
    from backend.feature_store.seed_scenarios import seed_scoring_criteria
    from backend.feature_store.store import get_scoring_criteria_by_setup
    from backend.feature_store.engine import IndicatorSnapshot, score_setup
    from backend.feature_store.engine import ScenarioResult

    tmp_db = conn_tmp_path
    if tmp_db is None:
        # When pytest fixture is not available, create a temp DB path
        import tempfile
        p = tempfile.NamedTemporaryFile(delete=False)
        tmp_db = p.name
    conn = get_connection(str(tmp_db))
    init_db(conn)
    seed_scoring_criteria(conn)

    criteria = get_scoring_criteria_by_setup(conn, "ML")
    snap = IndicatorSnapshot(entry_quality="Optimal")
    active_scenario = ScenarioResult(
        scenario_name="continuation_up",
        parent_regime="Trending up",
        subtype="continuation_up",
        confidence=0.9,
        matched_weight=0.0,
        total_weight=0.0,
        characteristics="",
        risk_adjustments={},
    )
    score = score_setup(snap, criteria, active_scenario)

    # Find ml_entry_location contribution in breakdown
    found = [b for b in score.breakdown if b["criterion_name"] == "ml_entry_location"]
    assert found, "ml_entry_location not found in breakdown"
    assert found[0]["matched"] is True
    conn.close()

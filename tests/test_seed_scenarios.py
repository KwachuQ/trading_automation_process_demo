"""
tests/test_seed_scenarios.py
Tests for the feature store seeding logic.
"""

import sqlite3
from pathlib import Path
import pytest

from backend.db import get_connection, init_db
from backend.feature_store.store import get_market_scenarios, get_scoring_criteria
from backend.feature_store.seed_scenarios import seed_market_scenarios, seed_scoring_criteria

@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test_seed.db"
    c = get_connection(str(db_path))
    init_db(c)
    return c

def test_seed_market_scenarios(conn: sqlite3.Connection) -> None:
    # Clear DB if needed, but init_db should be empty initially.
    
    # First run
    seed_market_scenarios(conn)
    scenarios = get_market_scenarios(conn)
    assert len(scenarios) == 16, f"Expected 16 scenarios, got {len(scenarios)}"
    assert all(s.is_active for s in scenarios), "Expected all scenarios to be active"
    
    # Second run (idempotency)
    seed_market_scenarios(conn)
    scenarios2 = get_market_scenarios(conn)
    assert len(scenarios2) == 16, "Seed should be idempotent and not duplicate rows"

def test_seed_scoring_criteria(conn: sqlite3.Connection) -> None:
    # First run
    seed_scoring_criteria(conn)
    criteria = get_scoring_criteria(conn)
    assert len(criteria) == 52, f"Expected 52 criteria, got {len(criteria)}"
    
    # Check counts per setup
    setup_counts = {}
    for c in criteria:
        setup_counts[c.setup_type] = setup_counts.get(c.setup_type, 0) + 1
    
    for setup_type in ['ML', 'MS', 'MRL', 'MRS']:
        assert setup_counts.get(setup_type) == 13, f"Expected 13 criteria for {setup_type}"
        
    # Second run (idempotency)
    seed_scoring_criteria(conn)
    criteria2 = get_scoring_criteria(conn)
    assert len(criteria2) == 52, "Seed should be idempotent and not duplicate rows"

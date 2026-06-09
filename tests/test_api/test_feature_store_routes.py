"""
tests/test_api/test_feature_store_routes.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Full CRUD test suite for the Feature Store REST API:

    - Regime rules: POST → GET (all) → PUT → GET (by id) → DELETE → GET (empty)
    - Scoring criteria: same full cycle
    - Validation: empty name → 422, empty conditions → 422, weight=0 → 422
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.db import get_connection, init_db
from backend.main import app
from backend.state import app_state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(tmp_path: Path):
    """Stand up an in-memory test DB and wire it into app_state.

    Yields:
        TestClient configured against the FastAPI app.
    """
    db_path = str(tmp_path / "test_fs.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    # Use the same app_state key that the feature_store router reads
    app_state["db_path"] = db_path
    yield TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Shared payload factories
# ---------------------------------------------------------------------------


def _regime_payload(name: str = "Trending Bullish") -> dict:
    """Build a valid POST/PUT body for a market scenario."""
    return {
        "name": name,
        "conditions": [
            {
                "indicator": "trend_yearly",
                "operator": "==",
                "value": "rising",
                "weight": 2.0,
            }
        ],
        "characteristics": "Strong uptrend across all timeframes.",
        "risk_adjustments": {"position_size_modifier": 1.5},
        "is_active": True,
        "parent_regime": "Trending up",
        "subtype": "continuation_up",
    }


def _criterion_payload(name: str = "Rising yearly trend") -> dict:
    """Build a valid POST/PUT body for a scoring criterion."""
    return {
        "name": name,
        "condition": {
            "indicator": "trend_yearly",
            "operator": "==",
            "value": "rising",
            "weight": 3.0,
        },
        "weight": 3.0,
        "is_active": True,
    }


# ---------------------------------------------------------------------------
# Regime rule CRUD tests
# ---------------------------------------------------------------------------


class TestRegimeRuleCRUD:
    """Full lifecycle tests for /api/feature-store/scenarios."""

    def test_post_regime_returns_201(self, client: TestClient) -> None:
        """POST a valid regime rule → 201 with id assigned."""
        resp = client.post("/api/feature-store/scenarios", json=_regime_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == "Trending Bullish"
        assert len(body["conditions"]) == 1

    def test_get_all_regimes_returns_list_of_one(self, client: TestClient) -> None:
        """GET after one POST → list of length 17."""
        client.post("/api/feature-store/scenarios", json=_regime_payload())
        resp = client.get("/api/feature-store/scenarios")
        assert resp.status_code == 200
        assert len(resp.json()) == 17

    def test_put_renames_regime_rule(self, client: TestClient) -> None:
        """PUT with a new name → 200, name updated."""
        rule_id = client.post(
            "/api/feature-store/scenarios", json=_regime_payload()
        ).json()["id"]

        updated_payload = _regime_payload("Renamed Regime")
        resp = client.put(f"/api/feature-store/scenarios/{rule_id}", json=updated_payload)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Regime"

    def test_get_by_id_returns_updated_name(self, client: TestClient) -> None:
        """GET /regimes/{id} after PUT → reflects the renamed value."""
        rule_id = client.post(
            "/api/feature-store/scenarios", json=_regime_payload()
        ).json()["id"]
        client.put(f"/api/feature-store/scenarios/{rule_id}", json=_regime_payload("New Name"))

        resp = client.get(f"/api/feature-store/scenarios/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_delete_regime_returns_204(self, client: TestClient) -> None:
        """DELETE a rule → 204 No Content."""
        rule_id = client.post(
            "/api/feature-store/scenarios", json=_regime_payload()
        ).json()["id"]

        resp = client.delete(f"/api/feature-store/scenarios/{rule_id}")
        assert resp.status_code == 204

    def test_get_all_regimes_empty_after_delete(self, client: TestClient) -> None:
        """GET after DELETE → length 16."""
        rule_id = client.post(
            "/api/feature-store/scenarios", json=_regime_payload()
        ).json()["id"]
        client.delete(f"/api/feature-store/scenarios/{rule_id}")

        resp = client.get("/api/feature-store/scenarios")
        assert resp.status_code == 200
        assert len(resp.json()) == 16

    def test_get_nonexistent_regime_returns_404(self, client: TestClient) -> None:
        """GET /regimes/9999 → 404."""
        resp = client.get("/api/feature-store/scenarios/9999")
        assert resp.status_code == 404

    def test_put_nonexistent_regime_returns_404(self, client: TestClient) -> None:
        """PUT to a non-existent id → 404."""
        resp = client.put(
            "/api/feature-store/scenarios/9999", json=_regime_payload("Ghost")
        )
        assert resp.status_code == 404

    def test_delete_nonexistent_regime_returns_404(self, client: TestClient) -> None:
        """DELETE a non-existent id → 404."""
        resp = client.delete("/api/feature-store/scenarios/9999")
        assert resp.status_code == 404

    def test_active_only_filter_excludes_inactive_rule(
        self, client: TestClient
    ) -> None:
        """Inactive rules do not appear in the default ?active_only=true list."""
        payload = _regime_payload()
        payload["is_active"] = False
        client.post("/api/feature-store/scenarios", json=payload)

        # Default list (active_only=True) should be 16
        resp = client.get("/api/feature-store/scenarios")
        assert len(resp.json()) == 16

        # Explicit active_only=false should return it
        resp_all = client.get("/api/feature-store/scenarios?active_only=false")
        assert len(resp_all.json()) == 17


# ---------------------------------------------------------------------------
# Scoring criterion CRUD tests
# ---------------------------------------------------------------------------


class TestScoringCriterionCRUD:
    """Full lifecycle tests for /api/feature-store/scoring."""

    def test_post_criterion_returns_201(self, client: TestClient) -> None:
        """POST a valid criterion → 201 with id assigned."""
        resp = client.post("/api/feature-store/scoring", json=_criterion_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["id"] is not None
        assert body["name"] == "Rising yearly trend"
        assert body["weight"] == 3.0

    def test_get_all_criteria_returns_list_of_one(self, client: TestClient) -> None:
        """GET after one POST → list of length 49."""
        client.post("/api/feature-store/scoring", json=_criterion_payload())
        resp = client.get("/api/feature-store/scoring")
        assert resp.status_code == 200
        assert len(resp.json()) == 53

    def test_put_updates_criterion(self, client: TestClient) -> None:
        """PUT with new name → 200, name updated."""
        crit_id = client.post(
            "/api/feature-store/scoring", json=_criterion_payload()
        ).json()["id"]

        updated = _criterion_payload("Renamed Criterion")
        resp = client.put(f"/api/feature-store/scoring/{crit_id}", json=updated)
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed Criterion"

    def test_get_by_id_returns_updated_name(self, client: TestClient) -> None:
        """GET /scoring/{id} after PUT → reflects the renamed value."""
        crit_id = client.post(
            "/api/feature-store/scoring", json=_criterion_payload()
        ).json()["id"]
        client.put(
            f"/api/feature-store/scoring/{crit_id}",
            json=_criterion_payload("Updated Name"),
        )

        resp = client.get(f"/api/feature-store/scoring/{crit_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_delete_criterion_returns_204(self, client: TestClient) -> None:
        """DELETE a criterion → 204 No Content."""
        crit_id = client.post(
            "/api/feature-store/scoring", json=_criterion_payload()
        ).json()["id"]

        resp = client.delete(f"/api/feature-store/scoring/{crit_id}")
        assert resp.status_code == 204

    def test_get_all_criteria_empty_after_delete(self, client: TestClient) -> None:
        """GET after DELETE → length 48."""
        crit_id = client.post(
            "/api/feature-store/scoring", json=_criterion_payload()
        ).json()["id"]
        client.delete(f"/api/feature-store/scoring/{crit_id}")

        resp = client.get("/api/feature-store/scoring")
        assert resp.status_code == 200
        assert len(resp.json()) == 52

    def test_get_nonexistent_criterion_returns_404(self, client: TestClient) -> None:
        """GET /scoring/9999 → 404."""
        resp = client.get("/api/feature-store/scoring/9999")
        assert resp.status_code == 404

    def test_put_nonexistent_criterion_returns_404(self, client: TestClient) -> None:
        """PUT to a non-existent criterion id → 404."""
        resp = client.put(
            "/api/feature-store/scoring/9999", json=_criterion_payload("Ghost")
        )
        assert resp.status_code == 404

    def test_delete_nonexistent_criterion_returns_404(
        self, client: TestClient
    ) -> None:
        """DELETE a non-existent criterion id → 404."""
        resp = client.delete("/api/feature-store/scoring/9999")
        assert resp.status_code == 404

    def test_active_only_filter_excludes_inactive_criterion(
        self, client: TestClient
    ) -> None:
        """Inactive criteria do not appear in the default active-only list."""
        payload = _criterion_payload()
        payload["is_active"] = False
        client.post("/api/feature-store/scoring", json=payload)

        resp = client.get("/api/feature-store/scoring")
        assert len(resp.json()) == 52

        resp_all = client.get("/api/feature-store/scoring?active_only=false")
        assert len(resp_all.json()) == 53


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


class TestValidation:
    """Input validation tests — should return 422 on bad payloads."""

    def test_post_regime_with_empty_name_returns_422(
        self, client: TestClient
    ) -> None:
        """Regime rule with blank name → 422."""
        payload = _regime_payload()
        payload["name"] = ""
        resp = client.post("/api/feature-store/scenarios", json=payload)
        assert resp.status_code == 422

    def test_post_regime_with_whitespace_name_returns_422(
        self, client: TestClient
    ) -> None:
        """Regime rule with whitespace-only name → 422."""
        payload = _regime_payload()
        payload["name"] = "   "
        resp = client.post("/api/feature-store/scenarios", json=payload)
        assert resp.status_code == 422

    def test_post_regime_with_empty_conditions_returns_422(
        self, client: TestClient
    ) -> None:
        """Regime rule with empty conditions list → 422."""
        payload = _regime_payload()
        payload["conditions"] = []
        resp = client.post("/api/feature-store/scenarios", json=payload)
        assert resp.status_code == 422

    def test_post_criterion_with_zero_weight_returns_422(
        self, client: TestClient
    ) -> None:
        """Scoring criterion with weight=0 → 422."""
        payload = _criterion_payload()
        payload["weight"] = 0
        payload["condition"]["weight"] = 0
        resp = client.post("/api/feature-store/scoring", json=payload)
        assert resp.status_code == 422

    def test_post_criterion_with_negative_weight_returns_422(
        self, client: TestClient
    ) -> None:
        """Scoring criterion with negative weight → 422."""
        payload = _criterion_payload()
        payload["weight"] = -1.0
        payload["condition"]["weight"] = -1.0
        resp = client.post("/api/feature-store/scoring", json=payload)
        assert resp.status_code == 422

    def test_post_criterion_with_empty_name_returns_422(
        self, client: TestClient
    ) -> None:
        """Scoring criterion with blank name → 422."""
        payload = _criterion_payload()
        payload["name"] = ""
        resp = client.post("/api/feature-store/scoring", json=payload)
        assert resp.status_code == 422

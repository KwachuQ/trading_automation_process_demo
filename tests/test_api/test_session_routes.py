import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db import get_connection, init_db
from backend.main import app
from backend.state import app_state

@pytest.fixture()
def client(tmp_path: Path):
    db_path = str(tmp_path / "test_session.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    db_conn = get_connection(db_path)
    app_state["db_conn"] = db_conn
    app_state["db_path"] = db_path

    from backend.config import Config, SierraChartConfig
    from backend.ingestion.slope import SlopeConfig, DeltaSlopeConfig
    app_state["config"] = Config(
        sierra_chart=SierraChartConfig(
            data_dir=".", yearly_vwap="y.txt", quarterly_vwap="q.txt", monthly_vwap="m.txt", weekly_vwap="w.txt",
            daily_adr="d.txt", eth_750v="e.txt", rth_500v="rth.txt", rvol_30min="r.txt", nq_1min="n.txt", qqq_1min="qqq.txt"
        ),
        slope=SlopeConfig(),
        slope_delta=DeltaSlopeConfig(),
        slope_rvol=SlopeConfig(entry_threshold=0.2, exit_threshold=0.05),
        volatility=None, calendar=None, report=None, scaling=None, poller=None, server=None, logging=None
    )
    yield TestClient(app, raise_server_exceptions=True)
    db_conn.close()

def test_scenario_crud(client: TestClient):
    # POST scenarios
    response = client.post(
        "/api/session/scenarios",
        json={
            "session_date": "2026-05-19",
            "scenarios": [
                {
                    "scenario_number": 1,
                    "setup_type": "MRS",
                    "rationale": "High RVOL",
                    "targets": "VWAP"
                },
                {
                    "scenario_number": 2,
                    "setup_type": "MRL",
                    "rationale": "Low RVOL",
                    "targets": "HOD"
                }
            ]
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["scenario_number"] == 1
    assert data[0]["setup_type"] == "MRS"

    # GET scenarios
    response = client.get("/api/session/scenarios/2026-05-19")
    assert response.status_code == 200
    assert len(response.json()) == 2

    # DELETE scenario
    response = client.delete("/api/session/scenarios/2026-05-19/1")
    assert response.status_code == 200

    # GET after delete
    response = client.get("/api/session/scenarios/2026-05-19")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["scenario_number"] == 2

    # DELETE non-existent
    response = client.delete("/api/session/scenarios/2026-05-19/999")
    assert response.status_code == 404


@patch("backend.routers.session.get_recent_bars")
def test_live_session(mock_get_recent_bars, client: TestClient):
    import pandas as pd
    
    # Mock get_recent_bars to return empty df so it doesn't crash, 
    # we just want to test that the endpoint calls evaluation successfully.
    mock_get_recent_bars.return_value = pd.DataFrame()

    response = client.get("/api/session/live")
    assert response.status_code == 200
    data = response.json()
    assert "snapshot" in data
    assert "regime" in data
    assert "setup_scores" in data
    assert data["regime"]["scenario_name"] == "Unclassified" # since empty snapshot and no rules


@patch("backend.routers.session.get_recent_bars")
def test_live_session_entry_quality(mock_get_recent_bars, client: TestClient):
    import pandas as pd
    from backend.ingestion.sc_parser import SchemaType

    # Construct minimal ETH and NQ dataframes that will trigger entry-location logic.
    eth_df = pd.DataFrame([
        {"VWAP": 30445.91, "Upper Band 2": 30518.72, "Close": 30500.0, "Avg": 1.0, "delta_close": 2.0}
    ])
    nq_df = pd.DataFrame([
        {"Last": 30531.0}
    ])

    def side_effect(path, schema, n=5):
        if schema == SchemaType.ETH_RTH_VWAP:
            return eth_df
        if schema == SchemaType.ONE_MIN:
            return nq_df
        return pd.DataFrame()

    mock_get_recent_bars.side_effect = side_effect

    # Mark an active setup so classification runs
    response = client.post("/api/session/active-setup", json={"setup_type": "ML"})
    assert response.status_code == 200

    response = client.get("/api/session/live")
    assert response.status_code == 200
    data = response.json()
    assert "snapshot" in data
    assert "entry_quality" in data["snapshot"]
    assert data["snapshot"]["entry_quality"] is not None


# ---------------------------------------------------------------------------
# GET /api/session/active-setup — re-hydration endpoint tests
# ---------------------------------------------------------------------------

def test_get_active_setup_returns_none_when_no_rows(client: TestClient):
    """GET /active-setup returns null setup_type when nothing has been logged today."""
    response = client.get("/api/session/active-setup")
    assert response.status_code == 200
    assert response.json()["setup_type"] is None


def test_get_active_setup_returns_posted_setup(client: TestClient):
    """GET /active-setup reflects the setup_type written by POST /active-setup."""
    post_resp = client.post("/api/session/active-setup", json={"setup_type": "ML"})
    assert post_resp.status_code == 200

    get_resp = client.get("/api/session/active-setup")
    assert get_resp.status_code == 200
    assert get_resp.json()["setup_type"] == "ML"


def test_get_active_setup_returns_most_recent_when_multiple_rows(client: TestClient):
    """GET /active-setup returns the *latest* row when the trader switched setups."""
    client.post("/api/session/active-setup", json={"setup_type": "MRS"})
    client.post("/api/session/active-setup", json={"setup_type": "ML"})

    get_resp = client.get("/api/session/active-setup")
    assert get_resp.status_code == 200
    assert get_resp.json()["setup_type"] == "ML"


def test_get_active_setup_returns_empty_string_when_cleared(client: TestClient):
    """GET /active-setup returns '' (not None) when the trader explicitly cleared the setup."""
    client.post("/api/session/active-setup", json={"setup_type": "ML"})
    client.post("/api/session/active-setup", json={"setup_type": ""})

    get_resp = client.get("/api/session/active-setup")
    assert get_resp.status_code == 200
    # An explicit clear is stored as "" — the frontend treats "" as inactive.
    assert get_resp.json()["setup_type"] == ""

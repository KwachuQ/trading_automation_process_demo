from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db import get_connection, init_db
from backend.ingestion.slope import SlopeConfig
from backend.ingestion.volatility import VolatilityData, VolatilityFetchError
from backend.ingestion.economic_calendar import CalendarEvent
from backend.ingestion.qqq_nq_converter import ConversionResult
from backend.main import app
from backend.state import app_state
import pandas as pd


@pytest.fixture()
def client(tmp_path: Path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    app_state["db_path"] = db_path
    # Do not use 'with' context manager — avoids triggering the production lifespan
    yield TestClient(app, raise_server_exceptions=True), db_path


_VALID_NQ_DATA = {
    "call_resistance": 21000.0,
    "put_support": 20800.0,
    "call_resistance_0dte": 21050.0,
    "put_support_0dte": 20750.0,
    "hvl": 20900.0,
    "hvl_0dte": 20850.0,
    "exp_move_max": 21100.0,
    "exp_move_min": 20700.0,
}

_VALID_QQQ_DATA = {
    "call_resistance": 490.0,
    "put_support": 480.0,
    "call_resistance_0dte": 492.0,
    "put_support_0dte": 478.0,
    "hvl": 485.0,
    "hvl_0dte": 484.0,
    "exp_move_max": 495.0,
    "exp_move_min": 475.0,
}


class TestManualInputEndpoint:
    def test_post_menthorq_nq_returns_201(self, client):
        c, db_path = client
        resp = c.post("/api/ingestion/manual", json={
            "input_type": "menthorq_nq",
            "data": _VALID_NQ_DATA,
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body["input_type"] == "menthorq_nq"
        assert body["id"] is not None

        # Verify row exists in DB
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT COUNT(*) FROM manual_inputs WHERE input_type = 'menthorq_nq'"
        ).fetchone()
        conn.close()
        assert row[0] == 1

    def test_upsert_keeps_single_row_and_updates_value(self, client):
        c, db_path = client
        c.post("/api/ingestion/manual", json={
            "input_type": "menthorq_nq",
            "data": _VALID_NQ_DATA,
        })
        # Second submission with updated value
        updated = {**_VALID_NQ_DATA, "call_resistance": 21500.0}
        resp = c.post("/api/ingestion/manual", json={
            "input_type": "menthorq_nq",
            "data": updated,
        })
        assert resp.status_code == 201

        conn = get_connection(db_path)
        rows = conn.execute(
            "SELECT data_json FROM manual_inputs WHERE input_type = 'menthorq_nq'"
        ).fetchall()
        conn.close()
        assert len(rows) == 1
        saved = json.loads(rows[0][0])
        assert saved["call_resistance"] == 21500.0

    def test_post_gamma_returns_201(self, client):
        c, _ = client
        resp = c.post("/api/ingestion/manual", json={
            "input_type": "gamma",
            "data": {"regime": "positive"},
        })
        assert resp.status_code == 201
        assert resp.json()["input_type"] == "gamma"

    def test_missing_required_field_returns_422(self, client):
        c, _ = client
        incomplete = {k: v for k, v in _VALID_NQ_DATA.items() if k != "hvl"}
        resp = c.post("/api/ingestion/manual", json={
            "input_type": "menthorq_nq",
            "data": incomplete,
        })
        assert resp.status_code == 422

    def test_invalid_gamma_regime_returns_422(self, client):
        c, _ = client
        resp = c.post("/api/ingestion/manual", json={
            "input_type": "gamma",
            "data": {"regime": "bullish"},
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Orchestration tests
# ---------------------------------------------------------------------------

_DUMMY_SC_CONFIG = {
    "data_dir": "/sc",
    "nq_1min": "nq.txt",
    "qqq_1min": "qqq.txt",
    "quarterly_vwap": "q.txt",
    "monthly_vwap": "m.txt",
    "weekly_vwap": "w.txt",
    "yearly_vwap": "y.txt",
    "daily_adr": "d.txt",
    "rth_500v": "r.txt",
    "eth_750v": "e.txt",
    "rvol_30min": "rvol.txt",
}


def _build_mock_config(tmp_path):
    from backend.config import (
        CalendarConfig, PollerConfig, ReportConfig, ScalingConfig,
        ServerConfig, SierraChartConfig, VolatilityConfig, LoggingConfig,
        Config
    )
    from backend.ingestion.slope import SlopeConfig, DeltaSlopeConfig
    sc = SierraChartConfig(**_DUMMY_SC_CONFIG)
    vol = VolatilityConfig(tickers=("^VVIX", "^VIX"), ratio_thresholds=(4.0, 5.5))
    cal = CalendarConfig(
        rapiapi_host="example.com",
        rapiapi_url="https://example.com/calendar",
        impact_labels=("High",),
        watchlist=("Fed",),
    )
    return Config(
        sierra_chart=sc,
        volatility=vol,
        calendar=cal,
        report=ReportConfig(output_dir=str(tmp_path / "reports")),
        scaling=ScalingConfig(thresholds=()),
        poller=PollerConfig(interval_seconds=120),
        server=ServerConfig(host="127.0.0.1", port=8000),
        logging=LoggingConfig(level="INFO", file=str(tmp_path / "app.log"), max_bytes=1000, backup_count=1),
        slope=SlopeConfig(),
        slope_delta=DeltaSlopeConfig(),
        slope_rvol=SlopeConfig(entry_threshold=0.2, exit_threshold=0.05),
    )


def _make_vwap_df(n: int = 5, vwap_start: float = 19780.0) -> pd.DataFrame:
    """Build a VWAP_MULTI-like DataFrame with a clearly upward-trending VWAP.

    Values are chosen so that both short and long z-scores exceed the default
    entry_threshold=1.0, ensuring classify_trend returns 'rising'.
    The Close sits between the bands so band_position is 'inside_value'.
    """
    # Non-uniform increments produce non-zero log-return sigma
    vwap_vals = [19780.0, 19795.0, 19815.0, 19825.0, 19850.0]
    rows = []
    for i in range(min(n, len(vwap_vals))):
        v = vwap_vals[i]
        rows.append({
            "Close": v - 10.0,       # inside the ±100 bands
            "VWAP": v,
            "Upper Band 2": v + 100.0,
            "Lower Band 2": v - 100.0,
        })
    return pd.DataFrame(rows)


def _make_eth_df(n: int = 5) -> pd.DataFrame:
    """Build a minimal ETH_RTH_VWAP-like DataFrame with required columns."""
    rows = []
    for i in range(n):
        rows.append({
            "Close": 19800.0 + i,
            "VWAP": 19805.0 + i,
            "Upper Band 2": 19840.0 + i,
            "Lower Band 2": 19760.0 + i,
            "delta_close": 100.0 + i,
            "Avg": 95.0 + i,
        })
    return pd.DataFrame(rows)


def _make_rvol_df(n: int = 5) -> pd.DataFrame:
    """Build a minimal RVOL_30MIN-like DataFrame."""
    rows = [{"Close": 19800.0 + i, "Cumulative Volume Ratio": 1.1 + i * 0.05} for i in range(n)]
    return pd.DataFrame(rows)


def _make_daily_df(n: int = 10) -> pd.DataFrame:
    rows = []
    for i in range(n):
        rows.append({"Avg": 43000.0 + i * 10, "ADR": 140.0 + i, "Volume": 50000.0})
    return pd.DataFrame(rows)


_DUMMY_LATEST_BAR = {"Avg": 44090.0, "ADR": 149.0, "datetime": "2026-04-13T00:00:00"}
_DUMMY_RATIO = ConversionResult(ratio=43.5, nq_price=20000.0, qqq_price=459.77, timestamp=pd.Timestamp("2026-04-15 09:30"))
_DUMMY_VOL = VolatilityData(vvix=90.0, vix=20.0, ratio=4.5, classification="medium")
_DUMMY_EVENTS = [CalendarEvent(event_id="1", event_name="Fed Speech", date="2026-04-15T14:00:00", impact_label="Medium")]


class TestIngestionRunEndpoint:
    def _patch_sc(self):
        """Return a context manager patching the SC helpers used in the run endpoint."""
        from unittest.mock import patch, MagicMock
        import contextlib

        @contextlib.contextmanager
        def _ctx():
            with (
                patch("backend.routers.ingestion.get_recent_bars") as mock_recent,
                patch("backend.routers.ingestion.parse_sc_file",
                      return_value=_make_eth_df()) as mock_parse,
                patch("backend.routers.ingestion.get_latest_bar",
                      return_value=_DUMMY_LATEST_BAR) as mock_latest,
                patch("backend.routers.ingestion.compute_ratio", return_value=_DUMMY_RATIO),
                patch("backend.routers.ingestion.fetch_vvix_vix", return_value=_DUMMY_VOL),
                patch("backend.routers.ingestion.fetch_economic_calendar", return_value=_DUMMY_EVENTS),
            ):
                # get_recent_bars is called 5 times:
                #   once per VWAP file (4) + once for daily + once for ETH 750v
                mock_recent.side_effect = [
                    _make_vwap_df(),   # yearly
                    _make_vwap_df(),   # quarterly
                    _make_vwap_df(),   # monthly
                    _make_vwap_df(),   # weekly
                    _make_daily_df(),  # daily
                    _make_eth_df(),    # ETH 750v
                    _make_rvol_df(),   # RVOL 30-min
                ]
                yield mock_recent, mock_latest, mock_parse

        return _ctx()

    def test_all_sections_succeed(self, client, tmp_path):
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        with self._patch_sc():
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        body = resp.json()
        assert body["session_date"] is not None
        sections = {s["name"]: s for s in body["sections"]}
        assert all(s["success"] for s in sections.values()), sections

        # session_data row written with all fields non-null
        conn = get_connection(db_path)
        row = conn.execute("SELECT * FROM session_data").fetchone()
        conn.close()
        assert row is not None
        assert row[2] is not None   # timeframe_context_json
        assert row[4] is not None   # volatility_json
        assert row[5] is not None   # calendar_json
        assert row[6] is not None   # overnight_json
        assert row[7] is not None   # qqq_nq_ratio

    def test_timeframe_context_json_structure(self, client, tmp_path):
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        with self._patch_sc():
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        conn = get_connection(db_path)
        row = conn.execute("SELECT timeframe_context_json FROM session_data").fetchone()
        conn.close()
        ctx = json.loads(row[0])
        for tf in ("yearly", "quarterly", "monthly", "weekly"):
            assert tf in ctx, f"Missing timeframe: {tf}"
            entry = ctx[tf]
            assert "uvwap" in entry
            assert "lvwap" in entry
            assert "vwap_slope" in entry
            assert "last" in entry
            assert isinstance(entry["uvwap"], float)
            assert isinstance(entry["lvwap"], float)
            # New trend classification fields
            assert "trend" in entry, f"Missing 'trend' for {tf}"
            assert "band_position" in entry, f"Missing 'band_position' for {tf}"
            assert entry["trend"] in ("rising", "falling", "sideways")
            assert entry["band_position"] in ("imbalance_up", "inside_value", "imbalance_down")

    def test_overnight_json_structure(self, client, tmp_path):
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        with self._patch_sc():
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        conn = get_connection(db_path)
        row = conn.execute("SELECT overnight_json FROM session_data").fetchone()
        conn.close()
        overnight = json.loads(row[0])
        # Daily file values from last completed bar (last row during pre-market)
        assert overnight["dvma"] == 44090.0
        assert overnight["adr"] == 149.0
        # Slopes computed
        assert "dvma_slope" in overnight
        assert "adr_slope" in overnight
        # ETH 750v values
        assert "eth_upper_1" in overnight
        assert "eth_lower_1" in overnight
        assert "cumulative_delta" in overnight
        assert "cd_ma" in overnight
        assert "eth_vwap_slope" in overnight
        assert "cd_ma_slope" in overnight
        # RVOL 30-min
        assert "rvol" in overnight
        assert "rvol_slope" in overnight
        assert overnight["rvol"] is not None

    def test_volatility_failure_isolated(self, client, tmp_path):
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        with (
            patch("backend.routers.ingestion.get_recent_bars") as mock_recent,
            patch("backend.routers.ingestion.parse_sc_file", return_value=_make_eth_df()),
            patch("backend.routers.ingestion.get_latest_bar",
                  return_value=_DUMMY_LATEST_BAR),
            patch("backend.routers.ingestion.compute_ratio", return_value=_DUMMY_RATIO),
            patch("backend.routers.ingestion.fetch_vvix_vix",
                  side_effect=VolatilityFetchError("yfinance network error")),
            patch("backend.routers.ingestion.fetch_economic_calendar", return_value=_DUMMY_EVENTS),
        ):
            mock_recent.side_effect = [
                _make_vwap_df(), _make_vwap_df(), _make_vwap_df(), _make_vwap_df(),
                _make_daily_df(), _make_eth_df(), _make_rvol_df(),
            ]
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        sections = {s["name"]: s for s in resp.json()["sections"]}
        assert sections["volatility"]["success"] is False
        assert "yfinance network error" in sections["volatility"]["error"]
        assert sections["timeframe_context"]["success"] is True
        assert sections["overnight"]["success"] is True
        assert sections["qqq_nq_ratio"]["success"] is True
        assert sections["calendar"]["success"] is True

        # session_data row exists with volatility_json null, others populated
        conn = get_connection(db_path)
        row = conn.execute(
            "SELECT timeframe_context_json, overnight_json, qqq_nq_ratio, volatility_json, calendar_json "
            "FROM session_data"
        ).fetchone()
        conn.close()
        assert row is not None
        assert row[0] is not None   # timeframe_context_json
        assert row[1] is not None   # overnight_json
        assert row[2] is not None   # qqq_nq_ratio
        assert row[3] is None       # volatility_json — null
        assert row[4] is not None   # calendar_json

    def test_levels_json_populated_with_qqq_inputs(self, client, tmp_path):
        """levels_json is written when menthorq_qqq row exists and ratio is available."""
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        # Seed a menthorq_qqq manual input row
        from datetime import date
        today = date.today().isoformat()
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO manual_inputs (session_date, input_type, data_json) VALUES (?, ?, ?)",
            (today, "menthorq_qqq", json.dumps(_VALID_QQQ_DATA)),
        )
        conn.commit()
        conn.close()

        with self._patch_sc():
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        sections = {s["name"]: s for s in resp.json()["sections"]}
        assert sections["levels"]["success"] is True

        # levels_json must be non-null and contain both sub-dicts
        conn = get_connection(db_path)
        row = conn.execute("SELECT levels_json FROM session_data").fetchone()
        conn.close()
        assert row is not None
        levels = json.loads(row[0])
        assert "qqq_original" in levels
        assert "qqq_as_nq" in levels

        # qqq_original mirrors the seeded data
        assert levels["qqq_original"]["call_resistance"] == _VALID_QQQ_DATA["call_resistance"]

        # qqq_as_nq values are qqq_original * ratio (rounded to 2 dp)
        ratio = _DUMMY_RATIO.ratio
        for key in _VALID_QQQ_DATA:
            expected = round(_VALID_QQQ_DATA[key] * ratio, 2)
            assert levels["qqq_as_nq"][key] == pytest.approx(expected, rel=1e-6), (
                f"{key}: expected {expected}, got {levels['qqq_as_nq'][key]}"
            )

    def test_levels_json_null_when_no_qqq_inputs(self, client, tmp_path):
        """levels_json is null (graceful skip) when no menthorq_qqq row exists."""
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        with self._patch_sc():
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        conn = get_connection(db_path)
        row = conn.execute("SELECT levels_json FROM session_data").fetchone()
        conn.close()
        # null because no QQQ manual input was seeded
        assert row[0] is None

    def test_levels_json_null_when_ratio_unavailable(self, client, tmp_path):
        """levels_json is null when ratio computation fails."""
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        from datetime import date
        today = date.today().isoformat()
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO manual_inputs (session_date, input_type, data_json) VALUES (?, ?, ?)",
            (today, "menthorq_qqq", json.dumps(_VALID_QQQ_DATA)),
        )
        conn.commit()
        conn.close()

        with (
            patch("backend.routers.ingestion.get_recent_bars") as mock_recent,
            patch("backend.routers.ingestion.parse_sc_file", return_value=_make_eth_df()),
            patch("backend.routers.ingestion.get_latest_bar",
                  return_value=_DUMMY_LATEST_BAR),
            patch("backend.routers.ingestion.compute_ratio",
                  side_effect=ValueError("no overlapping timestamps")),
            patch("backend.routers.ingestion.fetch_vvix_vix", return_value=_DUMMY_VOL),
            patch("backend.routers.ingestion.fetch_economic_calendar", return_value=_DUMMY_EVENTS),
        ):
            mock_recent.side_effect = [
                _make_vwap_df(), _make_vwap_df(), _make_vwap_df(), _make_vwap_df(),
                _make_daily_df(), _make_eth_df(), _make_rvol_df(),
            ]
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        conn = get_connection(db_path)
        row = conn.execute("SELECT levels_json FROM session_data").fetchone()
        conn.close()
        assert row[0] is None

    def test_gamma_mixed_when_nq_and_qqq_differ(self, client, tmp_path):
        """volatility_indication_json has gamma_regime='mixed' when NQ and QQQ gamma differ."""
        c, db_path = client
        app_state["config"] = _build_mock_config(tmp_path)

        from datetime import date
        today = date.today().isoformat()
        conn = get_connection(db_path)
        conn.execute(
            "INSERT INTO manual_inputs (session_date, input_type, data_json) VALUES (?, ?, ?)",
            (today, "gamma_nq", json.dumps({"regime": "negative"})),
        )
        conn.execute(
            "INSERT INTO manual_inputs (session_date, input_type, data_json) VALUES (?, ?, ?)",
            (today, "gamma_qqq", json.dumps({"regime": "positive"})),
        )
        conn.commit()
        conn.close()

        with self._patch_sc():
            resp = c.post("/api/ingestion/run")

        assert resp.status_code == 200
        conn = get_connection(db_path)
        row = conn.execute("SELECT volatility_indication_json FROM session_data").fetchone()
        conn.close()
        assert row[0] is not None
        indication = json.loads(row[0])
        assert indication["gamma_regime"] == "mixed"

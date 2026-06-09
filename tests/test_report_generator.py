import json
import sqlite3
from pathlib import Path

import pytest

from backend.db import get_connection, init_db
from backend.config import (
    CalendarConfig, Config, LoggingConfig,
    PollerConfig, ReportConfig, ScalingConfig, ServerConfig,
    SierraChartConfig, VolatilityConfig,
)
from backend.ingestion.slope import SlopeConfig, DeltaSlopeConfig
from backend.report.generator import generate_report


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SC_CONFIG = {
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


def _make_config(tmp_path: Path) -> Config:
    return Config(
        sierra_chart=SierraChartConfig(**_SC_CONFIG),
        volatility=VolatilityConfig(tickers=("^VVIX", "^VIX"), ratio_thresholds=(4.0, 5.5)),
        calendar=CalendarConfig(
            rapiapi_host="example.com",
            rapiapi_url="https://example.com/calendar",
            impact_labels=("High",),
            watchlist=("Fed",),
        ),
        report=ReportConfig(output_dir=str(tmp_path / "reports")),
        scaling=ScalingConfig(thresholds=()),
        poller=PollerConfig(interval_seconds=120),
        server=ServerConfig(host="127.0.0.1", port=8000),
        logging=LoggingConfig(
            level="INFO",
            file=str(tmp_path / "app.log"),
            max_bytes=1000,
            backup_count=1,
        ),
        slope=SlopeConfig(),
        slope_delta=DeltaSlopeConfig(),
        slope_rvol=SlopeConfig(entry_threshold=0.2, exit_threshold=0.05),
    )


@pytest.fixture()
def db_conn(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture()
def config(tmp_path):
    return _make_config(tmp_path)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

SESSION_DATE = "2026-04-15"

_TIMEFRAME_CONTEXT = {
    "yearly": {"trend": "rising", "band_position": "imbalance_up"},
    "quarterly": {"trend": "sideways", "band_position": "inside_value"},
    "monthly": {"trend": "rising", "band_position": "imbalance_up"},
    "weekly": {"trend": "falling", "band_position": "imbalance_down"},
}
_VOLATILITY = {"vvix": 90.0, "vix": 20.0, "ratio": 4.5, "classification": "medium"}
_CALENDAR = [{"event_id": "1", "event_name": "Fed Speech", "date": "2026-04-15T14:00:00", "impact_label": "High"}]
_OVERNIGHT = {"rvol": 1.2, "adr": 150.0, "Open": 20000.0}
_QQQ_NQ_RATIO = 43.5

_NQ_LEVELS = {
    "call_resistance": 21000.0, "put_support": 20000.0,
    "call_resistance_0dte": 20800.0, "put_support_0dte": 20200.0,
    "hvl": 20500.0, "hvl_0dte": 20450.0,
    "exp_move_max": 21100.0, "exp_move_min": 19900.0,
}
_QQQ_LEVELS = {k: v / 43.5 for k, v in _NQ_LEVELS.items()}
_GAMMA = {"regime": "positive"}
_LEVELS = {
    "qqq_original": _QQQ_LEVELS,
    "qqq_as_nq": _NQ_LEVELS,
}


_VOLATILITY_INDICATION = {
    "level": "high",
    "score": 4.0,
    "rvol_level": "elevated",
    "rvol": 1.2,
    "adr_trend": "rising",
    "dvma_trend": "rising",
    "gamma_regime": "negative",
}


def _seed_complete(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO session_data "
        "(session_date, timeframe_context_json, volatility_json, calendar_json, overnight_json, qqq_nq_ratio, levels_json, nq_last_price, volatility_indication_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            SESSION_DATE,
            json.dumps(_TIMEFRAME_CONTEXT),
            json.dumps(_VOLATILITY),
            json.dumps(_CALENDAR),
            json.dumps(_OVERNIGHT),
            _QQQ_NQ_RATIO,
            json.dumps(_LEVELS),
            20000.0,
            json.dumps(_VOLATILITY_INDICATION),
        ),
    )
    for itype, data in [("menthorq_nq", _NQ_LEVELS), ("menthorq_qqq", _QQQ_LEVELS), ("gamma", _GAMMA), ("gamma_nq", {"regime": "positive", "exp_move_max_pct": 1.5})]:
        conn.execute(
            "INSERT OR REPLACE INTO manual_inputs (session_date, input_type, data_json) VALUES (?, ?, ?)",
            (SESSION_DATE, itype, json.dumps(data)),
        )
    conn.commit()


class TestGenerateReportComplete:
    """All session_data and manual_inputs populated — happy path."""

    def test_file_created_and_non_empty(self, db_conn, config):
        _seed_complete(db_conn)
        path = generate_report(SESSION_DATE, db_conn, config)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_html_contains_all_section_headings(self, db_conn, config):
        _seed_complete(db_conn)
        path = generate_report(SESSION_DATE, db_conn, config)
        html = path.read_text(encoding="utf-8")
        for heading in [
            "Multi-Timeframe Context",
            "VVIX / VIX Ratio",
            "Economic Calendar",
            "Overnight Assessment",
        ]:
            assert heading in html, f"Missing section heading: {heading}"

    def test_no_unrendered_template_tags(self, db_conn, config):
        _seed_complete(db_conn)
        path = generate_report(SESSION_DATE, db_conn, config)
        html = path.read_text(encoding="utf-8")
        assert "{{" not in html

    def test_reports_row_inserted(self, db_conn, config):
        _seed_complete(db_conn)
        generate_report(SESSION_DATE, db_conn, config)
        row = db_conn.execute(
            "SELECT session_date FROM reports WHERE session_date = ?", (SESSION_DATE,)
        ).fetchone()
        assert row is not None

    def test_volatility_high_description(self, db_conn, config):
        """Task 17: high classification shows 'calm before the storm' description."""
        conn = db_conn
        conn.execute(
            "INSERT OR REPLACE INTO session_data "
            "(session_date, timeframe_context_json, volatility_json, calendar_json, overnight_json, qqq_nq_ratio) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                SESSION_DATE,
                json.dumps(_TIMEFRAME_CONTEXT),
                json.dumps({"vvix": 90.0, "vix": 12.0, "ratio": 7.5, "classification": "high"}),
                json.dumps(_CALENDAR),
                json.dumps(_OVERNIGHT),
                _QQQ_NQ_RATIO,
            ),
        )
        conn.commit()
        path = generate_report(SESSION_DATE, conn, config)
        html = path.read_text(encoding="utf-8")
        assert "Calm before the storm" in html

    def test_levels_removed_from_report(self, db_conn, config):
        """Levels are displayed in the dashboard, not in the report template."""
        _seed_complete(db_conn)
        path = generate_report(SESSION_DATE, db_conn, config)
        html = path.read_text(encoding="utf-8")
        assert "Important Levels" not in html
        assert "Copy Levels" not in html

    def test_estimated_range_displayed(self, db_conn, config):
        """Task 33: estimated range = round(nq_last_price * exp_move_max / 100)."""
        # nq_last_price=20000.0, exp_move_max=1.5 → 20000 * 1.5 / 100 = 300
        _seed_complete(db_conn)
        path = generate_report(SESSION_DATE, db_conn, config)
        html = path.read_text(encoding="utf-8")
        assert "Estimated range: 300 pts" in html


class TestGenerateReportNullData:
    """All JSON fields null in session_data — must not raise and must show unavailable."""

    def test_generates_without_raising(self, db_conn, config):
        # no session_data row at all
        path = generate_report(SESSION_DATE, db_conn, config)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_contains_data_unavailable(self, db_conn, config):
        path = generate_report(SESSION_DATE, db_conn, config)
        html = path.read_text(encoding="utf-8")
        assert "unavailable" in html.lower()

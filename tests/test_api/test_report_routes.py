from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.db import get_connection, init_db
from backend.main import app
from backend.state import app_state


@pytest.fixture()
def client(tmp_path: Path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    init_db(conn)
    conn.close()

    app_state["db_path"] = db_path
    app_state["config"] = _make_config(tmp_path)
    yield TestClient(app, raise_server_exceptions=True), db_path, tmp_path


def _make_config(tmp_path: Path):
    """Return a minimal Config-like object with report.output_dir set."""
    from types import SimpleNamespace
    return SimpleNamespace(
        report=SimpleNamespace(output_dir=str(tmp_path / "reports")),
        sierra_chart=SimpleNamespace(
            data_dir=str(tmp_path),
            nq_1min="nq.txt",
            rth_500v="rth.txt",
            eth_750v="eth.txt",
            quarterly_vwap="qv.txt",
            monthly_vwap="mv.txt",
            weekly_vwap="wv.txt",
            daily_adr="daily.txt",
            yearly_vwap="yv.txt",
            qqq_1min="qqq.txt",
        ),
    )


def _seed_session_data(db_path: str, session_date: str) -> None:
    conn = get_connection(db_path)
    conn.execute(
        "INSERT OR REPLACE INTO session_data "
        "(session_date, timeframe_context_json, levels_json, volatility_json, "
        "calendar_json, overnight_json, qqq_nq_ratio) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            session_date,
            json.dumps({"weekly": {"trend": "rising", "band_position": "imbalance_up"}}),
            json.dumps({"call_resistance": 21000, "put_support": 20800}),
            json.dumps({"vvix": 90.0, "vix": 18.0, "ratio": 5.0, "classification": "medium"}),
            json.dumps([{"event_id": "1", "event_name": "CPI", "date": session_date, "impact_label": "High"}]),
            json.dumps({"adr": 150.0, "rvol": 1.2}),
            20.85,
        ),
    )
    conn.commit()
    conn.close()


class TestGenerateReport:
    def test_generate_creates_file_and_returns_metadata(self, client):
        c, db_path, tmp_path = client
        session_date = "2026-04-15"
        _seed_session_data(db_path, session_date)

        resp = c.post("/api/report/generate", json={"session_date": session_date})
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_date"] == session_date
        assert Path(body["file_path"]).exists()

    def test_generate_no_session_data_returns_200_with_unavailable_sections(self, client):
        c, db_path, tmp_path = client
        session_date = "2026-04-15"
        # No session_data seeded — generator should still produce a file

        resp = c.post("/api/report/generate", json={"session_date": session_date})
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_date"] == session_date
        out_file = Path(body["file_path"])
        assert out_file.exists()
        content = out_file.read_text(encoding="utf-8")
        assert "unavailable" in content.lower() or "Data unavailable" in content

    def test_generate_defaults_session_date_to_today(self, client):
        from datetime import date
        c, db_path, tmp_path = client
        today = str(date.today())

        resp = c.post("/api/report/generate", json={})
        assert resp.status_code == 200
        assert resp.json()["session_date"] == today


class TestGetLatestReport:
    def test_latest_returns_404_when_no_report(self, client):
        c, db_path, tmp_path = client
        resp = c.get("/api/report/latest")
        assert resp.status_code == 404

    def test_latest_returns_metadata_after_generate(self, client):
        from datetime import date
        c, db_path, tmp_path = client
        today = str(date.today())
        _seed_session_data(db_path, today)

        c.post("/api/report/generate", json={})
        resp = c.get("/api/report/latest")
        assert resp.status_code == 200
        body = resp.json()
        assert body["session_date"] == today
        assert "file_path" in body
        assert "created_at" in body


class TestViewReport:
    def test_view_returns_html(self, client):
        from datetime import date
        c, db_path, tmp_path = client
        today = str(date.today())
        _seed_session_data(db_path, today)

        c.post("/api/report/generate", json={})
        resp = c.get(f"/api/report/view/{today}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "<!DOCTYPE html>" in resp.text or "<html" in resp.text.lower()

    def test_view_returns_404_for_unknown_date(self, client):
        c, db_path, tmp_path = client
        resp = c.get("/api/report/view/1999-01-01")
        assert resp.status_code == 404

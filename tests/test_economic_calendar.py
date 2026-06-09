from __future__ import annotations

import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import httpx
import pytest

from backend.ingestion.economic_calendar import (
    CalendarEvent,
    CalendarFetchError,
    fetch_economic_calendar,
)


# ---------------------------------------------------------------------------
# Config stubs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _CalendarConfig:
    rapiapi_url: str
    rapiapi_host: str
    impact_labels: tuple[str, ...]
    watchlist: tuple[str, ...]


@dataclass(frozen=True)
class _Config:
    calendar: _CalendarConfig


def _make_config() -> _Config:
    return _Config(
        calendar=_CalendarConfig(
            rapiapi_url="https://economic-calendar-api-tradingeconomics.p.rapidapi.com/calendar",
            rapiapi_host="economic-calendar-api-tradingeconomics.p.rapidapi.com",
            impact_labels=("High", "Medium"),
            watchlist=(
                "Non-Farm Payrolls",
                "Consumer Price Index",
                "Fed",
                "Producer Price Index",
            ),
        )
    )


# ---------------------------------------------------------------------------
# Fixture data — 5 events: 3 matching (High/Medium + watchlist), 2 non-matching
# ---------------------------------------------------------------------------

_FIXTURE_EVENTS = [
    # Matches: High impact + "Non-Farm Payrolls"
    {"id": "1001", "date": "2026-04-15T08:30:00", "eventName": "Non-Farm Payrolls", "impactLabel": "High"},
    # Matches: High impact + "Consumer Price Index"
    {"id": "1002", "date": "2026-04-15T08:30:00", "eventName": "Consumer Price Index", "impactLabel": "High"},
    # Matches: Medium impact + "Fed"
    {"id": "1003", "date": "2026-04-15T14:00:00", "eventName": "Fed Barkin Speech", "impactLabel": "Medium"},
    # Non-matching: Low impact (filtered out by impact_labels)
    {"id": "1004", "date": "2026-04-15T09:00:00", "eventName": "Non-Farm Payrolls Revision", "impactLabel": "Low"},
    # Matches: High impact (keyword filter removed)
    {"id": "1005", "date": "2026-04-15T10:00:00", "eventName": "NOPA Crush Report", "impactLabel": "High"},
]

_FIXTURE_PAYLOAD = json.dumps({"events": _FIXTURE_EVENTS, "count": 5, "total": 5})


def _mock_response(status_code: int, body: str) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = (200 <= status_code < 300)
    resp.text = body
    resp.json.return_value = json.loads(body) if resp.is_success else {}
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFetchEconomicCalendar:
    def test_correct_filtered_count_and_names(self, monkeypatch):
        monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
        config = _make_config()

        with patch("backend.ingestion.economic_calendar.httpx.get") as mock_get:
            mock_get.return_value = _mock_response(200, _FIXTURE_PAYLOAD)
            events = fetch_economic_calendar(config)

        assert len(events) == 4
        names = {e.event_name for e in events}
        assert "Non-Farm Payrolls" in names
        assert "Consumer Price Index" in names
        assert "Fed Barkin Speech" in names
        assert "NOPA Crush Report" in names

    def test_events_sorted_by_date(self, monkeypatch):
        monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
        config = _make_config()

        with patch("backend.ingestion.economic_calendar.httpx.get") as mock_get:
            mock_get.return_value = _mock_response(200, _FIXTURE_PAYLOAD)
            events = fetch_economic_calendar(config)

        dates = [e.date for e in events]
        assert dates == sorted(dates)

    def test_http_400_raises_calendar_fetch_error(self, monkeypatch):
        monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
        config = _make_config()

        with patch("backend.ingestion.economic_calendar.httpx.get") as mock_get:
            mock_get.return_value = _mock_response(400, '{"error": "bad request"}')
            with pytest.raises(CalendarFetchError) as exc_info:
                fetch_economic_calendar(config)

        assert exc_info.value.diagnostic  # non-empty diagnostic

    def test_no_matching_events_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
        config = _make_config()

        payload = json.dumps({"events": [
            {"id": "9001", "date": "2026-04-15T10:00:00", "eventName": "Low Impact Event", "impactLabel": "Low"},
        ]})

        with patch("backend.ingestion.economic_calendar.httpx.get") as mock_get:
            mock_get.return_value = _mock_response(200, payload)
            events = fetch_economic_calendar(config)

        assert events == []

    def test_timeout_raises_calendar_fetch_error(self, monkeypatch):
        monkeypatch.setenv("RAPIDAPI_KEY", "test-key")
        config = _make_config()

        with patch("backend.ingestion.economic_calendar.httpx.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("timed out")
            with pytest.raises(CalendarFetchError) as exc_info:
                fetch_economic_calendar(config)

        assert "timed out" in exc_info.value.diagnostic

    def test_missing_api_key_raises_calendar_fetch_error(self, monkeypatch):
        monkeypatch.delenv("RAPIDAPI_KEY", raising=False)
        config = _make_config()

        with pytest.raises(CalendarFetchError) as exc_info:
            fetch_economic_calendar(config)

        assert "RAPIDAPI_KEY" in exc_info.value.diagnostic

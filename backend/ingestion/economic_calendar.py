from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class CalendarEvent:
    event_id: str
    event_name: str
    date: str
    impact_label: str


_WARSAW = ZoneInfo("Europe/Warsaw")


def _to_warsaw(date_str: str) -> str:
    """Convert an ISO datetime string (assumed UTC) to Warsaw local time.

    Returns the original string unchanged if it cannot be parsed.
    """
    if len(date_str) < 16:
        return date_str
    try:
        dt_utc = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        return dt_utc.astimezone(_WARSAW).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return date_str


class CalendarFetchError(Exception):
    def __init__(self, diagnostic: str) -> None:
        super().__init__(diagnostic)
        self.diagnostic = diagnostic


def fetch_economic_calendar(config) -> list[CalendarEvent]:
    """Fetch today's US economic calendar events from RapidAPI TradingEconomics.

    Args:
        config: Config object with calendar.rapiapi_url, calendar.rapiapi_host,
                calendar.impact_labels, and calendar.watchlist.

    Returns:
        List of CalendarEvent matching impact_labels AND watchlist keywords, sorted by date.

    Raises:
        CalendarFetchError: If RAPIDAPI_KEY is missing, HTTP error, malformed JSON,
                            or any httpx exception occurs.
    """
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        raise CalendarFetchError("RAPIDAPI_KEY environment variable is not set")

    today = date.today().isoformat()

    try:
        response = httpx.get(
            config.calendar.rapiapi_url,
            params={
                "country": "United States",
                "from": today,
                "to": today,
                "fields": "id,date,eventName,impactLabel",
            },
            headers={
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": config.calendar.rapiapi_host,
            },
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=5.0, pool=5.0),
        )
    except httpx.TimeoutException as exc:
        raise CalendarFetchError(f"Request timed out: {exc}") from exc
    except httpx.HTTPError as exc:
        raise CalendarFetchError(f"HTTP error: {exc}") from exc

    if not response.is_success:
        raise CalendarFetchError(
            f"API returned HTTP {response.status_code}: {response.text}"
        )

    try:
        payload = response.json()
        raw_events: list[dict] = payload["events"]
    except Exception as exc:
        raise CalendarFetchError(f"Malformed response JSON: {exc}") from exc

    impact_allowlist = {label.lower() for label in config.calendar.impact_labels}

    matched: list[CalendarEvent] = []
    for ev in raw_events:
        impact = (ev.get("impactLabel") or "").lower()
        name = ev.get("eventName") or ""
        if impact not in impact_allowlist:
            continue
        matched.append(
            CalendarEvent(
                event_id=str(ev.get("id", "")),
                event_name=name,
                date=_to_warsaw(ev.get("date", "")),
                impact_label=ev.get("impactLabel", ""),
            )
        )

    matched.sort(key=lambda e: e.date)
    logger.info("Economic calendar: %d matching events fetched for %s", len(matched), today)
    return matched

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from backend.ingestion.overnight_analysis import enrich_overnight_assessment


def _make_eth_df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Cumulative delta flags + price above upper band
# ---------------------------------------------------------------------------

def test_cd_above_zero_above_ma_price_above_band():
    overnight = {
        "cumulative_delta": 150.0,
        "cd_ma": 100.0,
        "eth_upper_1": 20000.0,
        "eth_lower_1": 19800.0,
        "dvma": 5000.0,
    }
    eth_df = _make_eth_df([
        {"Close": 19900.0, "High": 19950.0, "Low": 19850.0},
        {"Close": 20050.0, "High": 20100.0, "Low": 19980.0},  # latest Close > eth_upper_1
    ])
    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    assert result["cd_above_zero"] is True
    assert result["cd_above_ma"] is True
    assert result["price_vs_eth_bands"] == "above +1.0 std ETH"
    assert result["volume_ma"] == 5000.0


# ---------------------------------------------------------------------------
# Cumulative delta below zero and below MA + price below lower band
# ---------------------------------------------------------------------------

def test_cd_below_zero_below_ma_price_below_band():
    overnight = {
        "cumulative_delta": -50.0,
        "cd_ma": 100.0,
        "eth_upper_1": 20000.0,
        "eth_lower_1": 19800.0,
        "dvma": 4500.0,
    }
    eth_df = _make_eth_df([
        {"Close": 19850.0, "High": 19900.0, "Low": 19810.0},
        {"Close": 19750.0, "High": 19790.0, "Low": 19720.0},  # latest Close < eth_lower_1
    ])
    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    assert result["cd_above_zero"] is False
    assert result["cd_above_ma"] is False
    assert result["price_vs_eth_bands"] == "below -1.0 std ETH"
    assert result["volume_ma"] == 4500.0


# ---------------------------------------------------------------------------
# Price between ETH bands
# ---------------------------------------------------------------------------

def test_price_between_bands():
    overnight = {
        "cumulative_delta": 50.0,
        "cd_ma": 100.0,
        "eth_upper_1": 20000.0,
        "eth_lower_1": 19800.0,
        "dvma": 5000.0,
    }
    eth_df = _make_eth_df([
        {"Close": 19900.0, "High": 19950.0, "Low": 19860.0},  # Close between bands
    ])
    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    assert result["price_vs_eth_bands"] == "between ETH bands"


# ---------------------------------------------------------------------------
# ETH range computation — previous day High - Low from daily #8
# ---------------------------------------------------------------------------

def test_eth_range_full_session():
    # eth_df: max High=20010, min Low=19820 → range=190.0
    # adr = 150.0 → eth_range_above_adr = True (190 > 150)
    overnight = {
        "cumulative_delta": 0.0,
        "cd_ma": 0.0,
        "eth_upper_1": 20200.0,
        "eth_lower_1": 19800.0,
        "dvma": 5000.0,
        "adr": 150.0,
    }
    eth_df = pd.DataFrame({
        "Close": [19900.0, 19920.0, 19880.0, 19910.0, 19950.0],
        "High":  [19950.0, 19960.0, 19940.0, 19955.0, 20010.0],
        "Low":   [19850.0, 19880.0, 19820.0, 19865.0, 19900.0],
    })
    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    assert result["eth_range"] == pytest.approx(190.0)  # 20010 - 19820
    assert "eth_range_ma" not in result
    assert "eth_range_above_ma" not in result
    assert result["eth_range_above_adr"] is True


def test_eth_range_below_adr():
    # eth_df: max High=19980, min Low=19860 → range=120.0
    # adr = 200.0 → eth_range_above_adr = False
    overnight = {
        "cumulative_delta": 0.0,
        "cd_ma": 0.0,
        "eth_upper_1": 20200.0,
        "eth_lower_1": 19800.0,
        "dvma": 5000.0,
        "adr": 200.0,
    }
    eth_df = pd.DataFrame({
        "Close": [19900.0, 19920.0, 19950.0],
        "High":  [19950.0, 19980.0, 19970.0],
        "Low":   [19860.0, 19870.0, 19920.0],
    })
    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    assert result["eth_range"] == pytest.approx(120.0)  # 19980 - 19860
    assert result["eth_range_above_adr"] is False


def test_eth_range_above_adr_none_when_adr_missing():
    overnight = {
        "cumulative_delta": 0.0,
        "cd_ma": 0.0,
        # adr key absent
    }
    eth_df = pd.DataFrame({
        "Close": [19900.0],
        "High":  [19950.0],
        "Low":   [19850.0],
    })
    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    assert result["eth_range"] == pytest.approx(100.0)
    assert result["eth_range_above_adr"] is None


# ---------------------------------------------------------------------------
# Edge case: missing keys → None values, no crash
# ---------------------------------------------------------------------------

def test_missing_keys_returns_none_no_crash():
    result = enrich_overnight_assessment({}, pd.DataFrame(), pd.DataFrame())

    assert result["cd_above_zero"] is None
    assert result["cd_above_ma"] is None
    assert result["price_vs_eth_bands"] is None
    assert result["volume_ma"] is None
    assert result["eth_range"] is None
    assert result["eth_range_above_adr"] is None


def test_partial_overnight_data_no_crash():
    # Only cumulative_delta present, cd_ma missing
    overnight = {"cumulative_delta": 200.0}
    result = enrich_overnight_assessment(overnight, pd.DataFrame(), pd.DataFrame())

    assert result["cd_above_zero"] is True
    assert result["cd_above_ma"] is None  # cd_ma unavailable


def test_original_keys_preserved():
    overnight = {
        "cumulative_delta": 50.0,
        "cd_ma": 40.0,
        "dvma": 5000.0,
        "adr": 300.0,
        "adr_slope": 1.2,
    }
    result = enrich_overnight_assessment(overnight, pd.DataFrame(), pd.DataFrame())

    # Original keys must still be present
    assert result["cumulative_delta"] == 50.0
    assert result["adr"] == 300.0
    assert result["adr_slope"] == 1.2


# ---------------------------------------------------------------------------
# ETH range with DatetimeIndex session-window filtering (Task 36)
# ---------------------------------------------------------------------------

def _make_eth_df_with_index(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame with a DatetimeIndex from a list of dicts with 'dt' key."""
    df = pd.DataFrame(rows)
    df.index = pd.to_datetime(df.pop("dt"))
    df.index.name = "datetime"
    return df


def test_eth_range_session_window_filters_correctly():
    """Bars from 16:00 prev-day through 15:59:59 current day are included; outside that window excluded."""
    session_date = date(2026, 4, 17)  # current day
    # Bar at 15:59 prev day → outside window (before 16:00 start)
    # Bar at 16:00 prev day → inside window (boundary start)
    # Bar at 02:00 current day → inside window
    # Bar at 15:59:59 current day → inside window (boundary end)
    # Bar at 16:00 current day → outside window (next ETH session)
    rows = [
        {"dt": "2026-04-16 15:59:00", "Close": 19900.0, "High": 20500.0, "Low": 19000.0},  # out
        {"dt": "2026-04-16 16:00:00", "Close": 19910.0, "High": 19960.0, "Low": 19840.0},  # in
        {"dt": "2026-04-17 02:00:00", "Close": 19920.0, "High": 19970.0, "Low": 19830.0},  # in
        {"dt": "2026-04-17 15:59:00", "Close": 19930.0, "High": 19980.0, "Low": 19850.0},  # in
        {"dt": "2026-04-17 16:00:00", "Close": 19940.0, "High": 21000.0, "Low": 18000.0},  # out
    ]
    eth_df = _make_eth_df_with_index(rows)
    overnight = {"adr": 160.0, "cumulative_delta": 0.0, "cd_ma": 0.0}

    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame(), session_date=session_date)

    # Expected: max High across in-window bars = 19980, min Low = 19830 → range = 150.0
    assert result["eth_range"] == pytest.approx(150.0)
    assert result["eth_range_above_adr"] is False  # 150.0 not > 160.0


def test_eth_range_no_session_date_uses_all_rows():
    """Without session_date, all rows in eth_df are used regardless of timestamp."""
    rows = [
        {"dt": "2026-04-16 15:59:00", "Close": 19900.0, "High": 20100.0, "Low": 19700.0},
        {"dt": "2026-04-17 10:00:00", "Close": 19910.0, "High": 19960.0, "Low": 19840.0},
    ]
    eth_df = _make_eth_df_with_index(rows)
    overnight = {"adr": 200.0, "cumulative_delta": 0.0, "cd_ma": 0.0}

    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame())

    # All rows used: max High = 20100, min Low = 19700 → range = 400.0
    assert result["eth_range"] == pytest.approx(400.0)
    assert result["eth_range_above_adr"] is True


def test_eth_range_empty_window_returns_none():
    """When no bars fall in the 16:00 prev-day to 15:59:59 current-day window, eth_range is None."""
    session_date = date(2026, 4, 17)
    rows = [
        {"dt": "2026-04-16 10:00:00", "Close": 19900.0, "High": 20000.0, "Low": 19800.0},  # out
        {"dt": "2026-04-16 15:59:00", "Close": 19910.0, "High": 20010.0, "Low": 19810.0},  # out
    ]
    eth_df = _make_eth_df_with_index(rows)
    overnight = {"adr": 150.0, "cumulative_delta": 0.0, "cd_ma": 0.0}

    result = enrich_overnight_assessment(overnight, eth_df, pd.DataFrame(), session_date=session_date)

    assert result["eth_range"] is None
    assert result["eth_range_above_adr"] is None

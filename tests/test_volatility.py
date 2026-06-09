from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.ingestion.volatility import (
    VolatilityData,
    VolatilityFetchError,
    fetch_vvix_vix,
)


@dataclass(frozen=True)
class _VolatilityConfig:
    ratio_thresholds: tuple[float, ...]


@dataclass(frozen=True)
class _Config:
    volatility: _VolatilityConfig


def _make_config(low: float = 4.0, high: float = 5.5) -> _Config:
    return _Config(volatility=_VolatilityConfig(ratio_thresholds=(low, high)))


def _make_ticker_mock(close_value: float) -> MagicMock:
    df = pd.DataFrame({"Close": [close_value]})
    mock = MagicMock()
    mock.history.return_value = df
    return mock


class TestFetchVvixVix:
    def test_correct_ratio_arithmetic(self):
        config = _make_config()
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = [_make_ticker_mock(110.0), _make_ticker_mock(22.0)]
            result = fetch_vvix_vix(config)

        assert result.vvix == pytest.approx(110.0)
        assert result.vix == pytest.approx(22.0)
        assert result.ratio == pytest.approx(5.0)

    def test_classification_below_low_threshold(self):
        config = _make_config(low=4.0, high=5.5)
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            # ratio = 80 / 25 = 3.2 → low
            mock_ticker.side_effect = [_make_ticker_mock(80.0), _make_ticker_mock(25.0)]
            result = fetch_vvix_vix(config)

        assert result.classification == "low"

    def test_classification_between_thresholds(self):
        config = _make_config(low=4.0, high=5.5)
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            # ratio = 100 / 20 = 5.0 → medium
            mock_ticker.side_effect = [_make_ticker_mock(100.0), _make_ticker_mock(20.0)]
            result = fetch_vvix_vix(config)

        assert result.classification == "medium"

    def test_classification_above_high_threshold(self):
        config = _make_config(low=4.0, high=5.5)
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            # ratio = 120 / 20 = 6.0 → high
            mock_ticker.side_effect = [_make_ticker_mock(120.0), _make_ticker_mock(20.0)]
            result = fetch_vvix_vix(config)

        assert result.classification == "high"

    def test_empty_vvix_response_raises(self):
        config = _make_config()
        empty_mock = MagicMock()
        empty_mock.history.return_value = pd.DataFrame()
        normal_mock = _make_ticker_mock(20.0)
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = [empty_mock, normal_mock]
            with pytest.raises(VolatilityFetchError):
                fetch_vvix_vix(config)

    def test_empty_vix_response_raises(self):
        config = _make_config()
        normal_mock = _make_ticker_mock(100.0)
        empty_mock = MagicMock()
        empty_mock.history.return_value = pd.DataFrame()
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = [normal_mock, empty_mock]
            with pytest.raises(VolatilityFetchError):
                fetch_vvix_vix(config)

    def test_exception_during_fetch_raises(self):
        config = _make_config()
        error_mock = MagicMock()
        error_mock.history.side_effect = ConnectionError("network error")
        with patch("backend.ingestion.volatility.yf.Ticker") as mock_ticker:
            mock_ticker.side_effect = [error_mock]
            with pytest.raises(VolatilityFetchError) as exc_info:
                fetch_vvix_vix(config)
        assert "network error" in str(exc_info.value)

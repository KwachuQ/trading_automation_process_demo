from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class VolatilityData:
    vvix: float
    vix: float
    ratio: float
    classification: Literal["low", "medium", "high"]


class VolatilityFetchError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def fetch_vvix_vix(config) -> VolatilityData:
    """Fetch VVIX and VIX from Yahoo Finance, compute ratio and classification.

    Args:
        config: Config object with volatility.ratio_thresholds (two floats: low, high).

    Returns:
        VolatilityData with vvix, vix, ratio, classification.

    Raises:
        VolatilityFetchError: If either ticker returns empty data or any exception occurs.
    """
    try:
        vvix_hist = yf.Ticker("^VVIX").history(period="5d")
        if vvix_hist.empty:
            raise VolatilityFetchError("^VVIX returned empty DataFrame")

        vix_hist = yf.Ticker("^VIX").history(period="5d")
        if vix_hist.empty:
            raise VolatilityFetchError("^VIX returned empty DataFrame")

        vvix = float(vvix_hist["Close"].iloc[-1])
        vix = float(vix_hist["Close"].iloc[-1])
    except VolatilityFetchError:
        raise
    except Exception as exc:
        raise VolatilityFetchError(str(exc)) from exc

    ratio = vvix / vix
    thresholds = config.volatility.ratio_thresholds
    low_threshold = thresholds[0]
    high_threshold = thresholds[1]

    if ratio < low_threshold:
        classification: Literal["low", "medium", "high"] = "low"
    elif ratio > high_threshold:
        classification = "high"
    else:
        classification = "medium"

    logger.info(
        "Volatility fetch complete: VVIX=%.2f, VIX=%.2f, ratio=%.4f, classification=%s",
        vvix,
        vix,
        ratio,
        classification,
    )

    return VolatilityData(vvix=vvix, vix=vix, ratio=ratio, classification=classification)

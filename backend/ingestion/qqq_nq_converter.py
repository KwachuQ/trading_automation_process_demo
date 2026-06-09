from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from backend.ingestion.sc_parser import SchemaType, parse_sc_file

logger = logging.getLogger(__name__)


@dataclass
class ConversionResult:
    ratio: float
    nq_price: float
    qqq_price: float
    timestamp: pd.Timestamp


def compute_ratio(nq_path: str, qqq_path: str) -> ConversionResult:
    """Compute the NQ/QQQ price ratio at the latest common timestamp.

    Both files are parsed with the ONE_MIN schema. The ratio is determined at
    the most recent timestamp present in *both* DataFrames (QQQ quotes are
    delayed relative to NQ futures).

    Args:
        nq_path: Path to the NQ 1-min Sierra Chart export (#1).
        qqq_path: Path to the QQQ 1-min Sierra Chart export (#12).

    Returns:
        ConversionResult with ratio, individual prices, and aligned timestamp.

    Raises:
        FileNotFoundError: If either file does not exist.
        ValueError: If there are no overlapping timestamps between the two files.
    """
    nq_df = parse_sc_file(nq_path, SchemaType.ONE_MIN)
    qqq_df = parse_sc_file(qqq_path, SchemaType.ONE_MIN)

    common = nq_df.index.intersection(qqq_df.index)
    if common.empty:
        raise ValueError(
            f"No overlapping timestamps between NQ ({nq_path}) and QQQ ({qqq_path})"
        )

    latest_ts = common.max()
    nq_price = float(nq_df.loc[latest_ts, "Last"])
    qqq_price = float(qqq_df.loc[latest_ts, "Last"])
    ratio = nq_price / qqq_price

    logger.info(
        "QQQ-NQ ratio computed at %s: NQ=%.2f, QQQ=%.2f, ratio=%.4f",
        latest_ts,
        nq_price,
        qqq_price,
        ratio,
    )

    return ConversionResult(
        ratio=ratio,
        nq_price=nq_price,
        qqq_price=qqq_price,
        timestamp=latest_ts,
    )


def convert_level(qqq_level: float, ratio: float) -> float:
    """Convert a single QQQ options level to NQ equivalent.

    Args:
        qqq_level: QQQ price level (e.g. from MenthorQ).
        ratio: NQ/QQQ conversion ratio from :func:`compute_ratio`.

    Returns:
        NQ-equivalent price, rounded to 2 decimal places.
    """
    return round(qqq_level * ratio, 2)


def convert_levels(qqq_levels: dict[str, float], ratio: float) -> dict[str, float]:
    """Batch-convert a dict of QQQ levels to NQ equivalents.

    Args:
        qqq_levels: Mapping of level name → QQQ price.
        ratio: NQ/QQQ conversion ratio.

    Returns:
        New dict with the same keys and NQ-equivalent prices.
    """
    return {k: convert_level(v, ratio) for k, v in qqq_levels.items()}

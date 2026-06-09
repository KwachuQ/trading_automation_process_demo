"""Tests for qqq_nq_converter.py (Task 5)."""
from __future__ import annotations

import pytest

from backend.ingestion.qqq_nq_converter import (
    ConversionResult,
    compute_ratio,
    convert_level,
    convert_levels,
)

# ONE_MIN header shared by all fixture files
_HEADER = "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,Bid Volume,Ask Volume"


def _make_row(date: str, time: str, last: float) -> str:
    return f"{date},{time},0.0,0.0,0.0,{last},100,10,0.0,0.0,0.0,50,50"


def _write_file(path, rows: list[tuple[str, str, float]]) -> None:
    lines = [_HEADER] + [_make_row(d, t, p) for d, t, p in rows]
    path.write_text("\n".join(lines))


class TestComputeRatio:
    def test_uses_latest_common_timestamp(self, tmp_path):
        """Ratio must use the most recent timestamp present in both files."""
        nq_file = tmp_path / "nq.txt"
        qqq_file = tmp_path / "qqq.txt"

        # NQ: 5 rows, timestamps 09:30-09:34
        _write_file(nq_file, [
            ("2026-04-14", "09:30:00", 19800.0),
            ("2026-04-14", "09:31:00", 19810.0),
            ("2026-04-14", "09:32:00", 19820.0),
            ("2026-04-14", "09:33:00", 19830.0),
            ("2026-04-14", "09:34:00", 19840.0),
        ])
        # QQQ: 5 rows, 3 overlapping (09:30-09:32), 2 non-overlapping earlier
        _write_file(qqq_file, [
            ("2026-04-14", "09:28:00", 469.0),
            ("2026-04-14", "09:29:00", 469.5),
            ("2026-04-14", "09:30:00", 470.0),
            ("2026-04-14", "09:31:00", 470.5),
            ("2026-04-14", "09:32:00", 471.0),
        ])

        result = compute_ratio(str(nq_file), str(qqq_file))

        # Latest common timestamp is 09:32; NQ=19820, QQQ=471.0
        assert result.timestamp.strftime("%H:%M:%S") == "09:32:00"
        assert result.nq_price == 19820.0
        assert result.qqq_price == 471.0
        assert abs(result.ratio - 19820.0 / 471.0) < 1e-9

    def test_no_overlap_raises_value_error(self, tmp_path):
        nq_file = tmp_path / "nq.txt"
        qqq_file = tmp_path / "qqq.txt"

        _write_file(nq_file, [
            ("2026-04-14", "09:30:00", 19800.0),
            ("2026-04-14", "09:31:00", 19810.0),
        ])
        _write_file(qqq_file, [
            ("2026-04-14", "10:00:00", 472.0),
            ("2026-04-14", "10:01:00", 472.5),
        ])

        with pytest.raises(ValueError, match="overlapping"):
            compute_ratio(str(nq_file), str(qqq_file))

    def test_missing_nq_file_raises(self, tmp_path):
        qqq_file = tmp_path / "qqq.txt"
        _write_file(qqq_file, [("2026-04-14", "09:30:00", 470.0)])
        with pytest.raises(FileNotFoundError):
            compute_ratio(str(tmp_path / "nonexistent.txt"), str(qqq_file))

    def test_missing_qqq_file_raises(self, tmp_path):
        nq_file = tmp_path / "nq.txt"
        _write_file(nq_file, [("2026-04-14", "09:30:00", 19800.0)])
        with pytest.raises(FileNotFoundError):
            compute_ratio(str(nq_file), str(tmp_path / "nonexistent.txt"))


class TestConvertLevel:
    def test_arithmetic(self):
        assert convert_level(470.0, 42.0) == 19740.0

    def test_rounds_to_two_decimals(self):
        # 471.13 * 42.123 = 19843.75... — result should be 2 dp
        result = convert_level(471.13, 42.123)
        assert result == round(471.13 * 42.123, 2)

    def test_convert_levels_batch(self):
        levels = {"call_resistance": 472.0, "put_support": 468.0}
        ratio = 42.0
        result = convert_levels(levels, ratio)
        assert result["call_resistance"] == 472.0 * 42.0
        assert result["put_support"] == 468.0 * 42.0
        assert set(result.keys()) == {"call_resistance", "put_support"}

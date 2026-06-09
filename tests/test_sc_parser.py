"""Tests for sc_parser.py — VWAP_MULTI and DAILY_ADR schemas (Task 3)."""
from __future__ import annotations

import logging
from pathlib import Path

import pytest
import pandas as pd

from backend.ingestion.sc_parser import (
    SchemaType,
    parse_sc_file,
    get_latest_bar,
    get_pre_ultimate_bar,
    get_recent_bars,
    detect_schema,
)

# ---------------------------------------------------------------------------
# Fixture content helpers
# ---------------------------------------------------------------------------

VWAP_MULTI_HEADER = (
    "Date,Time,Open,High,Low,Close,Volume,"
    "VWAP,"
    "Upper Band 1,Lower Band 1,"
    "Upper Band 2,Lower Band 2,"
    "Upper Band 3,Lower Band 3,"
    "Upper Band 4,Lower Band 4"
)

VWAP_MULTI_ROW_1 = "2026-04-14,09:30:00,19800.00,19850.00,19780.00,19820.00,12345,19810.00,19830.00,19790.00,19850.00,19770.00,19870.00,19750.00,19890.00,19730.00"
VWAP_MULTI_ROW_2 = "2026-04-14,09:31:00,19820.00,19860.00,19800.00,19840.00,9800,19815.00,19835.00,19795.00,19855.00,19775.00,19875.00,19755.00,19895.00,19735.00"
VWAP_MULTI_ROW_3 = "2026-04-14,09:32:00,19840.00,19870.00,19820.00,19855.00,8500,19820.00,19840.00,19800.00,19860.00,19780.00,19880.00,19760.00,19900.00,19740.00"

VWAP_MULTI_CONTENT = "\n".join([VWAP_MULTI_HEADER, VWAP_MULTI_ROW_1, VWAP_MULTI_ROW_2, VWAP_MULTI_ROW_3])

# Yearly VWAP (#10) adds Difference and Avg columns
VWAP_MULTI_YEARLY_HEADER = VWAP_MULTI_HEADER + ",Difference,Avg"
VWAP_MULTI_YEARLY_ROW_1 = VWAP_MULTI_ROW_1 + ",10.00,19805.00"
VWAP_MULTI_YEARLY_ROW_2 = VWAP_MULTI_ROW_2 + ",15.00,19810.00"
VWAP_MULTI_YEARLY_ROW_3 = VWAP_MULTI_ROW_3 + ",20.00,19815.00"
VWAP_MULTI_YEARLY_CONTENT = "\n".join([
    VWAP_MULTI_YEARLY_HEADER,
    VWAP_MULTI_YEARLY_ROW_1,
    VWAP_MULTI_YEARLY_ROW_2,
    VWAP_MULTI_YEARLY_ROW_3,
])

DAILY_ADR_HEADER = "Date,Time,Open,High,Low,Close,Volume,Avg,ADR"
# Rows in ascending (chronological) order — matches real Sierra Chart exports
DAILY_ADR_ROW_1 = "2026-04-12,00:00:00,19600.00,19720.00,19550.00,19680.00,46000,43000.00,140.00"
DAILY_ADR_ROW_2 = "2026-04-13,00:00:00,19700.00,19810.00,19650.00,19750.00,48000,44000.00,145.00"
DAILY_ADR_ROW_3 = "2026-04-14,00:00:00,19800.00,19900.00,19750.00,19820.00,50000,45000.00,150.00"
DAILY_ADR_CONTENT = "\n".join([DAILY_ADR_HEADER, DAILY_ADR_ROW_1, DAILY_ADR_ROW_2, DAILY_ADR_ROW_3])

# Row with a malformed numeric value (non-numeric Close)
DAILY_ADR_MALFORMED_ROW = "2026-04-11,00:00:00,19500.00,19620.00,19450.00,BAD,44000,42000.00,138.00"


# ---------------------------------------------------------------------------
# VWAP_MULTI tests
# ---------------------------------------------------------------------------

class TestVwapMulti:
    def test_shape(self, tmp_path):
        f = tmp_path / "vwap.txt"
        f.write_text(VWAP_MULTI_CONTENT)
        df = parse_sc_file(str(f), SchemaType.VWAP_MULTI)
        assert df.shape == (3, 14)  # 16 cols minus Date and Time = 14

    def test_datetime_index(self, tmp_path):
        f = tmp_path / "vwap.txt"
        f.write_text(VWAP_MULTI_CONTENT)
        df = parse_sc_file(str(f), SchemaType.VWAP_MULTI)
        assert df.index.name == "datetime"
        assert pd.api.types.is_datetime64_any_dtype(df.index)
        assert str(df.index[0])[:10] == "2026-04-14"

    def test_numeric_dtypes(self, tmp_path):
        f = tmp_path / "vwap.txt"
        f.write_text(VWAP_MULTI_CONTENT)
        df = parse_sc_file(str(f), SchemaType.VWAP_MULTI)
        for col in ["Open", "High", "Low", "Close", "Volume", "VWAP",
                    "Upper Band 1", "Lower Band 1", "Upper Band 4", "Lower Band 4"]:
            assert df[col].dtype == float, f"{col} should be float"

    def test_yearly_extra_columns(self, tmp_path):
        f = tmp_path / "yearly.txt"
        f.write_text(VWAP_MULTI_YEARLY_CONTENT)
        df = parse_sc_file(str(f), SchemaType.VWAP_MULTI)
        assert "Difference" in df.columns
        assert "Avg" in df.columns
        assert df["Difference"].dtype == float
        assert df["Avg"].dtype == float
        assert df.shape == (3, 16)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        df = parse_sc_file(str(f), SchemaType.VWAP_MULTI)
        assert df.empty
        assert "VWAP" in df.columns

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_sc_file(str(tmp_path / "nonexistent.txt"), SchemaType.VWAP_MULTI)


# ---------------------------------------------------------------------------
# DAILY_ADR tests
# ---------------------------------------------------------------------------

class TestDailyAdr:
    def test_shape(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_CONTENT)
        df = parse_sc_file(str(f), SchemaType.DAILY_ADR)
        assert df.shape == (3, 7)  # 9 cols minus Date and Time = 7

    def test_datetime_index(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_CONTENT)
        df = parse_sc_file(str(f), SchemaType.DAILY_ADR)
        assert df.index.name == "datetime"
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    def test_numeric_dtypes(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_CONTENT)
        df = parse_sc_file(str(f), SchemaType.DAILY_ADR)
        for col in ["Open", "High", "Low", "Close", "Volume", "Avg", "ADR"]:
            assert df[col].dtype == float, f"{col} should be float"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        df = parse_sc_file(str(f), SchemaType.DAILY_ADR)
        assert df.empty
        assert "ADR" in df.columns

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_sc_file(str(tmp_path / "nonexistent.txt"), SchemaType.DAILY_ADR)

    def test_malformed_row_skipped(self, tmp_path, caplog):
        content = "\n".join([
            DAILY_ADR_HEADER,
            DAILY_ADR_ROW_1,
            DAILY_ADR_MALFORMED_ROW,  # bad row
            DAILY_ADR_ROW_3,
        ])
        f = tmp_path / "daily_bad.txt"
        f.write_text(content)
        with caplog.at_level(logging.WARNING, logger="backend.ingestion.sc_parser"):
            df = parse_sc_file(str(f), SchemaType.DAILY_ADR)
        assert df.shape[0] == 2, "Malformed row should be dropped"
        assert any("skipped" in msg.lower() for msg in caplog.messages)


# ---------------------------------------------------------------------------
# get_latest_bar tests
# ---------------------------------------------------------------------------

class TestGetLatestBar:
    def test_daily_adr_rvol(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_CONTENT)
        # Last row (most recent) has Volume=50000, Avg=45000
        bar = get_latest_bar(str(f), SchemaType.DAILY_ADR)
        # Volume=50000, Avg=45000 → rvol=50000/45000
        assert "rvol" in bar
        assert abs(bar["rvol"] - (50000.0 / 45000.0)) < 1e-9

    def test_daily_adr_adr_key(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_CONTENT)
        bar = get_latest_bar(str(f), SchemaType.DAILY_ADR)
        assert "adr" in bar
        assert bar["adr"] == 150.0

    def test_vwap_multi_no_rvol(self, tmp_path):
        f = tmp_path / "vwap.txt"
        f.write_text(VWAP_MULTI_CONTENT)
        bar = get_latest_bar(str(f), SchemaType.VWAP_MULTI)
        assert "rvol" not in bar
        assert "VWAP" in bar

    def test_empty_file_raises(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        with pytest.raises(ValueError):
            get_latest_bar(str(f), SchemaType.DAILY_ADR)


# ---------------------------------------------------------------------------
# ONE_MIN fixtures
# ---------------------------------------------------------------------------

ONE_MIN_HEADER = "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,Bid Volume,Ask Volume"
ONE_MIN_ROW_1 = "2026-04-14,09:30:00,19800.00,19810.00,19795.00,19805.00,500,42,19802.50,19803.33,19802.50,250,250"
ONE_MIN_ROW_2 = "2026-04-14,09:31:00,19805.00,19815.00,19800.00,19810.00,480,38,19807.50,19808.33,19807.50,240,240"
ONE_MIN_ROW_3 = "2026-04-14,09:32:00,19810.00,19820.00,19805.00,19815.00,520,45,19812.50,19813.33,19812.50,260,260"
ONE_MIN_CONTENT = "\n".join([ONE_MIN_HEADER, ONE_MIN_ROW_1, ONE_MIN_ROW_2, ONE_MIN_ROW_3])

# ETH_RTH_VWAP fixtures (same column layout as VWAP_MULTI 16-col)
ETH_RTH_VWAP_HEADER = (
    "Date,Time,Open,High,Low,Close,Volume,"
    "VWAP,"
    "Upper Band 1,Lower Band 1,"
    "Upper Band 2,Lower Band 2,"
    "Upper Band 3,Lower Band 3,"
    "Upper Band 4,Lower Band 4"
)
ETH_RTH_VWAP_ROW_1 = "2026-04-14,18:00:00,19800.00,19820.00,19790.00,19810.00,300,19805.00,19820.00,19790.00,19835.00,19775.00,19850.00,19760.00,19865.00,19745.00"
ETH_RTH_VWAP_ROW_2 = "2026-04-14,18:01:00,19810.00,19825.00,19800.00,19815.00,280,19808.00,19823.00,19793.00,19838.00,19778.00,19853.00,19763.00,19868.00,19748.00"
ETH_RTH_VWAP_ROW_3 = "2026-04-14,18:02:00,19815.00,19830.00,19805.00,19820.00,310,19810.00,19825.00,19795.00,19840.00,19780.00,19855.00,19765.00,19870.00,19750.00"
ETH_RTH_VWAP_CONTENT = "\n".join([ETH_RTH_VWAP_HEADER, ETH_RTH_VWAP_ROW_1, ETH_RTH_VWAP_ROW_2, ETH_RTH_VWAP_ROW_3])


# ---------------------------------------------------------------------------
# ONE_MIN tests
# ---------------------------------------------------------------------------

class TestOneMin:
    def test_shape(self, tmp_path):
        f = tmp_path / "nq_1min.txt"
        f.write_text(ONE_MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ONE_MIN)
        assert df.shape == (3, 11)  # 13 cols minus Date, Time = 11

    def test_datetime_index(self, tmp_path):
        f = tmp_path / "nq_1min.txt"
        f.write_text(ONE_MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ONE_MIN)
        assert pd.api.types.is_datetime64_any_dtype(df.index)
        assert df.index.name == "datetime"

    def test_numeric_dtypes(self, tmp_path):
        f = tmp_path / "nq_1min.txt"
        f.write_text(ONE_MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ONE_MIN)
        for col in ["Open", "High", "Low", "Last", "Volume", "# of Trades",
                    "Bid Volume", "Ask Volume"]:
            assert df[col].dtype == float, f"{col} should be float"

    def test_last_column_present(self, tmp_path):
        f = tmp_path / "nq_1min.txt"
        f.write_text(ONE_MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ONE_MIN)
        assert "Last" in df.columns

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        df = parse_sc_file(str(f), SchemaType.ONE_MIN)
        assert df.empty
        assert "Last" in df.columns

    def test_two_files_inner_join(self, tmp_path):
        """Two ONE_MIN files with matching timestamps can be inner-joined."""
        nq_f = tmp_path / "nq.txt"
        qqq_f = tmp_path / "qqq.txt"
        nq_f.write_text(ONE_MIN_CONTENT)
        # QQQ file with same timestamps but different prices
        qqq_row1 = "2026-04-14,09:30:00,470.00,471.00,469.80,470.50,1000,80,470.25,470.43,470.40,500,500"
        qqq_row2 = "2026-04-14,09:31:00,470.50,471.50,470.20,471.00,980,75,470.75,470.90,470.85,490,490"
        qqq_row3 = "2026-04-14,09:32:00,471.00,472.00,470.70,471.50,1020,85,471.25,471.40,471.35,510,510"
        qqq_content = "\n".join([ONE_MIN_HEADER, qqq_row1, qqq_row2, qqq_row3])
        qqq_f.write_text(qqq_content)

        nq_df = parse_sc_file(str(nq_f), SchemaType.ONE_MIN)
        qqq_df = parse_sc_file(str(qqq_f), SchemaType.ONE_MIN)
        joined = nq_df.join(qqq_df, how="inner", lsuffix="_nq", rsuffix="_qqq")
        assert len(joined) == 3
        assert "Last_nq" in joined.columns
        assert "Last_qqq" in joined.columns


# ---------------------------------------------------------------------------
# ETH_RTH_VWAP tests
# ---------------------------------------------------------------------------

class TestEthRthVwap:
    def test_shape(self, tmp_path):
        f = tmp_path / "eth.txt"
        f.write_text(ETH_RTH_VWAP_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert df.shape == (3, 14)  # 16 cols minus Date, Time = 14

    def test_datetime_index(self, tmp_path):
        f = tmp_path / "eth.txt"
        f.write_text(ETH_RTH_VWAP_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert pd.api.types.is_datetime64_any_dtype(df.index)

    def test_numeric_dtypes(self, tmp_path):
        f = tmp_path / "eth.txt"
        f.write_text(ETH_RTH_VWAP_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        for col in ["Open", "High", "Low", "Close", "VWAP",
                    "Upper Band 1", "Lower Band 4"]:
            assert df[col].dtype == float, f"{col} should be float"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert df.empty
        assert "VWAP" in df.columns



# ---------------------------------------------------------------------------
# ETH 750v (#4) and RTH 500v (#3) overlay column fixtures
# Headers match docs/headers.txt exactly (42 cols for #4, 45 cols for #3).
# ---------------------------------------------------------------------------

# File #4: 42 columns — base bar OHLCV + VWAP bands + overlay studies
# Columns: Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,
#   HL Avg,Bid Volume,Ask Volume,ECIVwap,Band2top,Band2bot,Band3top,Band3bot,
#   Band4top,Band4bot,Vwap ext,9x band ext,Text Display,Avg,Line1,
#   Open,High,Low,Close(delta),HA Open,HA Close,Open,High,Low,Last
ETH_750V_HEADER = (
    "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,"
    "Bid Volume,Ask Volume,ECIVwap,"
    "Top Band 2 of Vwap Standard Deviation,Bottom Band 2 of Vwap Standard Deviation,"
    "Top Band 3 of Vwap Standard Deviation,Bottom Band 3 of Vwap Standard Deviation,"
    "Top Band 4 of Vwap Standard Deviation,Bottom Band 4 of Vwap Standard Deviation,"
    "Vwap extension,Top band 1 extension,Bottom band 1 extension,"
    "Top band 2 extension,Bottom band 2 extension,"
    "Top band 3 extension,Bottom band 3 extension,"
    "Top band 4 extension,Bottom band 4 extension,"
    "Text Display,Avg,Line1,"
    "Open,High,Low,Close,"
    "HA Open,HA Close,"
    "Open,High,Low,Last"
)
# Row layout (42 values):
#   idx 5  → Close  (base bar, from "Last")   = 19810.00
#   idx 13 → VWAP   (from ECIVwap)            = 19805.00
#   idx 14 → Upper Band 2                      = 19840.00
#   idx 15 → Lower Band 2                      = 19770.00
#   idx 30 → Avg    (cumulative delta MA)       = 43200.00
#   idx 35 → delta_close (cumulative delta val) = 200.00
#   idx 36 → ha_open                            = 19808.00
#   idx 37 → ha_close                           = 19812.00
ETH_750V_ROW_1 = (
    "2026-04-14,18:00:00,19800.00,19820.00,19790.00,19810.00,300,120,"
    "19802.50,19806.67,19805.00,150,150,"
    "19805.00,19840.00,19770.00,19860.00,19750.00,19880.00,19730.00,"
    "0.50,0.20,0.15,0.30,0.25,0.40,0.35,0.45,0.38,"
    "0,43200.00,0,"
    "100.00,120.00,80.00,200.00,"
    "19808.00,19812.00,"
    "19795.00,19820.00,19785.00,19810.00"
)
ETH_750V_ROW_2 = (
    "2026-04-14,18:01:00,19810.00,19830.00,19800.00,19815.00,280,110,"
    "19811.25,19815.00,19815.00,140,140,"
    "19806.00,19841.00,19771.00,19861.00,19751.00,19881.00,19731.00,"
    "0.51,0.21,0.16,0.31,0.26,0.41,0.36,0.46,0.39,"
    "0,43300.00,0,"
    "110.00,130.00,85.00,210.00,"
    "19809.00,19813.00,"
    "19796.00,19821.00,19786.00,19811.00"
)
ETH_750V_ROW_3 = (
    "2026-04-14,18:02:00,19815.00,19835.00,19805.00,19820.00,310,130,"
    "19818.75,19820.00,19820.00,155,155,"
    "19807.00,19842.00,19772.00,19862.00,19752.00,19882.00,19732.00,"
    "0.52,0.22,0.17,0.32,0.27,0.42,0.37,0.47,0.40,"
    "0,43400.00,0,"
    "120.00,140.00,90.00,220.00,"
    "19810.00,19814.00,"
    "19797.00,19822.00,19787.00,19812.00"
)
ETH_750V_CONTENT = "\n".join([ETH_750V_HEADER, ETH_750V_ROW_1, ETH_750V_ROW_2, ETH_750V_ROW_3])

# File #3: 45 columns — same VWAP bands as #4, no Line1, with POC/VA group at end
# After "Avg" (idx 30): no Line1, delta group directly at idx 31
#   idx 34 → delta_close = -150.00
#   idx 35 → ha_open
#   idx 36 → ha_close
RTH_500V_HEADER = (
    "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,HLC Avg,HL Avg,"
    "Bid Volume,Ask Volume,ECIVwap,"
    "Top Band 2 of Vwap Standard Deviation,Bottom Band 2 of Vwap Standard Deviation,"
    "Top Band 3 of Vwap Standard Deviation,Bottom Band 3 of Vwap Standard Deviation,"
    "Top Band 4 of Vwap Standard Deviation,Bottom Band 4 of Vwap Standard Deviation,"
    "Vwap extension,Top band 1 extension,Bottom band 1 extension,"
    "Top band 2 extension,Bottom band 2 extension,"
    "Top band 3 extension,Bottom band 3 extension,"
    "Top band 4 extension,Bottom band 4 extension,"
    "Text Display,Avg,"
    "Open,High,Low,Close,"
    "HA Open,HA Close,"
    "Open,High,Low,Last,"
    "Point of Control,Value Area High Value,Value Area Low Value,"
    "Volume Weighted Average Price"
)
RTH_500V_ROW_1 = (
    "2026-04-14,16:00:00,19800.00,19820.00,19790.00,19810.00,400,150,"
    "19802.50,19806.67,19805.00,200,200,"
    "19805.00,19840.00,19770.00,19860.00,19750.00,19880.00,19730.00,"
    "0.50,0.20,0.15,0.30,0.25,0.40,0.35,0.45,0.38,"
    "0,43200.00,"
    "-50.00,-40.00,-160.00,-150.00,"
    "19808.00,19812.00,"
    "19795.00,19820.00,19785.00,19810.00,"
    "19800.00,19840.00,19760.00,19805.00"
)
RTH_500V_ROW_2 = (
    "2026-04-14,16:01:00,19810.00,19825.00,19800.00,19815.00,380,140,"
    "19812.50,19813.33,19812.50,190,190,"
    "19806.00,19841.00,19771.00,19861.00,19751.00,19881.00,19731.00,"
    "0.51,0.21,0.16,0.31,0.26,0.41,0.36,0.46,0.39,"
    "0,43100.00,"
    "-45.00,-35.00,-155.00,-145.00,"
    "19809.00,19813.00,"
    "19796.00,19821.00,19786.00,19811.00,"
    "19801.00,19841.00,19761.00,19806.00"
)
RTH_500V_ROW_3 = (
    "2026-04-14,16:02:00,19815.00,19830.00,19805.00,19820.00,420,160,"
    "19817.50,19818.33,19817.50,210,210,"
    "19807.00,19842.00,19772.00,19862.00,19752.00,19882.00,19732.00,"
    "0.52,0.22,0.17,0.32,0.27,0.42,0.37,0.47,0.40,"
    "0,43000.00,"
    "-40.00,-30.00,-150.00,-140.00,"
    "19810.00,19814.00,"
    "19797.00,19822.00,19787.00,19812.00,"
    "19802.00,19842.00,19762.00,19807.00"
)
RTH_500V_CONTENT = "\n".join([RTH_500V_HEADER, RTH_500V_ROW_1, RTH_500V_ROW_2, RTH_500V_ROW_3])


# ---------------------------------------------------------------------------
# ETH/RTH overlay column tests (Task 11a)
# ---------------------------------------------------------------------------

class TestEthRthVwapOverlay:
    """Tests for ETH 750v (#4) and RTH 500v (#3) with real 42/45-column headers."""

    # --- File #4: ETH 750v (42 columns, has Line1) ---

    def test_eth_750v_shape(self, tmp_path):
        f = tmp_path / "eth_750v.txt"
        f.write_text(ETH_750V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        # File #4 has no Band 1 columns, so present cols are:
        # Open/High/Low/Close/Volume(5) + VWAP(1) + Band2-4 top/bot(6) +
        # Avg(1) + delta*(4) + ha*(2) + trailing*(4) = 23
        assert df.shape[0] == 3
        assert df.shape[1] == 23

    def test_eth_750v_delta_close_extracted(self, tmp_path):
        f = tmp_path / "eth_750v.txt"
        f.write_text(ETH_750V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert "delta_close" in df.columns
        assert df["delta_close"].dtype == float
        assert df["delta_close"].iloc[0] == 200.00

    def test_eth_750v_delta_ma_extracted(self, tmp_path):
        f = tmp_path / "eth_750v.txt"
        f.write_text(ETH_750V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert "Avg" in df.columns
        assert df["Avg"].dtype == float
        assert df["Avg"].iloc[0] == 43200.00

    def test_eth_750v_base_close_distinct_from_delta(self, tmp_path):
        f = tmp_path / "eth_750v.txt"
        f.write_text(ETH_750V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        # Base bar "Close" (from "Last" at idx 5) must not be overwritten by delta_close
        assert "Close" in df.columns
        assert df["Close"].iloc[0] == 19810.00
        assert df["delta_close"].iloc[0] != df["Close"].iloc[0]

    def test_eth_750v_ha_columns_extracted(self, tmp_path):
        f = tmp_path / "eth_750v.txt"
        f.write_text(ETH_750V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert "ha_open" in df.columns
        assert "ha_close" in df.columns
        assert df["ha_open"].iloc[0] == 19808.00
        assert df["ha_close"].iloc[0] == 19812.00

    def test_eth_750v_vwap_bands_present(self, tmp_path):
        f = tmp_path / "eth_750v.txt"
        f.write_text(ETH_750V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert df["Upper Band 2"].iloc[0] == 19840.00
        assert df["Lower Band 2"].iloc[0] == 19770.00
        assert df["VWAP"].iloc[0] == 19805.00

    # --- File #3: RTH 500v (45 columns, no Line1) ---

    def test_rth_500v_delta_close_extracted(self, tmp_path):
        f = tmp_path / "rth_500v.txt"
        f.write_text(RTH_500V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert "delta_close" in df.columns
        assert df["delta_close"].dtype == float
        assert df["delta_close"].iloc[0] == -150.00

    def test_rth_500v_base_close_distinct_from_delta(self, tmp_path):
        f = tmp_path / "rth_500v.txt"
        f.write_text(RTH_500V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert df["Close"].iloc[0] == 19810.00
        assert df["delta_close"].iloc[0] != df["Close"].iloc[0]

    def test_rth_500v_delta_ma_extracted(self, tmp_path):
        f = tmp_path / "rth_500v.txt"
        f.write_text(RTH_500V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert "Avg" in df.columns
        assert df["Avg"].iloc[0] == 43200.00

    def test_rth_500v_vwap_bands_present(self, tmp_path):
        f = tmp_path / "rth_500v.txt"
        f.write_text(RTH_500V_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert df["Upper Band 2"].iloc[0] == 19840.00
        assert df["Lower Band 2"].iloc[0] == 19770.00

    # --- Regression: simple fixture still parses without overlay columns ---

    def test_simple_fixture_unaffected(self, tmp_path):
        """The existing 16-col simple fixture must still parse correctly."""
        f = tmp_path / "eth_simple.txt"
        f.write_text(ETH_RTH_VWAP_CONTENT)
        df = parse_sc_file(str(f), SchemaType.ETH_RTH_VWAP)
        assert df.shape == (3, 14)
        assert "VWAP" in df.columns
        assert "delta_close" not in df.columns  # not in simple fixture


# ---------------------------------------------------------------------------
# detect_schema tests
# ---------------------------------------------------------------------------

class TestDetectSchema:
    def test_detects_daily_adr(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_CONTENT)
        assert detect_schema(str(f)) == SchemaType.DAILY_ADR

    def test_detects_one_min(self, tmp_path):
        f = tmp_path / "nq_1min.txt"
        f.write_text(ONE_MIN_CONTENT)
        assert detect_schema(str(f)) == SchemaType.ONE_MIN

    def test_detects_eth_rth_vwap(self, tmp_path):
        f = tmp_path / "eth.txt"
        f.write_text(ETH_RTH_VWAP_CONTENT)
        assert detect_schema(str(f)) == SchemaType.ETH_RTH_VWAP

    def test_detects_vwap_multi_yearly(self, tmp_path):
        f = tmp_path / "yearly.txt"
        f.write_text(VWAP_MULTI_YEARLY_CONTENT)
        assert detect_schema(str(f)) == SchemaType.VWAP_MULTI

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            detect_schema(str(tmp_path / "nonexistent.txt"))


# ---------------------------------------------------------------------------
# Task 11b: get_pre_ultimate_bar and get_recent_bars
# ---------------------------------------------------------------------------

# 4 daily rows — last row simulates a partial current-day bar with lower Avg/ADR
DAILY_ADR_4ROW_HEADER = "Date,Time,Open,High,Low,Close,Volume,Avg,ADR"
DAILY_ADR_4ROW_R1 = "2026-04-11,00:00:00,19500.00,19620.00,19450.00,19570.00,44000,42000.00,138.00"
DAILY_ADR_4ROW_R2 = "2026-04-12,00:00:00,19600.00,19720.00,19550.00,19680.00,46000,43000.00,140.00"
DAILY_ADR_4ROW_R3 = "2026-04-13,00:00:00,19700.00,19810.00,19650.00,19750.00,48000,44000.00,145.00"
# Partial current day — lower Avg and ADR
DAILY_ADR_4ROW_R4 = "2026-04-14,00:00:00,19800.00,19820.00,19750.00,19810.00,5000,10000.00,50.00"
DAILY_ADR_4ROW_CONTENT = "\n".join([
    DAILY_ADR_4ROW_HEADER,
    DAILY_ADR_4ROW_R1,
    DAILY_ADR_4ROW_R2,
    DAILY_ADR_4ROW_R3,
    DAILY_ADR_4ROW_R4,
])


class TestPreUltimateBar:
    def test_returns_penultimate_row(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_4ROW_CONTENT)
        row = get_pre_ultimate_bar(str(f), SchemaType.DAILY_ADR)
        # Should be 3rd row (index -2), not 4th partial row
        assert row["Avg"] == 44000.00
        assert row["ADR"] == 145.00

    def test_does_not_return_last_partial_row(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_4ROW_CONTENT)
        row = get_pre_ultimate_bar(str(f), SchemaType.DAILY_ADR)
        # Partial day has Avg=10000, ADR=50 — must not appear
        assert row["Avg"] != 10000.00
        assert row["ADR"] != 50.00

    def test_includes_datetime_key(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_4ROW_CONTENT)
        row = get_pre_ultimate_bar(str(f), SchemaType.DAILY_ADR)
        assert "datetime" in row
        assert "2026-04-13" in row["datetime"]

    def test_raises_on_single_row(self, tmp_path):
        f = tmp_path / "single.txt"
        f.write_text("\n".join([DAILY_ADR_4ROW_HEADER, DAILY_ADR_4ROW_R1]))
        with pytest.raises(ValueError, match="at least 2 rows"):
            get_pre_ultimate_bar(str(f), SchemaType.DAILY_ADR)


class TestGetRecentBars:
    def test_returns_n_rows(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_4ROW_CONTENT)
        result = get_recent_bars(str(f), SchemaType.DAILY_ADR, n=3)
        assert len(result) == 3

    def test_returns_trailing_rows(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_4ROW_CONTENT)
        result = get_recent_bars(str(f), SchemaType.DAILY_ADR, n=3)
        # Last of the 3 returned rows should be the 4th row (partial day)
        assert result["Avg"].iloc[-1] == 10000.00

    def test_capped_at_available_rows(self, tmp_path):
        f = tmp_path / "daily.txt"
        f.write_text(DAILY_ADR_4ROW_CONTENT)
        result = get_recent_bars(str(f), SchemaType.DAILY_ADR, n=10)
        assert len(result) == 4  # only 4 rows exist


# ---------------------------------------------------------------------------
# Task 13: RVOL_30MIN schema
# ---------------------------------------------------------------------------

RVOL_30MIN_HEADER = (
    "Date,Time,Open,High,Low,Last,Volume,# of Trades,OHLC Avg,"
    "HLC Avg,HL Avg,Bid Volume,Ask Volume,"
    "wVWAP,PW-Hi,PW-Lo,WK-Op,PW-VAH,PW-VAL,WK-Mid,"
    "Relative Volume,Cumulative Volume Ratio,"
    "100%,Single Prints Up (current session),Single Prints Down (current session)"
)
RVOL_30MIN_ROW_1 = "2026-04-14,09:30:00,19800.00,19850.00,19780.00,19820.00,5000,120,19812.50,19817.00,19815.00,2500,2500,19810.00,19900.00,19750.00,19795.00,19880.00,19740.00,19822.00,1.05,1.10,100.00,0.00,0.00"
RVOL_30MIN_ROW_2 = "2026-04-14,10:00:00,19820.00,19860.00,19800.00,19840.00,4800,115,19830.00,19833.33,19830.00,2400,2400,19812.00,19900.00,19750.00,19795.00,19880.00,19740.00,19822.00,1.10,1.15,100.00,0.00,0.00"
RVOL_30MIN_ROW_3 = "2026-04-14,10:30:00,19840.00,19870.00,19820.00,19855.00,5200,130,19846.25,19848.33,19845.00,2600,2600,19815.00,19900.00,19750.00,19795.00,19880.00,19740.00,19822.00,1.15,1.20,100.00,0.00,0.00"
RVOL_30MIN_CONTENT = "\n".join([RVOL_30MIN_HEADER, RVOL_30MIN_ROW_1, RVOL_30MIN_ROW_2, RVOL_30MIN_ROW_3])


class TestRvol30MinSchema:
    def test_cumulative_volume_ratio_parsed(self, tmp_path):
        f = tmp_path / "rvol.txt"
        f.write_text(RVOL_30MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.RVOL_30MIN)
        assert "Cumulative Volume Ratio" in df.columns
        assert df["Cumulative Volume Ratio"].dtype == float
        assert df["Cumulative Volume Ratio"].iloc[0] == 1.10

    def test_relative_volume_parsed(self, tmp_path):
        f = tmp_path / "rvol.txt"
        f.write_text(RVOL_30MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.RVOL_30MIN)
        assert "Relative Volume" in df.columns
        assert df["Relative Volume"].iloc[0] == 1.05

    def test_shape(self, tmp_path):
        f = tmp_path / "rvol.txt"
        f.write_text(RVOL_30MIN_CONTENT)
        df = parse_sc_file(str(f), SchemaType.RVOL_30MIN)
        assert df.shape[0] == 3

    def test_detect_schema_identifies_rvol_30min(self, tmp_path):
        f = tmp_path / "rvol.txt"
        f.write_text(RVOL_30MIN_CONTENT)
        assert detect_schema(str(f)) == SchemaType.RVOL_30MIN

    def test_empty_file_returns_empty_df(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        df = parse_sc_file(str(f), SchemaType.RVOL_30MIN)
        assert df.empty
        assert "Cumulative Volume Ratio" in df.columns


# ---------------------------------------------------------------------------
# Real-data test: delta_close column mapping in ETH 750v file
#
# The ETH 750v file has overlay study columns after "Text Display":
#   Bullish Divergence, Bearish Divergence, Avg, Line1,
#   Open, High, Low, Close  ← these are delta_open/high/low/close
# A bug in _build_col_index_eth_rth caused delta_close to map to "Line1"
# (always 0.000) instead of the actual cumulative-delta Close column.
# This test uses the real SC file to catch that regression.
# ---------------------------------------------------------------------------

ETH_VWAP_REAL_PATH = "C:/SierraChart/Data/eth_vwap.txt"


class TestEthDeltaCloseRealData:
    @staticmethod
    def _raw_delta_close_last_row(path: str) -> float:
        """Read the raw file and return the value at the delta_close column index
        for the last data row, derived directly from the header line."""
        with open(path, encoding="utf-8") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]

        raw_headers = [h.strip() for h in lines[0].split(",")]
        td_pos = raw_headers.index("Text Display")
        # After Text Display: Bullish Div, Bearish Div, Avg, Line1, Open, High, Low, Close(delta)
        # Advance past everything until we find "Avg"
        pos = td_pos + 1
        while pos < len(raw_headers) and raw_headers[pos] != "Avg":
            pos += 1
        pos += 1  # skip Avg
        if pos < len(raw_headers) and raw_headers[pos] == "Line1":
            pos += 1  # skip Line1
        # Now pos points to delta_open; delta_close is 3 further
        delta_close_col = pos + 3

        last_row = [v.strip() for v in lines[-1].split(",")]
        return float(last_row[delta_close_col])

    def test_delta_close_not_zero(self):
        """delta_close parsed by sc_parser must not be zero when the raw value is non-zero."""
        pytest.importorskip("pandas")
        raw_value = self._raw_delta_close_last_row(ETH_VWAP_REAL_PATH)
        # Sanity: if raw data happens to be 0, skip the meaningful assertion
        if raw_value == 0.0:
            pytest.skip("delta_close happens to be 0 in the current file — cannot distinguish from bug")

        df = parse_sc_file(ETH_VWAP_REAL_PATH, SchemaType.ETH_RTH_VWAP)
        assert "delta_close" in df.columns
        parsed_value = df["delta_close"].iloc[-1]
        assert parsed_value == raw_value, (
            f"delta_close mismatch: parser returned {parsed_value}, "
            f"raw file value is {raw_value}. "
            "Likely cause: _build_col_index_eth_rth maps delta_close to the wrong column."
        )

    def test_delta_close_sign_matches_raw(self):
        """The sign of parsed delta_close must match the raw file value."""
        raw_value = self._raw_delta_close_last_row(ETH_VWAP_REAL_PATH)
        if raw_value == 0.0:
            pytest.skip("delta_close is 0 — sign test not applicable")

        df = parse_sc_file(ETH_VWAP_REAL_PATH, SchemaType.ETH_RTH_VWAP)
        parsed_value = df["delta_close"].iloc[-1]
        assert (parsed_value > 0) == (raw_value > 0), (
            f"Sign mismatch: parser={parsed_value}, raw={raw_value}. "
            "cd_above_zero indicator will be wrong."
        )


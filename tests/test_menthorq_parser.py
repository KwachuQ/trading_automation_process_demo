"""Tests for the MenthorQ paste-string parser.

Uses the exact sample strings from docs/refinements.md as fixtures.
"""
from __future__ import annotations

import pytest

from backend.ingestion.menthorq_parser import parse_menthorq_string, split_combined_menthorq

# ---------------------------------------------------------------------------
# Exact sample strings from docs/refinements.md
# ---------------------------------------------------------------------------

_NQ_STRING = (
    "$NQ1!: Call Resistance, 26000, Put Support, 24000, HVL, 24740, "
    "1D Min, 25694.76, 1D Max, 26298.74, Call Resistance 0DTE, 26000, "
    "Put Support 0DTE, 25660, HVL 0DTE, 25790, Gamma Wall 0DTE, 26000, "
    "GEX 1, 26100, GEX 2, 26250, GEX 3, 25900, GEX 4, 26200, GEX 5, 25750, "
    "GEX 6, 25500, GEX 7, 26500, GEX 8, 25600, GEX 9, 25400, GEX 10, 26300"
)

_QQQ_STRING = (
    "$QQQ: Call Resistance, 630, Put Support, 590, HVL, 607, "
    "1D Min, 621.02, 1D Max, 636.18, Call Resistance 0DTE, 625, "
    "Put Support 0DTE, 615, HVL 0DTE, 615, Gamma Wall 0DTE, 625, "
    "GEX 1, 635, GEX 2, 628, GEX 3, 626, GEX 4, 623, GEX 5, 622, "
    "GEX 6, 620, GEX 7, 640, GEX 8, 621, GEX 9, 616, GEX 10, 617"
)


# ---------------------------------------------------------------------------
# Required core fields
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "call_resistance",
    "put_support",
    "call_resistance_0dte",
    "put_support_0dte",
    "hvl",
    "hvl_0dte",
    "exp_move_max",
    "exp_move_min",
}


class TestNQString:
    def test_all_required_keys_present(self) -> None:
        result = parse_menthorq_string(_NQ_STRING)
        assert _REQUIRED_KEYS.issubset(result.keys())

    def test_core_values_correct(self) -> None:
        result = parse_menthorq_string(_NQ_STRING)
        assert result["call_resistance"] == 26000.0
        assert result["put_support"] == 24000.0
        assert result["hvl"] == 24740.0
        assert result["exp_move_min"] == 25694.76
        assert result["exp_move_max"] == 26298.74
        assert result["call_resistance_0dte"] == 26000.0
        assert result["put_support_0dte"] == 25660.0
        assert result["hvl_0dte"] == 25790.0

    def test_gex_fields_included(self) -> None:
        result = parse_menthorq_string(_NQ_STRING)
        assert result["gex_1"] == 26100.0
        assert result["gex_10"] == 26300.0

    def test_gamma_wall_0dte_included(self) -> None:
        result = parse_menthorq_string(_NQ_STRING)
        assert result["gamma_wall_0dte"] == 26000.0

    def test_all_values_are_floats(self) -> None:
        result = parse_menthorq_string(_NQ_STRING)
        for key, val in result.items():
            assert isinstance(val, float), f"{key} is not float: {type(val)}"


class TestQQQString:
    def test_all_required_keys_present(self) -> None:
        result = parse_menthorq_string(_QQQ_STRING)
        assert _REQUIRED_KEYS.issubset(result.keys())

    def test_core_values_correct(self) -> None:
        result = parse_menthorq_string(_QQQ_STRING)
        assert result["call_resistance"] == 630.0
        assert result["put_support"] == 590.0
        assert result["hvl"] == 607.0
        assert result["exp_move_min"] == 621.02
        assert result["exp_move_max"] == 636.18

    def test_gex_fields_included(self) -> None:
        result = parse_menthorq_string(_QQQ_STRING)
        assert result["gex_1"] == 635.0
        assert result["gex_10"] == 617.0


class TestValidationErrors:
    def test_missing_required_fields_raises(self) -> None:
        # Truncated string — missing most required fields
        truncated = "$NQ1!: Call Resistance, 26000, Put Support, 24000"
        with pytest.raises(ValueError, match="Missing required fields"):
            parse_menthorq_string(truncated)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_menthorq_string("")

    def test_prefix_only_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_menthorq_string("$NQ1!:")

    def test_odd_token_count_raises(self) -> None:
        # Valid prefix + odd number of tokens after stripping
        odd = "$NQ1!: Call Resistance, 26000, Put Support"
        with pytest.raises(ValueError, match="even"):
            parse_menthorq_string(odd)

    def test_non_numeric_value_raises(self) -> None:
        bad = "$NQ1!: Call Resistance, N/A, Put Support, 24000"
        with pytest.raises(ValueError, match="Cannot convert"):
            parse_menthorq_string(bad)


class TestWhitespaceTolerance:
    def test_extra_spaces_around_commas(self) -> None:
        # Build a full valid string with extra spaces
        spaced = _NQ_STRING.replace(",", " , ")
        result = parse_menthorq_string(spaced)
        assert result["call_resistance"] == 26000.0
        assert result["exp_move_min"] == 25694.76

    def test_leading_trailing_whitespace_on_string(self) -> None:
        result = parse_menthorq_string("  " + _NQ_STRING + "  ")
        assert _REQUIRED_KEYS.issubset(result.keys())

    def test_no_prefix_still_parses_if_all_fields_present(self) -> None:
        # Strip the "$NQ1!: " prefix manually and feed raw label-value pairs
        no_prefix = _NQ_STRING.replace("$NQ1!: ", "")
        result = parse_menthorq_string(no_prefix)
        assert _REQUIRED_KEYS.issubset(result.keys())


# ---------------------------------------------------------------------------
# Combined string from docs/refinements.md
# ---------------------------------------------------------------------------

_COMBINED_STRING = (
    "Call Resistance, 26000, Put Support, 24000, HVL, 24740, "
    "1D Min, 26049.27, 1D Max, 26681.73, Call Resistance 0DTE, 26050, "
    "Put Support 0DTE, 25970, HVL 0DTE, 25230, "
    "Call Resistance, 640, Put Support, 590, HVL, 609.78, "
    "1D Min, 629.72, 1D Max, 645.08, Call Resistance 0DTE, 640, "
    "Put Support 0DTE, 626, HVL 0DTE, 626"
)


class TestSplitCombinedMenthorq:
    def test_split_produces_two_strings(self) -> None:
        nq, qqq = split_combined_menthorq(_COMBINED_STRING)
        assert isinstance(nq, str)
        assert isinstance(qqq, str)

    def test_nq_half_parses_correctly(self) -> None:
        nq, _ = split_combined_menthorq(_COMBINED_STRING)
        result = parse_menthorq_string(nq)
        assert result["call_resistance"] == 26000.0
        assert result["put_support"] == 24000.0
        assert result["hvl"] == 24740.0
        assert result["exp_move_min"] == 26049.27
        assert result["exp_move_max"] == 26681.73
        assert result["call_resistance_0dte"] == 26050.0
        assert result["put_support_0dte"] == 25970.0
        assert result["hvl_0dte"] == 25230.0

    def test_qqq_half_parses_correctly(self) -> None:
        _, qqq = split_combined_menthorq(_COMBINED_STRING)
        result = parse_menthorq_string(qqq)
        assert result["call_resistance"] == 640.0
        assert result["put_support"] == 590.0
        assert result["hvl"] == 609.78
        assert result["exp_move_min"] == 629.72
        assert result["exp_move_max"] == 645.08
        assert result["call_resistance_0dte"] == 640.0
        assert result["put_support_0dte"] == 626.0
        assert result["hvl_0dte"] == 626.0

    def test_wrong_token_count_raises(self) -> None:
        short = "Call Resistance, 26000, Put Support, 24000"
        with pytest.raises(ValueError, match="exactly 32 tokens"):
            split_combined_menthorq(short)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            split_combined_menthorq("")

    def test_prefixed_sections_with_gex(self) -> None:
        """Real MenthorQ paste format with $NQ1!: / $QQQ: prefixes and GEX levels."""
        full_paste = (
            "$NQ1!: Call Resistance, 26000, Put Support, 24000, HVL, 24740, "
            "1D Min, 26049.27, 1D Max, 26681.73, Call Resistance 0DTE, 26050, "
            "Put Support 0DTE, 25970, HVL 0DTE, 25230, Gamma Wall 0DTE, 26050, "
            "GEX 1, 26500, GEX 2, 26100, GEX 3, 26300, GEX 4, 26250, GEX 5, 26200, "
            "GEX 6, 25900, GEX 7, 25750, GEX 8, 26800, GEX 9, 25800, GEX 10, 26750\n\n"
            "$QQQ: Call Resistance, 640, Put Support, 590, HVL, 609.78, "
            "1D Min, 629.72, 1D Max, 645.08, Call Resistance 0DTE, 640, "
            "Put Support 0DTE, 626, HVL 0DTE, 626, Gamma Wall 0DTE, 640, "
            "GEX 1, 630, GEX 2, 635, GEX 3, 645, GEX 4, 638, GEX 5, 631, "
            "GEX 6, 650, GEX 7, 625, GEX 8, 628, GEX 9, 629, GEX 10, 627"
        )
        nq, qqq = split_combined_menthorq(full_paste)
        nq_result = parse_menthorq_string(nq)
        qqq_result = parse_menthorq_string(qqq)

        assert nq_result["call_resistance"] == 26000.0
        assert nq_result["exp_move_min"] == 26049.27
        assert nq_result["hvl_0dte"] == 25230.0
        assert nq_result["gex_1"] == 26500.0

        assert qqq_result["call_resistance"] == 640.0
        assert qqq_result["exp_move_min"] == 629.72
        assert qqq_result["hvl_0dte"] == 626.0
        assert qqq_result["gex_10"] == 627.0

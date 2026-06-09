from __future__ import annotations

import re

_LABEL_OVERRIDES: dict[str, str] = {
    "1d min": "exp_move_min",
    "1d max": "exp_move_max",
}

_REQUIRED_KEYS: frozenset[str] = frozenset({
    "call_resistance",
    "put_support",
    "call_resistance_0dte",
    "put_support_0dte",
    "hvl",
    "hvl_0dte",
    "exp_move_max",
    "exp_move_min",
})


def _normalise_label(label: str) -> str:
    lower = label.strip().lower()
    if lower in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[lower]
    return re.sub(r"\s+", "_", lower)


_TOKENS_PER_INSTRUMENT = 16  # 8 label-value pairs


def split_combined_menthorq(raw: str) -> tuple[str, str]:
    """Split a combined NQ+QQQ MenthorQ paste string into two separate strings.

    Handles two input formats:

    1. **Prefixed sections** (the real MenthorQ paste format, may include GEX levels):
       "$NQ1!: Call Resistance, 26000, ..., GEX 10, 26750
        $QQQ: Call Resistance, 640, ..., GEX 10, 627"

    2. **Compact combined string** (8 core pairs per instrument, no prefixes):
       "Call Resistance, 26000, ..., HVL 0DTE, 25230, Call Resistance, 640, ..., HVL 0DTE, 626"

    In both cases each half is returned as a plain comma-separated token string
    ready to be passed to :func:`parse_menthorq_string`.

    Raises:
        ValueError: For format 2, if the token count is not exactly 32.
        ValueError: If fewer than two sections are found.
    """
    # Format 1: split on "$TICKER:" or "$TICKER!:" instrument prefixes
    parts = re.split(r"\$\w+!?:\s*", raw.strip())
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) == 2:
        return parts[0], parts[1]

    if len(parts) > 2:
        raise ValueError(
            f"Found {len(parts)} instrument sections; expected exactly 2 (NQ and QQQ)"
        )

    # Format 2: single continuous string, exactly 8 core pairs per instrument
    tokens = [t.strip() for t in raw.strip().split(",")]
    total = len(tokens)
    if total != _TOKENS_PER_INSTRUMENT * 2:
        raise ValueError(
            f"Combined string must have exactly {_TOKENS_PER_INSTRUMENT * 2} tokens "
            f"(8 NQ pairs + 8 QQQ pairs), got {total}"
        )
    nq_string = ", ".join(tokens[:_TOKENS_PER_INSTRUMENT])
    qqq_string = ", ".join(tokens[_TOKENS_PER_INSTRUMENT:])
    return nq_string, qqq_string


def parse_menthorq_string(raw: str) -> dict[str, float]:
    """Parse a MenthorQ paste string into a dict of snake_case keys mapped to float values.

    Expected format (prefix is optional):
        "$NQ1!: Call Resistance, 26000, Put Support, 24000, ..."

    Raises:
        ValueError: if the string cannot be parsed or required core fields are missing.
    """
    stripped = re.sub(r"^\$\w+!?:\s*", "", raw.strip())
    if not stripped:
        raise ValueError("Empty string after stripping instrument prefix")

    tokens = [t.strip() for t in stripped.split(",")]
    if len(tokens) < 2:
        raise ValueError("String contains too few tokens to parse")
    if len(tokens) % 2 != 0:
        raise ValueError(
            f"Expected an even number of comma-separated tokens, got {len(tokens)}"
        )

    result: dict[str, float] = {}
    for i in range(0, len(tokens), 2):
        label = tokens[i]
        value_str = tokens[i + 1]
        if not label:
            raise ValueError(f"Empty label at token position {i}")
        try:
            value = float(value_str)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Cannot convert value '{value_str}' to float for label '{label}'"
            ) from exc
        key = _normalise_label(label)
        result[key] = value

    missing = _REQUIRED_KEYS - result.keys()
    if missing:
        raise ValueError(f"Missing required fields: {sorted(missing)}")

    return result

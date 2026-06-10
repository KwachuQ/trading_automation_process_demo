"""
backend/feature_store/engine.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Regime engine: weighted evaluator for market regime classification and
trade-setup scoring.

Key types
---------
IndicatorSnapshot
    A flat bag of all indicator values for one evaluation moment.  Every
    field is optional (``None`` by default).  ``None`` means "not yet
    available" — the engine *skips* (does not match) conditions that
    reference a ``None`` field.

ScenarioResult
    Output of ``evaluate_scenario``.  Contains the winning scenario name,
    confidence score (0–1), and the rule's metadata.

SetupScore
    Output of ``score_setup``.  Contains a 0–100 normalised score
    and a per-criterion breakdown.

Design notes
------------
- All enum field values exactly match ``docs/trading_logic/field-definitions.md``.
  Do NOT normalise or lower-case them — rules are authored using the same
  strings and comparisons are literal.
- The ``in`` operator accepts either a Python list (for programmatic use)
  or a comma-separated string (when the value comes from the DB JSON).
- Ties in regime evaluation are broken by the rule's id (lowest id wins).
- No in-process caching: the caller is expected to pass freshly-loaded
  rules / criteria lists so edits take effect on the next poll cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.feature_store.store import MarketScenario, ScoringCriterion


# ---------------------------------------------------------------------------
# IndicatorSnapshot — canonical field definitions
# ---------------------------------------------------------------------------


@dataclass
class IndicatorSnapshot:
    """One moment-in-time snapshot of all indicator values.

    Field types and allowed values follow ``docs/trading_logic/field-definitions.md``
    exactly.  ``None`` means "not yet available" for that field.

    Higher-timeframe trend fields
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    trend_yearly, trend_quarterly, trend_monthly, trend_weekly
        Enum: ``"rising"`` / ``"sideways"`` / ``"falling"``

    Band position fields
    ~~~~~~~~~~~~~~~~~~~~
    band_position_yearly, band_position_quarterly,
    band_position_monthly, band_position_weekly
        Enum: ``"Imbalance up"`` / ``"Imbalance down"`` / ``"Inside value area"``
        (title-case with spaces — exactly as in field-definitions.md)

    Numeric volatility fields
    ~~~~~~~~~~~~~~~~~~~~~~~~~
    adr
        Average daily range, in points (float).
    rvol
        Cumulative relative volume, in percent (float).
    vvix_vix_ratio
        VVIX / VIX ratio (float).

    Slope / trend direction fields
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    adr_slope, rvol_slope, delta_slope, vwap_slope
        Enum: ``"rising"`` / ``"sideways"`` / ``"falling"``
        (These are enums, NOT floats.)

    Options / flow fields
    ~~~~~~~~~~~~~~~~~~~~~
    gamma_regime
        Enum: ``"positive"`` / ``"negative"`` / ``"mixed"``
    cd_vs_ma
        Enum: ``"above MA"`` / ``"below MA"``  (with ``" MA"`` suffix)

    Pre-session composite
    ~~~~~~~~~~~~~~~~~~~~~
    vol_regime
        Enum: ``"EXTREME"`` / ``"HIGH"`` / ``"MODERATE"`` / ``"LOW"`` / ``"VERY_LOW"``
    """

    # --- Higher-timeframe trends ---
    trend_yearly: str | None = None
    trend_quarterly: str | None = None
    trend_monthly: str | None = None
    trend_weekly: str | None = None

    # --- Band positions ---
    band_position_yearly: str | None = None
    band_position_quarterly: str | None = None
    band_position_monthly: str | None = None
    band_position_weekly: str | None = None

    # --- Numeric volatility ---
    adr: float | None = None
    rvol: float | None = None
    vvix_vix_ratio: float | None = None

    # --- Slope / trend direction (enums, NOT floats) ---
    adr_slope: str | None = None
    rvol_slope: str | None = None
    delta_slope: str | None = None
    vwap_slope: str | None = None

    # --- Options / flow ---
    gamma_regime: str | None = None   # "positive" / "negative" / "mixed"
    cd_vs_ma: str | None = None       # "above MA" / "below MA"
    entry_quality: str | None = None  # "Optimal" / "Good" / "Acceptable" / "Poor" / "Unacceptable"

    # --- Pre-session composite ---
    vol_regime: str | None = None     # "EXTREME" / "HIGH" / "MODERATE" / "LOW" / "VERY_LOW"


# ---------------------------------------------------------------------------
# RegimeResult
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    """Output of ``evaluate_scenario``.

    Attributes:
        scenario_name:    Name of the winning rule, or ``"Unclassified"``.
        parent_regime:    The parent regime classification.
        subtype:          The specific subtype of the regime.
        confidence:       ``matched_weight / total_weight`` for the winner
                          (0.0 when Unclassified).
        matched_weight:   Sum of weights for conditions that fired.
        total_weight:     Sum of weights for ALL conditions in the winning
                          rule (including unmatched ones).
        characteristics:  Free-text description copied from the winning rule.
        risk_adjustments: Risk metadata dict copied from the winning rule.
    """

    scenario_name: str
    parent_regime: str
    subtype: str
    confidence: float
    matched_weight: float
    total_weight: float
    characteristics: str
    risk_adjustments: dict


# ---------------------------------------------------------------------------
# SetupScore
# ---------------------------------------------------------------------------


@dataclass
class SetupScore:
    """Output of ``score_trade_setup``.

    Attributes:
        total_score:  Normalised score in the range 0–100.
        breakdown:    Per-criterion detail list, each entry a dict with keys
                      ``criterion_name``, ``matched`` (bool), and
                      ``weighted_contribution`` (float).
    """

    total_score: float
    breakdown: list[dict]


# ---------------------------------------------------------------------------
# Internal condition evaluator
# ---------------------------------------------------------------------------


def _get_field(snapshot: IndicatorSnapshot, indicator: str) -> Any:
    """Return the snapshot value for ``indicator``, or ``None`` if unknown."""
    return getattr(snapshot, indicator, None)


def _parse_in_value(raw: Any) -> list:
    """Convert a condition value to a list for the ``in`` operator.

    Accepts:
    - A Python ``list`` already (programmatic construction).
    - A comma-separated string (values stored in the DB as JSON strings).
    """
    if isinstance(raw, list):
        return [str(v).strip() for v in raw]
    # Comma-separated string, e.g. '"EXTREME", "HIGH"' or 'EXTREME,HIGH'
    return [v.strip().strip('"\'') for v in str(raw).split(",") if v.strip()]


def _parse_range(raw: Any) -> tuple[float, float] | None:
    """Parse a two-value range from a list/tuple or comma-separated string."""
    try:
        if isinstance(raw, (list, tuple)):
            if len(raw) != 2:
                return None
            return float(raw[0]), float(raw[1])
        parts = [p.strip().strip('"\'') for p in str(raw).split(",") if p.strip()]
        if len(parts) != 2:
            return None
        return float(parts[0]), float(parts[1])
    except (TypeError, ValueError, IndexError):
        return None


def _handle_between(lhs: Any, rhs: Any) -> bool:
    rng = _parse_range(rhs)
    if rng is None:
        return False
    low, high = rng
    return low <= float(lhs) <= high


def _numeric_cmp_factory(op):
    def _cmp(lhs: Any, rhs: Any) -> bool:
        return op(float(lhs), float(rhs))
    return _cmp


def _evaluate_value(field_value: Any, operator: str, expected_value: Any) -> bool:
    if field_value is None:
        return False

    op = operator.strip()

    handlers = {
        "in": lambda l, r: str(l) in _parse_in_value(r),
        "between": _handle_between,
        "==": lambda l, r: l == r,
        "!=": lambda l, r: l != r,
        ">": _numeric_cmp_factory(lambda a, b: a > b),
        "<": _numeric_cmp_factory(lambda a, b: a < b),
        ">=": _numeric_cmp_factory(lambda a, b: a >= b),
        "<=": _numeric_cmp_factory(lambda a, b: a <= b),
    }

    handler = handlers.get(op)
    if handler is None:
        return False

    try:
        return bool(handler(field_value, expected_value))
    except (TypeError, ValueError, IndexError):
        return False
    
    # Numeric comparisons — only valid when both sides are numeric
    try:
        lhs = float(field_value)
        rhs = float(expected_value)
    except (TypeError, ValueError):
        # Non-numeric field used with a numeric operator — treat as no match.
        return False
    if op == ">":
        return lhs > rhs
    if op == "<":
        return lhs < rhs
    if op == ">=":
        return lhs >= rhs
    if op == "<=":
        return lhs <= rhs

    # Unknown operator — safe fallback
    return False


def _evaluate_condition(
    snapshot: IndicatorSnapshot,
    indicator: str,
    operator: str,
    value: Any,
) -> bool:
    """Evaluate one ``RuleCondition`` against ``snapshot``.

    Returns ``False`` (not matched) if the snapshot field is ``None`` so
    the engine gracefully degrades when intraday data is not yet available.
    """
    field_value = _get_field(snapshot, indicator)
    return _evaluate_value(field_value, operator, value)


# ---------------------------------------------------------------------------
# Regime evaluator
# ---------------------------------------------------------------------------


def evaluate_scenario(
    indicators: IndicatorSnapshot,
    rules: list[MarketScenario],
) -> ScenarioResult:
    """Classify market conditions by evaluating ``rules`` against ``indicators``.

    Algorithm
    ---------
    For every active scenario:
    1. Iterate its conditions and sum ``weight`` for each condition that
       matches.  Conditions referencing ``None`` fields are skipped.
    2. ``total_weight`` = sum of ALL condition weights (the denominator for
       confidence, even for conditions that did not fire).
    3. Pick the scenario with the highest ``matched_weight``.
    4. Ties → first scenario (lowest id) wins.
    5. If no scenario scores above zero or confidence < 0.5 → return ``"Unclassified"`` with 0.0
       confidence.

    Args:
        indicators: Live snapshot of all indicator values.
        rules:      List of active ``MarketScenario`` objects (should already be
                    filtered to active-only by the caller or the CRUD layer).

    Returns:
        ``ScenarioResult`` for the winning scenario, or an Unclassified result.
    """
    best_rule: MarketScenario | None = None
    best_matched: float = 0.0
    best_total: float = 0.0

    for rule in rules:
        if not rule.is_active:
            continue

        matched_weight: float = 0.0
        total_weight: float = 0.0

        for cond in rule.conditions:
            total_weight += cond.weight
            if _evaluate_condition(
                indicators, cond.indicator, cond.operator, cond.value
            ):
                matched_weight += cond.weight

        # Update best — ties broken by iterating in id order (caller must
        # sort rules by id ascending before calling, or pass in that order).
        if matched_weight > best_matched:
            best_matched = matched_weight
            best_total = total_weight
            best_rule = rule

    confidence = best_matched / best_total if best_total > 0.0 else 0.0

    if best_rule is None or confidence < 0.5:
        return ScenarioResult(
            scenario_name="Unclassified",
            parent_regime="",
            subtype="",
            confidence=0.0,
            matched_weight=0.0,
            total_weight=0.0,
            characteristics="",
            risk_adjustments={},
        )

    return ScenarioResult(
        scenario_name=best_rule.name,
        parent_regime=best_rule.parent_regime,
        subtype=best_rule.subtype,
        confidence=round(confidence, 4),
        matched_weight=best_matched,
        total_weight=best_total,
        characteristics=best_rule.characteristics,
        risk_adjustments=best_rule.risk_adjustments,
    )


# ---------------------------------------------------------------------------
# Setup scorer
# ---------------------------------------------------------------------------


def _scenario_field_value(
    indicators: IndicatorSnapshot,
    active_scenario: ScenarioResult | None,
    indicator: str,
) -> Any:
    """Return the field value either from `active_scenario` (for scenario attrs)
    or from the indicator snapshot."""
    if active_scenario is not None and indicator in ("scenario_name", "parent_regime", "subtype"):
        return getattr(active_scenario, indicator, None)
    return _get_field(indicators, indicator)


def _criterion_contribution(crit: ScoringCriterion, matched: bool) -> float:
    """Return the weighted contribution for a single criterion."""
    if "penalty" in crit.name.lower():
        return 0.0 if matched else crit.weight
    return crit.weight if matched else 0.0


def score_setup(
    indicators: IndicatorSnapshot,
    criteria: list[ScoringCriterion],
    active_scenario: ScenarioResult | None = None,
) -> SetupScore:
    """Return a 0–100 trade-setup score and per-criterion breakdown.

Evaluate each active `ScoringCriterion` against a resolved field value
(use `active_scenario` for `"scenario_name"`, `"parent_regime"`, `"subtype"`,
otherwise read from `indicators`). Penalty criteria (name contains "penalty",
case-insensitive) contribute their weight when NOT matched; normal criteria
contribute their weight when matched.

Score is (matched_weight / total_weight) * 100, rounded to 2 decimals.
If total weight is effectively zero the score is 0.0.

Args:
    indicators: `IndicatorSnapshot`
    criteria: list[`ScoringCriterion`]
    active_scenario: Optional[`ScenarioResult`]

Returns:
    `SetupScore` with `total_score` and `breakdown` (per-criterion dicts).
"""
    matched_weight: float = 0.0
    total_weight: float = 0.0
    breakdown: list[dict] = []

    for crit in criteria:
        if not crit.is_active:
            continue

        cond = crit.condition
        field_value = _scenario_field_value(indicators, active_scenario, cond.indicator)
        matched = _evaluate_value(field_value, cond.operator, cond.value)

        contribution = _criterion_contribution(crit, matched)

        matched_weight += contribution
        total_weight += crit.weight

        breakdown.append(
            {
                "criterion_name": crit.name,
                "matched": matched,
                "weighted_contribution": contribution,
            }
        )

    total_score = 0.0 if abs(total_weight) < 1e-12 else round((matched_weight / total_weight) * 100, 2)

    return SetupScore(total_score=total_score, breakdown=breakdown)



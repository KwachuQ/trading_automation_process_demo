"""
backend/feature_store/store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Pydantic models and raw-SQLite3 CRUD for the two feature-store entity
types:

* MarketScenario   — named market sub-regime with weighted indicator
                     conditions, risk-adjustment metadata, parent regime
                     and subtype classification.
* ScoringCriterion — a single weighted condition contributing to the
                     0-100 trade-setup score, optionally scoped to a
                     specific setup type (ML, MS, MRL, MRS).

Design principle: every read hits the database directly — no in-process
caching — so scenario edits are visible on the next polling cycle without
restarting the app.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class RuleCondition(BaseModel):
    """A single indicator condition inside a market scenario or scoring criterion.

    Attributes:
        indicator: Name of the indicator field on IndicatorSnapshot.
        operator:  Comparison operator string (``>``, ``<``, ``>=``, ``<=``,
                   ``==``, ``!=``, ``in``).
        value:     The threshold or reference value to compare against.
        weight:    Positive float contribution to the scenario score when matched.
    """

    indicator: str
    operator: str
    value: Any
    weight: float


class MarketScenario(BaseModel):
    """A named market sub-regime definition with weighted indicator conditions.

    Attributes:
        id:               Auto-assigned by SQLite on create; ``None`` for
                          new, unsaved scenarios.
        name:             Unique human-readable scenario name.
        conditions:       Ordered list of ``RuleCondition`` entries evaluated
                          against a live ``IndicatorSnapshot``.
        characteristics:  Free-text description of the scenario behaviour.
        risk_adjustments: Arbitrary dict with per-scenario risk metadata
                          (e.g. ``position_size_modifier``, ``expected_range``).
        is_active:        When ``False`` the engine skips this scenario entirely.
        parent_regime:    High-level regime this scenario belongs to
                          (e.g. ``\"Trending up\"``).
        subtype:          Machine-readable subtype key
                          (e.g. ``\"continuation_up\"``).
    """

    id: int | None = None
    name: str
    conditions: list[RuleCondition]
    characteristics: str
    risk_adjustments: dict
    is_active: bool = True
    parent_regime: str = ""
    subtype: str = ""


class ScoringCriterion(BaseModel):
    """A single weighted condition for the 0-100 trade-setup score.

    Attributes:
        id:         Auto-assigned by SQLite; ``None`` for unsaved criteria.
        name:       Unique human-readable criterion name.
        condition:  The single ``RuleCondition`` to evaluate.
        weight:     Positive weight; must be > 0.
        is_active:  Inactive criteria are skipped by the scorer.
        setup_type: Optional setup type this criterion applies to
                    (``\"ML\"``, ``\"MS\"``, ``\"MRL\"``, ``\"MRS\"``).
                    ``None`` means the criterion applies to all setup types.
    """

    id: int | None = None
    name: str
    condition: RuleCondition
    weight: float
    is_active: bool = True
    setup_type: str | None = None

    @field_validator("weight")
    @classmethod
    def weight_must_be_positive(cls, v: float) -> float:
        """Reject zero or negative weights at model-construction time."""
        if v <= 0:
            raise ValueError("weight must be > 0")
        return v


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _row_to_market_scenario(row: sqlite3.Row) -> MarketScenario:
    """Convert a ``sqlite3.Row`` from ``market_scenarios`` into a ``MarketScenario``."""
    return MarketScenario(
        id=row["id"],
        name=row["name"],
        conditions=[RuleCondition(**c) for c in json.loads(row["conditions_json"])],
        characteristics=row["characteristics"],
        risk_adjustments=json.loads(row["risk_adjustments_json"]),
        is_active=bool(row["is_active"]),
        parent_regime=row["parent_regime"] or "",
        subtype=row["subtype"] or "",
    )


def _row_to_scoring_criterion(row: sqlite3.Row) -> ScoringCriterion:
    """Convert a ``sqlite3.Row`` from ``scoring_criteria`` into a
    ``ScoringCriterion``."""
    return ScoringCriterion(
        id=row["id"],
        name=row["name"],
        condition=RuleCondition(**json.loads(row["condition_json"])),
        weight=row["weight"],
        is_active=bool(row["is_active"]),
        setup_type=row["setup_type"] if row["setup_type"] else None,
    )


# ---------------------------------------------------------------------------
# Market scenario CRUD
# ---------------------------------------------------------------------------


def get_market_scenarios(
    conn: sqlite3.Connection,
    active_only: bool = True,
) -> list[MarketScenario]:
    """Return all market scenarios, optionally filtered to active ones only.

    Args:
        conn:        Open SQLite connection.
        active_only: When ``True`` (default) only rows where
                     ``is_active = 1`` are returned.

    Returns:
        List of ``MarketScenario`` objects ordered by ``id`` ascending.
    """
    conn.row_factory = sqlite3.Row
    if active_only:
        rows = conn.execute(
            "SELECT * FROM market_scenarios WHERE is_active = 1 ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM market_scenarios ORDER BY id"
        ).fetchall()
    return [_row_to_market_scenario(r) for r in rows]


def get_market_scenario(
    conn: sqlite3.Connection,
    scenario_id: int,
) -> MarketScenario | None:
    """Fetch a single market scenario by primary key.

    Args:
        conn:        Open SQLite connection.
        scenario_id: Primary key of the desired scenario.

    Returns:
        ``MarketScenario`` if found, otherwise ``None``.
    """
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM market_scenarios WHERE id = ?", (scenario_id,)
    ).fetchone()
    return _row_to_market_scenario(row) if row else None


def upsert_market_scenario(
    conn: sqlite3.Connection,
    scenario: MarketScenario,
) -> MarketScenario:
    """Insert or update a market scenario.

    When ``scenario.id`` is ``None`` a new row is inserted; otherwise the
    existing row with that id is updated in place.

    Args:
        conn:     Open SQLite connection.
        scenario: ``MarketScenario`` to persist.

    Returns:
        The saved ``MarketScenario`` with its ``id`` filled in.
    """
    conditions_json = json.dumps([c.model_dump() for c in scenario.conditions])
    risk_adjustments_json = json.dumps(scenario.risk_adjustments)

    if scenario.id is None:
        # Insert new scenario
        cur = conn.execute(
            """
            INSERT INTO market_scenarios
                (name, conditions_json, characteristics,
                 risk_adjustments_json, is_active, parent_regime, subtype)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scenario.name,
                conditions_json,
                scenario.characteristics,
                risk_adjustments_json,
                int(scenario.is_active),
                scenario.parent_regime,
                scenario.subtype,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
    else:
        # Update existing scenario
        conn.execute(
            """
            UPDATE market_scenarios
            SET name = ?,
                conditions_json = ?,
                characteristics = ?,
                risk_adjustments_json = ?,
                is_active = ?,
                parent_regime = ?,
                subtype = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                scenario.name,
                conditions_json,
                scenario.characteristics,
                risk_adjustments_json,
                int(scenario.is_active),
                scenario.parent_regime,
                scenario.subtype,
                scenario.id,
            ),
        )
        conn.commit()
        new_id = scenario.id

    # Return the saved record
    saved = get_market_scenario(conn, new_id)
    assert saved is not None  # Guaranteed — we just wrote it
    return saved


def delete_market_scenario(conn: sqlite3.Connection, scenario_id: int) -> bool:
    """Delete a market scenario by primary key.

    Args:
        conn:        Open SQLite connection.
        scenario_id: Primary key of the scenario to delete.

    Returns:
        ``True`` if a row was deleted, ``False`` if not found.
    """
    cur = conn.execute("DELETE FROM market_scenarios WHERE id = ?", (scenario_id,))
    conn.commit()
    return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Scoring criterion CRUD
# ---------------------------------------------------------------------------


def get_scoring_criteria(
    conn: sqlite3.Connection,
    active_only: bool = True,
) -> list[ScoringCriterion]:
    """Return all scoring criteria, optionally filtered to active ones.

    Args:
        conn:        Open SQLite connection.
        active_only: When ``True`` (default) only rows where
                     ``is_active = 1`` are returned.

    Returns:
        List of ``ScoringCriterion`` objects ordered by ``id`` ascending.
    """
    conn.row_factory = sqlite3.Row
    if active_only:
        rows = conn.execute(
            "SELECT * FROM scoring_criteria WHERE is_active = 1 ORDER BY id"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM scoring_criteria ORDER BY id"
        ).fetchall()
    return [_row_to_scoring_criterion(r) for r in rows]


def get_scoring_criteria_by_setup(
    conn: sqlite3.Connection,
    setup_type: str,
    active_only: bool = True,
) -> list[ScoringCriterion]:
    """Return scoring criteria filtered by setup type.

    Args:
        conn:        Open SQLite connection.
        setup_type:  Setup type to filter by (``\"ML\"``, ``\"MS\"``,
                     ``\"MRL\"``, ``\"MRS\"``).
        active_only: When ``True`` (default) only active criteria are returned.

    Returns:
        List of ``ScoringCriterion`` objects for the given setup type,
        ordered by ``id`` ascending.
    """
    conn.row_factory = sqlite3.Row
    if active_only:
        rows = conn.execute(
            "SELECT * FROM scoring_criteria WHERE setup_type = ? AND is_active = 1 ORDER BY id",
            (setup_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM scoring_criteria WHERE setup_type = ? ORDER BY id",
            (setup_type,),
        ).fetchall()
    return [_row_to_scoring_criterion(r) for r in rows]


def get_scoring_criterion(
    conn: sqlite3.Connection,
    criterion_id: int,
) -> ScoringCriterion | None:
    """Fetch a single scoring criterion by primary key.

    Args:
        conn:         Open SQLite connection.
        criterion_id: Primary key of the desired criterion.

    Returns:
        ``ScoringCriterion`` if found, otherwise ``None``.
    """
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM scoring_criteria WHERE id = ?", (criterion_id,)
    ).fetchone()
    return _row_to_scoring_criterion(row) if row else None


def upsert_scoring_criterion(
    conn: sqlite3.Connection,
    criterion: ScoringCriterion,
) -> ScoringCriterion:
    """Insert or update a scoring criterion.

    When ``criterion.id`` is ``None`` a new row is inserted; otherwise
    the existing row is updated.

    Args:
        conn:      Open SQLite connection.
        criterion: ``ScoringCriterion`` to persist.

    Returns:
        The saved ``ScoringCriterion`` with its ``id`` filled in.
    """
    condition_json = json.dumps(criterion.condition.model_dump())

    if criterion.id is None:
        cur = conn.execute(
            """
            INSERT INTO scoring_criteria (name, condition_json, weight, is_active, setup_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                criterion.name,
                condition_json,
                criterion.weight,
                int(criterion.is_active),
                criterion.setup_type,
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
    else:
        conn.execute(
            """
            UPDATE scoring_criteria
            SET name = ?,
                condition_json = ?,
                weight = ?,
                is_active = ?,
                setup_type = ?,
                updated_at = datetime('now')
            WHERE id = ?
            """,
            (
                criterion.name,
                condition_json,
                criterion.weight,
                int(criterion.is_active),
                criterion.setup_type,
                criterion.id,
            ),
        )
        conn.commit()
        new_id = criterion.id

    saved = get_scoring_criterion(conn, new_id)
    assert saved is not None
    return saved


def delete_scoring_criterion(conn: sqlite3.Connection, criterion_id: int) -> bool:
    """Delete a scoring criterion by primary key.

    Args:
        conn:         Open SQLite connection.
        criterion_id: Primary key of the criterion to delete.

    Returns:
        ``True`` if a row was deleted, ``False`` if not found.
    """
    cur = conn.execute(
        "DELETE FROM scoring_criteria WHERE id = ?", (criterion_id,)
    )
    conn.commit()
    return cur.rowcount > 0

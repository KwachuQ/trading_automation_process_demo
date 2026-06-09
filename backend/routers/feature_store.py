"""
backend/routers/feature_store.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
REST API for the feature store: full CRUD for market scenarios and
scoring criteria.

Endpoints
---------
Market scenarios
    GET    /api/feature-store/scenarios          List (active only by default)
    POST   /api/feature-store/scenarios          Create a new scenario  → 201
    GET    /api/feature-store/scenarios/{id}     Fetch one scenario
    PUT    /api/feature-store/scenarios/{id}     Update a scenario      → 200
    DELETE /api/feature-store/scenarios/{id}     Delete a scenario      → 204

Scoring criteria
    GET    /api/feature-store/scoring          List (active only by default)
    POST   /api/feature-store/scoring          Create a criterion → 201
    GET    /api/feature-store/scoring/{id}     Fetch one criterion
    PUT    /api/feature-store/scoring/{id}     Update a criterion → 200
    DELETE /api/feature-store/scoring/{id}     Delete a criterion → 204

Validation rules enforced via 422:
    - Market scenario name must be non-empty.
    - Market scenario conditions list must be non-empty.
    - Scoring criterion weight must be > 0 (enforced by Pydantic model).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend.db import get_connection
from backend.feature_store.store import (
    RuleCondition,
    MarketScenario,
    ScoringCriterion,
    delete_market_scenario,
    delete_scoring_criterion,
    get_market_scenario,
    get_market_scenarios,
    get_scoring_criterion,
    get_scoring_criteria,
    get_scoring_criteria_by_setup,
    upsert_market_scenario,
    upsert_scoring_criterion,
)
from backend.state import app_state

router = APIRouter(prefix="/feature-store", tags=["feature-store"])


# ---------------------------------------------------------------------------
# Shared dependency helper — follows the same pattern as ingestion.py
# ---------------------------------------------------------------------------


def _get_conn() -> sqlite3.Connection:
    """Open a fresh SQLite connection from the shared db_path in app_state.

    No in-process caching: every request creates a connection so rule edits
    are visible on the next polling cycle without restarting the app.
    """
    return get_connection(app_state["db_path"])


# ---------------------------------------------------------------------------
# Request / Response Pydantic models
# ---------------------------------------------------------------------------


class MarketScenarioRequest(BaseModel):
    """Payload for creating or updating a market scenario."""

    name: str
    conditions: list[RuleCondition]
    characteristics: str = ""
    risk_adjustments: dict = {}
    is_active: bool = True
    parent_regime: str = ""
    subtype: str = ""

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Reject blank names at request-validation time."""
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("conditions")
    @classmethod
    def conditions_must_not_be_empty(cls, v: list) -> list:
        """At least one condition is required per market scenario."""
        if not v:
            raise ValueError("conditions must contain at least one entry")
        return v


class ScoringCriterionRequest(BaseModel):
    """Payload for creating or updating a scoring criterion."""

    name: str
    condition: RuleCondition
    weight: float
    is_active: bool = True
    setup_type: str | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_empty(cls, v: str) -> str:
        """Reject blank names at request-validation time."""
        if not v.strip():
            raise ValueError("name must not be empty")
        return v.strip()

    @field_validator("weight")
    @classmethod
    def weight_must_be_positive(cls, v: float) -> float:
        """Weight must be strictly greater than zero."""
        if v <= 0:
            raise ValueError("weight must be > 0")
        return v


# ---------------------------------------------------------------------------
# Market scenario endpoints
# ---------------------------------------------------------------------------


@router.get("/scenarios", response_model=list[MarketScenario])
async def list_market_scenarios(
    active_only: bool = True,
) -> list[MarketScenario]:
    """List market scenarios.

    Args:
        active_only: When ``True`` (default) only active scenarios are returned.
    """
    conn = _get_conn()
    try:
        return get_market_scenarios(conn, active_only=active_only)
    finally:
        conn.close()


@router.post("/scenarios", response_model=MarketScenario, status_code=201)
async def create_market_scenario(body: MarketScenarioRequest) -> MarketScenario:
    """Create a new market scenario and return it with its assigned id."""
    conn = _get_conn()
    try:
        scenario = MarketScenario(
            name=body.name,
            conditions=body.conditions,
            characteristics=body.characteristics,
            risk_adjustments=body.risk_adjustments,
            is_active=body.is_active,
            parent_regime=body.parent_regime,
            subtype=body.subtype,
        )
        return upsert_market_scenario(conn, scenario)
    finally:
        conn.close()


@router.get("/scenarios/{rule_id}", response_model=MarketScenario)
async def get_one_market_scenario(rule_id: int) -> MarketScenario:
    """Fetch a single market scenario by id.

    Raises:
        HTTPException: 404 when the id does not exist.
    """
    conn = _get_conn()
    try:
        scenario = get_market_scenario(conn, rule_id)
    finally:
        conn.close()
    if scenario is None:
        raise HTTPException(status_code=404, detail=f"Market scenario {rule_id} not found")
    return scenario


@router.put("/scenarios/{rule_id}", response_model=MarketScenario)
async def update_market_scenario(rule_id: int, body: MarketScenarioRequest) -> MarketScenario:
    """Update an existing market scenario.

    Raises:
        HTTPException: 404 when the id does not exist.
    """
    conn = _get_conn()
    try:
        existing = get_market_scenario(conn, rule_id)
        if existing is None:
            raise HTTPException(
                status_code=404, detail=f"Market scenario {rule_id} not found"
            )
        updated = MarketScenario(
            id=rule_id,
            name=body.name,
            conditions=body.conditions,
            characteristics=body.characteristics,
            risk_adjustments=body.risk_adjustments,
            is_active=body.is_active,
            parent_regime=body.parent_regime,
            subtype=body.subtype,
        )
        return upsert_market_scenario(conn, updated)
    finally:
        conn.close()


@router.delete("/scenarios/{rule_id}", status_code=204)
async def delete_one_market_scenario(rule_id: int) -> None:
    """Delete a market scenario by id.

    Raises:
        HTTPException: 404 when the id does not exist.
    """
    conn = _get_conn()
    try:
        deleted = delete_market_scenario(conn, rule_id)
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(
            status_code=404, detail=f"Market scenario {rule_id} not found"
        )


# ---------------------------------------------------------------------------
# Scoring criterion endpoints
# ---------------------------------------------------------------------------


@router.get("/scoring", response_model=list[ScoringCriterion])
async def list_scoring_criteria(
    active_only: bool = True,
    setup_type: str | None = None,
) -> list[ScoringCriterion]:
    """List scoring criteria.

    Args:
        active_only: When ``True`` (default) only active criteria are returned.
        setup_type: Optional setup type to filter by.
    """
    conn = _get_conn()
    try:
        if setup_type:
            return get_scoring_criteria_by_setup(conn, setup_type, active_only=active_only)
        return get_scoring_criteria(conn, active_only=active_only)
    finally:
        conn.close()


@router.post("/scoring", response_model=ScoringCriterion, status_code=201)
async def create_scoring_criterion(body: ScoringCriterionRequest) -> ScoringCriterion:
    """Create a new scoring criterion and return it with its assigned id."""
    conn = _get_conn()
    try:
        criterion = ScoringCriterion(
            name=body.name,
            condition=body.condition,
            weight=body.weight,
            is_active=body.is_active,
            setup_type=body.setup_type,
        )
        return upsert_scoring_criterion(conn, criterion)
    finally:
        conn.close()


@router.get("/scoring/{criterion_id}", response_model=ScoringCriterion)
async def get_one_scoring_criterion(criterion_id: int) -> ScoringCriterion:
    """Fetch a single scoring criterion by id.

    Raises:
        HTTPException: 404 when the id does not exist.
    """
    conn = _get_conn()
    try:
        criterion = get_scoring_criterion(conn, criterion_id)
    finally:
        conn.close()
    if criterion is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scoring criterion {criterion_id} not found",
        )
    return criterion


@router.put("/scoring/{criterion_id}", response_model=ScoringCriterion)
async def update_scoring_criterion(
    criterion_id: int,
    body: ScoringCriterionRequest,
) -> ScoringCriterion:
    """Update an existing scoring criterion.

    Raises:
        HTTPException: 404 when the id does not exist.
    """
    conn = _get_conn()
    try:
        existing = get_scoring_criterion(conn, criterion_id)
        if existing is None:
            raise HTTPException(
                status_code=404,
                detail=f"Scoring criterion {criterion_id} not found",
            )
        updated = ScoringCriterion(
            id=criterion_id,
            name=body.name,
            condition=body.condition,
            weight=body.weight,
            is_active=body.is_active,
            setup_type=body.setup_type,
        )
        return upsert_scoring_criterion(conn, updated)
    finally:
        conn.close()


@router.delete("/scoring/{criterion_id}", status_code=204)
async def delete_one_scoring_criterion(criterion_id: int) -> None:
    """Delete a scoring criterion by id.

    Raises:
        HTTPException: 404 when the id does not exist.
    """
    conn = _get_conn()
    try:
        deleted = delete_scoring_criterion(conn, criterion_id)
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Scoring criterion {criterion_id} not found",
        )

# backend/feature_store/__init__.py
"""
Feature store package.

Provides Pydantic models and raw-SQLite CRUD functions for market
scenarios and scoring criteria.  No in-process caching — every read
goes straight to the database so scenario changes are visible on the
next polling cycle without restarting the application.

Key exports
-----------
MarketScenario
    Named market sub-regime with weighted indicator conditions and
    classification metadata (parent_regime, subtype).
ScoringCriterion
    Single weighted condition for the 0-100 trade-setup score, optionally
    scoped to a specific setup type (ML, MS, MRL, MRS).
RuleCondition
    Atomic condition used inside both MarketScenario and ScoringCriterion.
"""

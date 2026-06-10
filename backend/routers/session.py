"""
backend/routers/session.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Session API: scenario management + live regime evaluation.

Endpoints
---------
GET    /api/session/scenarios/{session_date}      List saved scenarios
POST   /api/session/scenarios                     Save/overwrite batch
DELETE /api/session/scenarios/{date}/{number}     Delete one scenario
POST   /api/session/evaluate                      Regime + setup score
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.db import get_connection
from backend.feature_store.engine import (
    IndicatorSnapshot,
    ScenarioResult,
    SetupScore,
    evaluate_scenario,
    score_setup,
)
from backend.feature_store.store import get_market_scenarios, get_scoring_criteria_by_setup
from backend.ingestion.sc_parser import SchemaType, get_recent_bars
from backend.ingestion.slope import classify_delta_slope, classify_trend, compute_slope
from backend.ingestion.entry_location import classify_entry_quality
from backend.state import app_state

def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/session", tags=["session"])


# ---------------------------------------------------------------------------
# Scenario models and endpoints (pre-existing)
# ---------------------------------------------------------------------------


class ScenarioIn(BaseModel):
    """Input model for a single trading scenario."""

    scenario_number: int = Field(..., ge=1)
    setup_type: str
    rationale: str
    targets: str
    invalidated_if: str = Field(default="")


class ScenarioOut(ScenarioIn):
    """Output model for a saved trading scenario."""

    id: int
    session_date: str


class ScenariosBatch(BaseModel):
    """Batch payload for saving multiple scenarios at once."""

    session_date: str | None = None
    scenarios: list[ScenarioIn]


@router.get("/scenarios/{session_date}", response_model=list[ScenarioOut])
async def get_scenarios(session_date: str) -> list[ScenarioOut]:
    """Return all saved scenarios for a given session date."""
    conn = app_state["db_conn"]
    rows = conn.execute(
        "SELECT id, session_date, scenario_number, setup_type, rationale, targets, invalidated_if "
        "FROM scenarios WHERE session_date = ? ORDER BY scenario_number",
        (session_date,),
    ).fetchall()
    return [
        ScenarioOut(
            id=r[0],
            session_date=r[1],
            scenario_number=r[2],
            setup_type=r[3],
            rationale=r[4],
            targets=r[5],
            invalidated_if=r[6] or "",
        )
        for r in rows
    ]


@router.post("/scenarios", response_model=list[ScenarioOut])
async def save_scenarios(body: ScenariosBatch) -> list[ScenarioOut]:
    """Overwrite all scenarios for a session date with the supplied batch."""
    session_date = body.session_date or str(date.today())
    conn = app_state["db_conn"]

    conn.execute("DELETE FROM scenarios WHERE session_date = ?", (session_date,))

    for s in body.scenarios:
        conn.execute(
            "INSERT INTO scenarios "
            "(session_date, scenario_number, setup_type, rationale, targets, invalidated_if) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_date, s.scenario_number, s.setup_type, s.rationale, s.targets, s.invalidated_if),
        )
    conn.commit()
    logger.info("Saved %d scenarios for %s", len(body.scenarios), session_date)

    return await get_scenarios(session_date)


@router.delete("/scenarios/{session_date}/{scenario_number}")
async def delete_scenario(session_date: str, scenario_number: int) -> dict:
    """Delete one scenario by session date and scenario number."""
    conn = app_state["db_conn"]
    cur = conn.execute(
        "DELETE FROM scenarios WHERE session_date = ? AND scenario_number = ?",
        (session_date, scenario_number),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Active setup log endpoint
# ---------------------------------------------------------------------------


class ActiveSetupRequest(BaseModel):
    """Payload for marking a pre-market setup as the active trading setup."""

    setup_type: str  # e.g. "ML", "MRL", "MS", "MRS", or "" to clear


@router.get("/active-setup")
async def get_active_setup() -> dict:
    """Return the most recent active setup for today's NY-time session.

    Used by the frontend on mount to re-hydrate ``activeSetupType`` after
    a page navigation causes ``SessionDashboard`` to unmount and lose its
    local state.  The session_date filter uses New York time so it matches
    the timezone used when rows are written by ``mark_active_setup``.

    Returns
    -------
    dict
        ``{"setup_type": str | None}`` — the most recently marked setup
        type, or ``None`` when no active setup has been logged today.
    """
    conn = app_state["db_conn"]
    _ny_tz = ZoneInfo("America/New_York")
    today = datetime.now(_ny_tz).strftime("%Y-%m-%d")
    row = conn.execute(
        "SELECT setup_type FROM active_setup_log "
        "WHERE session_date = ? ORDER BY marked_at DESC, id DESC LIMIT 1",
        (today,),
    ).fetchone()
    return {"setup_type": row[0] if row else None}


@router.post("/active-setup")
async def mark_active_setup(body: ActiveSetupRequest) -> dict:
    """Log the setup the trader is currently trading.

    Inserts a new row into ``active_setup_log`` with the current UTC
    timestamp and today's session date.  Each call appends a new record
    so the full history of setup switches is preserved.  The auto-tagger
    reads the most recent row with ``marked_at <= trade.entry_datetime``
    to derive ``setup_tag`` without any direction-based inference.

    An empty ``setup_type`` is accepted and recorded — it signals that
    the trader has explicitly cleared the active setup.
    """
    conn = app_state["db_conn"]
    # Use New York local time so that marked_at strings are directly
    # comparable to Sierra Chart trade timestamps (also in NY time).
    _ny_tz = ZoneInfo("America/New_York")
    marked_at = datetime.now(_ny_tz).strftime("%Y-%m-%d %H:%M:%S")
    session_date = marked_at[:10]  # derive from NY time, not server date

    conn.execute(
        "INSERT INTO active_setup_log (session_date, setup_type, marked_at) VALUES (?, ?, ?)",
        (session_date, body.setup_type, marked_at),
    )
    conn.commit()

    logger.info(
        "Active setup marked: %s at %s (session %s)",
        body.setup_type or "<cleared>",
        marked_at,
        session_date,
    )
    return {
        "session_date": session_date,
        "setup_type": body.setup_type,
        "marked_at": marked_at,
    }


# ---------------------------------------------------------------------------
# Regime evaluation endpoint
# ---------------------------------------------------------------------------


class EvaluateResponse(BaseModel):
    """Response from POST /session/evaluate."""

    regime: dict


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_session(body: IndicatorSnapshot) -> EvaluateResponse:
    """Evaluate the current market regime and trade-setup score.

    Loads active regime rules and scoring criteria fresh from the database
    on every call — no in-process caching — so rule edits are visible
    immediately without restarting the app.

    Args:
        body: Live ``IndicatorSnapshot`` with all available indicator values.
              Fields that are ``null`` / ``None`` are skipped gracefully
              (the engine treats them as "not available", not as a mismatch).

    Returns:
        Dict with keys ``regime`` (RegimeResult) and ``setup_score``
        (SetupScore), both serialised to plain dicts.
    """
    db_path: str = app_state["db_path"]
    conn = get_connection(db_path)
    rules = get_market_scenarios(conn)
    result: ScenarioResult = evaluate_scenario(body, rules)

    return EvaluateResponse(
        regime=asdict(result),
    )


class LiveSessionResponse(BaseModel):
    """Response from GET /session/live."""
    snapshot: dict
    regime: dict
    setup_scores: list[dict]


@router.get("/live", response_model=LiveSessionResponse)
async def live_session() -> LiveSessionResponse:
    """Read latest data, evaluate regime and trade-setup score."""
    snapshot = IndicatorSnapshot()
    today = str(date.today())
    
    conn = app_state["db_conn"]
    try:
        # DB values: gamma_regime, vol_regime, vvix_vix_ratio, timeframe_context_json
        row = conn.execute(
            "SELECT volatility_json, volatility_indication_json, timeframe_context_json FROM session_data WHERE session_date = ?",
            (today,)
        ).fetchone()
        timeframe_context = {}
        if row:
            if row[0]:
                vol = json.loads(row[0])
                snapshot.vvix_vix_ratio = _to_float(vol.get("ratio"))
            if row[1]:
                vi = json.loads(row[1])
                snapshot.gamma_regime = vi.get("gamma_regime")
                snapshot.vol_regime = vi.get("expectation")
            if len(row) > 2 and row[2]:
                timeframe_context = json.loads(row[2])

        config = app_state["config"]
        sc = config.sierra_chart
        data_dir = sc.data_dir

        # VWAP files -> trends and bands
        vwap_files = {
            "yearly": f"{data_dir}/{sc.yearly_vwap}",
            "quarterly": f"{data_dir}/{sc.quarterly_vwap}",
            "monthly": f"{data_dir}/{sc.monthly_vwap}",
            "weekly": f"{data_dir}/{sc.weekly_vwap}",
        }
        import dataclasses
        timeframe_slope_config = dataclasses.replace(
            config.slope,
            short_window=21,
            long_window=80,
            vol_lookback=80,
        )
        for label, path in vwap_files.items():
            try:
                recent = get_recent_bars(path, SchemaType.VWAP_MULTI, n=100)
                if not recent.empty:
                    latest = recent.iloc[-1]
                    # Trend
                    vwap_series = recent["VWAP"] if "VWAP" in recent.columns else []
                    prev_regime = timeframe_context.get(label, {}).get("trend")
                    trend_res = classify_trend(vwap_series, timeframe_slope_config, prev_regime)
                    setattr(snapshot, f"trend_{label}", trend_res.label)
                    # Band position
                    close = _to_float(latest.get("Close"))
                    upper = _to_float(latest.get("Upper Band 2"))
                    lower = _to_float(latest.get("Lower Band 2"))
                    if close is not None and upper is not None and lower is not None:
                        if close > upper:
                            setattr(snapshot, f"band_position_{label}", "Imbalance up")
                        elif close < lower:
                            setattr(snapshot, f"band_position_{label}", "Imbalance down")
                        else:
                            setattr(snapshot, f"band_position_{label}", "Inside value area")
            except Exception as exc:
                logger.warning("VWAP live error (%s): %s", label, exc)

        # Daily File -> ADR, ADR slope
        try:
            from backend.ingestion.volatility_engine import classify_adr_trend
            daily_path = f"{data_dir}/{sc.daily_adr}"
            daily_recent = get_recent_bars(daily_path, SchemaType.DAILY_ADR, n=10)
            if not daily_recent.empty:
                snapshot.adr = _to_float(daily_recent.iloc[-1].get("ADR"))
                slope_val = compute_slope(daily_recent["ADR"], n_bars=3) if "ADR" in daily_recent.columns else 0.0
                snapshot.adr_slope = classify_adr_trend(slope_val)
        except Exception as exc:
            logger.warning("Daily ADR live error: %s", exc)

        # ETH 750v File -> delta slope, vwap slope, cd_vs_ma
        try:
            eth_path = f"{data_dir}/{sc.eth_750v}"
            eth_recent = get_recent_bars(eth_path, SchemaType.ETH_RTH_VWAP, n=50)
            if not eth_recent.empty:
                latest = eth_recent.iloc[-1]
                cd = _to_float(latest.get("delta_close"))
                cd_ma = _to_float(latest.get("Avg"))
                if cd is not None and cd_ma is not None:
                    snapshot.cd_vs_ma = "above MA" if cd > cd_ma else "below MA"
                
                # Use the dedicated absolute-threshold classifier so zero/
                # negative cd_ma values do not silently collapse to sideways.
                d_series = eth_recent["Avg"] if "Avg" in eth_recent.columns else []
                snapshot.delta_slope = classify_delta_slope(
                    d_series, config.slope_delta, None
                )
                
                v_series = eth_recent["VWAP"] if "VWAP" in eth_recent.columns else []
                snapshot.vwap_slope = classify_trend(v_series, config.slope, None).label
                # Entry location z-score -> entry_quality
                try:
                    eth_vwap = _to_float(latest.get("VWAP"))
                    eth_upper_1 = _to_float(latest.get("Upper Band 2"))
                    if eth_vwap is not None and eth_upper_1 is not None and eth_upper_1 > eth_vwap:
                        # Read latest NQ one-minute last price. Prefer explicit NQ
                        # 1-min file from config; if missing, fall back to the
                        # ETH 750v file's current price (Close/Last) so live UI still
                        # computes an entry_quality when NQ export isn't configured.
                        nq_last = None
                        nq_source = None
                        try:
                            nq_filename = None
                            if getattr(sc, "min_nq", None):
                                nq_filename = sc.min_nq
                            elif getattr(sc, "nq_1min", None):
                                nq_filename = sc.nq_1min
                            if nq_filename:
                                nq_path = f"{data_dir}/{nq_filename}"
                                nq_recent = get_recent_bars(nq_path, SchemaType.ONE_MIN, n=5)
                                if not nq_recent.empty:
                                    nq_last = _to_float(nq_recent.iloc[-1].get("Last"))
                                    nq_source = nq_filename
                        except Exception:
                            nq_last = None
                        # Fallback: use ETH file's Close/Last if NQ not available
                        if nq_last is None:
                            eth_price = _to_float(latest.get("Close") or latest.get("Last"))
                            if eth_price is not None:
                                nq_last = eth_price
                                nq_source = "eth_750v"

                        if nq_last is not None:
                            std_val = eth_upper_1 - eth_vwap
                            z_score = (nq_last - eth_vwap) / std_val if std_val != 0 else None
                            if z_score is not None:
                                # Find most recent active setup as of now
                                try:
                                    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    row2 = conn.execute(
                                        "SELECT setup_type FROM active_setup_log WHERE session_date = ? AND marked_at <= ? ORDER BY marked_at DESC LIMIT 1",
                                        (today, now),
                                    ).fetchone()
                                    setup_type = row2[0] if row2 else ""
                                except Exception:
                                    setup_type = ""

                                # Only classify when an active setup exists; otherwise
                                # leave entry_quality as None to match spec.
                                if setup_type:
                                    label = classify_entry_quality(z_score, setup_type)
                                    snapshot.entry_quality = label
                                    logger.debug(
                                        "Computed entry_quality z=%.3f -> %s (setup=%s, price_src=%s)",
                                        z_score,
                                        label,
                                        setup_type,
                                        nq_source,
                                    )
                except Exception as exc:
                    logger.warning("Entry location compute error: %s", exc)
        except Exception as exc:
            logger.warning("ETH 750v live error: %s", exc)

        # RVOL 30-min File -> RVOL, RVOL slope
        try:
            rvol_path = f"{data_dir}/{sc.rvol_30min}"
            rvol_recent = get_recent_bars(rvol_path, SchemaType.RVOL_30MIN, n=50)
            if not rvol_recent.empty:
                snapshot.rvol = _to_float(rvol_recent.iloc[-1].get("Cumulative Volume Ratio"))
                r_series = rvol_recent["Cumulative Volume Ratio"] if "Cumulative Volume Ratio" in rvol_recent.columns else []
                snapshot.rvol_slope = classify_trend(r_series, config.slope_rvol, None).label
        except Exception as exc:
            logger.warning("RVOL live error: %s", exc)

    finally:
        pass # app_state['db_conn'] is managed externally

    # Evaluate using the constructed snapshot
    eval_resp = await evaluate_session(snapshot)
    
    conn = app_state["db_conn"]
    setups = conn.execute(
        "SELECT scenario_number, setup_type, rationale FROM scenarios WHERE session_date = ? ORDER BY scenario_number",
        (today,)
    ).fetchall()
    
    setup_scores = []
    # Instantiate the active scenario from the dict response
    from backend.feature_store.engine import ScenarioResult
    active_scenario = ScenarioResult(**eval_resp.regime)
    
    for row in setups:
        s_num = row[0]
        s_type = row[1]
        rationale = row[2]
        
        criteria = get_scoring_criteria_by_setup(conn, s_type, active_only=True)
        score_res = score_setup(snapshot, criteria, active_scenario)
        
        setup_scores.append({
            "setup_type": s_type,
            "scenario_number": s_num,
            "rationale": rationale,
            "score": score_res.total_score,
            "breakdown": score_res.breakdown,
        })

    # -----------------------------------------------------------------------
    # Persist snapshot to session_snapshots for the auto-tagger
    # -----------------------------------------------------------------------
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Serialize the key indicator fields the auto-tagger extracts
        indicators_dict = {
            "gamma_regime": snapshot.gamma_regime,
            "cd_vs_ma": snapshot.cd_vs_ma,
            "delta_slope": snapshot.delta_slope,
            "vwap_slope": snapshot.vwap_slope,
            "vol_regime": snapshot.vol_regime,
            "entry_quality": snapshot.entry_quality,
        }
        indicators_json = json.dumps(indicators_dict)

        # Determine which setup score to store:
        # 1. Prefer the score matching the currently active setup
        # 2. Fall back to the highest-scoring setup
        chosen_score = 0.0
        chosen_breakdown: list[dict] = []

        if setup_scores:
            # Look up active setup from active_setup_log
            active_setup_row = conn.execute(
                "SELECT setup_type FROM active_setup_log "
                "WHERE session_date = ? AND marked_at <= ? "
                "ORDER BY marked_at DESC LIMIT 1",
                (today, now_str),
            ).fetchone()
            active_setup_type = active_setup_row[0] if active_setup_row else None

            # Try to match the active setup's score entry
            matched_entry = None
            if active_setup_type:
                matched_entry = next(
                    (s for s in setup_scores if s["setup_type"] == active_setup_type),
                    None,
                )

            if matched_entry:
                chosen_score = matched_entry["score"]
                chosen_breakdown = matched_entry["breakdown"]
            else:
                # Fall back to the highest score
                best = max(setup_scores, key=lambda s: s["score"])
                chosen_score = best["score"]
                chosen_breakdown = best["breakdown"]

        # Convert breakdown to the format auto-tagger expects:
        # list of {"name": str, "matched": bool}
        score_breakdown = [
            {
                "name": b.get("criterion_name", ""),
                "matched": b.get("matched", False),
                "weight": b.get("weighted_contribution", 0.0),
            }
            for b in chosen_breakdown
        ]

        regime_name = eval_resp.regime.get("scenario_name", "")
        regime_confidence = eval_resp.regime.get("confidence", 0.0)

        conn.execute(
            """
            INSERT INTO session_snapshots (
                session_date, snapshot_time, indicators_json,
                regime_name, regime_confidence,
                setup_score, score_breakdown_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                today,
                now_str,
                indicators_json,
                regime_name,
                regime_confidence,
                chosen_score,
                json.dumps(score_breakdown),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.error("Failed to persist session snapshot: %s", exc, exc_info=True)

    return LiveSessionResponse(
        snapshot=asdict(snapshot),
        regime=eval_resp.regime,
        setup_scores=setup_scores,
    )

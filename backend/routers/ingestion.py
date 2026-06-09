from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from backend.db import get_connection
from backend.ingestion.economic_calendar import CalendarFetchError, fetch_economic_calendar
from backend.ingestion.menthorq_parser import parse_menthorq_string, split_combined_menthorq
from backend.ingestion.volatility_engine import compute_volatility_indication
from backend.ingestion.overnight_analysis import enrich_overnight_assessment
from backend.ingestion.qqq_nq_converter import compute_ratio, convert_levels
from backend.ingestion.sc_parser import (
    SchemaType,
    get_latest_bar,
    get_recent_bars,
    parse_sc_file,
)
from backend.ingestion.slope import classify_trend, compute_slope
from backend.ingestion.volatility import VolatilityFetchError, fetch_vvix_vix
from backend.state import app_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _to_float(val: Any) -> float | None:
    """Convert numpy/pandas scalar to Python float, or None if absent."""
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None

_MENTHORQ_REQUIRED_KEYS = frozenset({
    "call_resistance",
    "put_support",
    "call_resistance_0dte",
    "put_support_0dte",
    "hvl",
    "hvl_0dte",
    "exp_move_max",
    "exp_move_min",
})

_GAMMA_REQUIRED_KEYS = frozenset({"regime"})
_GAMMA_REGIME_VALUES = {"positive", "negative"}


class ManualInputRequest(BaseModel):
    input_type: Literal["menthorq_nq", "menthorq_qqq", "gamma", "gamma_nq", "gamma_qqq"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def validate_data_keys(self) -> "ManualInputRequest":
        if self.input_type in ("menthorq_nq", "menthorq_qqq"):
            missing = _MENTHORQ_REQUIRED_KEYS - self.data.keys()
            if missing:
                raise ValueError(f"Missing required fields for {self.input_type}: {sorted(missing)}")
        elif self.input_type in ("gamma", "gamma_nq", "gamma_qqq"):
            if "regime" not in self.data:
                raise ValueError(f"Missing required field 'regime' for {self.input_type} input_type")
            if self.data["regime"] not in _GAMMA_REGIME_VALUES:
                raise ValueError("gamma.regime must be 'positive' or 'negative'")
        return self


class ManualInputResponse(BaseModel):
    id: int
    session_date: str
    input_type: str
    data_json: str
    created_at: str


def _row_to_manual_input(row: tuple) -> ManualInputResponse:
    return ManualInputResponse(
        id=row[0],
        session_date=row[1],
        input_type=row[2],
        data_json=row[3],
        created_at=row[4],
    )


def _get_conn() -> sqlite3.Connection:
    db_path: str = app_state["db_path"]
    return get_connection(db_path)


@router.get("/")
async def ingestion_root() -> dict:
    return {"status": "not_implemented"}


# ---------------------------------------------------------------------------
# String-based MenthorQ input endpoint
# ---------------------------------------------------------------------------

class ManualStringRequest(BaseModel):
    combined_string: str | None = None
    nq_string: str | None = None
    qqq_string: str | None = None

    @model_validator(mode="after")
    def _require_strings(self) -> "ManualStringRequest":
        if self.combined_string is None and (self.nq_string is None or self.qqq_string is None):
            raise ValueError(
                "Provide either 'combined_string' or both 'nq_string' and 'qqq_string'"
            )
        return self


class ManualStringResponse(BaseModel):
    nq: ManualInputResponse
    qqq: ManualInputResponse


@router.post("/manual-string", status_code=201, response_model=ManualStringResponse)
async def create_manual_input_from_string(body: ManualStringRequest) -> ManualStringResponse:
    today = date.today().isoformat()

    if body.combined_string is not None:
        try:
            nq_raw, qqq_raw = split_combined_menthorq(body.combined_string)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid combined string: {exc}") from exc
    else:
        nq_raw = body.nq_string  # type: ignore[assignment]
        qqq_raw = body.qqq_string  # type: ignore[assignment]

    try:
        nq_data = parse_menthorq_string(nq_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid NQ string: {exc}") from exc

    try:
        qqq_data = parse_menthorq_string(qqq_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid QQQ string: {exc}") from exc

    conn = _get_conn()
    try:
        for input_type, data in (("menthorq_nq", nq_data), ("menthorq_qqq", qqq_data)):
            conn.execute(
                """
                INSERT OR REPLACE INTO manual_inputs (session_date, input_type, data_json)
                VALUES (?, ?, ?)
                """,
                (today, input_type, json.dumps(data)),
            )
        conn.commit()

        rows = {}
        for input_type in ("menthorq_nq", "menthorq_qqq"):
            row = conn.execute(
                "SELECT id, session_date, input_type, data_json, created_at "
                "FROM manual_inputs WHERE session_date = ? AND input_type = ?",
                (today, input_type),
            ).fetchone()
            rows[input_type] = row
    finally:
        conn.close()

    return ManualStringResponse(
        nq=_row_to_manual_input(rows["menthorq_nq"]),
        qqq=_row_to_manual_input(rows["menthorq_qqq"]),
    )


@router.post("/manual", status_code=201, response_model=ManualInputResponse)
async def create_manual_input(body: ManualInputRequest) -> ManualInputResponse:
    today = date.today().isoformat()
    data_json = json.dumps(body.data)

    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO manual_inputs (session_date, input_type, data_json)
            VALUES (?, ?, ?)
            """,
            (today, body.input_type, data_json),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, session_date, input_type, data_json, created_at "
            "FROM manual_inputs WHERE session_date = ? AND input_type = ?",
            (today, body.input_type),
        ).fetchone()
    finally:
        conn.close()

    return _row_to_manual_input(row)


# ---------------------------------------------------------------------------
# Orchestration endpoint
# ---------------------------------------------------------------------------

class IngestionSectionStatus(BaseModel):
    name: str
    success: bool
    error: str | None = None


class IngestionRunResponse(BaseModel):
    session_date: str
    sections: list[IngestionSectionStatus]


@router.post("/run", response_model=IngestionRunResponse)
async def run_ingestion(session_date: str | None = None) -> IngestionRunResponse:
    today = session_date or date.today().isoformat()
    config = app_state["config"]
    sc = config.sierra_chart
    data_dir = sc.data_dir

    sections: list[IngestionSectionStatus] = []

    # Load previous timeframe regimes for hysteresis (best-effort)
    prev_regimes: dict[str, str | None] = {}
    conn_prev = _get_conn()
    try:
        prev_row = conn_prev.execute(
            "SELECT timeframe_context_json FROM session_data "
            "WHERE session_date < ? ORDER BY session_date DESC LIMIT 1",
            (today,),
        ).fetchone()
        if prev_row and prev_row[0]:
            prev_ctx = json.loads(prev_row[0])
            for tf in ("yearly", "quarterly", "monthly", "weekly"):
                prev_regimes[tf] = prev_ctx.get(tf, {}).get("trend")
    except Exception:
        pass
    finally:
        conn_prev.close()

    # (a) VWAP SC files — timeframe context
    timeframe_context_json: str | None = None
    try:
        vwap_files = {
            "yearly": f"{data_dir}/{sc.yearly_vwap}",
            "quarterly": f"{data_dir}/{sc.quarterly_vwap}",
            "monthly": f"{data_dir}/{sc.monthly_vwap}",
            "weekly": f"{data_dir}/{sc.weekly_vwap}",
        }
        timeframe_context: dict[str, Any] = {}
        import dataclasses
        timeframe_slope_config = dataclasses.replace(
            config.slope,
            short_window=21,
            long_window=80,
            vol_lookback=80,
        )
        for label, path in vwap_files.items():
            recent = get_recent_bars(path, SchemaType.VWAP_MULTI, n=100)
            latest = recent.iloc[-1]

            # Dual-window trend classification with hysteresis
            trend_result = classify_trend(
                recent["VWAP"] if "VWAP" in recent.columns else [],
                timeframe_slope_config,
                prev_regimes.get(label),
            )

            # Band position relative to ±1σ bands
            close = _to_float(latest.get("Close"))
            upper = _to_float(latest.get("Upper Band 2"))
            lower = _to_float(latest.get("Lower Band 2"))
            if close is not None and upper is not None and lower is not None:
                if close > upper:
                    band_position: str | None = "imbalance_up"
                elif close < lower:
                    band_position = "imbalance_down"
                else:
                    band_position = "inside_value"
            else:
                band_position = None

            timeframe_context[label] = {
                "uvwap": _to_float(latest.get("Upper Band 2")),
                "lvwap": _to_float(latest.get("Lower Band 2")),
                "vwap_slope": compute_slope(recent["VWAP"]) if "VWAP" in recent.columns else None,
                "last": _to_float(latest.get("Close")),
                "trend": trend_result.label,
                "short_score": trend_result.short_score,
                "long_score": trend_result.long_score,
                "band_position": band_position,
            }
        timeframe_context_json = json.dumps(timeframe_context)
        sections.append(IngestionSectionStatus(name="timeframe_context", success=True))
    except Exception as exc:
        logger.warning("timeframe_context step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="timeframe_context", success=False, error=str(exc)))

    # (b) Daily ADR file + ETH 750v — overnight info
    overnight_json: str | None = None
    try:
        overnight: dict[str, Any] = {}

        # Daily #8: last row is yesterday's completed bar during pre-market
        daily_path = f"{data_dir}/{sc.daily_adr}"
        last_bar = get_latest_bar(daily_path, SchemaType.DAILY_ADR)
        overnight["dvma"] = last_bar.get("Avg")
        overnight["adr"] = last_bar.get("ADR")

        # Slopes from completed bars (all rows are completed during pre-market)
        # n_bars=3: 3-day lookback is more reactive for daily ADR/DVMA which change slowly
        daily_recent = get_recent_bars(daily_path, SchemaType.DAILY_ADR, n=10)
        overnight["dvma_slope"] = compute_slope(daily_recent["Avg"], n_bars=3) if "Avg" in daily_recent.columns else None
        overnight["adr_slope"] = compute_slope(daily_recent["ADR"], n_bars=3) if "ADR" in daily_recent.columns else None

        # ETH 750v #4: latest bar + slope
        eth_path = f"{data_dir}/{sc.eth_750v}"
        eth_recent = get_recent_bars(eth_path, SchemaType.ETH_RTH_VWAP, n=50)
        eth_latest = eth_recent.iloc[-1]
        overnight["eth_upper_1"] = _to_float(eth_latest.get("Upper Band 2"))
        overnight["eth_lower_1"] = _to_float(eth_latest.get("Lower Band 2"))
        overnight["eth_vwap_slope"] = compute_slope(eth_recent["VWAP"]) if "VWAP" in eth_recent.columns else None
        overnight["cumulative_delta"] = _to_float(eth_latest.get("delta_close"))
        overnight["cd_ma"] = _to_float(eth_latest.get("Avg"))
        overnight["cd_ma_slope"] = compute_slope(eth_recent["Avg"]) if "Avg" in eth_recent.columns else None

        # Full ETH file for session-window range computation
        eth_full = parse_sc_file(eth_path, SchemaType.ETH_RTH_VWAP)

        # RVOL 30-min file: Cumulative Volume Ratio → rvol
        rvol_path = f"{data_dir}/{sc.rvol_30min}"
        rvol_recent = get_recent_bars(rvol_path, SchemaType.RVOL_30MIN, n=50)
        rvol_latest = rvol_recent.iloc[-1] if not rvol_recent.empty else None
        overnight["rvol"] = _to_float(rvol_latest.get("Cumulative Volume Ratio")) if rvol_latest is not None else None
        overnight["rvol_slope"] = (
            compute_slope(rvol_recent["Cumulative Volume Ratio"])
            if rvol_latest is not None and "Cumulative Volume Ratio" in rvol_recent.columns
            else None
        )

        overnight = enrich_overnight_assessment(
            overnight, eth_full, daily_recent,
            session_date=date.fromisoformat(today),
        )
        overnight_json = json.dumps(overnight)
        sections.append(IngestionSectionStatus(name="overnight", success=True))
    except Exception as exc:
        logger.warning("overnight step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="overnight", success=False, error=str(exc)))

    # (c) QQQ-NQ ratio
    qqq_nq_ratio: float | None = None
    nq_last_price: float | None = None
    try:
        result = compute_ratio(
            f"{data_dir}/{sc.nq_1min}",
            f"{data_dir}/{sc.qqq_1min}",
        )
        qqq_nq_ratio = result.ratio
        nq_last_price = result.nq_price
        sections.append(IngestionSectionStatus(name="qqq_nq_ratio", success=True))
    except Exception as exc:
        logger.warning("qqq_nq_ratio step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="qqq_nq_ratio", success=False, error=str(exc)))

    # (c2) QQQ levels → NQ equivalents
    levels_json: str | None = None
    try:
        if qqq_nq_ratio is not None:
            conn_levels = _get_conn()
            try:
                qqq_row = conn_levels.execute(
                    "SELECT data_json FROM manual_inputs "
                    "WHERE session_date = ? AND input_type = 'menthorq_qqq'",
                    (today,),
                ).fetchone()
            finally:
                conn_levels.close()

            if qqq_row is not None:
                qqq_original: dict[str, float] = {
                    k: v for k, v in json.loads(qqq_row[0]).items()
                    if isinstance(v, (int, float))
                }
                qqq_as_nq = convert_levels(qqq_original, qqq_nq_ratio)
                levels_json = json.dumps({
                    "qqq_original": qqq_original,
                    "qqq_as_nq": qqq_as_nq,
                })
        sections.append(IngestionSectionStatus(name="levels", success=True))
    except Exception as exc:
        logger.warning("levels step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="levels", success=False, error=str(exc)))

    # (d) Volatility
    volatility_json: str | None = None
    try:
        vol = fetch_vvix_vix(config)
        volatility_json = json.dumps(asdict(vol))
        sections.append(IngestionSectionStatus(name="volatility", success=True))
    except VolatilityFetchError as exc:
        logger.warning("volatility step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="volatility", success=False, error=exc.message))
    except Exception as exc:
        logger.warning("volatility step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="volatility", success=False, error=str(exc)))

    # (e) Economic calendar
    calendar_json: str | None = None
    try:
        events = fetch_economic_calendar(config)
        calendar_json = json.dumps([asdict(e) for e in events])
        sections.append(IngestionSectionStatus(name="calendar", success=True))
    except CalendarFetchError as exc:
        logger.warning("calendar step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="calendar", success=False, error=exc.diagnostic))
    except Exception as exc:
        logger.warning("calendar step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="calendar", success=False, error=str(exc)))

    # (f) Volatility indication engine
    volatility_indication_json: str | None = None
    try:
        # Inputs: adr_slope from overnight_json, rvol from overnight_json,
        # gamma from manual_inputs (gamma_nq preferred, fallback to gamma)
        _overnight = json.loads(overnight_json) if overnight_json else {}
        _adr_slope = _overnight.get("adr_slope")
        _rvol = _overnight.get("rvol")
        _dvma_slope = _overnight.get("dvma_slope")

        # Read gamma regime from manual_inputs (NQ + QQQ, compute "mixed" if they differ)
        conn_gamma = _get_conn()
        try:
            gamma_rows = conn_gamma.execute(
                "SELECT input_type, data_json FROM manual_inputs "
                "WHERE session_date = ? AND input_type IN ('gamma_nq', 'gamma_qqq', 'gamma')",
                (today,),
            ).fetchall()
        finally:
            conn_gamma.close()

        _gamma_map: dict[str, str] = {}
        for row in gamma_rows:
            regime_val = json.loads(row[1]).get("regime")
            if regime_val is not None:
                _gamma_map[row[0]] = regime_val.lower()

        _gamma_nq = _gamma_map.get("gamma_nq") or _gamma_map.get("gamma")
        _gamma_qqq = _gamma_map.get("gamma_qqq")

        _gamma: str | None
        if _gamma_nq is not None and _gamma_qqq is not None:
            _gamma = "mixed" if _gamma_nq != _gamma_qqq else _gamma_nq
        elif _gamma_nq is not None:
            _gamma = _gamma_nq
        else:
            _gamma = None

        if _adr_slope is not None and _rvol is not None and _gamma is not None:
            indication = compute_volatility_indication(
                _adr_slope, _rvol, _gamma, dvma_slope=_dvma_slope if _dvma_slope is not None else 0.0
            )
            volatility_indication_json = json.dumps({
                "adr_trend": indication.adr_trend,
                "rvol_level": indication.rvol_level,
                "gamma_regime": indication.gamma_regime,
                "dvma_trend": indication.dvma_trend,
                "score": indication.score,
                "expectation": indication.expectation,
                "description": indication.description,
                "rvol": _rvol,
                "adr": _overnight.get("adr"),
            })
        sections.append(IngestionSectionStatus(name="volatility_indication", success=True))
    except Exception as exc:
        logger.warning("volatility_indication step failed: %s", exc)
        sections.append(IngestionSectionStatus(name="volatility_indication", success=False, error=str(exc)))

    # Single upsert after all steps
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO session_data
                (session_date, timeframe_context_json, overnight_json,
                 qqq_nq_ratio, volatility_json, calendar_json, levels_json,
                 volatility_indication_json, nq_last_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (today, timeframe_context_json, overnight_json,
             qqq_nq_ratio, volatility_json, calendar_json, levels_json,
             volatility_indication_json, nq_last_price),
        )
        conn.commit()
    finally:
        conn.close()

    return IngestionRunResponse(session_date=today, sections=sections)


# ---------------------------------------------------------------------------
# Session levels endpoint (read-only, for Important Levels UI)
# ---------------------------------------------------------------------------

class SessionLevelsResponse(BaseModel):
    session_date: str
    nq_levels: dict[str, Any] | None = None
    qqq_levels: dict[str, Any] | None = None
    qqq_as_nq: dict[str, Any] | None = None


@router.get("/session-levels", response_model=SessionLevelsResponse)
async def get_session_levels(session_date: str | None = None) -> SessionLevelsResponse:
    today = session_date or date.today().isoformat()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT levels_json FROM session_data WHERE session_date = ?",
            (today,),
        ).fetchone()
        levels = json.loads(row[0]) if row and row[0] else None

        nq_row = conn.execute(
            "SELECT data_json FROM manual_inputs "
            "WHERE session_date = ? AND input_type = 'menthorq_nq'",
            (today,),
        ).fetchone()
        qqq_row = conn.execute(
            "SELECT data_json FROM manual_inputs "
            "WHERE session_date = ? AND input_type = 'menthorq_qqq'",
            (today,),
        ).fetchone()
    finally:
        conn.close()

    return SessionLevelsResponse(
        session_date=today,
        nq_levels=json.loads(nq_row[0]) if nq_row else None,
        qqq_levels=json.loads(qqq_row[0]) if qqq_row else None,
        qqq_as_nq=levels.get("qqq_as_nq") if levels else None,
    )

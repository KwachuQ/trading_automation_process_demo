from __future__ import annotations

import tomllib
from dataclasses import dataclass
from typing import Any
from pathlib import Path

from backend.ingestion.slope import DeltaSlopeConfig, SlopeConfig


@dataclass(frozen=True)
class SierraChartConfig:
    data_dir: str
    nq_1min: str
    rth_500v: str
    eth_750v: str
    quarterly_vwap: str
    monthly_vwap: str
    weekly_vwap: str
    daily_adr: str
    yearly_vwap: str
    qqq_1min: str
    rvol_30min: str
    saved_trade_activity_dir: str = "data"
    trades_list_file: str = "TradesList.txt"


@dataclass(frozen=True)
class VolatilityConfig:
    tickers: tuple[str, ...]
    ratio_thresholds: tuple[float, ...]


@dataclass(frozen=True)
class CalendarConfig:
    rapiapi_host: str
    rapiapi_url: str
    impact_labels: tuple[str, ...]
    watchlist: tuple[str, ...]


@dataclass(frozen=True)
class ReportConfig:
    output_dir: str


@dataclass(frozen=True)
class ScalingThreshold:
    equity: float
    contracts: int


@dataclass(frozen=True)
class ScalingConfig:
    thresholds: tuple[ScalingThreshold, ...]


@dataclass(frozen=True)
class PollerConfig:
    interval_seconds: int


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    file: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class Config:
    sierra_chart: SierraChartConfig
    volatility: VolatilityConfig
    calendar: CalendarConfig
    report: ReportConfig
    scaling: ScalingConfig
    poller: PollerConfig
    server: ServerConfig
    logging: LoggingConfig
    slope: SlopeConfig
    # Dedicated config for the cumulative-delta slope — uses absolute
    # thresholds on the raw Theil-Sen slope so zero/negative delta values
    # are handled correctly (log-transform path would always return sideways).
    slope_delta: DeltaSlopeConfig
    # Dedicated config for the RVOL slope
    slope_rvol: SlopeConfig


_REQUIRED_SIERRA_CHART_KEYS = (
    "data_dir", "nq_1min", "rth_500v", "eth_750v", "quarterly_vwap",
    "monthly_vwap", "weekly_vwap", "daily_adr", "yearly_vwap", "qqq_1min",
    "rvol_30min",
)


def _require(section: dict[str, Any], key: str, section_name: str) -> Any:
    if key not in section:
        raise ValueError(f"Missing required config key: [{section_name}].{key}")
    return section[key]


def load_config(path: str) -> Config:
    p = Path(path)
    if not p.exists():
        fallback = p.parent / "config.example.toml"
        if fallback.exists():
            p = fallback
        else:
            raise FileNotFoundError(f"Config file not found: {path}")

    with open(p, "rb") as f:
        raw = tomllib.load(f)

    # Provide a sensible default for report output directory when the
    # section is missing so the demo can run with minimal config files.
    if "report" not in raw:
        raw["report"] = {"output_dir": "reports"}

    for section in (
        "sierra_chart", "volatility", "calendar", "report"
    ):
        if section not in raw:
            raise ValueError(f"Missing required config section: [{section}] in {p}")

    sc_raw = raw["sierra_chart"]
    for key in _REQUIRED_SIERRA_CHART_KEYS:
        _require(sc_raw, key, "sierra_chart")
    sierra_chart = SierraChartConfig(
        data_dir=sc_raw["data_dir"],
        nq_1min=sc_raw["nq_1min"],
        rth_500v=sc_raw["rth_500v"],
        eth_750v=sc_raw["eth_750v"],
        quarterly_vwap=sc_raw["quarterly_vwap"],
        monthly_vwap=sc_raw["monthly_vwap"],
        weekly_vwap=sc_raw["weekly_vwap"],
        daily_adr=sc_raw["daily_adr"],
        yearly_vwap=sc_raw["yearly_vwap"],
        qqq_1min=sc_raw["qqq_1min"],
        rvol_30min=sc_raw["rvol_30min"],
        saved_trade_activity_dir=sc_raw.get("saved_trade_activity_dir", "data"),
        trades_list_file=sc_raw.get("trades_list_file", "TradesList.txt"),
    )

    vol_raw = raw["volatility"]
    _require(vol_raw, "tickers", "volatility")
    _require(vol_raw, "ratio_thresholds", "volatility")
    if len(vol_raw["ratio_thresholds"]) != 2:
        raise ValueError("[volatility].ratio_thresholds must have exactly 2 values (low, high)")
    volatility = VolatilityConfig(
        tickers=tuple(vol_raw["tickers"]),
        ratio_thresholds=tuple(float(v) for v in vol_raw["ratio_thresholds"]),
    )

    cal_raw = raw["calendar"]
    for key in ("rapiapi_host", "rapiapi_url", "impact_labels", "watchlist"):
        _require(cal_raw, key, "calendar")
    calendar = CalendarConfig(
        rapiapi_host=cal_raw["rapiapi_host"],
        rapiapi_url=cal_raw["rapiapi_url"],
        impact_labels=tuple(cal_raw["impact_labels"]),
        watchlist=tuple(cal_raw["watchlist"]),
    )

    rpt_raw = raw["report"]
    _require(rpt_raw, "output_dir", "report")
    report = ReportConfig(output_dir=rpt_raw["output_dir"])

    scl_raw = raw["scaling"]
    _require(scl_raw, "thresholds", "scaling")
    scaling = ScalingConfig(
        thresholds=tuple(
            ScalingThreshold(equity=float(t["equity"]), contracts=int(t["contracts"]))
            for t in scl_raw["thresholds"]
        )
    )

    pol_raw = raw["poller"]
    _require(pol_raw, "interval_seconds", "poller")
    poller = PollerConfig(interval_seconds=int(pol_raw["interval_seconds"]))

    srv_raw = raw["server"]
    for key in ("host", "port"):
        _require(srv_raw, key, "server")
    server = ServerConfig(host=srv_raw["host"], port=int(srv_raw["port"]))

    log_raw = raw["logging"]
    for key in ("level", "file", "max_bytes", "backup_count"):
        _require(log_raw, key, "logging")
    logging_cfg = LoggingConfig(
        level=log_raw["level"],
        file=log_raw["file"],
        max_bytes=int(log_raw["max_bytes"]),
        backup_count=int(log_raw["backup_count"]),
    )

    slope_raw = raw["slope"]
    slope_cfg = SlopeConfig(
        short_window=int(slope_raw.get("short_window", 8)),
        long_window=int(slope_raw.get("long_window", 21)),
        vol_lookback=int(slope_raw.get("vol_lookback", 21)),
        persistence_bars=int(slope_raw.get("persistence_bars", 2)),
        entry_threshold=float(slope_raw.get("entry_threshold", 1.0)),
        exit_threshold=float(slope_raw.get("exit_threshold", 0.4)),
    )

    # Dedicated delta-slope config — falls back to sensible defaults when the
    # [slope_delta] section is absent so old config files keep working.
    delta_raw = raw.get("slope_delta", {})
    slope_delta_cfg = DeltaSlopeConfig(
        n_bars=int(delta_raw.get("n_bars", 8)),
        entry_threshold=float(delta_raw.get("entry_threshold", 0.003)),
        exit_threshold=float(delta_raw.get("exit_threshold", 0.001)),
    )

    # Dedicated config for RVOL slope — inherits standard slope settings
    # for windows/lookback/persistence but overrides the entry/exit thresholds.
    rvol_raw = raw.get("slope_rvol", {})
    slope_rvol_cfg = SlopeConfig(
        short_window=int(rvol_raw.get("short_window", slope_cfg.short_window)),
        long_window=int(rvol_raw.get("long_window", slope_cfg.long_window)),
        vol_lookback=int(rvol_raw.get("vol_lookback", slope_cfg.vol_lookback)),
        persistence_bars=int(rvol_raw.get("persistence_bars", slope_cfg.persistence_bars)),
        entry_threshold=float(rvol_raw.get("entry_threshold", 0.2)),
        exit_threshold=float(rvol_raw.get("exit_threshold", 0.05)),
    )

    return Config(
        sierra_chart=sierra_chart,
        volatility=volatility,
        calendar=calendar,
        report=report,
        scaling=scaling,
        poller=poller,
        server=server,
        logging=logging_cfg,
        slope=slope_cfg,
        slope_delta=slope_delta_cfg,
        slope_rvol=slope_rvol_cfg,
    )

# Requirements

## Overview

A local automation system for an intraday Micro E-mini NQ Futures trader that replaces manual preparation, session monitoring, and post-session review workflows. The system ingests data from Sierra Chart exports, external sources, and manual inputs, then generates pre-market reports, provides a live session dashboard with market regime classification and trade setup scoring, and automates trade tagging and review integration.

## Problem Statement

The trader manually executes a multi-phase workflow (preparation → session monitoring → review) described across Notion pages, spreadsheets, and mental checklists. This manual process is slow, prone to skipped steps, and lacks real-time context during live sessions. Market regime characteristics and trade setup quality are assessed intuitively rather than scored systematically, reducing decision consistency. Trade tagging after sessions is tedious and often incomplete.

## Users

Primary: single retail trader running the system locally on a Windows machine. No secondary users.

## Functional Requirements

### Data Ingestion

FR-01: Parse Sierra Chart `.txt` export files from `C:/SierraChart/Data/`. Each file has a fixed header row. Column schemas by chart type:
- Multi-timeframe VWAP charts (Quarterly `#5`, Monthly `#6`, Weekly `#7`, Yearly `#10`): `Date, Time, Open, High, Low, Last, Volume, [# of Trades | OpenInt], OHLC Avg, HLC Avg, HL Avg, Bid Volume, Ask Volume, Point of Control, Value Area High Value, Value Area Low Value, Volume Weighted Average Price, ECIVwap, VWAP ±2σ/±3σ/±4σ top and bottom bands, Vwap extension, Top/Bottom band 2 extension, High, Low` (Yearly `#10` additionally includes `Difference, Avg`).
- Daily volume/ADR chart (`#8`): `Date, Time, Open, High, Low, Last, Volume, OpenInt, OHLC Avg, HLC Avg, HL Avg, Bid Volume, Ask Volume, Volume, Avg, ADR`.
- 1-minute charts (NQ `#1`, QQQ `#12`): `Date, Time, Open, High, Low, Last, Volume, # of Trades, OHLC Avg, HLC Avg, HL Avg, Bid Volume, Ask Volume`.
- ETH 750-vol VWAP (`#4`) and RTH 500-vol VWAP (`#3`): column schema to be confirmed from file headers when Sierra Chart is actively exporting.

FR-02: All Sierra Chart export file paths are configurable via the config file. Default paths (all under `C:/SierraChart/Data/`):
- Yearly VWAP: `NQM26 [CBV][M]  Daily #10_GraphData.txt`
- Quarterly VWAP: `NQM26 [CBV][M]  60000 Volume #5_GraphData.txt`
- Monthly VWAP: `NQM26 [CBV][M]  37500 Volume #6_GraphData.txt`
- Weekly: `NQM26 [CBV][M]  4500 Volume #7_GraphData.txt`
- Daily volume/ADR: `NQM26 [CBV][M]  Daily #8_GraphData.txt`
- ETH 750-vol VWAP: `NQM26 [CV][M]  750 Volume #4_GraphData.txt`
- RTH 500-vol VWAP: `NQM26[M]  500 Volume #3_GraphData.txt`
- NQ 1-min: `NQM26[M]  1 Min  #1_GraphData.txt`
- QQQ 1-min: `QQQ[M]  1 Min  #12_GraphData.txt`

FR-03: Fetch economic calendar data from the Trading Economics API and extract current day's events with time, event name, actual/forecast/previous values.

FR-04: Provide manual input forms for MenthorQ options levels: call resistance, put support, call resistance 0DTE, put support 0DTE, HVL, HVL 0DTE, 1D expected move max/min — for both NQ and QQQ.

FR-05: Provide a manual input form for gamma regime (positive/negative) and daily exp move for NQ/QQQ. Daily volume moving average (`Avg` column) and ADR are read automatically from `NQM26 [CBV][M]  Daily #8_GraphData.txt`; RVOL trend (rising/falling/sideways) is derived from that file — no manual input required for these values.

FR-06: Compute the QQQ-to-NQ conversion ratio by aligning the most recent common timestamp between `NQM26[M]  1 Min  #1_GraphData.txt` and `QQQ[M]  1 Min  #12_GraphData.txt`. Because QQQ quotes are delayed, the ratio uses the latest bar where both files have data, not the live NQ price.

FR-07: Fetch VVIX and VIX quotes from Yahoo Finance via `yfinance` and compute the VVIX/VIX ratio for the current session.

### Pre-Market Report

FR-09: Generate multi-timeframe context assessment from Sierra Chart weekly, monthly, quarterly, and yearly bar+VWAP data: trend direction (rising/sideways/falling) and price location vs ±1σ bands (imbalance down/inside value/imbalance up) for each timeframe.

FR-11: Include today's economic calendar events filtered from scraped data, matched against a user-editable watchlist of relevant event types.

FR-12: List all important levels grouped by source: MenthorQ options levels (NQ + recalculated QQQ), demand zone (W-LVWAP), supply zone (W-UVWAP).

FR-13: Include overnight session assessment: price location vs supply/demand zones and weekly value area, RVOL reading, ETH range in points.

FR-14: Include volatility indicators summary table with VVIX/VIX ratio classification (low/medium/high).

FR-15: Output the report as a single HTML file viewable in a local browser, with all data inline (no external dependencies).

FR-16: Store each generated report with a date-stamped filename for historical reference.

### Session Scenarios

FR-17: Accept 2 semi-structured scenario inputs per session: trade setup type, rationale, location (price levels), and targets.

FR-18: Persist scenarios linked to the session date.

FR-19: Display both scenarios on the live session dashboard.

### Feature Store — Market Regime Engine

FR-20: Store market regime classification rules as editable configurations. Each rule maps combinations of: multi-timeframe trend, ADR, RVOL, VVIX/VIX ratio, delta slope, gamma regime (positive/negative), and price position vs VWAP value area — to a named market regime.

FR-21: Provide a UI for creating, editing, and deleting regime rules.

FR-22: Each market regime definition includes: regime name, characteristics description, risk adjustments (position size modifier, expected range, execution style recommendations).

FR-23: Evaluate incoming live data against regime rules and output the currently active market regime with a confidence/match score.

FR-24: Store trade setup scoring criteria as editable rules in the feature store. Each criterion has a name, condition, and weight.

FR-25: Compute a composite trade setup score (0–100) from weighted criteria evaluated against current market data.

### Live Session Dashboard

FR-26: Poll Sierra Chart .txt export files every 2 minutes and update dashboard state.

FR-27: Display current market regime name, characteristics, and risk adjustment recommendations.

FR-28: Display current trade setup score with individual criterion breakdown.

FR-29: Display key indicators: gamma regime, RVOL value, cumulative delta position vs MA (above/below), cumulative delta slope, VWAP slope.

FR-30: Display the 2 pre-session scenarios for reference.

FR-31: Dashboard is a web page served locally, accessible in a browser.

### Trade Tagging & Review

FR-32: Import trade log from Sierra Chart exported trading_list.txt file.
- extract headers from TradesList.txt and save them in headers_trades.txt in technical_docs
- trades will be imported from path: "C:\SierraChart\SavedTradeActivity"
- use headers_trades.txt for correct headers mapping
- I will export trades to TradesList.txt, it will be new file created after each export, but new trades will be appended to old trades.
- only new trades should be imported to dashboard - meaning the trades that's not already in the database (it can be checked by comparing datetimes)

FR-33: Auto-tag each trade using feature store rules and session data at the time of the trade.
- there should be auto-tag feature for tags that can be derived from data:
    - all variables from feature store regarding key indicators
    - the rules that trade fullfilled from criteria score
    - entry location (tag derived from comparision between entry price and price value of VWAP bands)
- there should be possibility for manually added tags:
    - entry type: (frontrun/standard/late entry/re-entry)
    - entry direct context (ETH/RTH-based entry)
    - close type: (SL, trailed SL, TP, scratch, misclick, manual exit)

FR-34: Tags are derived from the feature store and are editable/extensible through the UI.

FR-35: Allow manual override or correction of any auto-assigned tag.

FR-36: Export tagged trades to the existing trading_dashboard SQLite database.

FR-37: Provide a plan vs execution comparison: overlay actual trades against the 2 pre-session scenarios.

FR-38: Integrate with trading_dashboard project.

- I have ready trading dashboard in path: "C:\Users\lkwas\Desktop\Data_engineering\trading_dashboard"

- in it I have defined necessary stats and features that I want them to be reused/integrated with current project

- the layout is basically defined as well - it would need only some styling like colors and borders to be in line with the rest of the web app

### Scaling Plan Reference

FR-39: Store the position sizing scale ($1000=1, $2000=2 MNQ, $5000=4, $8000=6, $11000=8, scale down on drop below threshold) and surface the current recommended size based on account equity input.

## Non-Functional Requirements

NFR-01: System runs entirely locally on Windows. No cloud dependencies for core functionality.

NFR-02: Backend: Python (FastAPI). Frontend: React or Vue SPA.

NFR-03: Data storage: SQLite (compatible with existing trading_dashboard schema where applicable).

NFR-04: Live dashboard data refresh: every 2 minutes via file polling.

NFR-05: Pre-market report generation completes within 60 seconds from initiation.

NFR-06: Trading Economics API integration must handle API errors gracefully — fail with a clear error message rather than producing corrupt data, and support a manual-input fallback.

NFR-07: System starts and stops via single CLI commands (start, stop). No Docker or complex orchestration required.

NFR-08: All configuration (file paths, conversion formulas, API keys, event watchlist) stored in a single config file (YAML or TOML).

NFR-09: Feature store rule changes take effect on the next polling cycle without requiring a restart.

NFR-10: All API endpoints require localhost-only binding (no external network exposure).

NFR-11: Logging: structured logs to file with rotation. Log all data ingestion, rule evaluation, and error events.

## Out of Scope

Fully automated trade execution or order placement.
Backtesting of trade setups.
Multi-user support or authentication.
Cloud deployment or remote access.
Mobile interface.
Direct broker API integration.
Automated screenshot capture from Sierra Chart.
Notion integration (system replaces Notion).
Automated ingestion of MenthorQ levels (manual input only for MVP). CME open interest data is out of scope entirely.
Financial news feed integration (e.g., FinancialJuice) — user continues checking externally.
Weekly, monthly, and yearly review automation (handled by existing trading_dashboard).

## Success Metrics

SM-01: Pre-market report covers 100% of the preparation checklist items from trading_process.md with no manual Notion entry required.

SM-02: Time from "start preparation" to "report generated" is under 5 minutes (including manual inputs), down from current ~20 minutes.

SM-03: Live dashboard displays correct market regime classification, verified against manual assessment for 5 consecutive sessions.

SM-04: Auto-tagging correctly assigns ≥90% of tags on imported trades, measured against manual tagging for 20 trades.

SM-05: Tagged trades successfully appear in the trading_dashboard after export.

## Assumptions

[ASSUMED] Sierra Chart .txt export column format is stable and consistent across all chart configurations. Parsing is column-position-based with the provided header schema.

[ASSUMED] The trader's playbook (referenced in trading_process.md as "laws of market dynamics") provides the conceptual basis for market regime rules but does not need to be programmatically ingested.

[ASSUMED] The existing trading_dashboard SQLite schema can be extended to accommodate new tag columns without breaking its existing FastAPI + Node.js application.

[ASSUMED] QQQ-to-NQ level conversion uses a constant ratio derived from current prices (e.g., NQ ≈ QQQ × conversion_factor), configurable in the config file.

[ASSUMED] The user will formalize market regime rules collaboratively during the feature store build phase — the system provides the framework, not pre-built rules.

[ASSUMED] Position sizing recommendations reference a manually entered account equity value, not a live broker feed.

[ASSUMED] Trade setup scoring weights start as equal and are tuned by the user over time through the UI.

## Open Questions

[RESOLVED] Trading dashboard local path: `C:\Users\lkwas\Desktop\Data_engineering\trading_dashboard`. Schema to be read from that repo before integration work begins.

[RESOLVED] QQQ price source: Sierra Chart `.txt` file export (`QQQ[M]  1 Min  #12_GraphData.txt`). No external API required.

[RESOLVED] Market profile data source: market profile section removed from pre-market report scope entirely.

[RESOLVED] Regime rule formalization format: weighted scoring matrix. Each regime rule maps indicator values to weights; the highest total score wins.

[RESOLVED] Trading dashboard integration direction: `trading_dashboard` will be absorbed into this project over time.

Summary: 36 FRs, 11 NFRs, 7 assumptions, 0 open questions (5 resolved).

MVP scope: FR-01 through FR-16 (data ingestion + pre-market report) and FR-20 through FR-25 (feature store / regime engine). The live dashboard (FR-26–31), trade tagging (FR-32–37), and scenario features (FR-17–19) follow as Phase 2.

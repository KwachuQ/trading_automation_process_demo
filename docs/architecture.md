# Architecture

## Overview

A locally-run automation system for intraday Micro E-mini NQ Futures trading that covers three phases: preparation (pre-market report), execution (live session dashboard with regime classification), and review (auto-tagging). The architecture follows a **monolithic backend + SPA frontend** pattern — a single FastAPI process serves the REST API, runs background polling, and generates reports, while a React SPA provides the UI.

This design satisfies the single-user local deployment constraint (NFR-01, NFR-07, NFR-10) while keeping the codebase simple enough for one developer to maintain. The existing `trading_dashboard` project (React 19 + Vite + Tailwind + FastAPI + SQLite) will be absorbed into this system over time, so the tech stack is intentionally aligned.

## System Design

Six backend modules feed data into a shared SQLite database. The React frontend reads state via REST endpoints. A background poller drives the live session loop.

```mermaid
graph TD
    subgraph "Data Sources"
        SC["Sierra Chart .txt exports"]
        Trading Economics["TD API<br/>(Economic Calendar)"]
        YF["Yahoo Finance (yfinance)"]
        MAN["Manual Inputs<br/>(MenthorQ, gamma)"]
    end

    subgraph "Backend (FastAPI)"
        ING["Ingestion Layer"]
        RPT["Report Generator"]
        FS["Feature Store"]
        ENG["Regime Engine"]
        POL["Live Poller<br/>(2-min cycle)"]
        TAG["Trade Tagger"]
        API["REST API Routes"]
    end

    DB[(SQLite DB)]
    HTML["HTML Report Files"]
    TDDB[(trading_dashboard<br/>trades.db)]

    subgraph "Frontend (React SPA)"
        UI["Dashboard / Forms / Review"]
    end

    SC --> ING
    TD --> ING
    YF --> ING
    MAN --> API --> ING

    ING --> DB
    DB --> RPT --> HTML
    DB --> ENG
    FS --> ENG
    POL --> ING
    POL --> ENG --> DB
    DB --> API --> UI
    DB --> TAG --> TDDB
```

## Components

### Config Manager

- **Purpose**: Load, validate, and provide typed access to the TOML configuration file.
- **Responsibilities**:
  - Parse `config/config.toml` at startup
  - Provide file path defaults for all 9 SC export files (FR-02)
  - Store conversion formula parameters, event watchlist, scraping targets (NFR-08)
  - Expose scaling plan thresholds (FR-38)
  - Expose logging settings: level, file path, max bytes, backup count (NFR-11)
- **Interface**:
  - `load_config(path: str) -> Config` — returns a validated dataclass; raises on missing/invalid keys
  - `Config` fields are read-only after load; poller and feature store re-read on demand (NFR-09)
- **Requirements satisfied**: NFR-08, NFR-11, FR-02

### SC File Parser

- **Purpose**: Read and parse all Sierra Chart `.txt` export files into structured DataFrames.
- **Responsibilities**:
  - Parse comma-separated `.txt` files with known header schemas (FR-01)
  - Handle four schema variants: multi-timeframe VWAP (`#5/#6/#7/#10`), Daily/ADR (`#8`), 1-min (`#1/#12`), and ETH/RTH VWAP (`#3/#4` — schema auto-detected from header row)
  - Extract derived values: RVOL from Daily `#8` (current volume / `Avg` column), ADR (FR-05)
  - Return last N rows or rows since a given timestamp
- **Interface**:
  - `parse_sc_file(path: str, schema: SchemaType) -> pd.DataFrame`
  - `get_latest_bar(path: str, schema: SchemaType) -> dict`
  - `SchemaType` enum: `VWAP_MULTI`, `DAILY_ADR`, `ONE_MIN`, `ETH_RTH_VWAP`
- **Requirements satisfied**: FR-01, FR-02, FR-05

### QQQ-NQ Converter

- **Purpose**: Compute the QQQ→NQ conversion ratio from Sierra Chart 1-minute exports.
- **Responsibilities**:
  - Read both `NQM26[M]  1 Min  #1_GraphData.txt` and `QQQ[M]  1 Min  #12_GraphData.txt`
  - Align on the most recent common timestamp (QQQ quotes are delayed) (FR-06)
  - Compute `ratio = NQ_last / QQQ_last` at that timestamp
  - Apply ratio to convert QQQ MenthorQ levels to NQ-equivalent levels
- **Interface**:
  - `compute_ratio(nq_path: str, qqq_path: str) -> ConversionResult` — returns `{ratio, nq_price, qqq_price, timestamp}`
  - `convert_level(qqq_level: float, ratio: float) -> float`
- **Requirements satisfied**: FR-06

### Volatility Service

- **Purpose**: Fetch VVIX/VIX data and compute the ratio.
- **Responsibilities**:
  - Fetch current VVIX and VIX quotes via `yfinance` (FR-07)
  - Compute VVIX/VIX ratio
  - Classify ratio into low/medium/high bucket based on configurable thresholds
- **Interface**:
  - `fetch_vvix_vix() -> VolatilityData` — returns `{vvix, vix, ratio, classification}`
  - Raises `VolatilityFetchError` on network failure (caller falls back to manual input)
- **Requirements satisfied**: FR-07, FR-14

### Economic Calendar Service

- **Purpose**: Fetch today's economic release dates from the Trading Economics API.
- **Responsibilities**:
  - Query Trading Economics API for upcoming economic releases on the current date (FR-03)
  - Extract: time, series ID, event name, actual/forecast/previous values
  - Filter against user-editable watchlist from config (FR-11)
  - Fail with a clear error on API errors; never produce corrupt data (NFR-06)
- **Interface**:
  - `fetch_economic_calendar(watchlist: list[str]) -> list[CalendarEvent]`
  - Raises `CalendarFetchError` with diagnostic message on failure
- **Requirements satisfied**: FR-03, FR-11, NFR-06

### Pre-Market Report Generator

- **Purpose**: Combine all ingested data into a single HTML report.
- **Responsibilities**:
  - Multi-timeframe context assessment: trend + VWAP band position for weekly/monthly/quarterly/yearly, ADR slope, daily volume moving average slope (FR-09)
  - Economic calendar section (FR-11)
  - Important levels table: MenthorQ NQ + recalculated QQQ, W-LVWAP, W-UVWAP (FR-12)
  - Overnight session assessment: price vs zones, RVOL, ETH range (FR-13)
  - Volatility summary with VVIX/VIX classification + gamma regime (FR-14)
  - Render via Jinja2 template → single self-contained HTML (FR-15)
  - Save to `reports/YYYY-MM-DD_premarket.html` (FR-16)
- **Interface**:
  - `generate_report(session_date: date) -> Path` — returns path to saved HTML file
  - Reads all required data from the database (populated by ingestion endpoints)
- **Requirements satisfied**: FR-09, FR-11 through FR-16, NFR-05

### Feature Store

- **Purpose**: CRUD for market regime rules and trade setup scoring criteria.
- **Responsibilities**:
  - Store regime rules as JSON in SQLite `regime_rules` table (FR-20)
  - Each rule: name, indicator-weight pairs, characteristics, risk adjustments (FR-22)
  - Store scoring criteria in `scoring_criteria` table (FR-24)
  - Provide REST endpoints for create/read/update/delete (FR-21)
  - Changes visible on next polling cycle without restart (NFR-09)
- **Interface**:
  - `get_regime_rules() -> list[RegimeRule]`
  - `upsert_regime_rule(rule: RegimeRule) -> RegimeRule`
  - `delete_regime_rule(rule_id: int) -> None`
  - `get_scoring_criteria() -> list[ScoringCriterion]`
  - `upsert_scoring_criterion(criterion: ScoringCriterion) -> ScoringCriterion`
  - `delete_scoring_criterion(criterion_id: int) -> None`
- **Requirements satisfied**: FR-20, FR-21, FR-22, FR-24, NFR-09

### Regime Engine

- **Purpose**: Evaluate live market data against regime rules using a weighted scoring matrix.
- **Responsibilities**:
  - Accept current indicator snapshot (trend per timeframe, ADR, RVOL, VVIX/VIX ratio, delta slope, gamma, VWAP position)
  - For each regime rule, sum weights of matched conditions (FR-23)
  - Highest total score wins; confidence = matched_weight / total_possible_weight
  - Compute composite trade setup score (0–100) from weighted criteria (FR-25)
- **Interface**:
  - `evaluate_regime(indicators: IndicatorSnapshot, rules: list[RegimeRule]) -> RegimeResult` — returns `{regime_name, confidence, characteristics, risk_adjustments}`
  - `score_trade_setup(indicators: IndicatorSnapshot, criteria: list[ScoringCriterion]) -> SetupScore` — returns `{total_score, criterion_breakdown}`
- **Requirements satisfied**: FR-23, FR-25

### Live Poller

- **Purpose**: Background task that drives the session dashboard data loop.
- **Responsibilities**:
  - Run on a 2-minute interval via `asyncio` scheduler (FR-26, NFR-04)
  - Re-read SC export files via SC File Parser
  - Feed fresh indicators into Regime Engine
  - Write updated regime result + setup score + indicator snapshot to SQLite
  - Frontend polls REST endpoint for latest state
- **Interface**:
  - `start_polling() -> None` — starts background loop
  - `stop_polling() -> None` — stops background loop
  - Internal: writes to `session_snapshots` table on each cycle
- **Requirements satisfied**: FR-26, NFR-04

### Trade Importer & Auto-Tagger

- **Purpose**: Import trades from Sierra Chart and auto-tag using feature store rules.
- **Responsibilities**:
  - Parse `trading_list.txt` (same format as trading_dashboard's `sierra_parser`) (FR-32)
  - For each trade's entry timestamp, look up the closest `session_snapshots` row to get market context
  - Auto-tag: gamma regime, CD vs MA, CD slope, entry location vs VWAP bands, outcome, entry quality, trade structure, session type (FR-33)
  - Tags are derived from feature store definitions, extensible (FR-34)
  - Allow manual override via API (FR-35)
  - Export to `trading_dashboard` SQLite DB at `C:\Users\lkwas\Desktop\Data_engineering\trading_dashboard\data\trades.db` — writes to `trades` table using the existing schema (FR-36)
  - Plan vs execution overlay (FR-37)
- **Interface**:
  - `import_trades(file_path: str) -> list[TaggedTrade]`
  - `auto_tag(trade: Trade, snapshot: IndicatorSnapshot) -> dict[str, str]`
  - `export_to_dashboard(trades: list[TaggedTrade]) -> int` — returns count exported
- **Requirements satisfied**: FR-32 through FR-37

### REST API Layer

- **Purpose**: FastAPI router layer exposing all functionality to the frontend.
- **Responsibilities**:
  - Bind to `127.0.0.1` only (NFR-10)
  - Group endpoints by domain (ingestion, report, feature store, session, review)
  - Structured JSON responses with error codes
- **Key endpoints**:
  - `POST /api/ingestion/run` — trigger full data ingestion pipeline
  - `POST /api/ingestion/manual` — submit MenthorQ levels, gamma regime
  - `POST /api/report/generate` — generate pre-market HTML report
  - `GET /api/report/latest` — get latest report metadata
  - `GET/POST/PUT/DELETE /api/feature-store/regimes` — regime rule CRUD
  - `GET/POST/PUT/DELETE /api/feature-store/scoring` — scoring criteria CRUD
  - `POST /api/session/scenarios` — save session scenarios
  - `GET /api/session/scenarios/{date}` — retrieve scenarios
  - `GET /api/session/live` — get latest dashboard snapshot (regime, score, indicators, scenarios)
  - `POST /api/session/poller/start` — start live polling
  - `POST /api/session/poller/stop` — stop live polling
  - `POST /api/review/import` — import trade log
  - `GET /api/review/trades/{date}` — get tagged trades for a session
  - `PUT /api/review/trades/{id}/tags` — override tags
  - `POST /api/review/export` — export to trading_dashboard DB
  - `GET /api/review/plan-vs-execution/{date}` — plan vs execution comparison
  - `GET /api/session/scaling?equity={value}` — position size recommendation
- **Requirements satisfied**: NFR-02, NFR-10, FR-17, FR-18, FR-19, FR-38

### React Frontend

- **Purpose**: Single-page application providing all user-facing UI.
- **Responsibilities**:
  - **Pre-Market page**: manual input forms (MenthorQ, gamma), trigger ingestion + report generation, view/download report (FR-04, FR-05, FR-15)
  - **Session Dashboard page**: live regime display, setup score breakdown, indicator panel, scenario cards, scaling card with equity input (FR-27 through FR-31, FR-38)
  - **Feature Store page**: CRUD forms for regime rules and scoring criteria (FR-21)
  - **Review page**: trade import, tag grid with edit-in-place, plan vs execution view, export button (FR-34, FR-35, FR-37)
  - Polls `GET /api/session/live` every 2 minutes when on dashboard page
- **Tech**: React 19, Vite, Tailwind CSS 4, Recharts (aligned with trading_dashboard)
- **Requirements satisfied**: FR-04, FR-05, FR-21, FR-27 through FR-31, FR-34, FR-35, FR-38, NFR-02

## Data Flow

### Pre-Market Preparation

1. User opens **Pre-Market page** in browser.
2. User fills **manual input forms** (MenthorQ levels for NQ + QQQ, gamma regime) and submits.
3. Frontend calls `POST /api/ingestion/manual` → data persisted to `manual_inputs` table.
4. User clicks **Generate Report**.
5. Frontend calls `POST /api/ingestion/run` which:
   a. **SC File Parser** reads multi-timeframe VWAP files (`#5, #6, #7, #10`) → trend + band position per timeframe.
   b. **SC File Parser** reads Daily `#8` → volume avg, ADR, RVOL.
   c. **QQQ-NQ Converter** reads `#1` + `#12` → computes ratio → converts QQQ MenthorQ levels to NQ.
   d. **Volatility Service** calls yfinance → VVIX/VIX ratio + classification.
   e. **Economic Calendar Service** queries FRED API → filtered events.
   f. All results written to `session_data` table for current date.
6. Frontend calls `POST /api/report/generate`.
7. **Report Generator** reads `session_data` + `manual_inputs` → renders Jinja2 template → saves `reports/YYYY-MM-DD_premarket.html`.
8. Frontend receives path, user opens HTML in browser.

### Live Session

1. User inputs 2 **scenarios** on Session Dashboard → `POST /api/session/scenarios`.
2. User clicks **Start Polling** → `POST /api/session/poller/start`.
3. Every 2 minutes, **Live Poller**:
   a. Re-reads SC export files (`#3, #4` for ETH/RTH VWAP bands; `#8` for RVOL; `#1` for NQ price).
   b. Builds `IndicatorSnapshot` (gamma from manual input, RVOL, CD position vs MA, CD slope, VWAP slope, prices vs bands).
   c. Calls **Regime Engine** → regime result + trade setup score.
   d. Writes snapshot + results to `session_snapshots` table.
4. Frontend polls `GET /api/session/live` every 2 minutes → updates regime card, score breakdown, indicator panel, scenarios.

### Post-Session Review

1. User uploads `trading_list.txt` on Review page → `POST /api/review/import`.
2. **Trade Importer** parses fills into F2F trades (same logic as trading_dashboard's `sierra_parser`).
3. For each trade, **Auto-Tagger** looks up `session_snapshots` at the trade's `entry_datetime` → applies feature store rules → assigns tags.
4. Tagged trades displayed in grid. User can **override** any tag via inline edit → `PUT /api/review/trades/{id}/tags`.
5. User clicks **Export** → `POST /api/review/export` → **Exporter** writes to `C:\Users\lkwas\Desktop\Data_engineering\trading_dashboard\data\trades.db` using the existing `trades` table schema (maps auto-tags to `setup_tag` + `additional_tag` columns).

## Data Model

### SQLite Database: `data/trading_automation.db`

```sql
-- Persisted manual inputs (MenthorQ, gamma) per session date
CREATE TABLE manual_inputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    input_type TEXT NOT NULL,        -- 'menthorq_nq', 'menthorq_qqq', 'gamma'
    data_json TEXT NOT NULL,         -- JSON blob with field values
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(session_date, input_type)
);

-- Aggregated session data produced by ingestion run
CREATE TABLE session_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL UNIQUE,
    timeframe_context_json TEXT,     -- {yearly: {trend, band_position}, ...}
    levels_json TEXT,                -- {menthorq_nq: {...}, menthorq_qqq: {...}, wlvwap, wuvwap}
    volatility_json TEXT,            -- {vvix, vix, ratio, classification, gamma, rvol, adr}
    calendar_json TEXT,              -- [{time, event, impact, ...}]
    overnight_json TEXT,             -- {price_vs_zones, rvol, eth_range}
    qqq_nq_ratio REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Session scenarios (2 per date)
CREATE TABLE scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    scenario_number INTEGER NOT NULL CHECK(scenario_number IN (1, 2)),
    setup_type TEXT NOT NULL,
    rationale TEXT NOT NULL,
    location TEXT NOT NULL,
    targets TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(session_date, scenario_number)
);

-- Live poller snapshots (one row per poll cycle)
CREATE TABLE session_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    snapshot_time TEXT NOT NULL,
    indicators_json TEXT NOT NULL,    -- full IndicatorSnapshot
    regime_name TEXT,
    regime_confidence REAL,
    regime_details_json TEXT,
    setup_score REAL,
    score_breakdown_json TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_snapshots_date_time ON session_snapshots(session_date, snapshot_time);

-- Feature store: regime rules
CREATE TABLE regime_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    conditions_json TEXT NOT NULL,    -- [{indicator, operator, value, weight}, ...]
    characteristics TEXT NOT NULL,
    risk_adjustments_json TEXT NOT NULL, -- {position_size_modifier, expected_range, execution_style}
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Feature store: scoring criteria
CREATE TABLE scoring_criteria (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    condition_json TEXT NOT NULL,     -- {indicator, operator, value}
    weight REAL NOT NULL DEFAULT 1.0,
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Imported trades with auto-tags (local to this system)
CREATE TABLE tagged_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_datetime TEXT NOT NULL,
    exit_datetime TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL NOT NULL,
    quantity INTEGER DEFAULT 1,
    pnl REAL DEFAULT 0.0,
    net_pnl REAL DEFAULT 0.0,
    tags_json TEXT NOT NULL DEFAULT '{}',   -- {tag_category: tag_value, ...}
    tags_auto INTEGER DEFAULT 1,            -- 1 = auto-tagged, 0 = manually overridden
    snapshot_id INTEGER REFERENCES session_snapshots(id),
    import_hash TEXT UNIQUE,
    exported_to_dashboard INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_tagged_session ON tagged_trades(session_date);

-- Pre-market report log
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Integration with trading_dashboard

The **Exporter** writes to `C:\Users\lkwas\Desktop\Data_engineering\trading_dashboard\data\trades.db` directly. It maps `tagged_trades` to the existing `trades` schema:
- `setup_tag` ← comma-joined primary tags (gamma, CD position, entry location, trade structure)
- `additional_tag` ← comma-joined secondary tags (entry quality, session type)
- `setup_rating` ← derived from `setup_score` (1–5 stars mapped from 0–100)
- `import_hash` ← same SHA256 scheme for dedup
- OHLC, PnL, duration fields map 1:1

## Key Technical Decisions

- **TOML over YAML for config**: Python has built-in `tomllib` (3.11+). No external dependency. Simpler syntax for the flat key-value structure of file paths and thresholds. — *Alternative: YAML (requires PyYAML)* — per NFR-08.

- **Jinja2 HTML over PDF for reports**: Self-contained HTML with inline CSS renders instantly in any browser. PDF generation adds wkhtmltopdf or WeasyPrint dependencies and is slower. — *Alternative: PDF via WeasyPrint* — per FR-15.

- **Weighted scoring matrix for regime classification**: Each regime rule defines indicator→weight pairs. For a given indicator snapshot, each rule's matched weights are summed; highest total wins. Confidence = matched/total. Simple to understand, edit via UI, and debug. — *Alternatives: decision tree (brittle, hard to edit), ML classifier (overkill for single user)* — per FR-23.

- **File polling over streaming**: SC writes `.txt` files at configurable intervals. The poller re-reads files every 2 minutes. No WebSocket or file-watcher complexity needed. — *Alternative: watchdog filesystem events (more complex, marginal benefit at 2-min granularity)* — per FR-26, NFR-04.

- **Separate DB from trading_dashboard**: This system uses its own `trading_automation.db` for all internal state. Exports go to `trades.db` via a dedicated exporter. This avoids schema conflicts during the absorption period. — per NFR-03.

- **React 19 + Vite + Tailwind CSS 4**: Matches the existing trading_dashboard stack exactly. When trading_dashboard is absorbed, its components can be migrated directly. — per NFR-02.

- **raw sqlite3 over ORM**: Matches trading_dashboard's approach. Single-user local system with known schema — an ORM adds complexity without benefit. — *Alternative: SQLAlchemy (heavier, not needed)*

- **asyncio background task over APScheduler**: FastAPI runs on `asyncio`. A simple `asyncio.create_task` loop handles the 2-minute poll cycle with no extra dependency. — *Alternative: APScheduler (extra package, more features than needed)*

- **CLI via `main.py` entry point**: `python -m backend.main start` launches uvicorn on `127.0.0.1:8000`. `Ctrl+C` stops. No separate CLI framework needed for a single-user local tool. — per NFR-07.

## File & Folder Structure

```
trading_process_automation/
├── config/
│   └── config.toml                    # All configurable paths, thresholds, watchlists
├── backend/
│   ├── __init__.py
│   ├── main.py                        # FastAPI app, lifespan (startup/shutdown), CORS, logging setup (NFR-11)
│   ├── config.py                      # Config loader + dataclass
│   ├── db.py                          # SQLite connection, table creation, migrations
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── sc_parser.py               # Sierra Chart .txt file parser (all schema variants)
│   │   ├── qqq_nq_converter.py        # Timestamp-aligned ratio calculation
│   │   ├── volatility.py              # yfinance VVIX/VIX fetcher
│   │   └── economic_calendar.py        # FRED API economic calendar client
│   ├── report/
│   │   ├── __init__.py
│   │   ├── generator.py               # Pre-market HTML report builder
│   │   └── templates/
│   │       └── premarket.html          # Jinja2 template
│   ├── feature_store/
│   │   ├── __init__.py
│   │   ├── store.py                   # CRUD for regime rules + scoring criteria
│   │   └── engine.py                  # Regime evaluator + setup scorer
│   ├── session/
│   │   ├── __init__.py
│   │   ├── scenarios.py               # Scenario CRUD
│   │   └── poller.py                  # Background polling loop
│   ├── review/
│   │   ├── __init__.py
│   │   ├── trade_importer.py          # Parse trading_list.txt into trades
│   │   ├── auto_tagger.py             # Tag trades from snapshot + feature store
│   │   └── exporter.py                # Write to trading_dashboard trades.db
│   └── routers/
│       ├── __init__.py
│       ├── ingestion.py               # /api/ingestion/*
│       ├── report.py                  # /api/report/*
│       ├── feature_store.py           # /api/feature-store/*
│       ├── session.py                 # /api/session/* (includes scenarios + scaling)
│       └── review.py                  # /api/review/*
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                    # Router + layout
│       ├── api.js                     # Axios client (baseURL: localhost)
│       ├── pages/
│       │   ├── PreMarketPage.jsx      # Manual inputs + report generation
│       │   ├── SessionDashboard.jsx   # Live regime, score, indicators, scenarios
│       │   ├── FeatureStorePage.jsx   # Regime rules + scoring criteria CRUD
│       │   └── ReviewPage.jsx         # Trade import, tag grid, plan vs execution
│       ├── components/
│       │   ├── ManualInputForm.jsx
│       │   ├── ScenarioInput.jsx
│       │   ├── RegimeCard.jsx
│       │   ├── ScoreBreakdown.jsx
│       │   ├── IndicatorPanel.jsx
│       │   ├── ScalingCard.jsx
│       │   ├── TradeTagGrid.jsx
│       │   ├── RuleEditor.jsx
│       │   └── PlanVsExecution.jsx
│       └── hooks/
│           ├── useLiveSession.js      # Polls /api/session/live
│           └── useFeatureStore.js
├── reports/                           # Generated HTML reports
├── data/
│   └── trading_automation.db          # SQLite database (auto-created)
├── logs/
│   └── app.log                        # Rotating log file
├── docs/
│   ├── project-brief.md
│   ├── trading_process.md
│   ├── requirements.md
│   ├── architecture.md
│   └── sc_files.txt
├── tests/
│   ├── conftest.py                    # Fixtures: temp DB, sample SC files
│   ├── test_sc_parser.py
│   ├── test_qqq_nq_converter.py
│   ├── test_volatility.py
│   ├── test_economic_calendar.py
│   ├── test_report_generator.py
│   ├── test_regime_engine.py
│   ├── test_auto_tagger.py
│   ├── test_exporter.py
│   └── test_api/
│       ├── test_ingestion_routes.py
│       ├── test_feature_store_routes.py
│       └── test_session_routes.py
├── requirements.txt
└── README.md
```

## Configuration

`config/config.toml` structure:

```toml
[sierra_chart]
data_dir = "C:/SierraChart/Data"

[sierra_chart.files]
yearly_vwap = "NQM26 [CBV][M]  Daily #10_GraphData.txt"
quarterly_vwap = "NQM26 [CBV][M]  60000 Volume #5_GraphData.txt"
monthly_vwap = "NQM26 [CBV][M]  37500 Volume #6_GraphData.txt"
weekly = "NQM26 [CBV][M]  4500 Volume #7_GraphData.txt"
daily_adr = "NQM26 [CBV][M]  Daily #8_GraphData.txt"
eth_750v = "NQM26 [CV][M]  750 Volume #4_GraphData.txt"
rth_500v = "NQM26[M]  500 Volume #3_GraphData.txt"
nq_1min = "NQM26[M]  1 Min  #1_GraphData.txt"
qqq_1min = "QQQ[M]  1 Min  #12_GraphData.txt"
trading_list = "trading_list.txt"

[volatility]
vvix_ticker = "^VVIX"
vix_ticker = "^VIX"
ratio_thresholds = { low = 4.0, high = 5.5 }

[calendar]
fred_api_key = "YOUR_FRED_API_KEY"
fred_base_url = "https://api.stlouisfed.org/fred"
watchlist = ["Non-Farm Payrolls", "CPI", "FOMC", "Initial Jobless Claims", "GDP", "PCE", "PPI", "ISM Manufacturing", "ISM Services"]

[report]
output_dir = "reports"

[scaling]
thresholds = [
    { equity = 2000, contracts = 2 },
    { equity = 5000, contracts = 4 },
    { equity = 8000, contracts = 6 },
    { equity = 11000, contracts = 8 },
]

[poller]
interval_seconds = 120

[dashboard]
trading_dashboard_db = "C:/Users/lkwas/Desktop/Data_engineering/trading_dashboard/data/trades.db"

[server]
host = "127.0.0.1"
port = 8000

[logging]
level = "INFO"
file = "logs/app.log"
max_bytes = 10_485_760
backup_count = 5
```

## Testing Strategy

| Layer | Scope | Approach |
|---|---|---|
| **SC File Parser** | Unit | Feed sample `.txt` snippets (copied from real headers + 2-3 data rows). Assert correct DataFrame shape, column types, derived values (RVOL, ADR). |
| **QQQ-NQ Converter** | Unit | Two sample 1-min files with overlapping and non-overlapping timestamps. Assert correct ratio, correct timestamp alignment. |
| **Volatility Service** | Unit | Mock `yfinance.Ticker.history()`. Assert ratio calculation and classification. |
| **Economic Calendar Service** | Unit | Mock FRED API responses with saved JSON fixtures. Assert parsed events. Test with API error responses → expect `CalendarFetchError`. |
| **Report Generator** | Integration | Run with a seeded DB. Assert HTML file created, contains expected sections, is valid HTML. |
| **Regime Engine** | Unit | Define 3 test rules + test indicator snapshots. Assert correct winner, confidence, score. Edge cases: no rules match, tied scores. |
| **Auto-Tagger** | Unit | Given a known trade + known snapshot → assert expected tags for each category. |
| **Exporter** | Integration | Export to a temp SQLite DB with trading_dashboard schema. Assert rows match, `import_hash` dedup works. |
| **API Routes** | Integration | `TestClient` (FastAPI) against an in-memory DB. Cover happy paths + validation errors per router. |
| **Frontend** | Manual | Verified during development. No automated UI tests for MVP (single user, low risk). |

Run: `pytest tests/ -v` from project root.

## Error Handling

- **SC file not found or empty**: Log warning, skip that data source, mark section as "unavailable" in report. Do not block report generation for a single missing file.
- **yfinance network failure**: Log error, fall back to manual VVIX/VIX input via the UI. Report shows "ratio unavailable" if no manual input either.
- **FRED API failure**: Log error with API response diagnostic. Calendar section shows "calendar fetch failed — enter events manually" with a manual input form (NFR-06).
- **trading_dashboard DB locked or missing**: Exporter logs error with path. No data lost — tagged trades remain in `trading_automation.db` and export can be retried.
- **Malformed SC data rows**: Parser skips malformed rows, logs line number + content. Continues with valid rows.

## Assumptions

[ASSUMED] `yfinance` provides sufficiently current VVIX/VIX quotes for pre-market use (typically 15-min delayed; acceptable for ratio classification).

[ASSUMED] The 2-minute polling interval is sufficient for regime changes — market regime shifts happen on a longer timescale than individual ticks.

[ASSUMED] The trading_dashboard `sierra_parser` fill-aggregation logic can be reused (copied/adapted) in `trade_importer.py` to maintain identical F2F trade computation.

[ASSUMED] Jinja2 is sufficient for HTML report templating; no client-side JS needed in the report file.

[ASSUMED] Frontend dev server proxies to FastAPI at `localhost:8000` during development; production build serves static files from FastAPI.

## Open Questions

None — all questions from requirements have been resolved.

---

Summary: 11 components designed, 8 key technical decisions documented, 0 open questions remaining.

# Trading Process Automation (Demo Version)

> **Note:** This repository is a sanitized Demo version of a proprietary trading system. All private trade history, personal setup parameters, and sensitive API keys have been removed. It includes a mock data generator so others can test the application without accessing the author's real data.

A local automation system for an intraday Micro E-mini NQ Futures trader. Replaces manual preparation, session monitoring, and post-session review workflows.

## What it does

**Pre-market preparation** — ingests data from Sierra Chart exports, VVIX/VIX from Yahoo Finance, and an economic calendar API. Accepts manual inputs for MenthorQ options levels and gamma regime. Generates a self-contained HTML report covering multi-timeframe VWAP context, important levels, overnight assessment, and volatility summary.

**Live session dashboard** — polls Sierra Chart export files every 2 minutes. Classifies the current market regime using a weighted scoring matrix defined in the feature store. Displays regime characteristics, risk adjustment recommendations, a composite trade setup score, and the two pre-session scenarios.

**Post-session review** — imports the Sierra Chart `trading_list.txt`, auto-tags each trade using feature store rules and session snapshot data, and exports tagged trades to the existing `trading_dashboard` SQLite database.

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Frontend | React 19, Vite, Tailwind CSS 4 |
| Database | SQLite (`data/trading_automation.db`) |
| Templating | Jinja2 |
| Data | pandas, yfinance, httpx |

## Project structure

```
trading_process_automation/
├── backend/
│   ├── main.py                 # FastAPI app entry point
│   ├── config.py               # Config loader
│   ├── db.py                   # SQLite setup
│   ├── state.py                # Global app state management
│   ├── feature_store/          # Regime rules and scoring criteria
│   ├── ingestion/              # SC parser, volatility, calendar, converters
│   ├── report/                 # HTML report generator + Jinja2 template
│   ├── review/                 # Trade importer, tagger, stats, and manager
│   ├── routers/                # REST API routers
│   └── scripts/                # Utility scripts
├── frontend/
│   └── src/
│       ├── components/         # UI components
│       ├── context/            # React context providers
│       ├── hooks/              # Custom React hooks
│       └── pages/              # PreMarketPage, SessionDashboard, FeatureStorePage, ReviewPage
├── config/
│   └── config.toml             # All configurable paths and thresholds
├── reports/                    # Generated HTML reports (date-stamped)
├── data/                       # Downloaded files and intermediate data
├── logs/                       # Rotating log file
├── docs/                       # Architecture, requirements, task plan
└── tests/                      # pytest test suite
```

## Demo Setup & Running Locally

To test this application locally with mock data (protecting the author's trade history), we provide a script that generates a clean `demo.db` and populates it with standard feature rules and sample trades.

### Prerequisites

- Python 3.11+
- Node.js 18+
- **RapidAPI Key** for Trading Economics (Free tier works): Required only if you want to generate *new* pre-market reports.
- *Note on Market Data:* The system uses `yfinance` to fetch VVIX/VIX data, which is completely free, does not require an API key, and works out of the box.

### Install & Configure

```bash
# 1. Clone the repo and set up backend
python -m venv venv
# On Windows: venv\Scripts\activate
# On Mac/Linux: source venv/bin/activate
pip install -r requirements.txt

# 2. Copy the example config
cp config/config.example.toml config/config.toml

# 3. Generate mock demo data
# (Windows PowerShell)
$env:PYTHONPATH="."
$env:DATABASE_URL="data/demo.db"
python backend/scripts/seed_demo_data.py

# (Mac/Linux)
# export PYTHONPATH="."
# export DATABASE_URL="data/demo.db"
# python backend/scripts/seed_demo_data.py
```

### Start the application

If you have historical pre-market HTML reports you'd like to share as examples, place them in the `demo_reports/` directory.

**Backend:**
```bash
# Terminal 1
# On Windows: venv\Scripts\activate
$env:DATABASE_URL="data/demo.db"
python -m backend.main
```

**Frontend:**
```bash
# Terminal 2
cd frontend
npm install
npm run dev
```

Then visit `http://localhost:5173` to explore the dashboard.

## Deploying for Free (Vercel & Render)

This stack can be hosted completely for free so you can show off your demo online.

1. **Frontend (Vercel)**
   - Import this repository to Vercel.
   - Framework Preset: `Vite`
   - Build Command: `npm run build`
   - Output Directory: `dist`
   - Add environment variable `VITE_API_URL` pointing to your Render backend URL (e.g., `https://my-trading-demo.onrender.com/api`).

2. **Backend (Render)**
   - Create a new "Web Service" on Render and link this repository.
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `export PYTHONPATH=. && python backend/scripts/seed_demo_data.py && uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Add environment variable `CORS_ORIGINS` with your Vercel URL (e.g., `https://my-frontend.vercel.app`).
   - Add environment variable `DATABASE_URL` as `data/demo.db`.
   
*(Note: Render's free tier spins down after inactivity. On spin-up, the disk is wiped and `seed_demo_data.py` runs automatically, creating a fresh sandbox environment for every visitor—which is perfect for a public demo!)*

## Daily workflow

1. Open the **Pre-Market page** in the browser.
2. Fill in MenthorQ options levels and gamma regime, then click **Generate Report**.
3. Open the generated HTML report from `reports/YYYY-MM-DD_premarket.html`.
4. Switch to **Session Dashboard**, enter your two scenarios, and click **Start Polling**.
5. After the session, go to **Review**, upload `trading_list.txt`, review auto-tags, and export to `trading_dashboard`.

## Tests

```bash
cd tests
pytest
```

Tests use real Sierra Chart export files where file-reading logic is involved. Place sample files in `tests/fixtures/` matching the schemas in `docs/technical_docs/headers.txt`.

## API

The backend binds to `127.0.0.1:8000` only (no external network exposure). Key endpoints:

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/ingestion/run` | Run full data ingestion pipeline |
| `POST` | `/api/ingestion/manual` | Save manual inputs (MenthorQ, gamma) |
| `POST` | `/api/report/generate` | Generate pre-market HTML report |
| `GET` | `/api/session/live` | Current regime + score snapshot |
| `POST` | `/api/session/poller/start` | Start 2-minute polling loop |
| `POST` | `/api/session/scenarios` | Save session scenarios |
| `GET/POST/PUT/DELETE` | `/api/feature-store/regimes` | Regime rule CRUD |
| `GET/POST/PUT/DELETE` | `/api/feature-store/criteria` | Scoring criterion CRUD |
| `POST` | `/api/review/import` | Import and auto-tag Sierra Chart trade log |
| `GET` | `/api/review/trades` | Retrieve tagged trades |
| `PATCH` | `/api/review/trades/{id}` | Update tags for a trade |
| `GET` | `/api/review/stats` | Get review statistics and chart data |
| `GET` | `/api/review/plan-vs-execution` | Compare trades against session scenarios |
| `POST` | `/api/review/trades/merge` | Merge multiple trades into one |
| `POST` | `/api/review/trades/bulk-delete` | Delete multiple trades |

Interactive API docs available at `http://localhost:8000/docs`.

## Feature store

The feature store holds two types of editable rules:

- **Regime rules** — map combinations of multi-timeframe trend, ADR, RVOL, VVIX/VIX ratio, delta slope, gamma regime, and VWAP position to a named market regime with characteristics and risk adjustments.
- **Scoring criteria** — weighted conditions evaluated against live data to produce a 0–100 trade setup score.

Rules are edited through the **Feature Store** page in the UI. Changes take effect on the next polling cycle without a restart.

## Reports

Generated reports are saved as `reports/YYYY-MM-DD_premarket.html` — self-contained HTML files with all data inline. No external dependencies are required to view them.

To share historical examples in this public demo, place your sample HTML files into the `demo_reports/` folder (which is tracked by Git, unlike the private `reports/` folder).

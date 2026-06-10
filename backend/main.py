from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import Config, load_config
from backend.db import get_connection, init_db
from backend.routers import feature_store, ingestion, report, review, session
from backend.state import app_state

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_CONFIG_PATH = Path(os.getenv("CONFIG_PATH", _PROJECT_ROOT / "config" / "config.toml"))


def _setup_logging(cfg: Config) -> None:
    log_path = Path(cfg.logging.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=cfg.logging.max_bytes,
        backupCount=cfg.logging.backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(cfg.logging.level)
    root_logger.addHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root_logger.addHandler(console_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    config = load_config(str(_CONFIG_PATH))
    _setup_logging(config)

    logger = logging.getLogger(__name__)
    logger.info("Starting trading automation backend")

    # Resolve DB path relative to the project root (parent of this file's directory)
    # so the same file is used regardless of the working directory at startup.
    project_root = Path(__file__).resolve().parent.parent
    db_path_str = os.getenv("DATABASE_URL", str(project_root / "data" / "trading_automation.db"))
    db_path = Path(db_path_str)
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(str(db_path))
    init_db(conn)
    logger.info("Database initialised at %s", db_path)

    app_state["config"] = config
    app_state["db_conn"] = conn
    app_state["db_path"] = str(db_path)

    yield

    conn.close()
    logger.info("Shutdown complete")


app = FastAPI(title="Trading Automation API", lifespan=lifespan)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,https://trading-automation-process-demo.vercel.app").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingestion.router, prefix="/api")
app.include_router(report.router, prefix="/api")
app.include_router(feature_store.router, prefix="/api")
app.include_router(session.router, prefix="/api")
app.include_router(review.router, prefix="/api")


if __name__ == "__main__":
    config = load_config(str(_CONFIG_PATH))
    uvicorn.run(
        "backend.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )

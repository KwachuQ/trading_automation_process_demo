from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.config import Config

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_NAME = "premarket.html"


def generate_report(
    session_date: str,
    conn: sqlite3.Connection,
    config: Config,
) -> Path:
    """Render the pre-market HTML report for *session_date* and save it to disk.

    Reads from ``session_data`` and ``manual_inputs`` tables, assembles a
    template context, renders the Jinja2 template, writes the file, and
    upserts a row in the ``reports`` table.  Returns the output ``Path``.
    """
    # --- read session_data -----------------------------------------------
    row = conn.execute(
        "SELECT timeframe_context_json, levels_json, volatility_json, "
        "calendar_json, overnight_json, qqq_nq_ratio, volatility_indication_json, "
        "nq_last_price "
        "FROM session_data WHERE session_date = ?",
        (session_date,),
    ).fetchone()

    if row:
        timeframe_context = _load_json(row[0])
        levels = _load_json(row[1])
        volatility = _load_json(row[2])
        calendar = _load_json(row[3])
        overnight = _load_json(row[4])
        qqq_nq_ratio = row[5]
        volatility_indication = _load_json(row[6])
        nq_last_price = row[7]
    else:
        timeframe_context = levels = volatility = calendar = overnight = None
        qqq_nq_ratio = None
        volatility_indication = None
        nq_last_price = None

    # --- read manual_inputs ----------------------------------------------
    manual_rows = conn.execute(
        "SELECT input_type, data_json FROM manual_inputs WHERE session_date = ?",
        (session_date,),
    ).fetchall()
    manual_inputs: dict[str, dict] = {}
    for itype, djson in manual_rows:
        manual_inputs[itype] = json.loads(djson)

    # --- compute estimated range ----------------------------------------
    estimated_range: int | None = None
    gamma_nq_inputs = manual_inputs.get("gamma_nq", {})
    exp_move_max_pct = gamma_nq_inputs.get("exp_move_max_pct")
    if nq_last_price is not None and exp_move_max_pct is not None:
        try:
            estimated_range = round(float(nq_last_price) * float(exp_move_max_pct) / 100)
        except (TypeError, ValueError):
            pass

    # --- assemble template context ---------------------------------------
    context = {
        "session_date": session_date,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timeframe_context": timeframe_context,
        "levels": levels,
        "volatility": volatility,
        "calendar": calendar,
        "overnight": overnight,
        "qqq_nq_ratio": qqq_nq_ratio,
        "manual_inputs": manual_inputs,
        "volatility_indication": volatility_indication,
        "estimated_range": estimated_range,
    }

    # --- render template -------------------------------------------------
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    template = env.get_template(_TEMPLATE_NAME)
    html = template.render(**context)

    # --- write file ------------------------------------------------------
    output_dir = Path(config.report.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{session_date}_premarket.html"
    out_path.write_text(html, encoding="utf-8")

    # --- upsert reports row ----------------------------------------------
    conn.execute(
        "INSERT OR REPLACE INTO reports (session_date, file_path) VALUES (?, ?)",
        (session_date, str(out_path)),
    )
    conn.commit()

    logger.info("Report written: %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(value: str | None) -> dict | list | None:
    if value is None:
        return None
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None

from __future__ import annotations

import logging
import re
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.db import get_connection
from backend.report.generator import generate_report
from backend.state import app_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/report", tags=["report"])


class GenerateReportRequest(BaseModel):
    session_date: str | None = None


class GenerateReportResponse(BaseModel):
    session_date: str
    file_path: str


class ReportMetaResponse(BaseModel):
    session_date: str
    file_path: str
    created_at: str


@router.post("/generate", response_model=GenerateReportResponse, status_code=200)
def generate_report_endpoint(body: GenerateReportRequest = GenerateReportRequest()) -> GenerateReportResponse:
    session_date = body.session_date or str(date.today())
    config = app_state["config"]
    conn = get_connection(app_state["db_path"])
    try:
        out_path = generate_report(session_date, conn, config)
    finally:
        conn.close()
    return GenerateReportResponse(session_date=session_date, file_path=str(out_path))


@router.get("/latest", response_model=ReportMetaResponse)
def get_latest_report() -> ReportMetaResponse:
    today = str(date.today())
    conn = get_connection(app_state["db_path"])
    try:
        row = conn.execute(
            "SELECT session_date, file_path, created_at FROM reports "
            "WHERE session_date = ? ORDER BY created_at DESC LIMIT 1",
            (today,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="No report found for today")
    return ReportMetaResponse(session_date=row[0], file_path=row[1], created_at=row[2])


@router.get("/view/{session_date}")
def view_report(session_date: str) -> FileResponse:
    conn = get_connection(app_state["db_path"])
    try:
        row = conn.execute(
            "SELECT file_path FROM reports WHERE session_date = ? ORDER BY created_at DESC LIMIT 1",
            (session_date,),
        ).fetchone()
    finally:
        conn.close()
    if row is not None:
        file_path = Path(row[0])
        if file_path.exists():
            return FileResponse(path=str(file_path), media_type="text/html")
    # fallback: look for file directly on disk
    output_dir = Path(app_state["config"].report.output_dir)
    candidate = output_dir / f"{session_date}_premarket.html"
    if candidate.exists():
        return FileResponse(path=str(candidate), media_type="text/html")
    raise HTTPException(status_code=404, detail="No report found for this date")


_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_premarket\.html$")


@router.get("/list")
def list_reports() -> list[str]:
    """Return sorted list of available report dates (descending) from disk."""
    output_dir = Path(app_state["config"].report.output_dir)
    if not output_dir.exists():
        return []
    dates = sorted(
        (m.group(1) for f in output_dir.iterdir() if (m := _DATE_RE.match(f.name))),
        reverse=True,
    )
    return dates


"""
scripts/migrate_active_setup_log_to_ny_time.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

One-time migration: convert active_setup_log.marked_at from server-local
(CET, UTC+2) to America/New_York time (EDT = UTC-4 in summer).

Background
----------
Before the fix in session.py (2026-06-07), mark_active_setup stored
marked_at using datetime.now() (server-local CET time).  The auto-tagger
compares marked_at <= trade.entry_datetime as a plain string, and
Sierra Chart exports trade timestamps in NY time.  This means CET-recorded
setups at 15:xx are never <= NY-time trades at 09:xx.

This script back-fills existing rows by converting CET -> NY time.  Use
--session-date to target only specific dates whose trades are not yet tagged.
Without --session-date all rows before the fix date are shown/updated.

Usage
-----
    # Preview changes for a specific date only (safest)
    python backend/scripts/migrate_active_setup_log_to_ny_time.py
        --db data/trading_automation.db --session-date 2026-06-05 --dry-run

    # Apply the migration for that date
    python backend/scripts/migrate_active_setup_log_to_ny_time.py
        --db data/trading_automation.db --session-date 2026-06-05
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Timezone definitions for the conversion.
_CET_TZ = ZoneInfo("Europe/Paris")  # Server timezone (CET/CEST)
_NY_TZ = ZoneInfo("America/New_York")  # Sierra Chart export timezone
_DB_FMT = "%Y-%m-%d %H:%M:%S"

# Default cutoff: only migrate rows recorded before the fix date.
_DEFAULT_CUTOFF = "2026-06-07"


def _cet_to_ny(marked_at_str: str) -> str:
    """Convert a CET/CEST naive datetime string to America/New_York string."""
    naive = datetime.strptime(marked_at_str.strip(), _DB_FMT)
    cet_aware = naive.replace(tzinfo=_CET_TZ)
    ny_aware = cet_aware.astimezone(_NY_TZ)
    return ny_aware.strftime(_DB_FMT)


def migrate(
    db_path: str,
    session_date: str | None = None,
    cutoff_date: str = _DEFAULT_CUTOFF,
    dry_run: bool = False,
) -> None:
    """
    Run the migration against the given database file.

    Parameters
    ----------
    db_path : str
        Path to the SQLite database.
    session_date : str | None
        If given, only migrate rows for this specific session date.
        If None, all rows with session_date < cutoff_date are migrated.
    cutoff_date : str
        Upper bound (exclusive) on session_date for rows to migrate.
        Ignored when session_date is provided.
    dry_run : bool
        If True, print the planned changes but do not write to the database.
    """
    conn = sqlite3.connect(db_path)
    try:
        if session_date:
            rows = conn.execute(
                "SELECT id, session_date, setup_type, marked_at "
                "FROM active_setup_log "
                "WHERE session_date = ? "
                "ORDER BY id",
                (session_date,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, session_date, setup_type, marked_at "
                "FROM active_setup_log "
                "WHERE session_date < ? "
                "ORDER BY id",
                (cutoff_date,),
            ).fetchall()

        if not rows:
            print("No rows matched -- nothing to do.")
            return

        prefix = "DRY RUN: " if dry_run else ""
        print(f"{prefix}Migrating {len(rows)} row(s)...")
        for row_id, s_date, setup_type, marked_at_old in rows:
            marked_at_new = _cet_to_ny(marked_at_old)
            print(
                f"  id={row_id} [{s_date}] {setup_type!r}: "
                f"{marked_at_old} (CET) -> {marked_at_new} (NY)"
            )
            if not dry_run:
                conn.execute(
                    "UPDATE active_setup_log SET marked_at = ? WHERE id = ?",
                    (marked_at_new, row_id),
                )

        if not dry_run:
            conn.commit()
            print(f"Done. Updated {len(rows)} row(s).")
        else:
            print("Dry run complete -- no changes made.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default="data/trading_automation.db",
        help="Path to the SQLite database (default: data/trading_automation.db)",
    )
    parser.add_argument(
        "--session-date",
        help="Migrate only rows for this session_date (e.g. 2026-06-05). "
             "Omit to migrate all rows before the fix date.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the database.",
    )
    args = parser.parse_args()

    if not Path(args.db).exists():
        raise FileNotFoundError(f"Database not found: {args.db}")

    migrate(args.db, session_date=args.session_date, dry_run=args.dry_run)

"""Export all SQLite tables to JSONL files for Postgres import.

One-shot migration tool: reads fastapi_backend_service/dev.db, writes one
JSONL per table under scripts/migration/dumps/<table>.jsonl.

Datetime columns are serialised as ISO8601 strings. JSON text columns stay
as strings (the import side doesn't need to parse them). Boolean columns
are kept as 0/1 integers — the import script handles the conversion
depending on Postgres column type.

Usage:
    cd fastapi_backend_service
    ../.venv/bin/python scripts/migration/export_sqlite.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DUMPS_DIR = SCRIPT_DIR / "dumps"
DEFAULT_SQLITE_PATH = SCRIPT_DIR.parent.parent / "dev.db"

# Order matters: tables with FKs to others must come AFTER their dependencies.
# This ordering is used for the corresponding import step.
TABLE_ORDER = [
    # Independent (no FKs into other app tables)
    "users",
    "event_types",
    "data_subjects",
    "system_parameters",
    "mcp_definitions",
    "items",
    "agent_tools",
    "feedback_logs",
    "mock_data_sources",
    "nats_event_logs",
    "cron_jobs",
    # Depend on users
    "user_preferences",
    "agent_sessions",
    "agent_drafts",
    "agent_memories",
    # Depend on mcp_definitions / event_types / users
    "skill_definitions",
    "routine_checks",
    # Depend on skill_definitions
    "script_versions",
    "auto_patrols",
    # Depend on auto_patrols / execution_logs
    "execution_logs",
    "alarms",
    "generated_events",
]


def _row_to_jsonable(row: sqlite3.Row) -> dict:
    """Convert sqlite3.Row to a plain dict with JSON-safe values."""
    out = {}
    for key in row.keys():
        val = row[key]
        # sqlite3 already returns Python native types for INTEGER/REAL/TEXT/NULL/BLOB
        # BLOB → bytes, skip (we don't have any blob columns)
        if isinstance(val, bytes):
            out[key] = val.decode("utf-8", errors="replace")
        else:
            out[key] = val
    return out


def export_table(conn: sqlite3.Connection, table: str, out_dir: Path) -> int:
    """Dump one table. Returns row count written."""
    cur = conn.execute(f"SELECT * FROM {table}")
    rows = cur.fetchall()

    out_file = out_dir / f"{table}.jsonl"
    with out_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_row_to_jsonable(row), ensure_ascii=False, default=str))
            f.write("\n")

    return len(rows)


def main() -> int:
    sqlite_path = Path(os.getenv("SQLITE_PATH", str(DEFAULT_SQLITE_PATH)))
    if not sqlite_path.exists():
        print(f"❌ SQLite DB not found: {sqlite_path}", file=sys.stderr)
        return 1

    DUMPS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"📤 Exporting from: {sqlite_path}")
    print(f"📁 Output dir:     {DUMPS_DIR}")
    print()

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    # List of tables actually present in this SQLite DB
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'"
        )
    }

    total_rows = 0
    exported_tables = []
    for table in TABLE_ORDER:
        if table not in existing:
            print(f"  ⊘ {table:30s} (not in SQLite — skip)")
            continue
        n = export_table(conn, table, DUMPS_DIR)
        total_rows += n
        exported_tables.append(table)
        print(f"  ✓ {table:30s} {n:>6} rows")

    # Warn about any SQLite tables not in TABLE_ORDER (shouldn't happen, but safety)
    unknown = existing - set(TABLE_ORDER)
    if unknown:
        print()
        print(f"⚠️  {len(unknown)} unknown table(s) in SQLite not exported:")
        for t in sorted(unknown):
            print(f"     {t}")

    conn.close()
    print()
    print(f"✅ Exported {len(exported_tables)} tables, {total_rows} total rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())

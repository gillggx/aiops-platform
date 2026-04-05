"""Import JSONL dumps into Postgres via SQLAlchemy Core.

Reads scripts/migration/dumps/<table>.jsonl produced by export_sqlite.py
and inserts into Postgres. Uses SQLAlchemy Core for type coercion
(datetime, bool, int handled by column types in the metadata).

Post-import:
  - Reset autoincrement sequences so next INSERT uses max(id)+1
  - Run row count verification per table
  - Dump a summary of (sqlite_count, postgres_count, diff)

Usage:
    cd fastapi_backend_service
    DATABASE_URL="postgresql+asyncpg://gill@localhost:5432/aiops" \\
        ../.venv/bin/python scripts/migration/import_postgres.py

Prerequisites:
  - Target Postgres DB has schema already (init_db() ran, tables exist)
  - Tables are EMPTY (no partial previous import — script aborts if not)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DUMPS_DIR = SCRIPT_DIR / "dumps"

# Ensure project root is importable
sys.path.insert(0, str(SCRIPT_DIR.parent.parent))

# Import order resolves the circular dependency between skill_definitions
# and auto_patrols by inserting skills with trigger_patrol_id=NULL first,
# then auto_patrols, then patching skills with their real trigger_patrol_id.
TABLE_ORDER = [
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
    "user_preferences",
    "agent_sessions",
    "agent_drafts",
    "agent_memories",
    "skill_definitions",   # step 1 of cycle break — trigger_patrol_id nulled
    "auto_patrols",         # references skill_definitions.id
    "cron_jobs",            # references skill_definitions.id
    "routine_checks",       # references skill_definitions.id
    "script_versions",      # references skill_definitions.id
    "execution_logs",       # references skill_definitions + auto_patrols
    "alarms",               # references skill_definitions + execution_logs
    # generated_events table was removed in v18 — skip even if SQLite still has it
]

# Columns to null-out during first insert because of FK cycles.
# These are patched back in a second pass after the referenced table exists.
CYCLE_BREAK_COLUMNS = {
    "skill_definitions": ["trigger_patrol_id"],
}


def _coerce_value(col_type: Any, val: Any) -> Any:
    """Convert a JSONL value to the type the target column expects."""
    if val is None:
        return None

    type_str = str(col_type).upper()

    # Datetime: SQLite stored as ISO string, Postgres expects datetime
    if "DATETIME" in type_str or "TIMESTAMP" in type_str:
        if isinstance(val, str):
            # Handle both "2026-04-05 12:34:56" and "2026-04-05T12:34:56" formats
            try:
                return datetime.fromisoformat(val.replace(" ", "T").split("+")[0].rstrip("Z"))
            except ValueError:
                # Some rows might have microseconds: "2026-04-05 12:34:56.789"
                try:
                    return datetime.strptime(val[:26], "%Y-%m-%dT%H:%M:%S.%f")
                except ValueError:
                    return datetime.strptime(val[:19], "%Y-%m-%dT%H:%M:%S")
        return val

    # Boolean: SQLite stored as 0/1 int, Postgres expects True/False
    if "BOOLEAN" in type_str:
        if isinstance(val, (int, bool)):
            return bool(val)
        if isinstance(val, str):
            return val.lower() in ("1", "true", "yes", "t")
        return bool(val)

    return val


def _coerce_row(table_obj: Any, row: dict) -> dict:
    """Apply type coercion to every column in the row."""
    cols_by_name = {c.name: c for c in table_obj.columns}
    out = {}
    for key, val in row.items():
        col = cols_by_name.get(key)
        if col is None:
            # Unknown column — skip (schema drift, safer than failing)
            continue
        out[key] = _coerce_value(col.type, val)
    return out


def _remap_system_user_ids(table: str, rows: list[dict], admin_user_id: int) -> list[dict]:
    """Fix legacy system memories that used user_id=0 (SQLite had FK checks off).

    Any row with user_id=0 in tables that FK to users is remapped to the admin user.
    """
    if table != "agent_memories":
        return rows
    fixed = 0
    for r in rows:
        if r.get("user_id") == 0:
            r["user_id"] = admin_user_id
            fixed += 1
    if fixed:
        print(f"    (remapped {fixed} system memories from user_id=0 to admin id={admin_user_id})")
    return rows


async def verify_empty(engine, table: str) -> bool:
    """Return True if the table is empty."""
    from sqlalchemy import text
    async with engine.connect() as conn:
        result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
        return result.scalar() == 0


def _load_rows(table: str) -> list[dict]:
    src = DUMPS_DIR / f"{table}.jsonl"
    if not src.exists():
        return []
    rows = []
    with src.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


async def import_table(engine, metadata, table: str, admin_user_id: int = 1) -> tuple[int, int]:
    """Import one table. Returns (rows_read, rows_inserted).

    For tables in CYCLE_BREAK_COLUMNS, listed FK columns are temporarily
    nulled during this insert pass. They must be patched afterwards via
    _patch_cycle_break_columns().
    """
    rows = _load_rows(table)
    if not rows:
        print(f"  ○ {table:30s} (empty)")
        return 0, 0

    table_obj = metadata.tables.get(table)
    if table_obj is None:
        print(f"  ⚠️ {table:30s} (table not in ORM metadata — skipping)")
        return len(rows), 0

    # Legacy data fixups (SQLite had FKs off; Postgres is strict)
    rows = _remap_system_user_ids(table, rows, admin_user_id)

    # Cycle-break: temporarily null FK columns that point to tables not yet imported
    cycle_cols = CYCLE_BREAK_COLUMNS.get(table, [])
    if cycle_cols:
        for r in rows:
            for col in cycle_cols:
                if col in r:
                    r[col] = None

    # Coerce each row to the right types
    coerced = [_coerce_row(table_obj, r) for r in rows]

    async with engine.begin() as conn:
        await conn.execute(table_obj.insert(), coerced)

    return len(rows), len(coerced)


async def _patch_cycle_break_columns(engine, metadata) -> None:
    """Second pass: restore FK columns that were nulled during cycle-break insert."""
    from sqlalchemy import update
    for table, cols in CYCLE_BREAK_COLUMNS.items():
        rows = _load_rows(table)
        if not rows:
            continue
        table_obj = metadata.tables.get(table)
        if table_obj is None:
            continue
        updates_applied = 0
        async with engine.begin() as conn:
            for row in rows:
                updates = {}
                for col in cols:
                    if col in row and row[col] is not None:
                        updates[col] = row[col]
                if not updates:
                    continue
                await conn.execute(
                    update(table_obj)
                    .where(table_obj.c.id == row["id"])
                    .values(**updates)
                )
                updates_applied += 1
        if updates_applied:
            print(f"  🔗 {table:30s} patched {updates_applied} cycle-break rows ({', '.join(cols)})")


async def reset_sequences(engine) -> None:
    """Reset autoincrement sequences so SELECT MAX(id) + 1 is next value."""
    from sqlalchemy import text
    # For each table with an id column, setval its sequence
    query = """
    SELECT pg_get_serial_sequence(table_schema || '.' || table_name, 'id') AS seq, table_name
    FROM information_schema.columns
    WHERE column_name = 'id'
      AND table_schema = 'public'
      AND pg_get_serial_sequence(table_schema || '.' || table_name, 'id') IS NOT NULL
    """
    async with engine.connect() as conn:
        result = await conn.execute(text(query))
        seqs = result.fetchall()

    async with engine.begin() as conn:
        for seq_name, table_name in seqs:
            try:
                await conn.execute(text(
                    f"SELECT setval(:seq, COALESCE((SELECT MAX(id) FROM {table_name}), 1), "
                    f"(SELECT MAX(id) IS NOT NULL FROM {table_name}))"
                ), {"seq": seq_name})
            except Exception as exc:
                print(f"  ⚠️ setval failed for {table_name}: {exc}")


async def main() -> int:
    database_url = os.getenv("DATABASE_URL", "")
    if "postgresql" not in database_url:
        print("❌ DATABASE_URL must point at Postgres. Got:", database_url)
        return 1

    os.chdir(SCRIPT_DIR.parent.parent)  # so app imports resolve
    from app import config
    config.get_settings.cache_clear()

    # Trigger model registration
    import main as _main_mod  # noqa
    from app.database import Base, _get_engine

    engine = _get_engine()
    metadata = Base.metadata

    print(f"📥 Importing to:  {engine.url}")
    print(f"📁 Dumps dir:     {DUMPS_DIR}")
    print()

    # Sanity check: target must be empty
    empty_check_table = "users"
    if not await verify_empty(engine, empty_check_table):
        print(f"❌ Table '{empty_check_table}' is not empty. Aborting to avoid data mixing.")
        print("   Drop/recreate the DB first, then run init_db (no seed) before importing.")
        return 1

    # Determine admin user id from the users dump (for FK remapping)
    admin_user_id = 1
    users_dump = DUMPS_DIR / "users.jsonl"
    if users_dump.exists():
        with users_dump.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if row.get("username") == "admin":
                    admin_user_id = row.get("id", 1)
                    break
    print(f"  (admin user id: {admin_user_id})")
    print()

    total_read = 0
    total_inserted = 0
    for table in TABLE_ORDER:
        read, inserted = await import_table(engine, metadata, table, admin_user_id=admin_user_id)
        total_read += read
        total_inserted += inserted
        if inserted > 0:
            print(f"  ✓ {table:30s} {inserted:>6} rows")

    print()
    print("🔗 Patching cycle-break columns...")
    await _patch_cycle_break_columns(engine, metadata)

    print()
    print("🔢 Resetting autoincrement sequences...")
    await reset_sequences(engine)

    # Verification: compare row counts with dumps
    print()
    print("🔍 Verifying row counts...")
    from sqlalchemy import text
    mismatches = []
    async with engine.connect() as conn:
        # Only verify tables that exist in Postgres
        result = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
        ))
        pg_tables = {row[0] for row in result.fetchall()}

        for table in TABLE_ORDER:
            if table not in pg_tables:
                continue
            src = DUMPS_DIR / f"{table}.jsonl"
            expected = sum(1 for _ in src.open(encoding="utf-8")) if src.exists() else 0
            result = await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
            actual = result.scalar()
            status = "✓" if expected == actual else "✗"
            if expected != actual:
                mismatches.append((table, expected, actual))
            if expected > 0 or actual > 0:
                print(f"  {status} {table:30s} expected={expected:>6} actual={actual:>6}")

    await engine.dispose()

    print()
    if mismatches:
        print(f"⚠️  {len(mismatches)} table(s) with count mismatch:")
        for t, e, a in mismatches:
            print(f"     {t}: expected {e}, got {a} (diff {a - e:+d})")
        return 2
    print(f"✅ Imported {total_inserted} rows across all tables, counts match.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

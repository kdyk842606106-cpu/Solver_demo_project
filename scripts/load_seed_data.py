"""
Seed data loader script.

Loads initial data from SQL files into the database.

Usage:
    python scripts/load_seed_data.py [--file seeds/001_initial_data.sql]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.db.session import async_engine


ID_TABLES = [
    "machine_type",
    "machine",
    "state_feature_def",
    "machine_state",
    "machine_state_feature",
    "op_rule",
    "op_rule_precond",
    "op_rule_effect",
    "op_rule_resource_req",
    "resource",
    "solve_request",
    "candidate_plan",
    "candidate_plan_step",
    "schedule_result",
    "blockage_event",
]


def split_sql_statements(sql_content: str) -> list[str]:
    """Split seed SQL into executable statements.

    Seed files in this project do not contain procedural SQL blocks, so a
    semicolon split is sufficient and keeps the loader dependency-free.
    """
    return [statement.strip() for statement in sql_content.split(";") if statement.strip()]


def is_insert_statement(statement: str) -> bool:
    """Return True when a statement starts with INSERT after SQL comments."""
    for line in statement.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        return stripped.upper().startswith("INSERT INTO ")
    return False


def make_conflict_tolerant(statement: str, dialect_name: str, skip_conflicts: bool) -> str:
    """Make PostgreSQL INSERT statements skip duplicate rows when requested."""
    if (
        skip_conflicts
        and dialect_name == "postgresql"
        and is_insert_statement(statement)
        and "ON CONFLICT" not in statement.upper()
    ):
        return f"{statement}\nON CONFLICT DO NOTHING"
    return statement


def is_unique_violation(error: Exception) -> bool:
    """Detect duplicate-key errors from sync/async PostgreSQL drivers."""
    if not isinstance(error, IntegrityError):
        return False
    message = str(error).lower()
    return (
        "uniqueviolation" in message
        or "duplicate key" in message
        or "重复键" in message
        or "唯一约束" in message
    )


async def reset_postgres_sequences(conn) -> int:
    """Move PostgreSQL id sequences past the current max(id) values."""
    if conn.dialect.name != "postgresql":
        return 0

    table_rows = await conn.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
    )
    existing_tables = {row[0] for row in table_rows}
    reset_count = 0

    for table_name in ID_TABLES:
        if table_name not in existing_tables:
            continue

        sequence_name = (
            await conn.execute(
                text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
                {"table_name": table_name},
            )
        ).scalar()
        if not sequence_name:
            continue

        max_id = (
            await conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table_name}"))
        ).scalar()
        if max_id and max_id > 0:
            await conn.execute(
                text("SELECT setval(CAST(:sequence_name AS regclass), :value, true)"),
                {"sequence_name": sequence_name, "value": int(max_id)},
            )
        else:
            await conn.execute(
                text("SELECT setval(CAST(:sequence_name AS regclass), 1, false)"),
                {"sequence_name": sequence_name},
            )
        reset_count += 1

    return reset_count


async def load_seed_data(sql_file: str, skip_conflicts: bool = False) -> None:
    """Load seed data from SQL file."""
    sql_path = Path(sql_file)
    
    if not sql_path.exists():
        print(f"Error: SQL file not found: {sql_path}")
        sys.exit(1)
    
    print(f"Loading seed data from: {sql_path}")
    if skip_conflicts:
        print("Duplicate seed rows will be skipped.")
    
    sql_content = sql_path.read_text(encoding="utf-8")
    statements = split_sql_statements(sql_content)
    executed = 0
    skipped = 0
    
    async with async_engine.connect() as conn:
        dialect_name = conn.dialect.name
        outer_transaction = await conn.begin()
        try:
            # Use a SAVEPOINT per statement so one duplicate does not abort the
            # whole seed load transaction.
            total = len(statements)
            for i, statement in enumerate(statements, 1):
                statement_to_execute = make_conflict_tolerant(
                    statement, dialect_name=dialect_name, skip_conflicts=skip_conflicts
                )
                savepoint = await conn.begin_nested()
                try:
                    await conn.execute(text(statement_to_execute))
                    await savepoint.commit()
                    executed += 1
                    print(f"  [{i}/{total}] Executed statement")
                except Exception as e:
                    await savepoint.rollback()
                    if skip_conflicts and is_unique_violation(e):
                        skipped += 1
                        print(f"  [{i}/{total}] Skipped duplicate statement")
                        continue
                    print(f"  [{i}/{total}] Error: {e}")
                    raise
            reset_count = await reset_postgres_sequences(conn)
            await outer_transaction.commit()
        except Exception:
            await outer_transaction.rollback()
            raise
    
    if reset_count:
        print(f"Reset PostgreSQL id sequences: {reset_count}")
    print(f"Seed data loaded successfully! Executed: {executed}, skipped duplicates: {skipped}")


async def verify_seed_data() -> None:
    """Verify seed data was loaded correctly."""
    print("\nVerifying seed data...")
    
    async with async_engine.connect() as conn:
        # Check machine types
        result = await conn.execute(text("SELECT COUNT(*) FROM machine_type"))
        count = result.scalar()
        print(f"  Machine Types: {count}")
        
        # Check machines
        result = await conn.execute(text("SELECT COUNT(*) FROM machine"))
        count = result.scalar()
        print(f"  Machines: {count}")
        
        # Check state feature definitions
        result = await conn.execute(text("SELECT COUNT(*) FROM state_feature_def"))
        count = result.scalar()
        print(f"  State Feature Defs: {count}")
        
        # Check machine states
        result = await conn.execute(text("SELECT COUNT(*) FROM machine_state"))
        count = result.scalar()
        print(f"  Machine States: {count}")
        
        # Check machine state features
        result = await conn.execute(text("SELECT COUNT(*) FROM machine_state_feature"))
        count = result.scalar()
        print(f"  Machine State Features: {count}")
        
        # Check operation rules
        result = await conn.execute(text("SELECT COUNT(*) FROM op_rule"))
        count = result.scalar()
        print(f"  Operation Rules: {count}")
        
        # Check preconditions
        result = await conn.execute(text("SELECT COUNT(*) FROM op_rule_precond"))
        count = result.scalar()
        print(f"  Preconditions: {count}")
        
        # Check effects
        result = await conn.execute(text("SELECT COUNT(*) FROM op_rule_effect"))
        count = result.scalar()
        print(f"  Effects: {count}")
        
        # Check resources
        result = await conn.execute(text("SELECT COUNT(*) FROM resource"))
        count = result.scalar()
        print(f"  Resources: {count}")
    
    print("\nVerification complete!")


async def main():
    parser = argparse.ArgumentParser(description="Load seed data into database")
    parser.add_argument(
        "--file",
        type=str,
        default="seeds/001_initial_data.sql",
        help="SQL file to load",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing data, don't load",
    )
    parser.add_argument(
        "--skip-conflicts",
        action="store_true",
        help="Skip duplicate rows when loading seed data",
    )
    
    args = parser.parse_args()
    
    if args.verify_only:
        await verify_seed_data()
    else:
        await load_seed_data(args.file, skip_conflicts=args.skip_conflicts)
        await verify_seed_data()
    
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

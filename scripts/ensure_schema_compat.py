"""Small compatibility guard for databases created by earlier dev packages.

This script is intentionally narrow. It only verifies columns that are present
in the current SQLAlchemy model but may be missing from older intranet dev
databases whose Alembic version table was already stamped.
"""
import sys
from pathlib import Path

from sqlalchemy import inspect, text

# When executed as `python scripts/ensure_schema_compat.py`, Python puts the
# scripts directory on sys.path. Add the project root so `app` imports work.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import sync_engine


def main() -> int:
    with sync_engine.begin() as conn:
        inspector = inspect(conn)
        table_names = set(inspector.get_table_names())
        if "solve_request" not in table_names:
            print("[SCHEMA] solve_request table not found; skipping compatibility guard")
            return 0

        columns = {column["name"] for column in inspector.get_columns("solve_request")}
        if "blockage_constraints" in columns:
            print("[SCHEMA] solve_request.blockage_constraints exists")
            return 0

        dialect_name = conn.dialect.name
        if dialect_name == "postgresql":
            conn.execute(text("ALTER TABLE solve_request ADD COLUMN blockage_constraints JSONB"))
        else:
            conn.execute(text("ALTER TABLE solve_request ADD COLUMN blockage_constraints JSON"))

        print("[SCHEMA] Added solve_request.blockage_constraints")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

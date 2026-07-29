"""Read-only release gate for the sunset Scope Guard tables."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db.session import sync_engine


def validate_scope_guard_counts(scope_guard_count: int, precondition_count: int) -> None:
    """Fail release validation when historical Scope Guard data exists."""

    if scope_guard_count or precondition_count:
        raise RuntimeError(
            "SCOPE_GUARD_DATA_PRESENT: release blocked; "
            f"scope_guard={scope_guard_count}, "
            f"scope_guard_precond={precondition_count}. "
            "No automatic conversion or migration is allowed by TICKET-097."
        )


def read_scope_guard_counts() -> tuple[int, int]:
    with sync_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT
                    (SELECT count(*) FROM scope_guard) AS scope_guard_count,
                    (SELECT count(*) FROM scope_guard_precond) AS precondition_count
                """
            )
        ).one()
    return int(row.scope_guard_count), int(row.precondition_count)


def main() -> int:
    counts = read_scope_guard_counts()
    validate_scope_guard_counts(*counts)
    print(f"SCOPE_GUARD_ZERO_OK scope_guard={counts[0]} scope_guard_precond={counts[1]}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

"""Read-only integrity audit for the body/reference model cutover."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

from app.db.session import sync_engine


BLOCKING_KEYS = (
    "atomic_state_with_parent",
    "duplicate_state_reference",
    "duplicate_activity_reference",
    "cross_machine_state_reference",
    "cross_machine_activity_reference",
    "self_state_reference",
    "scope_guard",
    "scope_guard_precondition",
)


def validate_audit_counts(counts: dict[str, int]) -> None:
    blockers = {key: int(counts.get(key, 0)) for key in BLOCKING_KEYS if counts.get(key, 0)}
    if blockers:
        raise RuntimeError(f"BODY_REFERENCE_AUDIT_BLOCKED {json.dumps(blockers, sort_keys=True)}")


def read_audit_report() -> dict[str, Any]:
    count_sql = {
        "atomic_state_with_parent": """
            SELECT count(*) FROM state_node
            WHERE state_kind <> 'aggregate' AND parent_id IS NOT NULL
        """,
        "duplicate_state_reference": """
            SELECT count(*) FROM (
                SELECT state_node_id, parent_state_node_id
                FROM state_node_reference
                GROUP BY state_node_id, parent_state_node_id
                HAVING count(*) > 1
            ) AS duplicate_pairs
        """,
        "duplicate_activity_reference": """
            SELECT count(*) FROM (
                SELECT activity_node_id, atomic_activity_id
                FROM activity_package_atomic_ref
                GROUP BY activity_node_id, atomic_activity_id
                HAVING count(*) > 1
            ) AS duplicate_pairs
        """,
        "cross_machine_state_reference": """
            SELECT count(*)
            FROM state_node_reference AS ref
            JOIN state_node AS body ON body.id = ref.state_node_id
            JOIN state_node AS package ON package.id = ref.parent_state_node_id
            WHERE body.machine_type_id <> package.machine_type_id
        """,
        "cross_machine_activity_reference": """
            SELECT count(*)
            FROM activity_package_atomic_ref AS ref
            JOIN atomic_activity AS body ON body.id = ref.atomic_activity_id
            JOIN activity_node AS package ON package.id = ref.activity_node_id
            WHERE body.machine_type_id <> package.machine_type_id
        """,
        "self_state_reference": """
            SELECT count(*) FROM state_node_reference
            WHERE state_node_id = parent_state_node_id
        """,
        "legacy_activity_node_level3": """
            SELECT count(*) FROM activity_node WHERE level = 3
        """,
        "legacy_activity_rule_binding": """
            SELECT count(*) FROM op_rule WHERE activity_node_id IS NOT NULL
        """,
        "historical_context_input_binding": """
            SELECT count(*) FROM activity_state_binding
            WHERE activity_node_id IS NOT NULL AND binding_role = 'context_input'
        """,
        "historical_declared_output_binding": """
            SELECT count(*) FROM activity_state_binding
            WHERE activity_node_id IS NOT NULL AND binding_role = 'declared_output'
        """,
        "scope_guard": "SELECT count(*) FROM scope_guard",
        "scope_guard_precondition": "SELECT count(*) FROM scope_guard_precond",
    }
    with sync_engine.connect() as connection:
        counts = {
            name: int(connection.execute(text(sql)).scalar_one())
            for name, sql in count_sql.items()
        }
        per_machine_type = [
            dict(row._mapping)
            for row in connection.execute(
                text(
                    """
                    SELECT
                        mt.id AS machine_type_id,
                        mt.code AS machine_type_code,
                        (SELECT count(*) FROM state_node s WHERE s.machine_type_id = mt.id) AS state_body_count,
                        (SELECT count(*) FROM state_node s WHERE s.machine_type_id = mt.id AND s.state_kind = 'aggregate') AS state_package_count,
                        (SELECT count(*) FROM state_node s WHERE s.machine_type_id = mt.id AND s.state_kind <> 'aggregate') AS atomic_state_count,
                        (
                            SELECT count(*) FROM state_node_reference ref
                            JOIN state_node s ON s.id = ref.state_node_id
                            WHERE s.machine_type_id = mt.id
                        ) AS state_reference_count,
                        (SELECT count(*) FROM activity_node a WHERE a.machine_type_id = mt.id AND a.level IN (1, 2)) AS activity_package_count,
                        (SELECT count(*) FROM atomic_activity a WHERE a.machine_type_id = mt.id) AS atomic_activity_count,
                        (
                            SELECT count(*) FROM activity_package_atomic_ref ref
                            JOIN atomic_activity a ON a.id = ref.atomic_activity_id
                            WHERE a.machine_type_id = mt.id
                        ) AS activity_reference_count,
                        (SELECT count(*) FROM activity_state_binding b WHERE b.machine_type_id = mt.id) AS binding_count
                    FROM machine_type mt
                    ORDER BY mt.id
                    """
                )
            )
        ]
    return {
        "schema_version": "body-reference-audit/v1",
        "counts": counts,
        "per_machine_type": per_machine_type,
        "scope_guard_migration_executed": False,
    }


def main() -> int:
    report = read_audit_report()
    validate_audit_counts(report["counts"])
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

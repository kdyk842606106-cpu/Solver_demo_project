"""Deployment and database status checks used by ops scripts and API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from app.db.models import Base
from app.db.session import sync_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class DeployIssue:
    code: str
    message: str
    detail: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


def get_release_info() -> dict[str, Any]:
    """Return release metadata from env vars or VERSION.json when present."""

    version_file = PROJECT_ROOT / "VERSION.json"
    file_payload: dict[str, Any] = {}
    if version_file.exists():
        try:
            file_payload = json.loads(version_file.read_text(encoding="utf-8"))
        except Exception as exc:
            file_payload = {"version_file_error": str(exc)}

    return {
        "app_version": os.getenv("APP_VERSION") or file_payload.get("app_version") or "dev",
        "app_commit": os.getenv("APP_COMMIT") or file_payload.get("app_commit"),
        "release_id": os.getenv("RELEASE_ID") or file_payload.get("release_id"),
        # The deployment API needs to report which metadata source was used,
        # but exposing the server's absolute checkout path is unnecessary.
        "version_file": version_file.name if version_file.exists() else None,
        "version_file_error": file_payload.get("version_file_error"),
    }


def get_alembic_status() -> dict[str, Any]:
    """Return the database revision and migration script heads."""

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    script = ScriptDirectory.from_config(config)
    expected_heads = sorted(script.get_heads())

    with sync_engine.connect() as conn:
        context = MigrationContext.configure(conn)
        current_heads = sorted(context.get_current_heads())

    return {
        "current_heads": current_heads,
        "expected_heads": expected_heads,
        "is_current": current_heads == expected_heads,
    }


def check_schema_columns(max_issues: int = 50) -> list[DeployIssue]:
    """Check that all mapped tables and columns exist in the live database."""

    issues: list[DeployIssue] = []
    with sync_engine.connect() as conn:
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        for table_name, table in sorted(Base.metadata.tables.items()):
            if table_name not in existing_tables:
                issues.append(
                    DeployIssue(
                        code="SCHEMA_TABLE_MISSING",
                        message=f"Mapped table is missing: {table_name}",
                        detail={"table": table_name},
                    )
                )
                if len(issues) >= max_issues:
                    return issues
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name not in existing_columns:
                    issues.append(
                        DeployIssue(
                            code="SCHEMA_COLUMN_MISSING",
                            message=f"Mapped column is missing: {table_name}.{column.name}",
                            detail={"table": table_name, "column": column.name},
                        )
                    )
                    if len(issues) >= max_issues:
                        return issues
    return issues


def _allowed_value_set(payload: Any) -> set[str]:
    if payload is None:
        return set()
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict):
        for key in ("values", "options", "allowed_values", "items"):
            if isinstance(payload.get(key), list):
                values = payload[key]
                break
        else:
            values = list(payload.values())
    else:
        values = [payload]
    return {str(value) for value in values if value is not None}


def _append_rows(
    issues: list[DeployIssue],
    rows: list[Any],
    code: str,
    message: str,
    max_issues: int,
) -> None:
    for row in rows:
        if len(issues) >= max_issues:
            return
        issues.append(DeployIssue(code=code, message=message, detail=dict(row._mapping)))


def check_data_format(max_issues: int = 50) -> list[DeployIssue]:
    """Run data checks that catch common verifier-machine breakages."""

    issues: list[DeployIssue] = []
    with sync_engine.connect() as conn:
        checks = [
            (
                "DATA_MACHINE_STATE_FEATURE_UNKNOWN_KEY",
                "Machine state feature references a feature_key not defined for the machine type.",
                """
                SELECT msf.id, m.code AS machine_code, mt.code AS machine_type_code, msf.feature_key
                FROM machine_state_feature msf
                JOIN machine_state ms ON ms.id = msf.machine_state_id
                JOIN machine m ON m.id = ms.machine_id
                JOIN machine_type mt ON mt.id = m.machine_type_id
                LEFT JOIN state_feature_def sfd
                    ON sfd.machine_type_id = m.machine_type_id
                    AND sfd.feature_key = msf.feature_key
                WHERE sfd.id IS NULL
                ORDER BY msf.id
                LIMIT :limit
                """,
            ),
            (
                "DATA_RULE_PRECOND_UNKNOWN_KEY",
                "Rule precondition references a feature_key not defined for the machine type.",
                """
                SELECT p.id, r.code AS op_rule_code, mt.code AS machine_type_code, p.feature_key
                FROM op_rule_precond p
                JOIN op_rule r ON r.id = p.op_rule_id
                JOIN machine_type mt ON mt.id = r.machine_type_id
                LEFT JOIN state_feature_def sfd
                    ON sfd.machine_type_id = r.machine_type_id
                    AND sfd.feature_key = p.feature_key
                WHERE sfd.id IS NULL
                ORDER BY p.id
                LIMIT :limit
                """,
            ),
            (
                "DATA_RULE_EFFECT_UNKNOWN_KEY",
                "Rule effect references a feature_key not defined for the machine type.",
                """
                SELECT e.id, r.code AS op_rule_code, mt.code AS machine_type_code, e.feature_key
                FROM op_rule_effect e
                JOIN op_rule r ON r.id = e.op_rule_id
                JOIN machine_type mt ON mt.id = r.machine_type_id
                LEFT JOIN state_feature_def sfd
                    ON sfd.machine_type_id = r.machine_type_id
                    AND sfd.feature_key = e.feature_key
                WHERE sfd.id IS NULL
                ORDER BY e.id
                LIMIT :limit
                """,
            ),
            (
                "DATA_STATE_NODE_UNKNOWN_KEY",
                "Atomic state node references a feature_key not defined for the machine type.",
                """
                SELECT sn.id, sn.code AS state_node_code, mt.code AS machine_type_code, sn.feature_key
                FROM state_node sn
                JOIN machine_type mt ON mt.id = sn.machine_type_id
                LEFT JOIN state_feature_def sfd
                    ON sfd.machine_type_id = sn.machine_type_id
                    AND sfd.feature_key = sn.feature_key
                WHERE sn.feature_key IS NOT NULL
                    AND sfd.id IS NULL
                ORDER BY sn.id
                LIMIT :limit
                """,
            ),
        ]

        for code, message, sql in checks:
            rows = list(conn.execute(text(sql), {"limit": max_issues}).fetchall())
            _append_rows(issues, rows, code, message, max_issues)
            if len(issues) >= max_issues:
                return issues

        enum_defs = conn.execute(
            text(
                """
                SELECT machine_type_id, feature_key, allowed_values
                FROM state_feature_def
                WHERE value_type = 'enum' AND allowed_values IS NOT NULL
                """
            )
        ).fetchall()
        allowed_by_key = {
            (row.machine_type_id, row.feature_key): _allowed_value_set(row.allowed_values)
            for row in enum_defs
        }
        allowed_by_key = {key: values for key, values in allowed_by_key.items() if values}

        value_sources = [
            (
                "DATA_MACHINE_STATE_ENUM_VALUE_INVALID",
                "Machine state feature value is outside allowed_values.",
                "feature_value",
                """
                SELECT msf.id, m.machine_type_id, mt.code AS machine_type_code,
                    msf.feature_key, msf.feature_value AS value
                FROM machine_state_feature msf
                JOIN machine_state ms ON ms.id = msf.machine_state_id
                JOIN machine m ON m.id = ms.machine_id
                JOIN machine_type mt ON mt.id = m.machine_type_id
                ORDER BY msf.id
                """,
            ),
            (
                "DATA_RULE_PRECOND_ENUM_VALUE_INVALID",
                "Rule precondition value is outside allowed_values.",
                "feature_value",
                """
                SELECT p.id, r.machine_type_id, mt.code AS machine_type_code,
                    p.feature_key, p.feature_value AS value
                FROM op_rule_precond p
                JOIN op_rule r ON r.id = p.op_rule_id
                JOIN machine_type mt ON mt.id = r.machine_type_id
                ORDER BY p.id
                """,
            ),
            (
                "DATA_RULE_EFFECT_ENUM_VALUE_INVALID",
                "Rule effect value is outside allowed_values.",
                "new_value",
                """
                SELECT e.id, r.machine_type_id, mt.code AS machine_type_code,
                    e.feature_key, e.new_value AS value
                FROM op_rule_effect e
                JOIN op_rule r ON r.id = e.op_rule_id
                JOIN machine_type mt ON mt.id = r.machine_type_id
                ORDER BY e.id
                """,
            ),
            (
                "DATA_STATE_NODE_ENUM_VALUE_INVALID",
                "State node target_value is outside allowed_values.",
                "target_value",
                """
                SELECT sn.id, sn.machine_type_id, mt.code AS machine_type_code,
                    sn.feature_key, sn.target_value AS value
                FROM state_node sn
                JOIN machine_type mt ON mt.id = sn.machine_type_id
                WHERE sn.feature_key IS NOT NULL AND sn.target_value IS NOT NULL
                ORDER BY sn.id
                """,
            ),
        ]

        for code, message, value_field, sql in value_sources:
            for row in conn.execute(text(sql)):
                allowed = allowed_by_key.get((row.machine_type_id, row.feature_key))
                value = None if row.value is None else str(row.value)
                if allowed and value not in allowed:
                    issues.append(
                        DeployIssue(
                            code=code,
                            message=message,
                            detail={
                                "id": row.id,
                                "machine_type_code": row.machine_type_code,
                                "feature_key": row.feature_key,
                                value_field: value,
                                "allowed_values": sorted(allowed),
                            },
                        )
                    )
                    if len(issues) >= max_issues:
                        return issues

    return issues


def build_system_status(include_data_checks: bool = False, max_issues: int = 50) -> dict[str, Any]:
    """Build a deployment-readiness status payload."""

    alembic_status = get_alembic_status()
    schema_issues = check_schema_columns(max_issues=max_issues)
    data_issues = []
    data_checks_skipped = False
    if include_data_checks:
        if schema_issues:
            data_checks_skipped = True
        else:
            data_issues = check_data_format(max_issues=max_issues)
    issues = schema_issues + data_issues

    return {
        "status": "ready" if alembic_status["is_current"] and not issues else "blocked",
        "release": get_release_info(),
        "database": {
            "alembic": alembic_status,
            "schema_issue_count": len(schema_issues),
            "data_issue_count": len(data_issues),
            "data_checks_skipped": data_checks_skipped,
        },
        "issues": [issue.as_dict() for issue in issues[:max_issues]],
        "truncated": len(issues) > max_issues,
    }

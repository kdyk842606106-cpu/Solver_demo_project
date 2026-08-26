"""Move Planner activity targets to runtime state goals.

Revision ID: 017_planner_runtime_state_targets
Revises: 016_planner_compat_merge
Create Date: 2026-08-26
"""

from collections import defaultdict
from typing import Any, Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "017_planner_runtime_state_targets"
down_revision: Union[str, None] = "016_planner_compat_merge"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _convert(scenario: dict[str, Any]) -> bool:
    provenance = scenario.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
        scenario["provenance"] = provenance
    if provenance.get("runtime_state_target_migration_v1"):
        return False
    target_activity_ids = list(scenario.get("target_activity_ids", []))
    target_package_ids = list(scenario.get("target_activity_package_ids", []))
    if not target_activity_ids and not target_package_ids:
        scenario["target_activity_ids"] = []
        scenario["target_activity_package_ids"] = []
        return False

    activities = {item.get("id"): item for item in scenario.get("activities", []) if item.get("id")}
    packages = {item.get("id"): item for item in scenario.get("activity_packages", []) if item.get("id")}
    members_by_package: dict[str, set[str]] = defaultdict(set)
    children: dict[str, list[str]] = defaultdict(list)
    for membership in scenario.get("activity_package_memberships", []):
        members_by_package[membership.get("package_id")].add(membership.get("activity_id"))
    for package in packages.values():
        if package.get("parent_id"):
            children[package["parent_id"]].append(package["id"])

    def members(package_id: str, stack: tuple[str, ...] = ()) -> set[str]:
        if package_id in stack or package_id not in packages:
            return set()
        result = set(members_by_package.get(package_id, set()))
        for child_id in children.get(package_id, []):
            result.update(members(child_id, (*stack, package_id)))
        return result

    converted_ids = set(target_activity_ids)
    for package_id in target_package_ids:
        converted_ids.update(members(package_id))
    converted_ids = {
        activity_id for activity_id in converted_ids
        if activities.get(activity_id, {}).get("is_active", True)
    }
    added_goal_state_ids = sorted({
        activities[activity_id].get("output_state_id")
        for activity_id in converted_ids
        if activity_id in activities and activities[activity_id].get("output_state_id")
    })
    original_goals = list(scenario.get("goal_state_ids", []))
    provenance["runtime_state_target_migration_v1"] = {
        "original_goal_state_ids": original_goals,
        "original_target_activity_ids": target_activity_ids,
        "original_target_activity_package_ids": target_package_ids,
        "added_goal_state_ids": added_goal_state_ids,
    }
    scenario["goal_state_ids"] = sorted(set(original_goals) | set(added_goal_state_ids))
    scenario["target_activity_ids"] = []
    scenario["target_activity_package_ids"] = []
    return True


def upgrade() -> None:
    # The exact revision identifier is 33 characters; older Alembic schemas
    # create version_num as VARCHAR(32).
    op.alter_column(
        "alembic_version",
        "version_num",
        existing_type=sa.String(length=32),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, revision, scenario_json FROM planner_scenario FOR UPDATE")).mappings()
    for row in rows:
        scenario = dict(row["scenario_json"] or {})
        if not _convert(scenario):
            continue
        next_revision = int(row["revision"]) + 1
        scenario["revision"] = next_revision
        bind.execute(
            sa.text(
                "UPDATE planner_scenario SET scenario_json=:scenario, revision=:revision, updated_at=now() WHERE id=:id"
            ).bindparams(sa.bindparam("scenario", type_=postgresql.JSONB)),
            {"scenario": scenario, "revision": next_revision, "id": row["id"]},
        )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, revision, scenario_json FROM planner_scenario FOR UPDATE")).mappings()
    for row in rows:
        scenario = dict(row["scenario_json"] or {})
        provenance = scenario.get("provenance") or {}
        if not isinstance(provenance, dict):
            continue
        marker = provenance.get("runtime_state_target_migration_v1")
        if not marker:
            continue
        scenario["goal_state_ids"] = list(marker.get("original_goal_state_ids", []))
        scenario["target_activity_ids"] = list(marker.get("original_target_activity_ids", []))
        scenario["target_activity_package_ids"] = list(marker.get("original_target_activity_package_ids", []))
        provenance.pop("runtime_state_target_migration_v1", None)
        next_revision = int(row["revision"]) + 1
        scenario["revision"] = next_revision
        bind.execute(
            sa.text(
                "UPDATE planner_scenario SET scenario_json=:scenario, revision=:revision, updated_at=now() WHERE id=:id"
            ).bindparams(sa.bindparam("scenario", type_=postgresql.JSONB)),
            {"scenario": scenario, "revision": next_revision, "id": row["id"]},
        )

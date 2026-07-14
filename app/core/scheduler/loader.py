"""
RAG structure loader module.

Loads candidate plan steps from database, reconstructs the RAG
with operation durations and resource requirements for CP-SAT modeling.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ActivityPackageAtomicRef,
    ActivityNode,
    AtomicActivity,
    CandidatePlan,
    CandidatePlanStep,
    OpRule,
    OpRuleResourceReq,
    Resource,
    StateFeatureDef,
)


@dataclass
class StepData:
    """A single step in the RAG with all data needed for scheduling."""
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    duration_min: int
    step_id: int | None = None
    resource_reqs: list[dict[str, Any]] = field(default_factory=list)
    resource_type: str = "NONE"       # backward compat: primary resource
    resource_qty: int = 0             # backward compat: primary qty
    not_before: int | None = None
    activity_node_id: int | None = None
    activity_node_code: str | None = None
    activity_node_level: int | None = None
    activity_group_id: int | None = None
    activity_group_code: str | None = None
    activity_group_name: str | None = None
    state_continuity_groups: list[dict[str, Any]] = field(default_factory=list)
    atomic_activity_id: int | None = None
    responsible_subsystem: str | None = None
    effect_dimension_keys: list[str] = field(default_factory=list)


@dataclass
class RagData:
    """Complete RAG data structure for CP-SAT modeling."""
    candidate_plan_id: int
    steps: list[StepData]
    edges: list[tuple[int, int]]  # (from_step_order, to_step_order)
    machine_id: int = 0
    solve_request_id: int = 0
    parent_plan_id: int | None = None
    calendar_enabled: bool = False
    schedule_start_at: Any | None = None
    schedule_timezone: str | None = None
    calendar_snapshot: dict[str, Any] | None = None
    constraints: dict[str, Any] | None = None


@dataclass
class ResourceData:
    """Resource instance data."""
    id: int
    code: str
    name: str
    resource_type: str
    capacity: int


async def load_rag(
    candidate_plan_id: int,
    session: AsyncSession,
) -> Optional[RagData]:
    """
    Load RAG structure from database for CP-SAT modeling.

    Joins candidate_plan_step with op_rule to get durations,
    and op_rule_resource_req to get resource requirements.
    Reconstructs edges from predecessor_ids.

    Args:
        candidate_plan_id: ID of the candidate plan
        session: SQLAlchemy async session

    Returns:
        RagData or None if plan not found
    """
    # Load candidate plan with steps
    result = await session.execute(
        select(CandidatePlan)
        .where(CandidatePlan.id == candidate_plan_id)
        .options(
            selectinload(CandidatePlan.steps),
            selectinload(CandidatePlan.solve_request),
        )
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        return None

    if not plan.steps:
        return None

    if plan.solve_request is None:
        return None

    # Load all op_rule data we need in one query
    op_rule_ids = [step.op_rule_id for step in plan.steps]
    rules_result = await session.execute(
        select(OpRule)
        .where(OpRule.id.in_(op_rule_ids))
        .options(
            selectinload(OpRule.resource_reqs),
            selectinload(OpRule.effects),
            selectinload(OpRule.activity_node).selectinload(ActivityNode.parent),
            selectinload(OpRule.atomic_activity)
            .selectinload(AtomicActivity.package_refs)
            .selectinload(ActivityPackageAtomicRef.activity_node),
        )
    )
    rules_map: dict[int, OpRule] = {r.id: r for r in rules_result.scalars().all()}
    machine_type_id = next(iter(rules_map.values())).machine_type_id if rules_map else 0
    feature_result = await session.execute(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    feature_defs = list(feature_result.scalars().all())
    feature_by_key = {item.feature_key: item for item in feature_defs}
    feature_by_id = {item.id: item for item in feature_defs}

    # Build steps and edges
    steps: list[StepData] = []
    edges: list[tuple[int, int]] = []

    for step in sorted(plan.steps, key=lambda s: s.step_order):
        rule = rules_map.get(step.op_rule_id)
        if rule is None:
            continue

        # Collect ALL required resource requirements
        resource_reqs = []
        resource_type = "NONE"
        resource_qty = 0
        for req in rule.resource_reqs:
            if req.is_required:
                resource_reqs.append({
                    "resource_type": req.resource_type,
                    "quantity": req.quantity,
                })
                if resource_type == "NONE":
                    resource_type = req.resource_type
                    resource_qty = req.quantity

        activity_node = rule.activity_node
        atomic_activity = rule.atomic_activity
        activity_group = activity_node.parent if activity_node and activity_node.level == 3 else None
        if atomic_activity is not None:
            activity_node_id = -atomic_activity.id
            activity_node_code = atomic_activity.code
            activity_node_level = 3
            refs = sorted(
                atomic_activity.package_refs,
                key=lambda item: (item.sort_order, item.id),
            )
            activity_group = refs[0].activity_node if refs else None
        else:
            activity_node_id = activity_node.id if activity_node else None
            activity_node_code = activity_node.code if activity_node else None
            activity_node_level = activity_node.level if activity_node else None

        dimension_keys: set[str] = set()
        for effect in rule.effects:
            feature = feature_by_key.get(effect.feature_key)
            if feature is None:
                continue
            template = feature if feature.is_dimension_template else feature_by_id.get(feature.dimension_template_id)
            if template is not None:
                dimension_keys.add(template.feature_key)
        atomic_metadata = (
            atomic_activity.metadata_json
            if atomic_activity is not None and isinstance(atomic_activity.metadata_json, dict)
            else {}
        )
        responsible_subsystem = atomic_metadata.get("responsible_subsystem")
        if responsible_subsystem is not None:
            responsible_subsystem = str(responsible_subsystem).strip() or None

        steps.append(StepData(
            step_order=step.step_order,
            step_id=step.id,
            op_rule_id=rule.id,
            op_rule_code=rule.code,
            op_rule_name=rule.name,
            duration_min=rule.duration_min,
            resource_reqs=resource_reqs,
            resource_type=resource_type,
            resource_qty=resource_qty,
            not_before=step.not_before,
            activity_node_id=activity_node_id,
            activity_node_code=activity_node_code,
            activity_node_level=activity_node_level,
            activity_group_id=activity_group.id if activity_group else None,
            activity_group_code=activity_group.code if activity_group else None,
            activity_group_name=activity_group.name if activity_group else None,
            atomic_activity_id=atomic_activity.id if atomic_activity else None,
            responsible_subsystem=responsible_subsystem,
            effect_dimension_keys=sorted(dimension_keys),
        ))

        # Build edges from predecessor_ids
        if step.predecessor_ids:
            for pred_id in step.predecessor_ids:
                edges.append((pred_id, step.step_order))

    return RagData(
        candidate_plan_id=candidate_plan_id,
        machine_id=plan.solve_request.machine_id,
        solve_request_id=plan.solve_request.id,
        parent_plan_id=plan.solve_request.parent_plan_id,
        calendar_enabled=plan.solve_request.calendar_enabled,
        schedule_start_at=plan.solve_request.schedule_start_at,
        schedule_timezone=plan.solve_request.schedule_timezone,
        calendar_snapshot=plan.solve_request.calendar_snapshot,
        constraints=plan.solve_request.constraints,
        steps=steps,
        edges=edges,
    )


async def load_resources(
    resource_types: list[str],
    session: AsyncSession,
    machine_id: int,
    available_only: bool = True,
) -> list[ResourceData]:
    """
    Load available resources filtered by type.

    Args:
        resource_types: List of resource type strings to load
        machine_id: Machine whose local resource pool should be loaded
        session: SQLAlchemy async session
        available_only: If True, only load available resources

    Returns:
        List of ResourceData
    """
    query = select(Resource).where(
        Resource.machine_id == machine_id,
        Resource.resource_type.in_(resource_types),
    )

    if available_only:
        query = query.where(Resource.is_available == True)

    result = await session.execute(query.order_by(Resource.code))
    resources = result.scalars().all()

    return [
        ResourceData(
            id=r.id,
            code=r.code,
            name=r.name,
            resource_type=r.resource_type,
            capacity=r.capacity,
        )
        for r in resources
    ]


def get_resource_capacity(
    resources: list[ResourceData],
    resource_type: str,
) -> int:
    """
    Get total capacity for a resource type.

    Args:
        resources: List of ResourceData
        resource_type: Resource type to query

    Returns:
        Total capacity (sum of all matching resources' capacity)
    """
    return sum(r.capacity for r in resources if r.resource_type == resource_type)

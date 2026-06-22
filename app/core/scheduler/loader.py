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
)


@dataclass
class StepData:
    """A single step in the RAG with all data needed for scheduling."""
    step_order: int
    op_rule_id: int
    op_rule_code: str
    op_rule_name: str | None
    duration_min: int
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


@dataclass
class RagData:
    """Complete RAG data structure for CP-SAT modeling."""
    candidate_plan_id: int
    steps: list[StepData]
    edges: list[tuple[int, int]]  # (from_step_order, to_step_order)
    machine_id: int = 0


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
            selectinload(OpRule.activity_node).selectinload(ActivityNode.parent),
            selectinload(OpRule.atomic_activity)
            .selectinload(AtomicActivity.package_refs)
            .selectinload(ActivityPackageAtomicRef.activity_node),
        )
    )
    rules_map: dict[int, OpRule] = {r.id: r for r in rules_result.scalars().all()}

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

        steps.append(StepData(
            step_order=step.step_order,
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
        ))

        # Build edges from predecessor_ids
        if step.predecessor_ids:
            for pred_id in step.predecessor_ids:
                edges.append((pred_id, step.step_order))

    return RagData(
        candidate_plan_id=candidate_plan_id,
        machine_id=plan.solve_request.machine_id,
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

"""
RAG structure loader module.

Loads candidate plan steps from database, reconstructs the RAG
with operation durations and resource requirements for CP-SAT modeling.
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
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
    resource_type: str
    resource_qty: int
    not_before: int | None = None


@dataclass
class RagData:
    """Complete RAG data structure for CP-SAT modeling."""
    candidate_plan_id: int
    steps: list[StepData]
    edges: list[tuple[int, int]]  # (from_step_order, to_step_order)


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
        .options(selectinload(CandidatePlan.steps))
    )
    plan = result.scalar_one_or_none()

    if plan is None:
        return None

    if not plan.steps:
        return None

    # Load all op_rule data we need in one query
    op_rule_ids = [step.op_rule_id for step in plan.steps]
    rules_result = await session.execute(
        select(OpRule)
        .where(OpRule.id.in_(op_rule_ids))
        .options(selectinload(OpRule.resource_reqs))
    )
    rules_map: dict[int, OpRule] = {r.id: r for r in rules_result.scalars().all()}

    # Build steps and edges
    steps: list[StepData] = []
    edges: list[tuple[int, int]] = []

    for step in sorted(plan.steps, key=lambda s: s.step_order):
        rule = rules_map.get(step.op_rule_id)
        if rule is None:
            continue

        # Get primary resource requirement (first required one)
        resource_type = "NONE"
        resource_qty = 0
        for req in rule.resource_reqs:
            if req.is_required:
                resource_type = req.resource_type
                resource_qty = req.quantity
                break

        steps.append(StepData(
            step_order=step.step_order,
            op_rule_id=rule.id,
            op_rule_code=rule.code,
            op_rule_name=rule.name,
            duration_min=rule.duration_min,
            resource_type=resource_type,
            resource_qty=resource_qty,
            not_before=step.not_before,
        ))

        # Build edges from predecessor_ids
        if step.predecessor_ids:
            for pred_id in step.predecessor_ids:
                edges.append((pred_id, step.step_order))

    return RagData(
        candidate_plan_id=candidate_plan_id,
        steps=steps,
        edges=edges,
    )


async def load_resources(
    resource_types: list[str],
    session: AsyncSession,
    available_only: bool = True,
) -> list[ResourceData]:
    """
    Load available resources filtered by type.

    Args:
        resource_types: List of resource type strings to load
        session: SQLAlchemy async session
        available_only: If True, only load available resources

    Returns:
        List of ResourceData
    """
    query = select(Resource).where(Resource.resource_type.in_(resource_types))

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

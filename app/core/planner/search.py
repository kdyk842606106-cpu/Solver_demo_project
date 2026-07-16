"""
RAG (Resource-Aware Graph) construction module.

Planner uses an instance-level Partial Order Planner as its main strategy. This
module loads states/rules, delegates planning to partial_order.py, and persists
the resulting operation instances in the Scheduler-compatible RAG contract.
"""

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.planner.matcher import load_rules
from app.core.planner.partial_order import partial_order_plan
from app.core.planner.state import StateDict, is_goal, load_state
from app.core.solver.rule_evaluator import RuleEvaluator
from app.db.models import (
    CandidatePlan,
    CandidatePlanStep,
    Machine,
    MachineState,
    StateFeatureDef,
)


@dataclass
class RAGNode:
    """Represents a node in the RAG."""

    id: int
    op_rule_id: int
    op_rule_code: str
    predecessors: list[int]


@dataclass
class RAG:
    """Represents a Resource-Aware Graph."""

    nodes: list[RAGNode]
    edges: list[tuple[int, int]]  # (from_id, to_id)


@dataclass
class PlanResult:
    """Result of RAG construction."""

    status: str  # "success" | "no_solution" | "error"
    rag: Optional[RAG] = None
    error_message: Optional[str] = None
    diagnostics: dict[str, Any] | None = None


async def _load_feature_defs(
    machine_type_id: int,
    session: AsyncSession,
) -> dict[str, StateFeatureDef]:
    """Load feature definitions for value_type based search guards."""
    result = await session.execute(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    return {item.feature_key: item for item in result.scalars().all()}


async def build_rag(
    current_state_id: int,
    target_state_id: int,
    session: AsyncSession,
    current_state_override: dict | None = None,
    include_repair: bool = False,
) -> PlanResult:
    """
    Build a RAG from partial-order planning.

    Args:
        current_state_id: ID of the current machine state.
        target_state_id: ID of the target machine state.
        session: SQLAlchemy async session.
        current_state_override: Optional feature injection used by Strategy B.
        include_repair: Whether repair rules can be expanded by BFS.
    """
    current_state_override = current_state_override or {}

    current_state = await load_state(current_state_id, session)
    if current_state is None:
        return PlanResult(
            status="error",
            error_message=f"Current state {current_state_id} not found",
        )
    current_state = {**current_state, **current_state_override}

    target_state = await load_state(target_state_id, session)
    if target_state is None:
        return PlanResult(
            status="error",
            error_message=f"Target state {target_state_id} not found",
        )

    if is_goal(current_state, target_state):
        return PlanResult(
            status="no_solution",
            error_message="Already at target state, no operations needed",
        )

    result = await session.execute(
        select(Machine)
        .join(MachineState)
        .where(MachineState.id == current_state_id)
    )
    machine = result.scalar_one_or_none()
    if machine is None:
        return PlanResult(
            status="error",
            error_message="Could not determine machine for state",
        )

    rules = await load_rules(machine.machine_type_id, session, include_repair=include_repair)
    if not rules:
        return PlanResult(
            status="no_solution",
            error_message="No operation rules found for machine type",
        )

    if include_repair and current_state_override:
        target_state = _with_repair_targets(current_state, target_state, rules)

    feature_defs = await _load_feature_defs(machine.machine_type_id, session)
    pop_result = partial_order_plan(
        current_state=current_state,
        target_state=target_state,
        rules=rules,
        feature_defs=feature_defs,
    )
    if pop_result.status != "success":
        return PlanResult(
            status=pop_result.status,
            error_message=pop_result.error_message,
            diagnostics=pop_result.diagnostics,
        )

    rag = RAG(
        nodes=[
            RAGNode(
                id=node.id,
                op_rule_id=node.op_rule_id,
                op_rule_code=node.op_rule_code,
                predecessors=node.predecessors,
            )
            for node in pop_result.nodes
        ],
        edges=pop_result.edges,
    )
    if has_cycle(rag.nodes, rag.edges):
        return PlanResult(
            status="error",
            error_message="Circular dependency detected in RAG",
        )

    return PlanResult(status="success", rag=rag, diagnostics=pop_result.diagnostics)


def _with_repair_targets(
    current_state: StateDict,
    target_state: StateDict,
    rules: list,
) -> StateDict:
    """Add effects of currently applicable repair rules to the BFS goal."""
    evaluator = RuleEvaluator()
    adjusted_target = dict(target_state)
    for rule in rules:
        if not getattr(rule, "is_repair", False):
            continue
        if not evaluator.evaluate_preconditions(current_state, rule.preconditions):
            continue
        for effect in rule.effects:
            adjusted_target[effect.feature_key] = evaluator.apply_effect(
                current_state,
                effect,
            ).get(effect.feature_key, "")
    return adjusted_target


def has_cycle(nodes: list[RAGNode], edges: list[tuple[int, int]]) -> bool:
    """
    Check if the RAG has a cycle using DFS.

    Args:
        nodes: List of RAG nodes
        edges: List of (from, to) edges

    Returns:
        True if a cycle exists
    """
    adj: dict[int, list[int]] = {n.id: [] for n in nodes}
    for from_id, to_id in edges:
        adj[from_id].append(to_id)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def dfs(node_id: int) -> bool:
        color[node_id] = GRAY
        for neighbor in adj.get(node_id, []):
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE:
                if dfs(neighbor):
                    return True
        color[node_id] = BLACK
        return False

    for node in nodes:
        if color[node.id] == WHITE:
            if dfs(node.id):
                return True

    return False


async def save_candidate_plan(
    rag: RAG,
    solve_request_id: int,
    session: AsyncSession,
    version: int = 1,
    parent_plan_id: int | None = None,
    replan_reason: str | None = None,
) -> int:
    """
    Save a RAG to the database as a candidate plan.

    Args:
        rag: RAG to save
        solve_request_id: ID of the solve request
        session: SQLAlchemy async session
        version: Plan version number (default 1)
        parent_plan_id: Parent plan ID for version chain (default None)
        replan_reason: Reason for replan (default None)

    Returns:
        ID of the created candidate_plan
    """
    candidate_plan = CandidatePlan(
        solve_request_id=solve_request_id,
        total_steps=len(rag.nodes),
        search_method="partial_order",
        version=version,
        parent_plan_id=parent_plan_id,
        replan_reason=replan_reason,
    )
    session.add(candidate_plan)
    await session.flush()

    for node in rag.nodes:
        step = CandidatePlanStep(
            candidate_plan_id=candidate_plan.id,
            step_order=node.id,
            op_rule_id=node.op_rule_id,
            predecessor_ids=node.predecessors,
        )
        session.add(step)

    return candidate_plan.id


def format_rag(rag: RAG) -> str:
    """
    Format RAG as a human-readable string.

    Args:
        rag: RAG to format

    Returns:
        Human-readable string representation
    """
    lines = ["RAG Structure:"]
    lines.append("-" * 40)

    for node in rag.nodes:
        preds = ", ".join(str(p) for p in node.predecessors) or "none"
        lines.append(f"  Node {node.id}: {node.op_rule_code} (predecessors: {preds})")

    if rag.edges:
        lines.append("")
        lines.append("Dependencies:")
        for from_id, to_id in rag.edges:
            lines.append(f"  {from_id} -> {to_id}")

    parallel_groups = find_parallel_groups(rag)
    if parallel_groups:
        lines.append("")
        lines.append("Parallel opportunities:")
        for group in parallel_groups:
            lines.append(f"  Nodes {group} can run in parallel")

    return "\n".join(lines)


def find_parallel_groups(rag: RAG) -> list[list[int]]:
    """
    Find groups of nodes that can run in parallel.

    Two nodes can run in parallel if they have the same predecessors
    (or both have no predecessors).
    """
    pred_groups: dict[frozenset[int], list[int]] = {}

    for node in rag.nodes:
        pred_key = frozenset(node.predecessors)
        if pred_key not in pred_groups:
            pred_groups[pred_key] = []
        pred_groups[pred_key].append(node.id)

    parallel_groups = []
    for group in pred_groups.values():
        if len(group) > 1:
            parallel_groups.append(sorted(group))

    return parallel_groups

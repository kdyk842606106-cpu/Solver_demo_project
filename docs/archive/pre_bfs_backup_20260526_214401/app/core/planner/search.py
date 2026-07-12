"""
RAG (Resource-Aware Graph) construction module.

This module implements the core algorithm for building a RAG from
state inference - deriving operation dependencies from precondition/effect chains.

Key concepts:
- State delta: difference between current and target states
- Effect matching: finding operations that can produce required effects
- Precondition analysis: determining which operations depend on others
- Parallel emergence: operations without mutual dependencies can run in parallel
"""

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CandidatePlan,
    CandidatePlanStep,
    Machine,
    MachineState,
    OpRule,
    StateFeatureDef,
)
from app.core.planner.state import StateDict, load_state, compute_state_delta, is_goal
from app.core.planner.matcher import (
    load_rules,
    check_preconditions,
    find_ops_for_delta,
    find_provider,
    rule_summary,
)
from app.core.planner.numeric import (
    NUMERIC_IMPLICIT_GOAL_CYCLE,
    NUMERIC_NO_PROVIDER,
    plan_exact_numeric_feature,
)
from app.core.solver.rule_evaluator import RuleEvaluator


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


async def _load_feature_defs(
    machine_type_id: int,
    session: AsyncSession,
) -> dict[str, StateFeatureDef]:
    """Load feature definitions for value_type based planner routing."""
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
    Build a RAG (Resource-Aware Graph) from state inference.

    This is the core algorithm for the Planner module. It:
    1. Computes the state delta (what needs to change)
    2. Finds operations that can eliminate each delta
    3. Analyzes preconditions to derive dependencies
    4. Constructs the RAG with parallel opportunities

    Args:
        current_state_id: ID of the current machine state
        target_state_id: ID of the target machine state
        session: SQLAlchemy async session
        current_state_override: Optional dict of feature_key->value to inject into
            current state before building RAG (used by Strategy B to inject blockage_reason)
        include_repair: If True, include is_repair=TRUE operations in rule loading

    Returns:
        PlanResult with RAG or error
    """
    current_state_override = current_state_override or {}

    current_state = await load_state(current_state_id, session)
    if current_state is None:
        return PlanResult(
            status="error",
            error_message=f"Current state {current_state_id} not found"
        )

    current_state = {**current_state, **current_state_override}

    target_state = await load_state(target_state_id, session)
    if target_state is None:
        return PlanResult(
            status="error",
            error_message=f"Target state {target_state_id} not found"
        )

    # Check if already at goal
    if is_goal(current_state, target_state):
        return PlanResult(
            status="no_solution",
            error_message="Already at target state, no operations needed"
        )

    # Compute state delta
    delta = compute_state_delta(current_state, target_state)

    if not delta:
        return PlanResult(
            status="no_solution",
            error_message="No state differences found"
        )

    # ============================================================
    # Phase 2: Get machine type and load rules
    # ============================================================

    # Get machine type from current state
    result = await session.execute(
        select(Machine)
        .join(MachineState)
        .where(MachineState.id == current_state_id)
    )
    machine = result.scalar_one_or_none()

    if machine is None:
        return PlanResult(
            status="error",
            error_message="Could not determine machine for state"
        )

    feature_defs = await _load_feature_defs(machine.machine_type_id, session)

    # Load all active operation rules
    rules = await load_rules(machine.machine_type_id, session, include_repair=include_repair)

    if not rules:
        return PlanResult(
            status="no_solution",
            error_message="No operation rules found for machine type"
        )

    # ============================================================
    # Phase 3: Find operations for each state delta
    # ============================================================

    needed_ops: list[OpRule] = []
    numeric_plans = []

    for feature_key, (current_val, target_val) in delta.items():
        feature_def = feature_defs.get(feature_key)
        if feature_def is not None and feature_def.value_type == "number":
            numeric_result = plan_exact_numeric_feature(
                feature_key=feature_key,
                current_state=current_state,
                target_value=target_val,
                rules=rules,
            )
            if numeric_result.status == "success":
                if numeric_result.steps:
                    numeric_plans.append(numeric_result)
                continue
            # Existing V0.2 numeric scenarios can still use set effects for
            # exact targets; only route to numeric chaining when a provider exists.
            if numeric_result.error_code != NUMERIC_NO_PROVIDER:
                return PlanResult(
                    status=(
                        "error"
                        if numeric_result.error_code == NUMERIC_IMPLICIT_GOAL_CYCLE
                        else "no_solution" if numeric_result.status == "no_solution" else "error"
                    ),
                    error_message=numeric_result.error_message,
                )

        # Find operations that can produce this effect
        candidates = find_ops_for_delta(feature_key, target_val, rules, current_state)

        if not candidates:
            return PlanResult(
                status="no_solution",
                error_message=f"No operation can set {feature_key} to {target_val}"
            )

        # Prefer candidates whose preconditions are already satisfied
        # by the current state (avoids selecting ops that need chaining)
        satisfiable = [
            c for c in candidates
            if check_preconditions(current_state, c.preconditions)
        ]

        if satisfiable:
            best = min(satisfiable, key=lambda r: r.duration_min)
        else:
            # No directly satisfiable candidate — pick shortest and
            # rely on Phase 4 to discover intermediate operations
            best = min(candidates, key=lambda r: r.duration_min)

        # Avoid duplicates (one operation might fix multiple deltas)
        if best.id not in [op.id for op in needed_ops]:
            needed_ops.append(best)

    # When a strategy B override is active, proactively include repair rules
    # whose preconditions are satisfied by the (overridden) current state.
    # These rules won't appear via the delta loop because the target state
    # typically doesn't declare the injected feature key (e.g. blockage_reason).
    if include_repair and current_state_override:
        for rule in rules:
            if not rule.is_repair:
                continue
            if check_preconditions(current_state, rule.preconditions):
                if rule.id not in [op.id for op in needed_ops]:
                    needed_ops.append(rule)

    # ============================================================
    # Phase 4: Analyze preconditions and build RAG
    # ============================================================

    # Node bookkeeping — will grow as intermediate ops are discovered
    op_id_to_node_id: dict[int, int] = {}
    nodes: list[RAGNode] = []
    edges: list[tuple[int, int]] = []

    def _ensure_node(op: OpRule) -> int:
        """Create a RAG node for *op* if one does not already exist."""
        if op.id not in op_id_to_node_id:
            nid = len(nodes) + 1
            op_id_to_node_id[op.id] = nid
            nodes.append(RAGNode(
                id=nid, op_rule_id=op.id,
                op_rule_code=op.code, predecessors=[],
            ))
        return op_id_to_node_id[op.id]

    # Seed nodes for the initial needed_ops
    for op in needed_ops:
        _ensure_node(op)

    # Worklist: process each op (list may grow during iteration)
    processed_idx = 0
    max_ops = 50  # safety cap

    while processed_idx < len(needed_ops) and processed_idx < max_ops:
        op = needed_ops[processed_idx]
        node_id = op_id_to_node_id[op.id]

        for precond in op.preconditions:
            evaluator = RuleEvaluator()
            if evaluator.evaluate_precondition(current_state, precond):
                continue

            # Look for a provider among already-needed ops
            provider = find_provider(
                precond.feature_key,
                precond.feature_value,
                needed_ops,
                exclude=op,
                current_state=current_state,
            )

            if provider is None:
                # Search ALL rules for an intermediate operation
                intermediate_candidates = find_ops_for_delta(
                    precond.feature_key, precond.feature_value, rules, current_state,
                )
                intermediate_candidates = [
                    c for c in intermediate_candidates if c.id != op.id
                ]

                if intermediate_candidates:
                    # Prefer one whose own preconditions are met by current state
                    sat = [
                        c for c in intermediate_candidates
                        if check_preconditions(current_state, c.preconditions)
                    ]
                    provider = (
                        min(sat, key=lambda r: r.duration_min)
                        if sat
                        else min(intermediate_candidates, key=lambda r: r.duration_min)
                    )
                    # Add to worklist so its own preconditions are processed
                    if provider.id not in [o.id for o in needed_ops]:
                        needed_ops.append(provider)
                    _ensure_node(provider)

            if provider is not None:
                _ensure_node(provider)
                provider_node_id = op_id_to_node_id[provider.id]
                edge = (provider_node_id, node_id)
                if edge not in edges:
                    edges.append(edge)
                    # node_id is 1-indexed, nodes list is 0-indexed
                    nodes[node_id - 1].predecessors.append(provider_node_id)

        processed_idx += 1

    for numeric_result in numeric_plans:
        instance_to_node_id: dict[str, int] = {}
        for planned_step in numeric_result.steps:
            node_id = len(nodes) + 1
            instance_to_node_id[planned_step.instance_id] = node_id

            predecessor_ids = [
                instance_to_node_id[instance_id]
                for instance_id in planned_step.predecessor_instance_ids
                if instance_id in instance_to_node_id
            ]

            nodes.append(RAGNode(
                id=node_id,
                op_rule_id=planned_step.op_rule.id,
                op_rule_code=planned_step.op_rule.code,
                predecessors=predecessor_ids,
            ))

            for predecessor_id in predecessor_ids:
                edge = (predecessor_id, node_id)
                if edge not in edges:
                    edges.append(edge)

    # ============================================================
    # Phase 5: Validate RAG (check for cycles)
    # ============================================================

    if has_cycle(nodes, edges):
        return PlanResult(
            status="error",
            error_message="Circular dependency detected in RAG"
        )

    # ============================================================
    # Phase 6: Return result
    # ============================================================

    rag = RAG(nodes=nodes, edges=edges)

    return PlanResult(
        status="success",
        rag=rag
    )


def has_cycle(nodes: list[RAGNode], edges: list[tuple[int, int]]) -> bool:
    """
    Check if the RAG has a cycle using DFS.

    Args:
        nodes: List of RAG nodes
        edges: List of (from, to) edges

    Returns:
        True if a cycle exists
    """
    # Build adjacency list
    adj: dict[int, list[int]] = {n.id: [] for n in nodes}
    for from_id, to_id in edges:
        adj[from_id].append(to_id)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def dfs(node_id: int) -> bool:
        color[node_id] = GRAY
        for neighbor in adj.get(node_id, []):
            if color[neighbor] == GRAY:
                return True  # Back edge found - cycle!
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
        search_method="state_inference",
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
            lines.append(f"  {from_id} → {to_id}")

    # Identify parallel opportunities
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

    Args:
        rag: RAG to analyze

    Returns:
        List of node ID groups that can run in parallel
    """
    # Group nodes by their predecessor set
    pred_groups: dict[frozenset[int], list[int]] = {}

    for node in rag.nodes:
        pred_key = frozenset(node.predecessors)
        if pred_key not in pred_groups:
            pred_groups[pred_key] = []
        pred_groups[pred_key].append(node.id)

    # Return groups with more than one node
    parallel_groups = []
    for group in pred_groups.values():
        if len(group) > 1:
            parallel_groups.append(sorted(group))

    return parallel_groups

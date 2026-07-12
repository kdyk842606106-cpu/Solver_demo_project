"""
Forward BFS state-space search for planner rule selection.

The search expands executable operation rules from the current state and stops
when the original state delta has been satisfied.  Rule checks and effects stay
behind RuleEvaluator so operator/effect registries remain the single entrypoint.
"""

from collections import Counter, deque
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.core.planner.state import StateDict, compute_state_delta, freeze
from app.core.solver.rule_evaluator import RuleEvaluator
from app.db.models import OpRule, StateFeatureDef


BFS_LIMIT_EXCEEDED = "BFS_LIMIT_EXCEEDED"
BFS_NO_SOLUTION = "BFS_NO_SOLUTION"
BFS_INVALID_NUMERIC_VALUE = "BFS_INVALID_NUMERIC_VALUE"


@dataclass(frozen=True)
class BfsLimits:
    """Safety limits for forward search."""

    max_depth: int = 50
    max_nodes: int = 2000


@dataclass
class Transition:
    """One instantiated operation rule in a discovered search path."""

    rule: OpRule
    before_state: StateDict
    after_state: StateDict


@dataclass
class SearchNode:
    """A BFS frontier item."""

    state: StateDict
    path: list[Transition] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.path)


@dataclass
class BfsPlanResult:
    """Result of forward BFS planning."""

    status: str  # success | no_solution | error
    path: list[Transition] = field(default_factory=list)
    final_state: StateDict | None = None
    error_code: str | None = None
    error_message: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)


def forward_bfs_plan(
    current_state: StateDict,
    target_state: StateDict,
    rules: list[OpRule],
    feature_defs: dict[str, StateFeatureDef],
    limits: BfsLimits | None = None,
) -> BfsPlanResult:
    """
    Search forward from current_state until all initially different target
    features are satisfied.

    The goal is intentionally the initial delta subset, not every target feature.
    This preserves existing planner semantics where temporary support features
    may move away from their original value while enabling a target-changing op.
    """
    limits = limits or BfsLimits()
    goal_state = _goal_state(current_state, target_state, feature_defs)
    base_diagnostics = {
        "rules_count": len(rules),
        "goal_feature_count": len(goal_state),
        "goal_features": sorted(goal_state.keys()),
        "max_depth_limit": limits.max_depth,
        "max_nodes_limit": limits.max_nodes,
    }
    if not goal_state:
        return BfsPlanResult(
            status="success",
            final_state=dict(current_state),
            diagnostics={
                **base_diagnostics,
                "expanded_nodes": 0,
                "visited_count": 1,
                "queue_size": 0,
                "queue_size_peak": 1,
                "max_depth_seen": 0,
                "limit_type": None,
                "path_length": 0,
                "matched_goal_features": [],
                "unmatched_goal_features": [],
                **_empty_search_stats(),
            },
        )

    bounds_result = _build_numeric_bounds(
        current_state=current_state,
        target_state=target_state,
        goal_state=goal_state,
        rules=rules,
        feature_defs=feature_defs,
    )
    if isinstance(bounds_result, BfsPlanResult):
        bounds_result.diagnostics = {
            **base_diagnostics,
            **bounds_result.diagnostics,
        }
        return bounds_result
    numeric_bounds = bounds_result

    evaluator = RuleEvaluator()
    ordered_rules = sorted(rules, key=lambda rule: (rule.duration_min, rule.id or 0))
    queue: deque[SearchNode] = deque([SearchNode(state=dict(current_state))])
    visited = {freeze(current_state)}
    expanded_nodes = 0
    limit_reached = False
    limit_type: str | None = None
    max_depth_seen = 0
    queue_size_peak = len(queue)
    last_node = SearchNode(state=dict(current_state))
    rule_checks = 0
    precondition_checks = 0
    precondition_failures = 0
    executable_transitions = 0
    effect_applications = 0
    enqueued_nodes = 0
    no_progress_skips = 0
    numeric_bound_skips = 0
    duplicate_state_skips = 0
    depth_expanded: Counter[int] = Counter()
    depth_enqueued: Counter[int] = Counter()
    depth_executable: Counter[int] = Counter()
    executable_rule_counts: Counter[str] = Counter()
    enqueued_rule_counts: Counter[str] = Counter()
    skip_reason_counts: Counter[str] = Counter()

    while queue:
        node = queue.popleft()
        last_node = node
        expanded_nodes += 1
        max_depth_seen = max(max_depth_seen, node.depth)
        depth_expanded[node.depth] += 1
        if expanded_nodes > limits.max_nodes:
            limit_reached = True
            limit_type = "max_nodes"
            break

        if _matches_goal(node.state, goal_state, feature_defs):
            return BfsPlanResult(
                status="success",
                path=node.path,
                final_state=dict(node.state),
                diagnostics=_search_diagnostics(
                    goal_state=goal_state,
                    state=node.state,
                    feature_defs=feature_defs,
                    base=base_diagnostics,
                    expanded_nodes=expanded_nodes,
                    visited_count=len(visited),
                    queue_size=len(queue),
                    queue_size_peak=queue_size_peak,
                    max_depth_seen=max_depth_seen,
                    limit_type=None,
                    path_length=len(node.path),
                    extra=_search_stats(
                        rule_checks=rule_checks,
                        precondition_checks=precondition_checks,
                        precondition_failures=precondition_failures,
                        executable_transitions=executable_transitions,
                        effect_applications=effect_applications,
                        enqueued_nodes=enqueued_nodes,
                        no_progress_skips=no_progress_skips,
                        numeric_bound_skips=numeric_bound_skips,
                        duplicate_state_skips=duplicate_state_skips,
                        depth_expanded=depth_expanded,
                        depth_enqueued=depth_enqueued,
                        depth_executable=depth_executable,
                        executable_rule_counts=executable_rule_counts,
                        enqueued_rule_counts=enqueued_rule_counts,
                        skip_reason_counts=skip_reason_counts,
                    ),
                ),
            )

        if node.depth >= limits.max_depth:
            limit_reached = True
            if limit_type is None:
                limit_type = "max_depth"
            continue

        for rule in ordered_rules:
            rule_checks += 1
            precondition_checks += len(rule.preconditions)
            if not evaluator.evaluate_preconditions(node.state, rule.preconditions):
                precondition_failures += 1
                skip_reason_counts["precondition_failed"] += 1
                continue

            executable_transitions += 1
            depth_executable[node.depth] += 1
            executable_rule_counts[_rule_label(rule)] += 1
            effect_applications += 1
            next_state = evaluator.apply_effects(node.state, rule.effects)
            if freeze(next_state) == freeze(node.state):
                no_progress_skips += 1
                skip_reason_counts["no_progress"] += 1
                continue
            if not _within_numeric_bounds(next_state, numeric_bounds):
                numeric_bound_skips += 1
                skip_reason_counts["numeric_bound"] += 1
                continue

            state_key = freeze(next_state)
            if state_key in visited:
                duplicate_state_skips += 1
                skip_reason_counts["duplicate_state"] += 1
                continue

            visited.add(state_key)
            enqueued_nodes += 1
            depth_enqueued[node.depth + 1] += 1
            enqueued_rule_counts[_rule_label(rule)] += 1
            queue.append(
                SearchNode(
                    state=next_state,
                    path=[
                        *node.path,
                        Transition(
                            rule=rule,
                            before_state=dict(node.state),
                            after_state=dict(next_state),
                        ),
                    ],
                )
            )
            queue_size_peak = max(queue_size_peak, len(queue))

    if limit_reached:
        return BfsPlanResult(
            status="no_solution",
            error_code=BFS_LIMIT_EXCEEDED,
            error_message=(
                f"Forward BFS exceeded limits: max_depth={limits.max_depth}, "
                f"max_nodes={limits.max_nodes}"
            ),
            diagnostics=_search_diagnostics(
                goal_state=goal_state,
                state=last_node.state,
                feature_defs=feature_defs,
                base=base_diagnostics,
                expanded_nodes=expanded_nodes,
                visited_count=len(visited),
                queue_size=len(queue),
                queue_size_peak=queue_size_peak,
                max_depth_seen=max_depth_seen,
                limit_type=limit_type,
                path_length=len(last_node.path),
                extra=_search_stats(
                    rule_checks=rule_checks,
                    precondition_checks=precondition_checks,
                    precondition_failures=precondition_failures,
                    executable_transitions=executable_transitions,
                    effect_applications=effect_applications,
                    enqueued_nodes=enqueued_nodes,
                    no_progress_skips=no_progress_skips,
                    numeric_bound_skips=numeric_bound_skips,
                    duplicate_state_skips=duplicate_state_skips,
                    depth_expanded=depth_expanded,
                    depth_enqueued=depth_enqueued,
                    depth_executable=depth_executable,
                    executable_rule_counts=executable_rule_counts,
                    enqueued_rule_counts=enqueued_rule_counts,
                    skip_reason_counts=skip_reason_counts,
                ),
            ),
        )

    return BfsPlanResult(
        status="no_solution",
        error_code=BFS_NO_SOLUTION,
        error_message="No forward BFS path can reach the target state",
        diagnostics=_search_diagnostics(
            goal_state=goal_state,
            state=last_node.state,
            feature_defs=feature_defs,
            base=base_diagnostics,
            expanded_nodes=expanded_nodes,
            visited_count=len(visited),
            queue_size=len(queue),
            queue_size_peak=queue_size_peak,
            max_depth_seen=max_depth_seen,
            limit_type=None,
            path_length=len(last_node.path),
            extra=_search_stats(
                rule_checks=rule_checks,
                precondition_checks=precondition_checks,
                precondition_failures=precondition_failures,
                executable_transitions=executable_transitions,
                effect_applications=effect_applications,
                enqueued_nodes=enqueued_nodes,
                no_progress_skips=no_progress_skips,
                numeric_bound_skips=numeric_bound_skips,
                duplicate_state_skips=duplicate_state_skips,
                depth_expanded=depth_expanded,
                depth_enqueued=depth_enqueued,
                depth_executable=depth_executable,
                executable_rule_counts=executable_rule_counts,
                enqueued_rule_counts=enqueued_rule_counts,
                skip_reason_counts=skip_reason_counts,
            ),
        ),
    )


def _search_diagnostics(
    goal_state: StateDict,
    state: StateDict,
    feature_defs: dict[str, StateFeatureDef],
    base: dict[str, object],
    expanded_nodes: int,
    visited_count: int,
    queue_size: int,
    queue_size_peak: int,
    max_depth_seen: int,
    limit_type: str | None,
    path_length: int,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    matched_goal_features = sorted(
        key
        for key, target_value in goal_state.items()
        if _values_equal(state.get(key), target_value, feature_defs.get(key))
    )
    unmatched_goal_features = sorted(
        key for key in goal_state.keys() if key not in matched_goal_features
    )
    return {
        **base,
        "expanded_nodes": expanded_nodes,
        "visited_count": visited_count,
        "queue_size": queue_size,
        "queue_size_peak": queue_size_peak,
        "max_depth_seen": max_depth_seen,
        "limit_type": limit_type,
        "path_length": path_length,
        "matched_goal_features": matched_goal_features,
        "unmatched_goal_features": unmatched_goal_features,
        **(extra or {}),
    }


def _empty_search_stats() -> dict[str, object]:
    return {
        "rule_checks": 0,
        "precondition_checks": 0,
        "precondition_failures": 0,
        "executable_transitions": 0,
        "effect_applications": 0,
        "enqueued_nodes": 0,
        "no_progress_skips": 0,
        "numeric_bound_skips": 0,
        "duplicate_state_skips": 0,
        "skip_reason_counts": {},
        "branching_factor": 0,
        "enqueue_rate": 0,
        "depth_expanded": {},
        "depth_enqueued": {},
        "depth_executable": {},
        "top_executable_rules": [],
        "top_enqueued_rules": [],
    }


def _search_stats(
    rule_checks: int,
    precondition_checks: int,
    precondition_failures: int,
    executable_transitions: int,
    effect_applications: int,
    enqueued_nodes: int,
    no_progress_skips: int,
    numeric_bound_skips: int,
    duplicate_state_skips: int,
    depth_expanded: Counter[int],
    depth_enqueued: Counter[int],
    depth_executable: Counter[int],
    executable_rule_counts: Counter[str],
    enqueued_rule_counts: Counter[str],
    skip_reason_counts: Counter[str],
) -> dict[str, object]:
    expanded_total = sum(depth_expanded.values())
    return {
        "rule_checks": rule_checks,
        "precondition_checks": precondition_checks,
        "precondition_failures": precondition_failures,
        "executable_transitions": executable_transitions,
        "effect_applications": effect_applications,
        "enqueued_nodes": enqueued_nodes,
        "no_progress_skips": no_progress_skips,
        "numeric_bound_skips": numeric_bound_skips,
        "duplicate_state_skips": duplicate_state_skips,
        "skip_reason_counts": dict(sorted(skip_reason_counts.items())),
        "branching_factor": round(enqueued_nodes / expanded_total, 4)
        if expanded_total
        else 0,
        "enqueue_rate": round(enqueued_nodes / executable_transitions, 4)
        if executable_transitions
        else 0,
        "depth_expanded": _counter_by_depth(depth_expanded),
        "depth_enqueued": _counter_by_depth(depth_enqueued),
        "depth_executable": _counter_by_depth(depth_executable),
        "top_executable_rules": _top_counter_items(executable_rule_counts),
        "top_enqueued_rules": _top_counter_items(enqueued_rule_counts),
    }


def _counter_by_depth(counter: Counter[int]) -> dict[str, int]:
    return {str(depth): count for depth, count in sorted(counter.items())}


def _top_counter_items(counter: Counter[str], limit: int = 10) -> list[dict[str, object]]:
    return [
        {"rule": rule, "count": count}
        for rule, count in counter.most_common(limit)
    ]


def _rule_label(rule: OpRule) -> str:
    return f"{getattr(rule, 'code', '') or 'UNKNOWN'}#{getattr(rule, 'id', '')}"


def _goal_state(
    current_state: StateDict,
    target_state: StateDict,
    feature_defs: dict[str, StateFeatureDef],
) -> StateDict:
    goal: StateDict = {}
    for key, (_, target_value) in compute_state_delta(current_state, target_state).items():
        current_value = current_state.get(key)
        if not _values_equal(current_value, target_value, feature_defs.get(key)):
            goal[key] = target_value
    return goal


def _matches_goal(
    state: StateDict,
    goal_state: StateDict,
    feature_defs: dict[str, StateFeatureDef],
) -> bool:
    return all(
        _values_equal(state.get(key), target_value, feature_defs.get(key))
        for key, target_value in goal_state.items()
    )


def _values_equal(
    left: str | None,
    right: str | None,
    feature_def: StateFeatureDef | None,
) -> bool:
    if feature_def is not None and feature_def.value_type == "number":
        try:
            return _parse_decimal(left) == _parse_decimal(right)
        except ValueError:
            return False
    return left == right


def _build_numeric_bounds(
    current_state: StateDict,
    target_state: StateDict,
    goal_state: StateDict,
    rules: list[OpRule],
    feature_defs: dict[str, StateFeatureDef],
) -> dict[str, tuple[Decimal, Decimal]] | BfsPlanResult:
    bounds: dict[str, list[Decimal]] = {}
    numeric_keys = {
        key
        for key, feature_def in feature_defs.items()
        if feature_def.value_type == "number"
    }

    for key in numeric_keys:
        for raw_value in (current_state.get(key), target_state.get(key), goal_state.get(key)):
            if raw_value is None:
                continue
            try:
                bounds.setdefault(key, []).append(_parse_decimal(raw_value))
            except ValueError as exc:
                return BfsPlanResult(
                    status="error",
                    error_code=BFS_INVALID_NUMERIC_VALUE,
                    error_message=str(exc),
                )

    for rule in rules:
        for precond in rule.preconditions:
            if precond.feature_key not in numeric_keys:
                continue
            try:
                bounds.setdefault(precond.feature_key, []).append(
                    _parse_decimal(precond.feature_value)
                )
            except ValueError:
                continue
        for effect in rule.effects:
            if effect.feature_key not in numeric_keys:
                continue
            if getattr(effect, "effect_type", "set") in {"set", "reset"}:
                try:
                    bounds.setdefault(effect.feature_key, []).append(
                        _parse_decimal(getattr(effect, "new_value", None))
                    )
                except ValueError:
                    continue

    return {
        key: (min(values), max(values))
        for key, values in bounds.items()
        if values
    }


def _within_numeric_bounds(
    state: StateDict,
    numeric_bounds: dict[str, tuple[Decimal, Decimal]],
) -> bool:
    for key, (lower, upper) in numeric_bounds.items():
        if key not in state:
            continue
        try:
            value = _parse_decimal(state.get(key))
        except ValueError:
            return False
        if value < lower or value > upper:
            return False
    return True


def _parse_decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc

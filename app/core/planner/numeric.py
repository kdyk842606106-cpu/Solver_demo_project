"""
Numeric feature planning helpers.

Phase 1 keeps this module in-memory only. It creates step instances for exact
numeric targets and does not persist or merge them into the main RAG yet.
"""

from collections import deque
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.planner.state import StateDict
from app.core.solver.operators import OperatorRegistry
from app.core.solver.rule_evaluator import RuleEvaluator
from app.db.models import OpRule


NUMERIC_NO_PROVIDER = "NUMERIC_NO_PROVIDER"
NUMERIC_EXACT_TARGET_UNREACHABLE = "NUMERIC_EXACT_TARGET_UNREACHABLE"
NUMERIC_MAX_STEPS_EXCEEDED = "NUMERIC_MAX_STEPS_EXCEEDED"
NUMERIC_INVALID_VALUE = "NUMERIC_INVALID_VALUE"
NUMERIC_IMPLICIT_GOAL_CYCLE = "NUMERIC_IMPLICIT_GOAL_CYCLE"


@dataclass
class PlannedStep:
    """A planner-only step instance generated from an operation rule template."""

    instance_id: str
    op_rule: OpRule
    target_feature: str
    before_state: StateDict
    after_state: StateDict
    predecessor_instance_ids: list[str]


@dataclass
class NumericPlanResult:
    """Result of planning an exact numeric feature target."""

    status: str  # success | no_solution | error
    steps: list[PlannedStep]
    final_state: StateDict | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class _CandidateRule:
    rule: OpRule
    step_size: Decimal
    side_effect_count: int
    duration_min: int


def plan_exact_numeric_feature(
    feature_key: str,
    current_state: StateDict,
    target_value: str,
    rules: list[OpRule],
    max_steps: int = 50,
    visited_goals: set[tuple[str, str, str]] | None = None,
) -> NumericPlanResult:
    """
    Generate step instances that move one numeric feature to an exact target.

    This function intentionally does not modify the top-level Planner flow yet.
    It is the Phase 1 preparation layer for later build_rag integration.
    """
    try:
        current_value = _parse_decimal(current_state.get(feature_key, "0"))
        target = _parse_decimal(target_value)
    except ValueError as exc:
        return NumericPlanResult(
            status="error",
            steps=[],
            error_code=NUMERIC_INVALID_VALUE,
            error_message=str(exc),
        )

    if current_value == target:
        return NumericPlanResult(status="success", steps=[], final_state=dict(current_state))

    goal_key = (feature_key, "eq", str(target_value))
    visited_goals = set() if visited_goals is None else set(visited_goals)
    if goal_key in visited_goals:
        return NumericPlanResult(
            status="error",
            steps=[],
            error_code=NUMERIC_IMPLICIT_GOAL_CYCLE,
            error_message=f"Implicit goal cycle detected for {feature_key} eq {target_value}",
        )
    visited_goals.add(goal_key)

    candidates = _find_candidate_rules(feature_key, current_value, target, current_state, rules)
    if not candidates:
        return NumericPlanResult(
            status="no_solution",
            steps=[],
            error_code=NUMERIC_NO_PROVIDER,
            error_message=f"No numeric rule can move {feature_key} toward {target_value}",
        )

    evaluator = RuleEvaluator()
    start_state = dict(current_state)
    queue = deque([(_numeric_key(current_value), start_state, [])])
    visited = {_numeric_key(current_value)}
    max_depth_reached = False
    terminal_error: NumericPlanResult | None = None

    while queue:
        _, state, path = queue.popleft()
        state_value = _parse_decimal(state.get(feature_key, "0"))

        if len(path) >= max_steps:
            max_depth_reached = True
            continue

        for candidate in candidates:
            precondition_result = _resolve_preconditions(
                state=state,
                rule=candidate.rule,
                rules=rules,
                max_steps=max_steps - len(path),
                visited_goals=visited_goals,
            )
            if precondition_result.status == "error":
                if precondition_result.error_code == NUMERIC_IMPLICIT_GOAL_CYCLE:
                    return precondition_result
                terminal_error = precondition_result
                continue
            if precondition_result.status != "success":
                continue

            precondition_path = _steps_to_path(precondition_result.steps)
            base_state = dict(precondition_result.final_state or state)
            next_state = evaluator.apply_effects(base_state, candidate.rule.effects)
            try:
                next_value = _parse_decimal(next_state.get(feature_key, "0"))
            except ValueError:
                continue

            if _is_farther(state_value, next_value, target):
                continue
            if not _is_between(current_value, next_value, target):
                continue

            next_path = [*path, *precondition_path, (candidate.rule, base_state, next_state)]
            if len(next_path) > max_steps:
                max_depth_reached = True
                continue
            if next_value == target:
                return NumericPlanResult(
                    status="success",
                    steps=_build_steps(feature_key, next_path),
                    final_state=next_state,
                )

            key = _numeric_key(next_value)
            if key not in visited:
                visited.add(key)
                queue.append((key, next_state, next_path))

    if terminal_error is not None:
        return terminal_error

    if max_depth_reached:
        return NumericPlanResult(
            status="error",
            steps=[],
            error_code=NUMERIC_MAX_STEPS_EXCEEDED,
            error_message=f"Numeric planning exceeded max_steps={max_steps}",
        )

    return NumericPlanResult(
        status="no_solution",
        steps=[],
        error_code=NUMERIC_EXACT_TARGET_UNREACHABLE,
        error_message=f"Cannot exactly reach {feature_key}={target_value}",
    )


def plan_precondition_goal(
    feature_key: str,
    operator: str,
    target_value: str,
    current_state: StateDict,
    rules: list[OpRule],
    max_steps: int = 50,
    visited_goals: set[tuple[str, str, str]] | None = None,
) -> NumericPlanResult:
    """Plan an implicit numeric goal needed to satisfy a rule precondition."""
    current_value = current_state.get(feature_key)
    if current_value is not None and OperatorRegistry.evaluate_precond(
        current_value=current_value,
        operator_name=operator,
        feature_value=target_value,
        value_list=None,
    ):
        return NumericPlanResult(status="success", steps=[], final_state=dict(current_state))

    goal_key = (feature_key, operator, str(target_value))
    visited_goals = set() if visited_goals is None else set(visited_goals)
    if goal_key in visited_goals:
        return NumericPlanResult(
            status="error",
            steps=[],
            error_code=NUMERIC_IMPLICIT_GOAL_CYCLE,
            error_message=f"Implicit goal cycle detected for {feature_key} {operator} {target_value}",
        )

    if operator in {"eq", "gte", "lte"}:
        return plan_exact_numeric_feature(
            feature_key=feature_key,
            current_state=current_state,
            target_value=target_value,
            rules=rules,
            max_steps=max_steps,
            visited_goals=visited_goals | {goal_key},
        )

    return NumericPlanResult(
        status="no_solution",
        steps=[],
        error_code=NUMERIC_NO_PROVIDER,
        error_message=f"Unsupported implicit numeric operator: {operator}",
    )


def _find_candidate_rules(
    feature_key: str,
    current_value: Decimal,
    target_value: Decimal,
    current_state: StateDict,
    rules: list[OpRule],
) -> list[_CandidateRule]:
    evaluator = RuleEvaluator()
    candidates: list[_CandidateRule] = []

    for rule in rules:
        target_effect = None
        for effect in rule.effects:
            if effect.feature_key == feature_key and getattr(effect, "effect_type", "set") in {
                "increment",
                "decrement",
            }:
                target_effect = effect
                break

        if target_effect is None:
            continue

        try:
            delta = _parse_decimal(getattr(target_effect, "delta_value", None))
        except ValueError:
            continue

        if delta <= 0:
            continue

        direction = Decimal("1") if target_value > current_value else Decimal("-1")
        effect_type = getattr(target_effect, "effect_type", "set")
        if (direction > 0 and effect_type != "increment") or (direction < 0 and effect_type != "decrement"):
            continue

        next_state = evaluator.apply_effects(current_state, rule.effects)
        try:
            next_value = _parse_decimal(next_state.get(feature_key, "0"))
        except ValueError:
            continue

        if _is_farther(current_value, next_value, target_value):
            continue

        candidates.append(
            _CandidateRule(
                rule=rule,
                step_size=abs(next_value - current_value),
                side_effect_count=sum(1 for effect in rule.effects if effect.feature_key != feature_key),
                duration_min=getattr(rule, "duration_min", 0),
            )
        )

    return sorted(
        candidates,
        key=lambda candidate: (
            candidate.side_effect_count,
            -candidate.step_size,
            candidate.duration_min,
        ),
    )


def _resolve_preconditions(
    state: StateDict,
    rule: OpRule,
    rules: list[OpRule],
    max_steps: int,
    visited_goals: set[tuple[str, str, str]],
) -> NumericPlanResult:
    evaluator = RuleEvaluator()
    resolved_state = dict(state)
    collected_steps: list[PlannedStep] = []

    for precond in getattr(rule, "preconditions", []):
        if evaluator.evaluate_precondition(resolved_state, precond):
            continue

        remaining_steps = max_steps - len(collected_steps)
        if remaining_steps <= 0:
            return NumericPlanResult(
                status="error",
                steps=[],
                error_code=NUMERIC_MAX_STEPS_EXCEEDED,
                error_message=f"Numeric planning exceeded max_steps={max_steps}",
            )

        sub_result = plan_precondition_goal(
            feature_key=precond.feature_key,
            operator=precond.operator,
            target_value=precond.feature_value,
            current_state=resolved_state,
            rules=rules,
            max_steps=remaining_steps,
            visited_goals=visited_goals,
        )
        if sub_result.status != "success":
            return sub_result

        if sub_result.steps:
            collected_steps.extend(sub_result.steps)
        resolved_state = dict(sub_result.final_state or resolved_state)

        if not evaluator.evaluate_precondition(resolved_state, precond):
            return NumericPlanResult(
                status="no_solution",
                steps=[],
                error_code=NUMERIC_NO_PROVIDER,
                error_message=(
                    f"No implicit provider can satisfy {precond.feature_key} "
                    f"{precond.operator} {precond.feature_value}"
                ),
            )

    return NumericPlanResult(status="success", steps=collected_steps, final_state=resolved_state)


def _build_steps(
    feature_key: str,
    path: list[tuple[OpRule, StateDict, StateDict]],
) -> list[PlannedStep]:
    steps: list[PlannedStep] = []
    predecessor_ids: list[str] = []

    for index, (rule, before_state, after_state) in enumerate(path, start=1):
        instance_id = f"{feature_key}:{rule.code}:{index}"
        steps.append(
            PlannedStep(
                instance_id=instance_id,
                op_rule=rule,
                target_feature=feature_key,
                before_state=dict(before_state),
                after_state=dict(after_state),
                predecessor_instance_ids=list(predecessor_ids),
            )
        )
        predecessor_ids = [instance_id]

    return steps


def _steps_to_path(steps: list[PlannedStep]) -> list[tuple[OpRule, StateDict, StateDict]]:
    return [(step.op_rule, step.before_state, step.after_state) for step in steps]


def _parse_decimal(value: object) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid numeric value: {value}") from exc


def _numeric_key(value: Decimal) -> str:
    return str(value.normalize())


def _is_farther(current_value: Decimal, next_value: Decimal, target_value: Decimal) -> bool:
    return abs(target_value - next_value) > abs(target_value - current_value)


def _is_between(start_value: Decimal, value: Decimal, target_value: Decimal) -> bool:
    lower = min(start_value, target_value)
    upper = max(start_value, target_value)
    return lower <= value <= upper

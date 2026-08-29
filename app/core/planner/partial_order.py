"""
Instance-level Partial Order Planner.

The planner searches over activity instances, open preconditions, causal links,
and ordering constraints, then emits the existing RAG-compatible step contract.
It keeps all POP-only explanation structures in memory for now.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from math import ceil
from typing import Any

from app.core.planner.state import StateDict, compute_state_delta
from app.core.solver.rule_evaluator import RuleEvaluator
from app.db.models import OpRule, OpRuleEffect, OpRulePrecond, StateFeatureDef


POP_NO_SOLUTION = "POP_NO_SOLUTION"
POP_CYCLE = "POP_CYCLE"
POP_CLOSURE_LIMIT = "POP_CLOSURE_LIMIT"

START_ID = "__START__"
FINISH_ID = "__FINISH__"
MAX_CLOSURE_ITERATIONS = 100
MAX_CLOSURE_INSTANCES = 500


@dataclass(frozen=True)
class Fact:
    """A normalized planning fact or obligation."""

    feature_key: str
    operator: str
    value: str
    value_list: tuple[Any, ...] | None = None


@dataclass(frozen=True)
class OpenPrecondition:
    """A fact required by one activity instance."""

    consumer_id: str
    fact: Fact
    is_goal: bool = False


@dataclass(frozen=True)
class CausalLink:
    """Provider supports a consumer fact."""

    provider_id: str
    consumer_id: str
    fact: Fact


@dataclass(frozen=True)
class OrderingConstraint:
    """Partial-order edge between instances."""

    before_id: str
    after_id: str


@dataclass
class ActivityInstance:
    """One concrete occurrence of an operation rule."""

    instance_id: str
    rule: OpRule
    ordinal: int
    provided_facts: list[Fact] = field(default_factory=list)


@dataclass
class ReplayStep:
    """One activity execution in a deterministic replay of the partial order."""

    instance_id: str
    before_state: StateDict
    after_state: StateDict
    latest_writers_before: dict[str, str]


@dataclass
class PopRagNode:
    """RAG-compatible node emitted by POP."""

    id: int
    op_rule_id: int
    op_rule_code: str
    predecessors: list[int]


@dataclass
class PopPlanResult:
    """Result of POP planning."""

    status: str  # success | no_solution | error
    nodes: list[PopRagNode] = field(default_factory=list)
    edges: list[tuple[int, int]] = field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    diagnostics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class _PseudoPrecond:
    feature_key: str
    operator: str
    feature_value: str
    value_list: list[Any] | None = None


@dataclass
class _PlannerStats:
    provider_branches: int = 0
    reused_provider_count: int = 0
    new_instance_count: int = 0
    start_provider_count: int = 0
    open_precondition_count_peak: int = 0
    threats_detected: int = 0
    threats_resolved: int = 0
    closure_iterations: int = 0
    causal_window_orderings: list[dict[str, object]] = field(default_factory=list)
    reprovider_insertions: list[dict[str, object]] = field(default_factory=list)
    initial_window_orderings: list[dict[str, object]] = field(default_factory=list)
    final_state_repaired: bool = False
    provider_rejections: dict[str, int] = field(
        default_factory=lambda: {
            "cycle": 0,
            "threat_unresolved": 0,
            "no_provider": 0,
            "numeric_bound": 0,
            "closure_limit": 0,
        }
    )

    def reject(self, reason: str) -> None:
        self.provider_rejections[reason] = self.provider_rejections.get(reason, 0) + 1


class PartialOrderPlanner:
    """Goal-directed POP implementation over the existing OpRule model."""

    def __init__(
        self,
        current_state: StateDict,
        target_state: StateDict,
        rules: list[OpRule],
        feature_defs: dict[str, StateFeatureDef],
        instance_limits: dict[int, int | None] | None = None,
    ) -> None:
        self.current_state = dict(current_state)
        self.target_state = dict(target_state)
        self.rules = sorted(rules, key=lambda r: (r.duration_min, r.id or 0))
        self.feature_defs = feature_defs
        self.instance_limits = dict(instance_limits or {})
        self.evaluator = RuleEvaluator()
        self.instances: dict[str, ActivityInstance] = {}
        self.instance_counts: dict[int, int] = {}
        self.open_preconditions: list[OpenPrecondition] = []
        self.causal_links: list[CausalLink] = []
        self.orderings: set[OrderingConstraint] = set()
        self.stats = _PlannerStats()

    def plan(self) -> PopPlanResult:
        goal_facts = [
            Fact(key, "eq", target_value)
            for key, (_, target_value) in compute_state_delta(
                self.current_state,
                self.target_state,
            ).items()
            if not self._fact_satisfied_by_state(Fact(key, "eq", target_value), self.current_state)
        ]

        base_diagnostics = {
            "planner_strategy": "partial_order",
            "rules_count": len(self.rules),
            "goal_feature_count": len(goal_facts),
            "goal_features": sorted(f.feature_key for f in goal_facts),
            "planner_objective": "minimize_activity_instances",
            "planner_tie_break": "total_duration_min",
        }

        if not goal_facts:
            return PopPlanResult(
                status="success",
                diagnostics={**base_diagnostics, **self._diagnostics(0, 0)},
            )

        self.open_preconditions = [
            OpenPrecondition(FINISH_ID, fact, is_goal=True) for fact in goal_facts
        ]
        self.stats.open_precondition_count_peak = len(self.open_preconditions)

        resolving: list[Fact] = []
        while self.open_preconditions:
            open_precond = self._select_open_precondition()
            if not self._resolve_open_precondition(open_precond, resolving):
                return PopPlanResult(
                    status="no_solution",
                    error_code=POP_NO_SOLUTION,
                    error_message=f"No provider can satisfy {self._fact_label(open_precond.fact)}",
                    diagnostics={**base_diagnostics, **self._diagnostics(0, 0)},
                )
            self.stats.open_precondition_count_peak = max(
                self.stats.open_precondition_count_peak,
                len(self.open_preconditions),
            )

        closure_error = self._close_reprovider_obligations()
        if closure_error is not None:
            return PopPlanResult(
                status="no_solution",
                error_code=closure_error,
                error_message="Re-provider closure could not produce a stable plan",
                diagnostics={**base_diagnostics, **self._diagnostics(0, 0)},
            )

        self._rebuild_causal_links_from_replay(goal_facts)
        self._protect_all_causal_links()
        if self._has_cycle(self.orderings):
            return PopPlanResult(
                status="error",
                error_code=POP_CYCLE,
                error_message="Circular dependency detected in POP ordering constraints",
                diagnostics={**base_diagnostics, **self._diagnostics(0, 0)},
            )

        self._add_write_conflict_orderings()
        raw_edges = self._real_ordering_edges()
        reduced_edges = self._transitive_reduction(raw_edges)
        nodes = self._to_rag_nodes(reduced_edges)

        return PopPlanResult(
            status="success",
            nodes=nodes,
            edges=reduced_edges,
            diagnostics={
                **base_diagnostics,
                **self._diagnostics(len(raw_edges), len(reduced_edges)),
            },
        )

    def _select_open_precondition(self) -> OpenPrecondition:
        def key(item: OpenPrecondition) -> tuple[int, int, int, str, str]:
            provider_count = self._provider_count(item.fact)
            current_unsatisfied = 0 if not self._fact_satisfied_by_state(item.fact, self.current_state) else 1
            goal_rank = 0 if item.is_goal else 1
            return (
                current_unsatisfied,
                provider_count,
                goal_rank,
                item.consumer_id,
                self._fact_label(item.fact),
            )

        selected = min(self.open_preconditions, key=key)
        self.open_preconditions.remove(selected)
        return selected

    def _resolve_open_precondition(
        self,
        open_precond: OpenPrecondition,
        resolving: list[Fact],
    ) -> bool:
        fact = open_precond.fact
        if fact in resolving:
            self.stats.reject("cycle")
            return False

        if self._fact_satisfied_by_state(fact, self.current_state):
            if not self._add_causal_link(START_ID, open_precond.consumer_id, fact):
                return False
            self.stats.start_provider_count += 1
            return True

        existing_provider = self._best_existing_provider(fact, open_precond.consumer_id)
        if existing_provider is not None:
            if not self._add_causal_link(existing_provider, open_precond.consumer_id, fact):
                return False
            self.stats.reused_provider_count += 1
            return True

        resolving.append(fact)
        provider = self._create_provider_for_fact(fact, resolving)
        resolving.pop()
        if provider is None:
            self.stats.reject("no_provider")
            return False

        if not self._add_causal_link(provider, open_precond.consumer_id, fact):
            return False
        return True

    def _create_provider_for_fact(
        self,
        fact: Fact,
        resolving: list[Fact],
        context_state: StateDict | None = None,
        context_writers: dict[str, str] | None = None,
    ) -> str | None:
        candidates = self._direct_provider_rules(fact)
        if self._is_numeric_fact(fact):
            candidates.extend(self._numeric_provider_rules(fact))

        ranked_rules = sorted(
            {rule.id or id(rule): rule for rule in candidates}.values(),
            key=lambda rule: (
                -self._open_fact_coverage(rule),
                self._estimated_rule_count(rule, fact),
                rule.duration_min,
                rule.id or 0,
            ),
        )
        self.stats.provider_branches += len(ranked_rules)

        for rule in ranked_rules:
            rule_id = rule.id or id(rule)
            limit = self.instance_limits.get(rule_id)
            if limit is not None and self.instance_counts.get(rule_id, 0) >= limit:
                self.stats.reject("instance_limit")
                continue
            if self._is_numeric_provider(rule, fact):
                provider = self._create_numeric_chain(rule, fact, resolving)
            else:
                provider = self._create_rule_instance(
                    rule,
                    resolving,
                    context_state=context_state,
                    context_writers=context_writers,
                )
            if provider is not None:
                return provider
        return None

    def _create_rule_instance(
        self,
        rule: OpRule,
        resolving: list[Fact],
        provided_facts: list[Fact] | None = None,
        context_state: StateDict | None = None,
        context_writers: dict[str, str] | None = None,
    ) -> str | None:
        instance = self._new_instance(rule, provided_facts or self._effect_facts(rule))
        for precond in sorted(rule.preconditions, key=lambda p: (p.feature_key, p.operator, p.feature_value)):
            fact = self._fact_from_precond(precond)
            if context_state is not None and self._fact_satisfied_by_state(fact, context_state):
                provider_id = (context_writers or {}).get(fact.feature_key, START_ID)
                if not self._add_causal_link(provider_id, instance.instance_id, fact):
                    self.instances.pop(instance.instance_id, None)
                    self.stats.reject("no_provider")
                    return None
                if provider_id == START_ID:
                    self.stats.start_provider_count += 1
                continue
            open_precond = OpenPrecondition(instance.instance_id, fact)
            if not self._resolve_open_precondition(open_precond, resolving):
                self.instances.pop(instance.instance_id, None)
                self.stats.reject("no_provider")
                return None
        self._satisfy_other_open_preconditions(instance)
        return instance.instance_id

    def _create_numeric_chain(
        self,
        rule: OpRule,
        fact: Fact,
        resolving: list[Fact],
    ) -> str | None:
        effect = next((e for e in rule.effects if e.feature_key == fact.feature_key), None)
        if effect is None:
            return None
        current = self._latest_numeric_value(fact.feature_key)
        target = self._parse_decimal(fact.value)
        delta = self._parse_decimal(getattr(effect, "delta_value", None))
        if delta == 0:
            self.stats.reject("numeric_bound")
            return None

        effect_type = getattr(effect, "effect_type", "set")
        step = delta if effect_type == "increment" else -delta
        if step == 0:
            self.stats.reject("numeric_bound")
            return None

        max_steps = self._numeric_step_limit(current, target, step)
        provider_id: str | None = None
        previous_writer = self._latest_writer_for_feature(fact.feature_key)
        rule_id = rule.id or id(rule)
        limit = self.instance_limits.get(rule_id)

        for _ in range(max_steps):
            if self._fact_satisfied_by_value(fact, self._format_decimal(current)):
                break
            if limit is not None and self.instance_counts.get(rule_id, 0) >= limit:
                self.stats.reject("instance_limit")
                return None
            next_value = current + step
            if self._moving_away(current, next_value, target, fact):
                self.stats.reject("numeric_bound")
                return None
            next_fact = Fact(fact.feature_key, "eq", self._format_decimal(next_value))
            instance_id = self._create_rule_instance(
                rule,
                resolving,
                provided_facts=[next_fact],
            )
            if instance_id is None:
                return None
            if previous_writer is not None:
                self._add_ordering(previous_writer, instance_id)
            previous_writer = instance_id
            provider_id = instance_id
            current = next_value

        if provider_id is not None and self._fact_satisfied_by_value(fact, self._format_decimal(current)):
            return provider_id

        self.stats.reject("numeric_bound")
        return None

    def _new_instance(self, rule: OpRule, provided_facts: list[Fact]) -> ActivityInstance:
        rule_id = rule.id or id(rule)
        ordinal = self.instance_counts.get(rule_id, 0) + 1
        self.instance_counts[rule_id] = ordinal
        instance = ActivityInstance(
            instance_id=f"{rule.code}#{ordinal}",
            rule=rule,
            ordinal=ordinal,
            provided_facts=provided_facts,
        )
        self.instances[instance.instance_id] = instance
        self.stats.new_instance_count += 1
        return instance

    def _satisfy_other_open_preconditions(self, instance: ActivityInstance) -> None:
        remaining: list[OpenPrecondition] = []
        for open_precond in self.open_preconditions:
            if any(self._provided_fact_satisfies(provided, open_precond.fact) for provided in instance.provided_facts):
                if not self._add_causal_link(instance.instance_id, open_precond.consumer_id, open_precond.fact):
                    remaining.append(open_precond)
            else:
                remaining.append(open_precond)
        self.open_preconditions = remaining

    def _best_existing_provider(self, fact: Fact, consumer_id: str) -> str | None:
        candidates: list[ActivityInstance] = []
        for instance in self.instances.values():
            if instance.instance_id == consumer_id:
                continue
            if any(self._provided_fact_satisfies(provided, fact) for provided in instance.provided_facts):
                if not self._would_create_cycle(instance.instance_id, consumer_id):
                    candidates.append(instance)
        if not candidates:
            return None
        return min(candidates, key=lambda i: (i.rule.duration_min, i.rule.id or 0, i.instance_id)).instance_id

    def _add_causal_link(self, provider_id: str, consumer_id: str, fact: Fact) -> bool:
        link = CausalLink(provider_id, consumer_id, fact)
        if link not in self.causal_links:
            self.causal_links.append(link)
        if provider_id != START_ID and consumer_id != START_ID:
            return self._add_ordering(provider_id, consumer_id)
        return True

    def _add_ordering(self, before_id: str, after_id: str) -> bool:
        if before_id == after_id:
            self.stats.reject("cycle")
            return False
        constraint = OrderingConstraint(before_id, after_id)
        if constraint in self.orderings:
            return True
        trial = set(self.orderings)
        trial.add(constraint)
        if self._has_cycle(trial):
            self.stats.reject("cycle")
            return False
        self.orderings.add(constraint)
        return True

    def _close_reprovider_obligations(self) -> str | None:
        for iteration in range(1, MAX_CLOSURE_ITERATIONS + 1):
            self.stats.closure_iterations = iteration
            replay_steps, final_state, final_writers = self._replay_plan()
            obligation = self._first_unmet_precondition(replay_steps)
            if obligation is None:
                obligation = self._first_final_goal_drift(replay_steps, final_state, final_writers)
            if obligation is None:
                return None
            if len(self.instances) >= MAX_CLOSURE_INSTANCES:
                self.stats.reject("closure_limit")
                return POP_CLOSURE_LIMIT
            if not self._resolve_reprovider_obligation(**obligation):
                return POP_NO_SOLUTION
        self.stats.reject("closure_limit")
        return POP_CLOSURE_LIMIT

    def _replay_plan(self) -> tuple[list[ReplayStep], StateDict, dict[str, str]]:
        state = dict(self.current_state)
        latest_writers: dict[str, str] = {}
        steps: list[ReplayStep] = []

        for instance_id in self._topological_instance_ids():
            instance = self.instances[instance_id]
            before_state = dict(state)
            writers_before = dict(latest_writers)
            after_state = self.evaluator.apply_effects(before_state, instance.rule.effects)
            steps.append(
                ReplayStep(
                    instance_id=instance_id,
                    before_state=before_state,
                    after_state=dict(after_state),
                    latest_writers_before=writers_before,
                )
            )
            state = dict(after_state)
            for effect in instance.rule.effects:
                latest_writers[effect.feature_key] = instance_id

        return steps, state, latest_writers

    def _first_unmet_precondition(self, replay_steps: list[ReplayStep]) -> dict[str, object] | None:
        for index, step in enumerate(replay_steps):
            instance = self.instances[step.instance_id]
            for precond in sorted(instance.rule.preconditions, key=lambda p: (p.feature_key, p.operator, p.feature_value)):
                if self.evaluator.evaluate_precondition(step.before_state, precond):
                    continue
                fact = self._fact_from_precond(precond)
                guard_consumers = [
                    previous.instance_id
                    for previous in replay_steps[:index]
                    if any(p.feature_key == fact.feature_key for p in self.instances[previous.instance_id].rule.preconditions)
                ]
                return {
                    "consumer_id": step.instance_id,
                    "fact": fact,
                    "latest_writer": step.latest_writers_before.get(fact.feature_key),
                    "observed_value": step.before_state.get(fact.feature_key),
                    "reason": "unmet_precondition",
                    "guard_consumers": guard_consumers,
                    "context_state": step.before_state,
                    "context_writers": step.latest_writers_before,
                }
        return None

    def _first_final_goal_drift(
        self,
        replay_steps: list[ReplayStep],
        final_state: StateDict,
        final_writers: dict[str, str],
    ) -> dict[str, object] | None:
        for feature_key, target_value in sorted(self.target_state.items()):
            fact = Fact(feature_key, "eq", target_value)
            if self._fact_satisfied_by_state(fact, final_state):
                continue
            if not self._direct_provider_rules(fact):
                continue
            return {
                "consumer_id": FINISH_ID,
                "fact": fact,
                "latest_writer": final_writers.get(feature_key),
                "observed_value": final_state.get(feature_key),
                "reason": "final_goal_drift",
                "guard_consumers": self._feature_touching_step_ids(replay_steps, {feature_key}),
                "context_state": final_state,
                "context_writers": final_writers,
            }
        return None

    def _feature_touching_step_ids(
        self,
        replay_steps: list[ReplayStep],
        feature_keys: set[str],
    ) -> list[str]:
        step_ids: list[str] = []
        for step in replay_steps:
            rule = self.instances[step.instance_id].rule
            touches_feature = any(precond.feature_key in feature_keys for precond in rule.preconditions) or any(
                effect.feature_key in feature_keys for effect in rule.effects
            )
            if touches_feature:
                step_ids.append(step.instance_id)
        return step_ids

    def _resolve_reprovider_obligation(
        self,
        consumer_id: str,
        fact: Fact,
        latest_writer: str | None,
        observed_value: object,
        reason: str,
        guard_consumers: list[str] | None = None,
        context_state: StateDict | None = None,
        context_writers: dict[str, str] | None = None,
    ) -> bool:
        if self._try_order_causal_window_before_writer(
            consumer_id=consumer_id,
            fact=fact,
            latest_writer=latest_writer,
            observed_value=observed_value,
            reason=reason,
        ):
            return True

        before_ids = set(self.instances)
        provider_id = self._create_provider_for_fact(
            fact,
            [],
            context_state=context_state,
            context_writers=context_writers,
        )
        if provider_id is None:
            self.stats.reject("no_provider")
            return False

        new_ids = sorted(set(self.instances) - before_ids, key=self._instance_sort_key)
        ordered_provider_ids = new_ids or [provider_id]
        if latest_writer is not None:
            for new_id in ordered_provider_ids:
                if not self._add_ordering(latest_writer, new_id):
                    return False
        for guard_id in guard_consumers or []:
            for new_id in ordered_provider_ids:
                if not self._add_ordering(guard_id, new_id):
                    return False
        if consumer_id != FINISH_ID and not self._add_ordering(provider_id, consumer_id):
            return False

        self.causal_links = [
            link for link in self.causal_links
            if not (link.consumer_id == consumer_id and link.fact == fact)
        ]
        self.causal_links.append(CausalLink(provider_id, consumer_id, fact))
        if reason == "final_goal_drift":
            self.stats.final_state_repaired = True
        self.stats.reprovider_insertions.append(
            {
                "provider": provider_id,
                "consumer": consumer_id,
                "fact": self._fact_label(fact),
                "latest_writer": latest_writer,
                "observed_value": observed_value,
                "reason": reason,
            }
        )
        return True

    def _try_order_causal_window_before_writer(
        self,
        *,
        consumer_id: str,
        fact: Fact,
        latest_writer: str | None,
        observed_value: object,
        reason: str,
    ) -> bool:
        if reason != "unmet_precondition":
            return False
        if consumer_id == FINISH_ID or latest_writer is None:
            return False
        writer = self.instances.get(latest_writer)
        if consumer_id not in self.instances or writer is None:
            return False
        link = self._causal_link_for_consumer_fact(consumer_id, fact)
        if link is None or link.provider_id == latest_writer:
            return False
        if not self._instance_threatens(writer, link):
            return False
        if not self._add_ordering(consumer_id, latest_writer):
            return False

        ordering = {
            "provider": link.provider_id,
            "consumer": consumer_id,
            "before_writer": latest_writer,
            "fact": self._fact_label(fact),
            "observed_value": observed_value,
            "reason": reason,
            "source": "initial_state" if link.provider_id == START_ID else "existing_provider",
        }
        self.stats.causal_window_orderings.append(ordering)
        if link.provider_id == START_ID:
            self.stats.initial_window_orderings.append(ordering)
        return True

    def _causal_link_for_consumer_fact(self, consumer_id: str, fact: Fact) -> CausalLink | None:
        matches = [
            link
            for link in self.causal_links
            if link.consumer_id == consumer_id
            and link.fact == fact
            and (link.provider_id == START_ID or link.provider_id in self.instances)
        ]
        if not matches:
            return None
        return min(matches, key=lambda link: (link.provider_id != START_ID, link.provider_id))

    def _rebuild_causal_links_from_replay(self, goal_facts: list[Fact]) -> None:
        replay_steps, final_state, final_writers = self._replay_plan()
        self.causal_links = []
        for step in replay_steps:
            instance = self.instances[step.instance_id]
            for precond in sorted(instance.rule.preconditions, key=lambda p: (p.feature_key, p.operator, p.feature_value)):
                fact = self._fact_from_precond(precond)
                if not self.evaluator.evaluate_precondition(step.before_state, precond):
                    continue
                provider_id = step.latest_writers_before.get(fact.feature_key, START_ID)
                self._add_causal_link(provider_id, step.instance_id, fact)

        for fact in goal_facts:
            if not self._fact_satisfied_by_state(fact, final_state):
                continue
            provider_id = final_writers.get(fact.feature_key, START_ID)
            self._add_causal_link(provider_id, FINISH_ID, fact)

    def _protect_all_causal_links(self) -> None:
        changed = True
        while changed:
            changed = False
            for link in list(self.causal_links):
                for instance in list(self.instances.values()):
                    if instance.instance_id in (link.provider_id, link.consumer_id):
                        continue
                    if not self._instance_threatens(instance, link):
                        continue
                    if not self._can_be_between(instance.instance_id, link.provider_id, link.consumer_id):
                        continue
                    self.stats.threats_detected += 1
                    if self._add_ordering(link.consumer_id, instance.instance_id):
                        self.stats.threats_resolved += 1
                        changed = True
                        continue
                    if self._add_ordering(instance.instance_id, link.provider_id):
                        self.stats.threats_resolved += 1
                        changed = True
                        continue
                    if self._reprovide_link(link, instance.instance_id):
                        self.stats.threats_resolved += 1
                        changed = True
                        continue
                    self.stats.reject("threat_unresolved")

    def _reprovide_link(self, link: CausalLink, threat_id: str) -> bool:
        new_provider = self._create_provider_for_fact(link.fact, [])
        if new_provider is None or new_provider == link.provider_id:
            return False
        if not self._add_ordering(threat_id, new_provider):
            return False
        if not self._add_ordering(new_provider, link.consumer_id):
            return False
        replacement = CausalLink(new_provider, link.consumer_id, link.fact)
        self.causal_links = [
            existing
            for existing in self.causal_links
            if not (
                existing.provider_id == link.provider_id
                and existing.consumer_id == link.consumer_id
                and existing.fact == link.fact
            )
        ]
        self.causal_links.append(replacement)
        return True

    def _add_write_conflict_orderings(self) -> None:
        by_feature: dict[str, list[ActivityInstance]] = {}
        for instance in sorted(self.instances.values(), key=lambda i: i.instance_id):
            for effect in instance.rule.effects:
                by_feature.setdefault(effect.feature_key, []).append(instance)
        for instances in by_feature.values():
            for prev, nxt in zip(instances, instances[1:]):
                if self._effects_commute(prev.rule.effects, nxt.rule.effects):
                    continue
                self._add_ordering(prev.instance_id, nxt.instance_id)

    def _instance_threatens(self, instance: ActivityInstance, link: CausalLink) -> bool:
        for effect in instance.rule.effects:
            if effect.feature_key != link.fact.feature_key:
                continue
            if getattr(effect, "effect_type", "set") != "set":
                return True
            if not self._fact_satisfied_by_value(link.fact, getattr(effect, "new_value", "")):
                return True
        return False

    def _can_be_between(self, threat_id: str, provider_id: str, consumer_id: str) -> bool:
        if provider_id != START_ID and self._path_exists(threat_id, provider_id, self.orderings):
            return False
        if consumer_id != FINISH_ID and self._path_exists(consumer_id, threat_id, self.orderings):
            return False
        return True

    def _direct_provider_rules(self, fact: Fact) -> list[OpRule]:
        providers = []
        for rule in self.rules:
            if any(self._effect_satisfies_fact(effect, fact) for effect in rule.effects):
                providers.append(rule)
        return providers

    def _numeric_provider_rules(self, fact: Fact) -> list[OpRule]:
        providers = []
        for rule in self.rules:
            for effect in rule.effects:
                if effect.feature_key != fact.feature_key:
                    continue
                if getattr(effect, "effect_type", "set") in ("increment", "decrement", "sub"):
                    providers.append(rule)
                    break
        return providers

    def _provider_count(self, fact: Fact) -> int:
        count = 1 if self._fact_satisfied_by_state(fact, self.current_state) else 0
        count += sum(
            1
            for instance in self.instances.values()
            if any(self._provided_fact_satisfies(provided, fact) for provided in instance.provided_facts)
        )
        count += len(self._direct_provider_rules(fact))
        if self._is_numeric_fact(fact):
            count += len(self._numeric_provider_rules(fact))
        return count

    def _open_fact_coverage(self, rule: OpRule) -> int:
        return sum(
            1
            for open_precond in self.open_preconditions
            if any(self._effect_satisfies_fact(effect, open_precond.fact) for effect in rule.effects)
        )

    def _estimated_rule_count(self, rule: OpRule, fact: Fact) -> int:
        if not self._is_numeric_provider(rule, fact):
            return 1
        effect = next((e for e in rule.effects if e.feature_key == fact.feature_key), None)
        if effect is None:
            return 999999
        try:
            current = self._latest_numeric_value(fact.feature_key)
            target = self._parse_decimal(fact.value)
            delta = self._parse_decimal(getattr(effect, "delta_value", None))
        except ValueError:
            return 999999
        if delta == 0:
            return 999999
        distance = abs(target - current)
        return max(1, ceil(distance / abs(delta)))

    def _effect_facts(self, rule: OpRule) -> list[Fact]:
        facts = []
        for effect in rule.effects:
            if getattr(effect, "effect_type", "set") in {"set", "reset"}:
                facts.append(Fact(effect.feature_key, "eq", getattr(effect, "new_value", "")))
        return facts

    def _fact_from_precond(self, precond: OpRulePrecond) -> Fact:
        value_list = getattr(precond, "value_list", None)
        return Fact(
            precond.feature_key,
            precond.operator,
            precond.feature_value,
            tuple(value_list) if value_list is not None else None,
        )

    def _effect_satisfies_fact(self, effect: OpRuleEffect, fact: Fact) -> bool:
        if effect.feature_key != fact.feature_key:
            return False
        if getattr(effect, "effect_type", "set") not in {"set", "reset"}:
            return False
        return self._fact_satisfied_by_value(fact, getattr(effect, "new_value", ""))

    def _provided_fact_satisfies(self, provided: Fact, required: Fact) -> bool:
        if provided.feature_key != required.feature_key:
            return False
        if provided.operator == "eq":
            return self._fact_satisfied_by_value(required, provided.value)
        return provided == required

    def _fact_satisfied_by_state(self, fact: Fact, state: StateDict) -> bool:
        precond = _PseudoPrecond(
            feature_key=fact.feature_key,
            operator=fact.operator,
            feature_value=fact.value,
            value_list=list(fact.value_list) if fact.value_list is not None else None,
        )
        return self.evaluator.evaluate_precondition(state, precond)  # type: ignore[arg-type]

    def _fact_satisfied_by_value(self, fact: Fact, value: str) -> bool:
        return self._fact_satisfied_by_state(fact, {fact.feature_key: value})

    def _is_numeric_fact(self, fact: Fact) -> bool:
        feature_def = self.feature_defs.get(fact.feature_key)
        if feature_def is not None and feature_def.value_type == "number":
            return True
        try:
            self._parse_decimal(fact.value)
            return fact.operator in {"eq", "gt", "gte", "lt", "lte"}
        except ValueError:
            return False

    def _is_numeric_provider(self, rule: OpRule, fact: Fact) -> bool:
        return any(
            effect.feature_key == fact.feature_key
            and getattr(effect, "effect_type", "set") in ("increment", "decrement", "sub")
            for effect in rule.effects
        )

    def _latest_numeric_value(self, feature_key: str) -> Decimal:
        latest_writer = self._latest_writer_for_feature(feature_key)
        if latest_writer is not None:
            instance = self.instances[latest_writer]
            for fact in instance.provided_facts:
                if fact.feature_key == feature_key and fact.operator == "eq":
                    return self._parse_decimal(fact.value)
        return self._parse_decimal(self.current_state.get(feature_key))

    def _latest_writer_for_feature(self, feature_key: str) -> str | None:
        writers = [
            instance
            for instance in self.instances.values()
            if any(effect.feature_key == feature_key for effect in instance.rule.effects)
        ]
        if not writers:
            return None
        return max(writers, key=lambda i: i.instance_id).instance_id

    def _numeric_step_limit(self, current: Decimal, target: Decimal, step: Decimal) -> int:
        distance = abs(target - current)
        return max(1, int(ceil(distance / abs(step))) + 2)

    def _moving_away(self, current: Decimal, next_value: Decimal, target: Decimal, fact: Fact) -> bool:
        if fact.operator in {"gt", "gte"}:
            return next_value <= current
        if fact.operator in {"lt", "lte"}:
            return next_value >= current
        return abs(next_value - target) > abs(current - target)

    def _effects_commute(self, left: list[OpRuleEffect], right: list[OpRuleEffect]) -> bool:
        for l_eff in left:
            for r_eff in right:
                if l_eff.feature_key != r_eff.feature_key:
                    continue
                l_type = getattr(l_eff, "effect_type", "set")
                r_type = getattr(r_eff, "effect_type", "set")
                if l_type in {"decrement", "sub"}:
                    l_type = "increment"
                if r_type in {"decrement", "sub"}:
                    r_type = "increment"
                if not (l_type == "increment" and r_type == "increment"):
                    return False
        return True

    def _real_ordering_edges(self) -> list[tuple[str, str]]:
        edges = []
        for constraint in sorted(self.orderings, key=lambda c: (c.before_id, c.after_id)):
            if constraint.before_id in (START_ID, FINISH_ID):
                continue
            if constraint.after_id in (START_ID, FINISH_ID):
                continue
            if constraint.before_id in self.instances and constraint.after_id in self.instances:
                edges.append((constraint.before_id, constraint.after_id))
        return edges

    def _to_rag_nodes(self, edges: list[tuple[int, int]] | list[tuple[str, str]]) -> list[PopRagNode]:
        topo_ids = self._topological_instance_ids()
        order_map = {instance_id: idx for idx, instance_id in enumerate(topo_ids, start=1)}
        normalized_edges: list[tuple[int, int]] = []
        for before, after in edges:
            if isinstance(before, str):
                normalized_edges.append((order_map[before], order_map[after]))  # type: ignore[index]
            else:
                normalized_edges.append((before, after))  # type: ignore[arg-type]

        predecessors: dict[int, set[int]] = {idx: set() for idx in range(1, len(topo_ids) + 1)}
        for before, after in normalized_edges:
            predecessors[after].add(before)

        nodes = []
        for instance_id, step_order in order_map.items():
            instance = self.instances[instance_id]
            nodes.append(
                PopRagNode(
                    id=step_order,
                    op_rule_id=instance.rule.id,
                    op_rule_code=instance.rule.code,
                    predecessors=sorted(predecessors[step_order]),
                )
            )
        return nodes

    def _topological_instance_ids(self) -> list[str]:
        ids = sorted(self.instances.keys(), key=self._instance_sort_key)
        adj: dict[str, list[str]] = {item: [] for item in ids}
        indegree: dict[str, int] = {item: 0 for item in ids}
        for before, after in self._real_ordering_edges():
            adj[before].append(after)
            indegree[after] += 1
        ready = sorted(
            [item for item, degree in indegree.items() if degree == 0],
            key=self._instance_sort_key,
        )
        result: list[str] = []
        while ready:
            current = ready.pop(0)
            result.append(current)
            for nxt in sorted(adj[current], key=self._instance_sort_key):
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)
                    ready.sort(key=self._instance_sort_key)
        return result if len(result) == len(ids) else ids

    def _instance_sort_key(self, instance_id: str) -> tuple[int, int, str]:
        instance = self.instances[instance_id]
        return (instance.rule.duration_min, instance.rule.id or 0, instance_id)

    def _transitive_reduction(self, edges: list[tuple[str, str]]) -> list[tuple[int, int]]:
        topo_ids = self._topological_instance_ids()
        order_map = {instance_id: idx for idx, instance_id in enumerate(topo_ids, start=1)}
        int_edges = sorted({(order_map[a], order_map[b]) for a, b in edges})
        reduced = []
        for edge in int_edges:
            remaining = [item for item in int_edges if item != edge]
            if self._int_path_exists(edge[0], edge[1], remaining):
                continue
            reduced.append(edge)
        return reduced

    def _has_cycle(self, orderings: set[OrderingConstraint]) -> bool:
        ids = set(self.instances.keys()) | {START_ID, FINISH_ID}
        adj: dict[str, list[str]] = {item: [] for item in ids}
        for constraint in orderings:
            adj.setdefault(constraint.before_id, []).append(constraint.after_id)
            adj.setdefault(constraint.after_id, [])
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> bool:
            if node in visiting:
                return True
            if node in visited:
                return False
            visiting.add(node)
            for nxt in adj.get(node, []):
                if visit(nxt):
                    return True
            visiting.remove(node)
            visited.add(node)
            return False

        return any(visit(node) for node in list(adj))

    def _would_create_cycle(self, before_id: str, after_id: str) -> bool:
        trial = set(self.orderings)
        trial.add(OrderingConstraint(before_id, after_id))
        return self._has_cycle(trial)

    def _path_exists(self, start: str, end: str, orderings: set[OrderingConstraint]) -> bool:
        adj: dict[str, list[str]] = {}
        for constraint in orderings:
            adj.setdefault(constraint.before_id, []).append(constraint.after_id)
        stack = [start]
        seen = set()
        while stack:
            current = stack.pop()
            if current == end:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adj.get(current, []))
        return False

    def _int_path_exists(self, start: int, end: int, edges: list[tuple[int, int]]) -> bool:
        adj: dict[int, list[int]] = {}
        for before, after in edges:
            adj.setdefault(before, []).append(after)
        stack = list(adj.get(start, []))
        seen: set[int] = set()
        while stack:
            current = stack.pop()
            if current == end:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(adj.get(current, []))
        return False

    def _diagnostics(self, before_reduction: int, after_reduction: int) -> dict[str, object]:
        return {
            "selected_instance_count": len(self.instances),
            "total_duration_min": sum(instance.rule.duration_min for instance in self.instances.values()),
            "open_precondition_count_peak": self.stats.open_precondition_count_peak,
            "open_precondition_count": len(self.open_preconditions),
            "causal_link_count": len(self.causal_links),
            "ordering_count_before_reduction": before_reduction,
            "ordering_count_after_reduction": after_reduction,
            "threats_detected": self.stats.threats_detected,
            "threats_resolved": self.stats.threats_resolved,
            "provider_branches": self.stats.provider_branches,
            "provider_rejections": dict(sorted(self.stats.provider_rejections.items())),
            "instance_limits": {
                str(rule_id): limit
                for rule_id, limit in sorted(self.instance_limits.items())
                if limit is not None
            },
            "reused_provider_count": self.stats.reused_provider_count,
            "new_instance_count": self.stats.new_instance_count,
            "start_provider_count": self.stats.start_provider_count,
            "closure_iterations": self.stats.closure_iterations,
            "causal_window_ordering_count": len(self.stats.causal_window_orderings),
            "causal_window_orderings": list(self.stats.causal_window_orderings),
            "initial_window_ordering_count": len(self.stats.initial_window_orderings),
            "initial_window_orderings": list(self.stats.initial_window_orderings),
            "reprovider_insertion_count": len(self.stats.reprovider_insertions),
            "reprovider_insertions": list(self.stats.reprovider_insertions),
            "final_state_repaired": self.stats.final_state_repaired,
        }

    def _fact_label(self, fact: Fact) -> str:
        return f"{fact.feature_key} {fact.operator} {fact.value}"

    def _parse_decimal(self, value: object) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid numeric value: {value}") from exc

    def _format_decimal(self, value: Decimal) -> str:
        normalized = value.normalize()
        if normalized == normalized.to_integral():
            return str(normalized.quantize(Decimal("1")))
        return format(normalized, "f")


def partial_order_plan(
    current_state: StateDict,
    target_state: StateDict,
    rules: list[OpRule],
    feature_defs: dict[str, StateFeatureDef],
    instance_limits: dict[int, int | None] | None = None,
) -> PopPlanResult:
    """Plan with instance-level POP and return a RAG-compatible result."""
    try:
        return PartialOrderPlanner(
            current_state=current_state,
            target_state=target_state,
            rules=rules,
            feature_defs=feature_defs,
            instance_limits=instance_limits,
        ).plan()
    except Exception as exc:
        return PopPlanResult(
            status="error",
            error_message=str(exc),
            diagnostics={"planner_strategy": "partial_order"},
        )

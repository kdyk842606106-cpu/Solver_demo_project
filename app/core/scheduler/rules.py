"""Registered, data-driven scheduling rules for the CP-SAT scheduler."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import re
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Machine, MachineType


class SchedulingRuleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


_RULE_TYPES: dict[str, dict[str, Any]] = {}
_GANTT_MARKER_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def _normalize_rule_presentation(code: str, raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise SchedulingRuleError(
            "SCHEDULING_RULE_CONFIG_INVALID",
            f"Rule {code} presentation must be an object",
        )
    marker = raw.get("gantt_marker")
    if marker is None:
        return {}
    if not isinstance(marker, dict):
        raise SchedulingRuleError(
            "SCHEDULING_RULE_CONFIG_INVALID",
            f"Rule {code} gantt_marker must be an object",
        )
    text = str(marker.get("text") or "").strip()
    if not 1 <= len(text) <= 4:
        raise SchedulingRuleError(
            "SCHEDULING_RULE_CONFIG_INVALID",
            f"Rule {code} gantt_marker text must contain 1 to 4 characters",
        )
    color = str(marker.get("color") or "#f59e0b").strip()
    if _GANTT_MARKER_COLOR.fullmatch(color) is None:
        raise SchedulingRuleError(
            "SCHEDULING_RULE_CONFIG_INVALID",
            f"Rule {code} gantt_marker color must use #RRGGBB",
        )
    return {"gantt_marker": {"text": text, "color": color.lower()}}


def register_scheduling_rule_type(
    rule_type: str,
    *,
    name: str,
    description: str,
    supported_selectors: list[str],
    parameters: dict[str, Any],
    supported_modes: list[str] | None = None,
    builtin_rule: dict[str, Any] | None = None,
) -> Callable[[type], type]:
    def decorator(cls: type) -> type:
        _RULE_TYPES[rule_type] = {
            "type": rule_type,
            "name": name,
            "description": description,
            "supported_selectors": supported_selectors,
            "parameters": parameters,
            "supported_modes": supported_modes or ["snapshot", "layered", "maintenance"],
            "builtin_rule": deepcopy(builtin_rule),
            "compiler": cls,
        }
        return cls

    return decorator


def scheduling_rule_type_descriptors() -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "compiler"}
        for _, item in sorted(_RULE_TYPES.items())
    ]


def scheduling_rule_supported_in_mode(rule: dict[str, Any], solve_mode: str | None) -> bool:
    if solve_mode is None:
        return True
    descriptor = _RULE_TYPES.get(str(rule.get("type") or "")) or {}
    return solve_mode in (descriptor.get("supported_modes") or [])


def builtin_scheduling_rules(solve_mode: str | None) -> list[dict[str, Any]]:
    if solve_mode is None:
        return []
    raw_rules = [
        deepcopy(item["builtin_rule"])
        for item in _RULE_TYPES.values()
        if item.get("builtin_rule")
        and solve_mode in (item.get("supported_modes") or [])
    ]
    if not raw_rules:
        return []
    return (validate_scheduling_config({"rules": raw_rules}) or {"rules": []})["rules"]


def validate_scheduling_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    if config is None:
        return None
    if not isinstance(config, dict):
        raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", "scheduling_config must be an object")
    subsystem_codes: set[str] = set()
    subsystems = []
    for item in config.get("responsible_subsystems") or []:
        code = str((item or {}).get("code") or "").strip()
        name = str((item or {}).get("name") or "").strip()
        if not code or not name or code in subsystem_codes:
            raise SchedulingRuleError(
                "SCHEDULING_RULE_CONFIG_INVALID",
                "responsible_subsystems require unique non-empty code and name",
            )
        subsystem_codes.add(code)
        subsystems.append({"code": code, "name": name})

    rule_codes: set[str] = set()
    rules = []
    for raw in config.get("rules") or []:
        rule = dict(raw or {})
        code = str(rule.get("code") or "").strip()
        rule_type = str(rule.get("type") or "").strip()
        if not code or code in rule_codes:
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", "Scheduling rule codes must be unique")
        if rule_type not in _RULE_TYPES:
            raise SchedulingRuleError("SCHEDULING_RULE_UNKNOWN_TYPE", f"Unknown scheduling rule type: {rule_type}")
        activation_mode = rule.get("activation_mode", "default_on")
        if activation_mode not in {"required", "default_on", "optional"}:
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Invalid activation_mode for {code}")
        enabled = bool(rule.get("enabled", True))
        if activation_mode == "required" and not enabled:
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Required rule {code} cannot be disabled")
        enforcement = dict(rule.get("enforcement") or {})
        if enforcement.get("mode", "soft") not in {"hard", "soft"}:
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Invalid enforcement mode for {code}")
        selector = dict(rule.get("selector") or {"match": "all"})
        supported = set(_RULE_TYPES[rule_type]["supported_selectors"])
        selector_keys = {key for key in selector if key != "match"}
        if selector.get("match") != "all" and not selector_keys:
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Rule {code} has no selector")
        if not selector_keys.issubset(supported):
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Rule {code} uses unsupported selector")
        if "effect_dimension_keys" in selector and not isinstance(selector["effect_dimension_keys"], list):
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Rule {code} dimension selector must be an array")
        parameters = _RULE_TYPES[rule_type]["compiler"].validate_parameters(
            code,
            dict(rule.get("parameters") or {}),
        )
        presentation = _normalize_rule_presentation(code, rule.get("presentation"))
        rule_codes.add(code)
        rule.update({
            "code": code,
            "name": str(rule.get("name") or code),
            "type": rule_type,
            "enabled": enabled,
            "activation_mode": activation_mode,
            "selector": selector,
            "enforcement": enforcement,
            "parameters": parameters,
        })
        if presentation:
            rule["presentation"] = presentation
        else:
            rule.pop("presentation", None)
        rules.append(rule)
    return {"responsible_subsystems": subsystems, "rules": rules}


@dataclass
class SchedulingRuleContext:
    active_rules: list[dict[str, Any]] = field(default_factory=list)
    overrides: list[dict[str, Any]] = field(default_factory=list)
    matched_rule_codes_by_step: dict[int, list[str]] = field(default_factory=dict)
    allowed_shift_codes_by_step: dict[int, set[str]] = field(default_factory=dict)
    hard_exclusive_pairs: set[tuple[int, int]] = field(default_factory=set)
    soft_exclusive_rules: list[dict[str, Any]] = field(default_factory=list)
    continuity_groups: dict[str, list[int]] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "active_rule_codes": [rule["code"] for rule in self.active_rules],
            "active_rules": self.active_rules,
            "matched_rule_codes_by_step": {
                str(key): value for key, value in sorted(self.matched_rule_codes_by_step.items())
            },
            "overrides": self.overrides,
            "warnings": self.warnings,
        }


def _matches(step: Any, selector: dict[str, Any]) -> bool:
    if selector.get("match") == "all":
        return True
    resource_type = selector.get("required_resource_type")
    if resource_type is not None:
        if not any(req.get("resource_type") == resource_type for req in step.resource_reqs or []):
            return False
    dimension_keys = selector.get("effect_dimension_keys")
    if dimension_keys is not None:
        if not set(map(str, dimension_keys)).intersection(step.effect_dimension_keys or []):
            return False
    subsystem = selector.get("responsible_subsystem")
    if subsystem is not None and step.responsible_subsystem != subsystem:
        return False
    if selector.get("state_package_membership") is True and not (
        step.state_continuity_groups or []
    ):
        return False
    return True


async def resolve_scheduling_rules(rag_data: Any, session: AsyncSession) -> SchedulingRuleContext:
    machine = await session.scalar(
        select(Machine)
        .where(Machine.id == rag_data.machine_id)
        .options(selectinload(Machine.machine_type))
    )
    if machine is None or machine.machine_type is None:
        raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", "Machine type is unavailable")

    request_context = dict((rag_data.constraints or {}).get("scheduling_rules") or {})
    snapshot = request_context.get("snapshot")
    if snapshot is None:
        config = validate_scheduling_config(machine.machine_type.scheduling_config) or {"rules": []}
        configured_rules = config.get("rules") or []
    else:
        configured_rules = validate_scheduling_config({"rules": snapshot}).get("rules") or []

    requested = request_context.get("active_rule_codes")
    if requested is None:
        active_codes = {
            rule["code"] for rule in configured_rules
            if rule["enabled"] and rule["activation_mode"] in {"required", "default_on"}
        }
    else:
        active_codes = {str(code) for code in requested}
    known_codes = {rule["code"] for rule in configured_rules}
    unknown = active_codes - known_codes
    if unknown:
        raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Unknown active rule codes: {sorted(unknown)}")
    active_codes.update(
        rule["code"] for rule in configured_rules
        if rule["enabled"] and rule["activation_mode"] == "required"
    )
    active_rules = [rule for rule in configured_rules if rule["enabled"] and rule["code"] in active_codes]
    overrides = list(request_context.get("overrides") or [])
    context = SchedulingRuleContext(active_rules=active_rules, overrides=overrides)

    all_steps = sorted(step.step_order for step in rag_data.steps)
    for rule in active_rules:
        matched = [step for step in rag_data.steps if _matches(step, rule["selector"])]
        if not matched:
            context.warnings.append({"code": "SCHEDULING_RULE_NO_MATCH", "rule_code": rule["code"]})
            continue
        matched_orders = [step.step_order for step in matched]
        for step_order in matched_orders:
            context.matched_rule_codes_by_step.setdefault(step_order, []).append(rule["code"])
        compiler = _RULE_TYPES[rule["type"]]["compiler"]
        compiler.compile(context, rule, matched, all_steps)

    for override in overrides:
        rule_code = str(override.get("rule_code") or "")
        step_order = override.get("target_step_order")
        parameters = dict(override.get("parameters") or {})
        if step_order is None or rule_code not in {rule["code"] for rule in active_rules}:
            raise SchedulingRuleError("SCHEDULING_RULE_OVERRIDE_INVALID", "Override target or rule is invalid")
        rule = next(rule for rule in active_rules if rule["code"] == rule_code)
        if not rule["enforcement"].get("overridable"):
            raise SchedulingRuleError("SCHEDULING_RULE_OVERRIDE_NOT_ALLOWED", f"Rule {rule_code} is not overridable")
        extra = {str(code) for code in parameters.get("allow_shift_codes") or []}
        context.allowed_shift_codes_by_step.setdefault(int(step_order), set()).update(extra)

    return context


def _priority_weight(rule: dict[str, Any]) -> int:
    enforcement = rule.get("enforcement") or {}
    if enforcement.get("weight") is not None:
        return max(1, int(round(float(enforcement["weight"]) * 1000)))
    priority = int(enforcement.get("priority") or 2)
    return {1: 100_000, 2: 10_000, 3: 1_000}.get(priority, 1_000)


def apply_scheduling_rules(model: Any, context: SchedulingRuleContext) -> None:
    for left, right in sorted(context.hard_exclusive_pairs):
        if left in model.task_vars and right in model.task_vars:
            model.model.add_no_overlap([model.task_vars[left].interval, model.task_vars[right].interval])

    objective_terms: list[dict[str, Any]] = []
    for item in context.soft_exclusive_rules:
        rule = item["rule"]
        violations = []
        for left, right in item["pairs"]:
            if left not in model.task_vars or right not in model.task_vars:
                continue
            before = model.model.new_bool_var(f"rule_{rule['code']}_{left}_{right}_before")
            after = model.model.new_bool_var(f"rule_{rule['code']}_{left}_{right}_after")
            violation = model.model.new_bool_var(f"rule_{rule['code']}_{left}_{right}_violation")
            model.model.add(model.task_vars[left].end <= model.task_vars[right].start).only_enforce_if(before)
            model.model.add(model.task_vars[right].end <= model.task_vars[left].start).only_enforce_if(after)
            model.model.add_bool_or([before, after, violation])
            violations.append(violation)
        if violations:
            objective_terms.append({
                "type": "scheduling_rule",
                "rule_code": rule["code"],
                "weight_int": _priority_weight(rule),
                "expression": sum(violations),
            })

    for group_key, step_orders in sorted(context.continuity_groups.items()):
        starts = [model.task_vars[step].start for step in step_orders]
        ends = [model.task_vars[step].end for step in step_orders]
        group_start = model.model.new_int_var(0, model.horizon, f"rule_group_{len(objective_terms)}_start")
        group_end = model.model.new_int_var(0, model.horizon, f"rule_group_{len(objective_terms)}_end")
        span = model.model.new_int_var(0, model.horizon, f"rule_group_{len(objective_terms)}_span")
        model.model.add_min_equality(group_start, starts)
        model.model.add_max_equality(group_end, ends)
        model.model.add(span == group_end - group_start)
        rule_code = group_key.split(":", 1)[0]
        rule = next(rule for rule in context.active_rules if rule["code"] == rule_code)
        weight_int = _priority_weight(rule)
        objective_terms.append({
            "type": "scheduling_rule",
            "rule_code": rule_code,
            "group_key": group_key,
            "metric": "span",
            "weight_int": weight_int,
            "expression": span,
        })
        duration_sum = sum(model.task_vars[step].duration for step in step_orders)
        gap = model.model.new_int_var(0, model.horizon, f"rule_group_{len(objective_terms)}_gap")
        model.model.add(gap >= span - duration_sum)
        objective_terms.append({
            "type": "scheduling_rule",
            "rule_code": rule_code,
            "group_key": group_key,
            "metric": "gap",
            "weight_int": weight_int,
            "expression": gap,
        })
        interruptions = []
        for outside_step in sorted(set(model.task_vars) - set(step_orders)):
            outside = model.task_vars[outside_step]
            starts_inside = model.model.new_bool_var(
                f"rule_group_{len(objective_terms)}_{outside_step}_starts_inside"
            )
            ends_inside = model.model.new_bool_var(
                f"rule_group_{len(objective_terms)}_{outside_step}_ends_inside"
            )
            interruption = model.model.new_bool_var(
                f"rule_group_{len(objective_terms)}_{outside_step}_interrupts"
            )
            model.model.add(outside.start >= group_start).only_enforce_if(starts_inside)
            model.model.add(outside.start < group_start).only_enforce_if(starts_inside.Not())
            model.model.add(outside.end <= group_end).only_enforce_if(ends_inside)
            model.model.add(outside.end > group_end).only_enforce_if(ends_inside.Not())
            model.model.add_bool_and([starts_inside, ends_inside]).only_enforce_if(interruption)
            model.model.add_bool_or([starts_inside.Not(), ends_inside.Not(), interruption])
            interruptions.append(interruption)
        if interruptions:
            objective_terms.append({
                "type": "scheduling_rule",
                "rule_code": rule_code,
                "group_key": group_key,
                "metric": "interruption",
                "weight_int": weight_int,
                "expression": sum(interruptions),
            })
    model.objective_cache["scheduling_rule_terms"] = objective_terms


def scheduling_rule_result_diagnostics(
    context: SchedulingRuleContext,
    tasks: list[Any],
) -> dict[str, Any]:
    by_step = {task.step_order: task for task in tasks}
    violations: list[dict[str, Any]] = []
    for item in context.soft_exclusive_rules:
        rule = item["rule"]
        for left, right in item["pairs"]:
            left_task = by_step.get(left)
            right_task = by_step.get(right)
            if left_task is None or right_task is None:
                continue
            if left_task.start_min < right_task.end_min and right_task.start_min < left_task.end_min:
                violations.append({
                    "rule_code": rule["code"],
                    "type": "overlap_pair",
                    "step_orders": [left, right],
                })
    groups = []
    for group_key, step_orders in sorted(context.continuity_groups.items()):
        group_tasks = [by_step[step] for step in step_orders if step in by_step]
        if not group_tasks:
            continue
        start = min(task.start_min for task in group_tasks)
        end = max(task.end_min for task in group_tasks)
        duration = sum(task.duration_min for task in group_tasks)
        group_steps = set(step_orders)
        interruption_steps = sorted(
            task.step_order
            for task in tasks
            if task.step_order not in group_steps and task.start_min >= start and task.end_min <= end
        )
        groups.append({
            "group_key": group_key,
            "step_orders": step_orders,
            "start_min": start,
            "end_min": end,
            "span_min": end - start,
            "internal_gap_min": max(0, end - start - duration),
            "interruption_count": len(interruption_steps),
            "interruption_step_orders": interruption_steps,
        })
    return {
        **context.diagnostics(),
        "violations": violations,
        "continuity_groups": groups,
    }


@register_scheduling_rule_type(
    "group_continuity",
    name="分组连续性",
    description="按责任子系统等步骤属性压缩同组活动跨度。",
    supported_selectors=["responsible_subsystem", "effect_dimension_keys", "required_resource_type"],
    parameters={"group_by": {"enum": ["responsible_subsystem"]}},
)
class GroupContinuityCompiler:
    @staticmethod
    def validate_parameters(code: str, parameters: dict[str, Any]) -> dict[str, Any]:
        group_by = parameters.get("group_by", "responsible_subsystem")
        if group_by != "responsible_subsystem":
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Rule {code} has invalid group_by")
        return {**parameters, "group_by": group_by}

    @staticmethod
    def compile(
        context: SchedulingRuleContext,
        rule: dict[str, Any],
        matched: list[Any],
        _all_steps: list[int],
    ) -> None:
        groups: dict[str, list[int]] = {}
        for step in matched:
            if not step.responsible_subsystem:
                context.warnings.append({
                    "code": "RESPONSIBLE_SUBSYSTEM_MISSING",
                    "rule_code": rule["code"],
                    "step_order": step.step_order,
                })
                continue
            groups.setdefault(step.responsible_subsystem, []).append(step.step_order)
        for group_code, step_orders in groups.items():
            if len(step_orders) >= 2:
                context.continuity_groups[f"{rule['code']}:{group_code}"] = sorted(step_orders)


@register_scheduling_rule_type(
    "state_package_continuity",
    name="状态包连续性",
    description="按求解目标状态路径形成的状态包归属压缩任务跨度、空档和插入。",
    supported_selectors=["state_package_membership"],
    parameters={"group_by": {"enum": ["state_package"]}},
    supported_modes=["layered", "maintenance"],
    builtin_rule={
        "code": "STATE_PACKAGE_CONTINUITY",
        "name": "状态包连续性",
        "type": "state_package_continuity",
        "enabled": True,
        "activation_mode": "optional",
        "selector": {"state_package_membership": True},
        "enforcement": {"mode": "soft", "priority": 2, "overridable": False},
        "parameters": {"group_by": "state_package"},
    },
)
class StatePackageContinuityCompiler:
    @staticmethod
    def validate_parameters(code: str, parameters: dict[str, Any]) -> dict[str, Any]:
        group_by = parameters.get("group_by", "state_package")
        if group_by != "state_package":
            raise SchedulingRuleError(
                "SCHEDULING_RULE_CONFIG_INVALID",
                f"Rule {code} has invalid group_by",
            )
        return {**parameters, "group_by": group_by}

    @staticmethod
    def compile(
        context: SchedulingRuleContext,
        rule: dict[str, Any],
        matched: list[Any],
        _all_steps: list[int],
    ) -> None:
        groups: dict[int, set[int]] = {}
        for step in matched:
            for membership in step.state_continuity_groups or []:
                group_id = membership.get("state_group_id")
                if group_id is None:
                    continue
                try:
                    group_id_int = int(group_id)
                except (TypeError, ValueError):
                    continue
                groups.setdefault(group_id_int, set()).add(step.step_order)
        for group_id, step_orders in groups.items():
            if len(step_orders) >= 2:
                context.continuity_groups[
                    f"{rule['code']}:state_package:{group_id}"
                ] = sorted(step_orders)


@register_scheduling_rule_type(
    "scope_exclusivity",
    name="作用域排他",
    description="命中活动与同一机器计划内其他活动不并行或尽量不并行。",
    supported_selectors=["responsible_subsystem", "effect_dimension_keys", "required_resource_type"],
    parameters={"against": {"enum": ["all_other_tasks"]}},
)
class ScopeExclusivityCompiler:
    @staticmethod
    def validate_parameters(code: str, parameters: dict[str, Any]) -> dict[str, Any]:
        against = parameters.get("against", "all_other_tasks")
        if against != "all_other_tasks":
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Rule {code} has invalid against scope")
        return {**parameters, "against": against}

    @staticmethod
    def compile(
        context: SchedulingRuleContext,
        rule: dict[str, Any],
        matched: list[Any],
        all_steps: list[int],
    ) -> None:
        matched_orders = [step.step_order for step in matched]
        pairs = {
            tuple(sorted((subject, other)))
            for subject in matched_orders
            for other in all_steps
            if subject != other
        }
        if rule["enforcement"].get("mode", "soft") == "hard":
            context.hard_exclusive_pairs.update(pairs)
        else:
            context.soft_exclusive_rules.append({"rule": rule, "pairs": sorted(pairs)})


@register_scheduling_rule_type(
    "shift_restriction",
    name="班次限制",
    description="限制命中活动可使用的 shift code。",
    supported_selectors=["responsible_subsystem", "effect_dimension_keys", "required_resource_type"],
    parameters={"allowed_shift_codes": {"type": "array", "items": {"type": "string"}}},
)
class ShiftRestrictionCompiler:
    @staticmethod
    def validate_parameters(code: str, parameters: dict[str, Any]) -> dict[str, Any]:
        allowed = parameters.get("allowed_shift_codes")
        if not isinstance(allowed, list) or not allowed or any(not str(item).strip() for item in allowed):
            raise SchedulingRuleError(
                "SCHEDULING_RULE_CONFIG_INVALID",
                f"Shift restriction {code} requires allowed_shift_codes",
            )
        return {
            **parameters,
            "allowed_shift_codes": list(dict.fromkeys(str(item).strip() for item in allowed)),
        }

    @staticmethod
    def compile(
        context: SchedulingRuleContext,
        rule: dict[str, Any],
        matched: list[Any],
        _all_steps: list[int],
    ) -> None:
        allowed = {str(code) for code in rule["parameters"].get("allowed_shift_codes") or []}
        for step in matched:
            current = context.allowed_shift_codes_by_step.get(step.step_order)
            context.allowed_shift_codes_by_step[step.step_order] = (
                allowed if current is None else current & allowed
            )

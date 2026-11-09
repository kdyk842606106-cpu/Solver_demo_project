"""Joint bounded state planning and scheduling, promoted from the validated compiler.

No POP-selected task set, experimental oracle, frozen run path, or solver hint
is used. The compiler retains optional occurrences and causal state protection.
The application adapter adds serial support, hard activity windows, cooperative
budgets, and structured diagnostics; existing engines are untouched.
"""
from __future__ import annotations

import copy
import math
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable
from functools import wraps

from ortools.sat.python import cp_model
from planner_experiment.models import Action, EngineResult
from planner_experiment.scenario import scenario_from_dict
from planner_experiment.simulator import PathSimulator
from planner_experiment.validator import ResultValidator
from planner_experiment.working_time import next_work_start, work_end, work_offset, elapsed_start, elapsed_end, next_activity_start
from app.services.planner_run_windows import frozen_run_windows
from app.core.joint_mandatory import identify_mandatory_activities

# Explicit mandatory-presence strengthening is disabled by default. Diagnostic
# processes can select appended/early without changing the business scenario.
_MANDATORY_ENCODING = 'none'
# Independent strengthening experiment; no business input or solver tuning.
_CAUSAL_RANKS = False
# Exact elimination of singleton support auxiliaries. Semantics are verified;
# opt-in for now because eight-worker recovery benchmarks still regress for
# some seeds/repeats. Diagnostic runs compare without changing business inputs.
_SINGLE_SOURCE_DIRECT = False


def search_worker_count(requested: int | None = None) -> int:
    """Use a bounded CPU portfolio; retain an explicit single-thread override."""
    available = max(1, (getattr(os, 'process_cpu_count', os.cpu_count)() or 1))
    if requested is None:
        configured = os.getenv('PLANNER_JOINT_CP_SAT_WORKERS')
        if configured is None:
            requested = min(8, available)
        else:
            try:
                requested = int(configured)
            except ValueError as exc:
                raise ValueError('PLANNER_JOINT_CP_SAT_WORKERS must be a positive integer') from exc
    if type(requested) is not int or requested < 1:
        raise ValueError('Joint CP-SAT worker_threads must be a positive integer')
    return min(requested, available)


class UnsupportedModel(ValueError):
    pass


@dataclass
class Slot:
    index: int
    aid: str
    ordinal: int
    duration: int
    present: object
    start: object
    end: object
    interval: object
    mandatory: bool = False
    causal_rank: object = None

    @property
    def presence_guards(self):
        return [] if self.mandatory else [self.present]


def _occurrence_limits(scenario, *, deadline=None):
    """Remove dominated repeats before creating any CP variables.

    First project onto a proof-checked scope for this run's initial/final
    states. Excluded activities receive zero slots; the rules below use only
    the remaining activities, without modifying the scenario used for replay.

    For an additive activity whose outputs are all persistent, keeping only
    its first occurrence preserves all later supports and final goals, even
    when other activities have destructive effects.
    Removing later occurrences only frees resources/locks and cannot worsen
    makespan or execution count. Windows and release events apply identically
    to every occurrence. This is an optimality-preserving reduction, not a
    claim that the discarded (redundant) execution sequences are infeasible.

    A transition consuming a fact with no producer also proves at most one
    occurrence: the fact cannot become true again. Other destructive actions
    and producers of removable facts keep their original repetition allowance.
    Use parsed semantics, including additional outputs and legacy SET removals.
    """
    original = {a.id: min(scenario.max_steps, a.max_instances
                         if a.max_instances is not None else scenario.max_steps)
                for a in scenario.activities}
    from app.core.joint_pruning import analyze_run_scope
    active, scope = analyze_run_scope(scenario, deadline=deadline)
    removed = {state for a in scenario.activities if a.id in active for state in a.removed_state_ids}
    produced = {state for a in scenario.activities if a.id in active for state in a.output_state_ids}
    state_events = any(e.add_state_ids or e.remove_state_ids for e in scenario.external_events)
    proofs, retained = {}, {}
    for a in scenario.activities:
        if a.id not in active:
            proofs[a.id] = scope['excluded_activities'][a.id]
            continue
        nonrenewable = set(a.transition_state_ids) - produced
        vulnerable = set(a.output_state_ids) & removed
        if state_events:
            retained[a.id] = {"reason": "state_changing_external_event"}
        elif nonrenewable:
            proofs[a.id] = {"reason": "nonrenewable_transition", "state_ids": sorted(nonrenewable)}
        elif not a.removed_state_ids and not vulnerable:
            proofs[a.id] = {"reason": "persistent_outputs", "state_ids": sorted(a.output_state_ids)}
        elif a.removed_state_ids:
            retained[a.id] = {"reason": "state_removal_or_transition", "state_ids": list(a.removed_state_ids)}
        else:
            retained[a.id] = {"reason": "output_can_be_removed", "state_ids": sorted(vulnerable)}
    reason = ("state_changing_external_event" if state_events else
              "no_safe_single_occurrence_proof" if not proofs else None)
    limits = {aid: 0 if aid not in active else min(limit, 1) if aid in proofs else limit
              for aid, limit in original.items()}
    changed = {aid: {"input_limit": original[aid], "effective_limit": limit}
               for aid, limit in limits.items() if limit != original[aid]}
    return limits, {
        "policy": "initial_goal_repeat_proof_v4",
        "eligible": bool(proofs),
        "applied": bool(changed),
        "skip_reason": reason,
        "input_slots": sum(original.values()),
        "effective_slots": sum(limits.values()),
        "removed_slots": sum(original.values()) - sum(limits.values()),
        "activity_limits": changed,
        "activity_proofs": proofs,
        "retained_activities": retained,
        "scope_analysis": scope,
    }


def _compile(payload, *, deadline=None, horizon_override=None):
    # Reject wrappers instead of accidentally consuming generator metadata.
    if 'scenario' in payload or 'answer' in payload or 'metadata' in payload:
        raise UnsupportedModel('Only a raw scenario is accepted')
    scenario = scenario_from_dict(payload)
    if scenario.execution_mode != 'parallel':
        raise UnsupportedModel('v1 supports parallel, non-preemptive execution only')
    if any(e.add_state_ids or e.remove_state_ids for e in scenario.external_events):
        raise UnsupportedModel('State-changing external events require a separate encoding')
    if any(a.duration <= 0 for a in scenario.activities):
        raise UnsupportedModel('v1 requires positive durations')
    occurrence_limits, occurrence_pruning = _occurrence_limits(scenario, deadline=deadline)
    encoding = _MANDATORY_ENCODING
    if encoding not in ('none', 'appended', 'early'):
        raise ValueError('Unknown mandatory activity encoding')
    mandatory, mandatory_stats = set(), {'policy': 'disabled', 'status': 'disabled',
                                        'activity_ids': [], 'proofs': {}}
    if encoding == 'early':
        mandatory, mandatory_stats = identify_mandatory_activities(
            scenario, occurrence_limits, deadline=deadline)
    def check():
        if deadline is not None and time.perf_counter() >= deadline:
            raise TimeoutError('MODEL_BUILD_TIME_LIMIT')
    t0 = scenario.start_time
    # Every event-driven trajectory waits at most until the last event plus
    # the sum of all executed durations. No oracle/witness upper bound is read.
    horizon = max([t0, *[e.time for e in scenario.external_events]]) + scenario.max_steps * max(
        [1, *[a.duration for a in scenario.activities]])
    if horizon_override is not None:
        horizon=horizon_override
    model = cp_model.CpModel()
    finish = model.new_int_var(t0, horizon, 'finish')
    slots = []
    by_activity = defaultdict(list)
    acts = scenario.activity_by_id
    for a in scenario.activities:
        check()
        limit = occurrence_limits[a.id]
        for k in range(limit):
            i = len(slots)
            required = encoding == 'early' and k == 0 and a.id in mandatory
            # Retain a named 0/1-domain variable for extraction, certificates and
            # execution-count optimization. Only its proven domain is fixed.
            p = model.new_int_var(1, 1, f'use:{i}') if required else model.new_bool_var(f'use:{i}')
            s = model.new_int_var(t0, horizon, f's:{i}')
            e = model.new_int_var(t0, horizon, f'e:{i}')
            interval = (model.new_interval_var(s, a.duration, e, f'I:{i}') if required else
                        model.new_optional_interval_var(s, a.duration, e, p, f'I:{i}'))
            slot = Slot(i, a.id, k + 1, a.duration, p, s, e, interval, required)
            if by_activity[a.id]:
                prev = by_activity[a.id][-1]
                if not prev.mandatory:
                    model.add(p <= prev.present)
                model.add(s >= prev.end).only_enforce_if(p)
            if not required:
                model.add(s == t0).only_enforce_if(p.Not())
                model.add(e == t0).only_enforce_if(p.Not())
            release = max([t0, *[scenario.event_by_id[x].time for x in a.required_events]])
            model.add(s >= release).only_enforce_if(slot.presence_guards)
            model.add(finish >= e).only_enforce_if(slot.presence_guards)
            slots.append(slot)
            by_activity[a.id].append(slot)
    model.add(sum(1 if x.mandatory else x.present for x in slots) <= scenario.max_steps)
    producers, deleters = defaultdict(list), defaultdict(list)
    for x in slots:
        a = acts[x.aid]
        for fact in a.output_state_ids:
            producers[fact].append(x)
        for fact in set(a.removed_state_ids) - set(a.output_state_ids):
            deleters[fact].append(x)
    support_count = threat_count = lock_count = 0
    singleton_initial = singleton_producer = 0
    causal_edges = []

    def support(fact, consumer=None, negative=False):
        nonlocal support_count, threat_count, singleton_initial, singleton_producer
        check()
        target = consumer.start if consumer is not None else finish
        truth = fact in scenario.initial_state_ids
        sources = deleters[fact] if negative else producers[fact]
        threats = producers[fact] if negative else deleters[fact]
        options = ([None] if truth != negative else []) + [x for x in sources if x is not consumer]
        active = consumer.presence_guards if consumer is not None else []
        choices = []
        # All alternatives support the SAME fact at the SAME consumer. Select
        # their support time once, then protect that interval once per threat.
        # Previously protection was repeated for every source x consumer x
        # destroyer, producing cubic models for renewable transition cycles.
        # Initial truth precedes all possible completion events (durations > 0).
        if _SINGLE_SOURCE_DIRECT and len(options) == 1:
            # Original sum(choices) == consumer.present fixes the only choice
            # to presence (or 1 for goals). Its support time can therefore be
            # substituted under the SAME guards. An absent consumer does not
            # require a producer or restrict that producer's time.
            producer = options[0]
            support_count += 1
            supported_at = t0 - 1 if producer is None else producer.end
            singleton_initial += producer is None
            singleton_producer += producer is not None
            if producer is not None and not producer.mandatory:
                model.add(producer.present == 1).only_enforce_if(active)
            if _CAUSAL_RANKS and producer is not None and consumer is not None:
                causal_edges.append((consumer.present, producer, consumer))
        else:
            supported_at = model.new_int_var(t0 - 1, horizon, f'supported_at:{support_count}')
            for producer in options:
                selected = model.new_bool_var(f'support:{support_count}')
                support_count += 1
                choices.append(selected)
                if producer is not None and not producer.mandatory:
                    model.add_implication(selected, producer.present)
                if _CAUSAL_RANKS and producer is not None and consumer is not None:
                    causal_edges.append((selected, producer, consumer))
                model.add(supported_at == (producer.end if producer is not None else t0 - 1)).only_enforce_if(selected)
            model.add(sum(choices) == (consumer.present if consumer is not None and not consumer.mandatory else 1))
        model.add(supported_at <= target).only_enforce_if(active)
        # Producers and deleters are disjoint: add effects win over deletions
        # above. Thus a selected source can never itself be a threat, for
        # positive or negative facts. The consumer's own end effect is exempt.
        for destroyer in threats:
            if destroyer is consumer:
                continue
            check()
            threat_count += 1
            guards = [*active, *destroyer.presence_guards]
            if consumer is None:
                model.add(destroyer.end <= supported_at).only_enforce_if(guards)
            else:
                before = model.new_bool_var(f'threat_before:{threat_count}')
                model.add(destroyer.end <= supported_at).only_enforce_if([*guards, before])
                model.add(destroyer.end > target).only_enforce_if([*guards, before.Not()])

    for x in slots:
        for fact in acts[x.aid].precondition_state_ids:
            support(fact, x)
    for fact in scenario.goal_state_ids:
        support(fact)
    for fact in scenario.forbidden_state_ids:
        support(fact, negative=True)
    reads = {a.id: set(a.required_state_ids) for a in scenario.activities}
    writes = {a.id: set(a.written_state_ids) for a in scenario.activities}
    for i, a in enumerate(scenario.activities):
        check()
        for b in scenario.activities[i:]:
            if not (writes[a.id] & (reads[b.id] | writes[b.id]) or reads[a.id] & writes[b.id]):
                continue
            for x in by_activity[a.id]:
                for y in by_activity[b.id]:
                    if x.index >= y.index and a.id == b.id:
                        continue
                    model.add_no_overlap([x.interval, y.interval])
                    lock_count += 1
    for resource in scenario.resources:
        selected = [(x, dict(acts[x.aid].resource_reqs).get(resource.id, 0)) for x in slots]
        selected = [(x, q) for x, q in selected if q]
        model.add_cumulative([x.interval for x, _ in selected], [q for _, q in selected], resource.capacity)
    exclusive_slots = [x for x in slots if acts[x.aid].exclusive_execution]
    if exclusive_slots:
        # Ordinary jobs use one unit; an exclusive job uses the entire gate.
        # Capacity equals the slot count so ordinary concurrency is unchanged.
        # This single cumulative avoids a quadratic set of pairwise disjunctions.
        gate_capacity = len(slots)
        model.add_cumulative([x.interval for x in slots],
                             [gate_capacity if acts[x.aid].exclusive_execution else 1 for x in slots],
                             gate_capacity)
    if encoding == 'appended':
        mandatory, mandatory_stats = identify_mandatory_activities(
            scenario, occurrence_limits, deadline=deadline)
        for aid in sorted(mandatory):
            check()
            # Existing prefix constraints make this equivalent to at least one
            # occurrence. Later occurrences and all timing decisions remain free.
            model.add(by_activity[aid][0].present == 1).with_name('mandatory:' + aid)
    mandatory_stats.update(encoding=encoding, added_constraints=len(mandatory) if encoding == 'appended' else 0,
                           fixed_first_occurrences=len(mandatory) if encoding == 'early' else 0)
    rank_stats = {'enabled': _CAUSAL_RANKS, 'policy': 'conditional_support_dag_v2_unbound_absent',
                  'variables': 0, 'edges': 0, 'constraints': 0, 'upper_bound': 0}
    if _CAUSAL_RANKS:
        # Add auxiliary variables after the existing compiler, preserving all
        # original variable indices and constraint order for paired comparisons.
        # A chosen producer ends before its consumer starts; positive durations
        # imply an acyclic instance graph. A topological rank fits in the number
        # of selected instances (<= max_steps). Different roots/parallel tasks
        # may share ranks. No AllDifferent, objective or timing order is added.
        rank_limit = min(scenario.max_steps, len(slots))
        rank_start_constraints = len(model.proto.constraints)
        for slot in slots:
            check()
            slot.causal_rank = model.new_int_var(0, rank_limit, f'causal_rank:{slot.index}')
            bound = model.add(slot.causal_rank >= 1)
            bound.only_enforce_if(slot.presence_guards)
            bound.with_name('causal_rank:present')
            # Inactive instances have no selected support edges. Leave their
            # auxiliary ranks free: tying rank zero to absence unnecessarily
            # couples presence decisions to the causal ordering encoding.
        for selected, producer, consumer in causal_edges:
            check()
            edge = model.add(producer.causal_rank < consumer.causal_rank)
            edge.only_enforce_if(selected)
            edge.with_name(f'causal_rank:support:{selected.index}:{producer.index}:{consumer.index}')
        rank_stats.update(variables=len(slots), edges=len(causal_edges), upper_bound=rank_limit,
                          constraints=len(model.proto.constraints)-rank_start_constraints)
    model.minimize(finish)
    check()
    error = model.validate()
    if error:
        raise ValueError(error)
    stats = {'candidate_activities': len(acts), 'optional_occurrence_slots': len(slots),
             'occurrence_pruning': occurrence_pruning,
             'mandatory_activities': mandatory_stats,
             'causal_ranks': rank_stats,
             'exclusive_activity_count': sum(a.exclusive_execution for a in scenario.activities),
             'exclusive_occurrence_slots': len(exclusive_slots),
             'state_count': len(scenario.state_definitions), 'horizon': horizon,
             'support_choices': support_count, 'threat_checks': threat_count, 'interval_locks': lock_count,
               'single_source_direct': {'enabled': _SINGLE_SOURCE_DIRECT,
                   'initial_sources': singleton_initial, 'producer_sources': singleton_producer,
                   'eliminated_variables': 2 * (singleton_initial + singleton_producer)},
               'support_choice_variables': support_count - singleton_initial - singleton_producer,
             'causal_protection_encoding': 'shared_support_time_v1',
             'variables': len(model.proto.variables), 'constraints': len(model.proto.constraints)}
    return model, finish, slots, stats


def prepare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Preserve window openings during replay, without changing caller input."""
    effective = copy.deepcopy(payload)
    run_windows = frozen_run_windows(effective)
    from app.services.planner_calendars import calendar_intervals, lift_day_windows
    frozen = effective.pop('working_intervals', None)
    expanded_calendar = calendar_intervals(effective)
    if frozen is not None and frozen != expanded_calendar:
        raise ValueError('Frozen calendar intervals differ from current expansion')
    effective['working_intervals'] = expanded_calendar
    allowed=lift_day_windows(effective,expanded_calendar)
    from app.services.planner_rules import exclusive_activity_ids
    exclusive = exclusive_activity_ids(effective)
    if effective.get('lift_day_windows') is not None and effective['lift_day_windows']!=allowed:
        raise ValueError('Frozen lift day windows differ from current expansion')
    for activity in effective.get('activities',[]):
        # Ignore raw derived flags; only supported scenario rules grant exclusivity.
        activity.pop('exclusive_execution', None)
        if activity['id'] in exclusive:
            activity['exclusive_execution'] = True
        activity.pop('allowed_execution_windows',None)
        if activity['id'] in allowed:
            activity['allowed_execution_windows']=allowed[activity['id']]
    windows = effective.pop("time_windows", [])
    if not isinstance(windows, list):
        raise ValueError("time_windows must be a list")
    for key in ("calendar", "calendars", "scheduling_rules", "adjustments", "resource_instances"):
        if effective.get(key):
            raise UnsupportedModel(f"Joint CP-SAT does not support {key}")
    acts = {a["id"]: a for a in effective.get("activities", [])}
    seen_ids, seen_activities = set(), set()
    event_ids = {e["id"] for e in effective.get("external_events", [])}
    for window in windows:
        if not isinstance(window, dict):
            raise ValueError("Each time window must be an object")
        aid, wid = window.get("activity_id"), window.get("id")
        if aid not in acts or aid in seen_activities or not isinstance(wid, str) or not wid or wid in seen_ids:
            raise ValueError("Unknown activity or duplicate/missing time window ID")
        start, end = window.get("earliest_start"), window.get("latest_finish")
        if type(start) is not int or type(end) is not int or start < effective.get("start_time", 0) or end < start + acts[aid]["duration"]:
            raise ValueError("Invalid earliest_start/latest_finish window")
        eid = "joint-window:" + wid
        if eid in event_ids:
            raise ValueError("Window release event ID collision")
        seen_ids.add(wid)
        seen_activities.add(aid)
        event_ids.add(eid)
        effective.setdefault("external_events", []).append({"id": eid, "time": start, "add_state_ids": [], "remove_state_ids": []})
        acts[aid].setdefault("event_reqs", []).append(eid)
    for window in run_windows:
        opening = window.get('earliest_start')
        if opening is None:
            continue
        eid = 'joint-run-window:' + window['id']
        if eid in event_ids:
            raise ValueError('Run window release event ID collision')
        event_ids.add(eid)
        effective.setdefault('external_events', []).append({'id': eid,
            'time': max(effective.get('start_time', 0), opening), 'add_state_ids': [], 'remove_state_ids': []})
        # Occurrences of one activity are ordered. All later executions already
        # follow the first, so the same release event is also valid for replay.
        acts[window['activity_id']].setdefault('event_reqs', []).append(eid)
    return effective


def build_model(payload: dict[str, Any], *, deadline: float | None = None):
    model, scenario, slots, stats, _ = _build_model_with_finish(payload, deadline=deadline)
    return model, scenario, slots, stats


def _build_model_with_finish(payload, *, deadline):
    effective = prepare_payload(payload)
    mode = effective.get("execution_mode", "serial")
    if mode not in ("serial", "parallel"):
        raise UnsupportedModel("Unsupported execution mode")
    compilation = copy.deepcopy(effective)
    compilation["execution_mode"] = "parallel"
    working=effective.get('working_intervals', [])
    if working:
        # Exact for a shared pause/resume calendar: no activity or resource can
        # do work during a closure. State/lock orders are unchanged by removing
        # those empty intervals. Replay still runs on the real elapsed axis.
        compilation['working_intervals']=[]
        compilation['start_time']=0
        for event in compilation.get('external_events', []):
            event['time']=work_offset(working,event['time'])
    from app.services.planner_calendars import night_rule_enabled
    model, finish, slots, stats = _compile(compilation, deadline=deadline,
        horizon_override=sum(b-a for a,b in working) if night_rule_enabled(effective) else None)
    if mode == "serial":
        model.add_no_overlap([x.interval for x in slots])
    windows = {w["activity_id"]: w for w in payload.get("time_windows", [])}
    run_windows = {w['activity_id']: w for w in frozen_run_windows(payload)}
    activity_by_id={a['id']:a for a in effective['activities']}
    for slot in slots:
        activity=activity_by_id[slot.aid]
        if 'allowed_execution_windows' in activity:
            domains=[[work_offset(working,left),work_offset(working,right)-activity['duration']]
                     for left,right in activity['allowed_execution_windows']]
            domains=[d for d in domains if d[0]<=d[1]]
            if domains:
                model.add_linear_expression_in_domain(slot.start,cp_model.Domain.from_intervals(domains)).only_enforce_if(slot.presence_guards)
            else:
                model.add(slot.present==0)
        if slot.aid in windows:
            closing=windows[slot.aid]['latest_finish']
            model.add(slot.end <= (work_offset(working,closing) if working else closing)).only_enforce_if(slot.presence_guards)
        if slot.ordinal == 1 and slot.aid in run_windows:
            closing = run_windows[slot.aid].get('latest_finish')
            if closing is not None:
                model.add(slot.end <= (work_offset(working, closing) if working else closing)).only_enforce_if(slot.presence_guards)
    error = model.validate()
    if error:
        raise ValueError(error)
    stats.update(execution_mode=mode, time_window_count=len(windows), run_time_window_count=len(run_windows),
                 model_time_axis='working_minutes' if working else 'elapsed_minutes',
                 variables=len(model.proto.variables), constraints=len(model.proto.constraints))
    return model, scenario_from_dict(effective), slots, stats, finish


def _required_execution_lower_bound(scenario):
    """Each unique producer of a necessary, initially absent fact must run at least once."""
    producers = defaultdict(set)
    for activity in scenario.activities:
        for fact in activity.output_state_ids:
            producers[fact].add(activity.id)
    needed = list(scenario.goal_state_ids)
    required = set()
    activities = scenario.activity_by_id
    while needed:
        fact = needed.pop()
        if fact in scenario.initial_state_ids or len(producers[fact]) != 1:
            continue
        aid = next(iter(producers[fact]))
        if aid not in required:
            required.add(aid)
            needed.extend(activities[aid].precondition_state_ids)
    return len(required)


def _check_windows(payload: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    windows = {w["activity_id"]: w for w in payload.get("time_windows", [])}
    run_windows = {w['activity_id']: w for w in frozen_run_windows(payload)}
    seen = set()
    for row in sorted(rows, key=lambda r: (r['start'], r['activity_id'])):
        w = windows.get(row["activity_id"])
        if w and (row["start"] < w["earliest_start"] or row["end"] > w["latest_finish"]):
            raise ValueError(f"Time window violation: {w['id']}")
        first = row['activity_id'] not in seen
        seen.add(row['activity_id'])
        w = run_windows.get(row['activity_id'])
        if first and w:
            lo, hi = w.get('earliest_start'), w.get('latest_finish')
            if (lo is not None and row['start'] < lo) or (hi is not None and row['end'] > hi):
                raise ValueError(f"First execution time window violation: {w['id']}")


def _check_resources(scenario: Any, executions: Any) -> None:
    """Independent interval sweep; completions release capacity before starts."""
    acts = scenario.activity_by_id
    for resource in scenario.resources:
        changes = defaultdict(int)
        for e in executions:
            quantity = dict(acts[e.activity_id].resource_reqs).get(resource.id, 0)
            changes[e.start_time] += quantity
            changes[e.end_time] -= quantity
        occupied = 0
        for t in sorted(changes):
            occupied += changes[t]
            if occupied < 0 or occupied > resource.capacity:
                raise ValueError(f"Resource capacity violation: {resource.id} at {t}")


def replay_candidate(payload: dict[str, Any], scenario: Any, rows: list[dict[str, Any]], *, run_id: str, seed: int):
    """Left shift preserves all disjoint orders; stop only at a valid terminal."""
    _check_windows(payload, rows)
    ordered = sorted(rows, key=lambda r: (r["start"], r["activity_id"], r["ordinal"]))
    for row in ordered:
        if next_activity_start(scenario.working_intervals,row['start'],scenario.activity_by_id[row['activity_id']])!=row['start']:
            raise ValueError('Activity execution crosses a forbidden night interval')
        if work_end(scenario.working_intervals,row['start'],scenario.activity_by_id[row['activity_id']].duration)!=row['end']:
            raise ValueError('Calendar work duration violation')
    shifted = []
    for i, row in enumerate(ordered):
        a = scenario.activity_by_id[row["activity_id"]]
        release = max([scenario.start_time, *[scenario.event_by_id[e].time for e in a.required_events]])
        start = max([release, *[shifted[j]["end"] for j in range(i) if ordered[j]["end"] <= row["start"]]])
        start = next_activity_start(scenario.working_intervals, start, a)
        if start is None or start > row["start"]:
            raise ValueError("Left shift delayed an activity")
        shifted.append(dict(row, start=start, end=work_end(scenario.working_intervals,start,a.duration)))
    pending = sorted(shifted, key=lambda r: (r["start"], r["activity_id"], r["ordinal"]))
    sim = PathSimulator(scenario)
    state = sim.initial_state()
    if scenario.execution_mode == "serial":
        for row in pending:
            if sim.is_goal(state):
                break
            while state.time < row["start"]:
                waits = [a for a in sim.enabled_actions(state) if a.kind == "WAIT"]
                if not waits or waits[0].target_time > row["start"]:
                    raise ValueError("Serial schedule cannot be replayed")
                state = sim.transition(state, waits[0])
            if state.time != row["start"]:
                raise ValueError("Serial execution overlaps")
            state = sim.transition(state, Action("EXECUTE", activity_id=row["activity_id"]))
    else:
        while pending or state.running:
            if sim.is_goal(state):
                break
            while pending and pending[0]["start"] == state.time:
                row = pending.pop(0)
                state = sim.transition(state, Action("START", activity_id=row["activity_id"]))
            if not pending and not state.running:
                break
            advances = [a for a in sim.enabled_actions(state) if a.kind == "ADVANCE"]
            if not advances or (pending and pending[0]["start"] < advances[0].target_time):
                raise ValueError("Parallel schedule cannot be replayed")
            state = sim.transition(state, advances[0])
    if not sim.is_goal(state):
        raise ValueError("Schedule does not reach all positive/negative goals")
    candidate = sim.candidate_from_state(state, algorithm="JOINT_CP_SAT", run_id=run_id, seed=seed,
                                         discovered_at_seconds=0, normalize=False)
    raw_span = max([scenario.start_time, *[r["end"] for r in rows]]) - scenario.start_time
    shifted_span = max([scenario.start_time, *[r["end"] for r in shifted]]) - scenario.start_time
    candidate = replace(candidate, raw_makespan=raw_span,
                        normalization_saved_time=raw_span - candidate.metrics.makespan)
    checked = ResultValidator(scenario).validate(candidate)
    if not checked.valid:
        raise ValueError(checked.code)
    candidate = checked.candidate
    _check_windows(payload, [{"activity_id": e.activity_id, "start": e.start_time, "end": e.end_time} for e in candidate.executions])
    _check_resources(scenario, candidate.executions)
    retained = {(e.activity_id, e.ordinal) for e in candidate.executions}
    details = {"raw_schedule_makespan": raw_span, "shifted_schedule_makespan": shifted_span,
               "delivered_makespan": candidate.metrics.makespan,
               "left_shift_saved_time": raw_span - shifted_span,
               "terminal_tail_saved_time": shifted_span - candidate.metrics.makespan,
               "omitted_tail_occurrences": [r for r in shifted if (r["activity_id"], r["ordinal"]) not in retained]}
    return candidate, details


def _certify_feedback(model, finish, slots, scenario, candidate, *, deadline, seed):
    """Find an exact model witness before using a replayed plan as a cutoff.

    Fix only a disposable clone. Auxiliary causal choices remain free; SAT
    certifies that they can support this exact plan. UNKNOWN/INFEASIBLE here
    rejects the optimization, never the original planning problem.
    """
    started = time.perf_counter()
    rows = {(e.activity_id, e.ordinal): e for e in candidate.executions}
    keys = {(x.aid, x.ordinal) for x in slots}
    if len(rows) != len(candidate.executions) or not rows.keys() <= keys:
        return {"status": "UNREPRESENTABLE"}, None
    def offset(value):
        return work_offset(scenario.working_intervals, value) if scenario.working_intervals else value
    cap = offset(scenario.start_time + candidate.metrics.makespan)
    witness = model.clone()
    witness.clear_objective()
    witness.clear_hints()
    for slot in slots:
        row = rows.get((slot.aid, slot.ordinal))
        witness.add(slot.present == int(row is not None))
        if row is not None:
            witness.add(slot.start == offset(row.start_time))
            witness.add(slot.end == offset(row.end_time))
    witness.add(finish == cap)
    remaining = deadline - time.perf_counter()
    if remaining <= 0:
        return {"status": "BUDGET_EXHAUSTED"}, None
    verifier = cp_model.CpSolver()
    verifier.parameters.num_search_workers = 1
    verifier.parameters.random_seed = seed
    verifier.parameters.max_time_in_seconds = min(2.0, remaining)
    status = verifier.solve(witness)
    record = {"status": verifier.status_name(status), "seconds": time.perf_counter()-started,
              "branches": verifier.num_branches, "conflicts": verifier.num_conflicts,
              "finish_cap": cap, "makespan": candidate.metrics.makespan,
              "execution_count": len(rows)}
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE) or time.perf_counter() >= deadline:
        return record, None
    values = [verifier.value(witness.get_int_var_from_proto_index(i)) for i in range(len(witness.proto.variables))]
    return record, values


def _apply_feedback(model, finish, slots, certificate, values, *, count_phase):
    # A non-strict bound retains the witnessed solution and every lexicographic
    # improvement. No order, causal choice or presence value is hard-fixed.
    model.add(finish <= certificate["finish_cap"])
    if count_phase:
        model.add(sum(x.present for x in slots) <= certificate["execution_count"])
    model.clear_hints()
    for i, value in enumerate(values):
        model.add_hint(model.get_int_var_from_proto_index(i), value)


class SearchProgress:
    """Use CP-SAT samples only; its counters restart at each solve()."""
    def __init__(self, observer):
        self.observer = observer
        self.metrics = {"phase": "BUILDING", "candidate_count": 0}
        self.base_branches = self.base_conflicts = 0
        self.previous = None

    def phase(self, name):
        self.metrics.update(phase=name, branches_per_second=None)
        self.previous = None
        self.base_branches = self.metrics.get("branches", 0)
        self.base_conflicts = self.metrics.get("conflicts", 0)
        self.emit()

    def sample(self, source):
        branches, seconds = source.num_branches, source.wall_time
        if self.previous is not None:
            prev_branches, prev_seconds = self.previous
            if seconds > prev_seconds:
                self.metrics["branches_per_second"] = round((branches-prev_branches)/(seconds-prev_seconds), 2)
        self.previous = branches, seconds
        self.metrics.update(branches=self.base_branches + branches,
                            conflicts=self.base_conflicts + source.num_conflicts,
                            sampled_at=datetime.now(timezone.utc).isoformat())

    def emit(self, candidate=None):
        if self.observer:
            self.observer(dict(self.metrics), candidate)


def solve_joint(payload: dict[str, Any], *, run_id: str, seed: int, budget: Any,
                deadline: float | None = None, candidate_observer: Callable | None = None,
                progress_observer: Callable | None = None, worker_threads: int | None = None) -> EngineResult:
    started = time.perf_counter()
    workers = search_worker_count(worker_threads)
    limit = float(budget.time_limit_seconds)
    if not math.isfinite(limit) or limit < 0:
        raise ValueError("Joint CP-SAT requires a finite non-negative time budget")
    deadline = min(deadline, started + limit) if deadline is not None else started + limit
    stats: dict[str, Any] = {"proven_optimal": False, "proven_infeasible": False, "candidate_count": 0,
        "validator_rejections": [], "late_candidate_count": 0, "candidate_history": [],
        "normalization_policy": "preserve_disjoint_orders_left_shift_then_stop_at_goal",
        "worker_threads": workers, "random_seed": seed, "lower_bound": None, "best_makespan": None,
        "search_counter_scope": "solver_response_per_epoch" if workers > 1 else "single_worker",
        "feedback_verifier_threads": 1,
        "time_limit_seconds": limit, "budget_policy": "cooperative deadline includes build and validation; late candidates excluded",
        "proof_scope": "input execution count bounds", "transition_limit_applied": False}
    stats.update(feedback_policy="latest_certified_incumbent_restart_v2", feedback_restarts=0,
                 feedback_certificates=[], search_epochs=0)
    best = None
    first = None
    bound = 0
    solver = None
    progress = SearchProgress(progress_observer)
    progress.metrics.update(worker_threads=workers,
                            search_counter_scope=stats['search_counter_scope'])
    progress.emit()
    callback_lock = threading.RLock()
    def synchronized(callback):
        @wraps(callback)
        def guarded(*args, **kwargs):
            with callback_lock:
                return callback(*args, **kwargs)
        return guarded
    try:
        if time.perf_counter() >= deadline:
            raise TimeoutError()
        model, scenario, slots, model_stats, finish = _build_model_with_finish(payload, deadline=deadline)
        stats["model"] = model_stats
        stats["build_seconds"] = time.perf_counter() - started
        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = workers
        solver.parameters.random_seed = seed
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise TimeoutError()
        solver.parameters.max_time_in_seconds = remaining

        def elapsed_objective(value):
            if scenario.working_intervals:
                return elapsed_end(scenario.working_intervals, max(0,math.ceil(value-1e-7)), scenario.start_time)-scenario.start_time
            return max(0,math.ceil(value-scenario.start_time-1e-7))

        @synchronized
        def on_bound(value):
            nonlocal bound
            previous_bound = stats["lower_bound"]
            bound = max(bound, elapsed_objective(value))
            stats["lower_bound"] = bound
            if previous_bound != bound:
                progress.metrics["lower_bound"] = bound
                progress.emit()
            if best is not None and bound >= best.metrics.makespan:
                if bound > best.metrics.makespan:
                    stats["validator_rejections"].append("Bound exceeds validated incumbent")
                solver.stop_search()
        solver.best_bound_callback = on_bound
        count_phase = False
        feedback_disabled = False
        pending_feedback = None
        progress.phase("FINDING_FIRST")
        stats.update(tie_breaker="minimize_execution_count", makespan_proven_optimal=False,
                     execution_count_proven_optimal=False)

        class Observer(cp_model.CpSolverSolutionCallback):
            @synchronized
            def on_solution_callback(self):
                nonlocal best, first, pending_feedback
                if time.perf_counter() >= deadline:
                    self.stop_search()
                    return
                try:
                    rows = [{"activity_id": x.aid, "ordinal": x.ordinal, "start": self.value(x.start), "end": self.value(x.end)}
                            for x in slots if self.value(x.present)]
                    if scenario.working_intervals:
                        rows=[dict(row,start=elapsed_start(scenario.working_intervals,row['start']),
                            end=elapsed_end(scenario.working_intervals,row['end'],scenario.start_time)) for row in rows]
                    candidate, normalization = replay_candidate(payload, scenario, rows, run_id=run_id, seed=seed)
                    now = time.perf_counter()
                    if now >= deadline:
                        stats["late_candidate_count"] += 1
                        self.stop_search()
                        return
                    elapsed = now - started
                    candidate = replace(candidate, discovered_at_seconds=elapsed)
                    first = elapsed if first is None else first
                    stats["candidate_count"] += 1
                    record = {"seconds": elapsed, "solver_objective": elapsed_objective(self.value(finish)),
                              "execution_count": len(candidate.executions),
                              **normalization}
                    if len(stats["candidate_history"]) < 200:
                        stats["candidate_history"].append({k: v for k, v in record.items() if k != "omitted_tail_occurrences"})
                    if best is None or (candidate.metrics.makespan, len(candidate.executions)) < (
                            best.metrics.makespan, len(best.executions)):
                        best = candidate
                        stats["best_makespan"] = best.metrics.makespan
                        stats["best_execution_count"] = len(best.executions)
                        stats["normalization"] = record
                        progress.metrics.update(last_improved_at=datetime.now(timezone.utc).isoformat(),
                                                best_makespan=best.metrics.makespan,
                                                best_execution_count=len(best.executions))
                    progress.metrics.update(phase="EXECUTION_COUNT" if count_phase else "MAKESPAN",
                                            candidate_count=stats["candidate_count"])
                    # Parallel solution callbacks may originate from different
                    # subsolvers: their counters cannot form one time series.
                    # Keep incumbent updates live, sample the native response
                    # once per completed epoch (not a sum of all workers).
                    if workers == 1:
                        progress.sample(self)
                    progress.emit(candidate if best is candidate else None)
                    if candidate_observer is not None:
                        candidate_observer(candidate)
                    if not count_phase:
                        on_bound(self.best_objective_bound)
                    # Only stop for a strict objective improvement over the raw
                    # assignment. Do not change a model while solve() is active.
                    better_than_raw = (len(candidate.executions) < sum(self.value(x.present) for x in slots)
                                       if count_phase else candidate.metrics.makespan < elapsed_objective(self.value(finish)))
                    if (not feedback_disabled and best is candidate and better_than_raw
                            and (count_phase or bound < best.metrics.makespan)):
                        pending_feedback = candidate
                        self.stop_search()
                except Exception as exc:
                    stats["validator_rejections"].append(str(exc))
                    self.stop_search()

        def search_phase(name):
            nonlocal pending_feedback, feedback_disabled
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    return cp_model.UNKNOWN
                pending_feedback = None
                stats["search_epochs"] += 1
                progress.metrics["search_epoch"] = stats["search_epochs"]
                solver.parameters.max_time_in_seconds = remaining
                status = solver.solve(model, Observer())
                progress.sample(solver)
                progress.emit()
                stats.update(solver_status=solver.status_name(status), branches=progress.metrics["branches"],
                             conflicts=progress.metrics["conflicts"], response_stats=solver.response_stats())
                if not count_phase and status not in (cp_model.INFEASIBLE, cp_model.MODEL_INVALID):
                    on_bound(solver.best_objective_bound)
                if (pending_feedback is None or stats["validator_rejections"]
                        or time.perf_counter() >= deadline
                        or (not count_phase and bound >= best.metrics.makespan)):
                    return status
                # solve() has returned: all solution callbacks are drained.
                # pending_feedback requests a restart; it may predate a better
                # raw-valid solution delivered while the stop was in flight.
                # Certify the current lexicographic best, never the stale trigger.
                feedback_candidate = best
                feedback_selection = {
                    "trigger_makespan": pending_feedback.metrics.makespan,
                    "trigger_execution_count": len(pending_feedback.executions),
                    "selected_makespan": feedback_candidate.metrics.makespan,
                    "selected_execution_count": len(feedback_candidate.executions),
                    "selected_discovered_at_seconds": feedback_candidate.discovered_at_seconds,
                    "refreshed_from_trigger": feedback_candidate is not pending_feedback,
                }
                try:
                    certificate, values = _certify_feedback(model, finish, slots, scenario, feedback_candidate,
                                                            deadline=deadline, seed=seed)
                except Exception as exc:
                    certificate, values = {"status": "ERROR", "error": str(exc)}, None
                certificate.update(phase=name, elapsed_seconds=time.perf_counter()-started,
                                   applied=False, selection=feedback_selection)
                stats["feedback_certificates"].append(certificate)
                if values is not None:
                    _apply_feedback(model, finish, slots, certificate, values, count_phase=count_phase)
                    certificate["applied"] = True
                    stats["feedback_restarts"] += 1
                else:
                    # Keep the validated incumbent and resume the unmodified
                    # model. A failed witness must never cause an infeasibility
                    # claim, cutoff, or a deterministic repeated-restart loop.
                    feedback_disabled = True
                progress.phase(name)

        status = search_phase("MAKESPAN")
        ended_in_time = time.perf_counter() <= deadline
        if status == cp_model.MODEL_INVALID:
            stats["validator_rejections"].append(solver.solution_info())
            outcome = "ERROR"
        elif stats["validator_rejections"] or (status == cp_model.INFEASIBLE and best is not None):
            outcome = "ERROR"
        elif ended_in_time and best is not None and bound == best.metrics.makespan:
            stats["makespan_proven_optimal"] = True
            required_count = _required_execution_lower_bound(scenario)
            count_proven = len(best.executions) == required_count
            outcome = "TIMEOUT_PARTIAL"
            if not count_proven:
                # Search only for strictly shorter execution lists at the proven
                # makespan. Keep the validated incumbent if the shared budget expires.
                finish_at = scenario.start_time + best.metrics.makespan
                finish_cap = work_offset(scenario.working_intervals, finish_at) if scenario.working_intervals else finish_at
                count = sum(x.present for x in slots)
                model.add(finish <= finish_cap)
                model.add(count < len(best.executions))
                model.minimize(count)
                remaining = deadline - time.perf_counter()
                if remaining > 0:
                    count_phase = True
                    progress.phase("EXECUTION_COUNT")
                    solver.best_bound_callback = None
                    # The previous full hint need not satisfy the strict new
                    # count cap. Drop it; it is never a constraint.
                    model.clear_hints()
                    secondary = search_phase("EXECUTION_COUNT")
                    stats["execution_count_solver_status"] = solver.status_name(secondary)
                    if secondary == cp_model.MODEL_INVALID:
                        stats["validator_rejections"].append(solver.solution_info())
                    if time.perf_counter() <= deadline:
                        count_proven = (len(best.executions) == required_count or secondary == cp_model.INFEASIBLE
                                        or (secondary == cp_model.OPTIMAL and len(best.executions) <= solver.objective_value))
            if stats["validator_rejections"]:
                outcome = "ERROR"
            elif count_proven:
                stats["execution_count_proven_optimal"] = True
                stats["proven_optimal"] = True
                outcome = "OPTIMAL"
        elif ended_in_time and status == cp_model.INFEASIBLE:
            outcome = "INFEASIBLE"
            stats["proven_infeasible"] = True
            stats["lower_bound"] = None
        elif best is not None:
            outcome = "TIMEOUT_PARTIAL" if not ended_in_time or status == cp_model.FEASIBLE else "FEASIBLE"
        else:
            outcome = "TIMEOUT_EMPTY" if not ended_in_time or status == cp_model.UNKNOWN else "UNKNOWN"
    except UnsupportedModel as exc:
        return EngineResult("JOINT_CP_SAT", run_id, seed, "UNSUPPORTED", stats=stats,
                            diagnosis={"error_code": "JOINT_CP_SAT_UNSUPPORTED", "error_message": str(exc)}, error=str(exc))
    except TimeoutError:
        outcome = "TIMEOUT_PARTIAL" if best is not None else "TIMEOUT_EMPTY"
    except Exception as exc:
        stats["validator_rejections"].append(str(exc))
        outcome = "ERROR"
    stats.update(stop_reason=outcome, elapsed_seconds=time.perf_counter()-started)
    error = "; ".join(stats["validator_rejections"]) or None
    return EngineResult("JOINT_CP_SAT", run_id, seed, outcome, paths=(best,) if best is not None else (),
                        first_solution_seconds=first, stats=stats, error=error,
                        diagnosis={"error_code": "JOINT_CP_SAT_" + outcome,
                                   "error_message": error or {"INFEASIBLE": "已证明在当前约束和执行次数范围内无解",
                                       "TIMEOUT_EMPTY": "预算内未找到通过校验的方案，尚未证明无解"}.get(outcome, "")})

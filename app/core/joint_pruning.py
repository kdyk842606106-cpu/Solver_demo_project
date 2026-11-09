"""Run-specific, proof-checked activity slicing for the joint compiler.

Only positive activity preconditions and final positive/negative goals are
handled. Resource/calendar restrictions are deliberately relaxed here. Each
completed round preserves an optimal plan by deleting unreachable executions
or projecting a plan onto a backward-closed set of relevant activities.
"""
from collections import defaultdict, deque
import time


class _AnalysisTimeout(Exception):
    pass


def _reachable(ids, initial, requires, outputs, check):
    reachable = set(initial)
    waiting = defaultdict(list)
    missing = {}
    ready = deque()
    for aid in ids:
        check()
        absent = requires[aid] - reachable
        missing[aid] = len(absent)
        if not absent:
            ready.append(aid)
        for fact in absent:
            waiting[fact].append(aid)
    enabled = set()
    while ready:
        check()
        aid = ready.popleft()
        enabled.add(aid)
        for fact in outputs[aid] - reachable:
            reachable.add(fact)
            for consumer in waiting[fact]:
                missing[consumer] -= 1
                if missing[consumer] == 0:
                    ready.append(consumer)
    return reachable, enabled


def _relevant(ids, goals, forbidden, stable, requires, outputs, removes, check):
    producers = defaultdict(list)
    relevant = set()
    pending = deque(goals - stable)
    for aid in ids:
        check()
        for fact in outputs[aid]:
            producers[fact].append(aid)
        # Cleanup may be needed even when the forbidden fact is initially
        # absent: a required activity can produce it later.
        if removes[aid] & forbidden:
            relevant.add(aid)
            pending.extend(requires[aid] - stable)
    visited = set()
    while pending:
        check()
        fact = pending.popleft()
        if fact in visited:
            continue
        visited.add(fact)
        for aid in producers[fact]:
            if aid not in relevant:
                relevant.add(aid)
                pending.extend(requires[aid] - stable)
    return relevant


def _verify_round(ids, reachable, enabled, relevant, initial, goals, forbidden,
                  stable, requires, outputs, removes, check):
    """Check the projection certificate independently of the work queues."""
    if not initial <= reachable or not relevant <= enabled <= set(ids):
        return False
    if not stable <= initial:
        return False
    needed = set(goals)
    for aid in relevant:
        check()
        needed.update(requires[aid])
    needed -= stable
    for aid in ids:
        check()
        if requires[aid] <= reachable:
            if aid not in enabled or not outputs[aid] <= reachable:
                return False
        elif aid in enabled:
            return False
        if aid in enabled:
            if removes[aid] & stable:
                return False
            if aid not in relevant and (outputs[aid] & needed or removes[aid] & forbidden):
                return False
    return True


def _inverse_cycle_candidates(ids, scenario, requires, outputs, removes, check):
    """Discover private two-state resets using indexes; verification is separate.

    A forward execution consumes an initially true private token and produces
    a persistent fact. Its inverse has no purpose except restoring that token.
    Only the exact single-output/single-transition shape is admitted here.
    """
    writers, users, edges = defaultdict(set), defaultdict(set), defaultdict(list)
    activities = scenario.activity_by_id
    for aid in ids:
        check()
        for fact in outputs[aid] | removes[aid]:
            writers[fact].add(aid)
        for fact in requires[aid]:
            users[fact].add(aid)
        if len(outputs[aid]) == len(removes[aid]) == 1:
            before, after = next(iter(removes[aid])), next(iter(outputs[aid]))
            if before != after and set(activities[aid].transition_state_ids) == {before}:
                edges[before, after].append(aid)
    initial, goals, forbidden = map(set, (scenario.initial_state_ids,
                                        scenario.goal_state_ids, scenario.forbidden_state_ids))
    certificates = []
    for (before, after), forwards in edges.items():
        check()
        if before not in initial or after in initial or before in goals or after in forbidden:
            continue
        for forward in forwards:
            for reset in edges.get((after, before), ()):
                check()
                pair = {forward, reset}
                if writers[before] == pair and writers[after] == pair and users[before] <= pair:
                    certificates.append({'forward_activity_id': forward, 'reset_activity_id': reset,
                                         'initial_state_id': before, 'persistent_state_id': after})
    return certificates


def _verify_inverse_cycle(scenario, ids, certificate, check):
    """Check the deletion theorem against parsed semantics, not discovery indexes.

    For any feasible plan keep the first forward execution at its original
    time, deleting all resets and later forwards. No external reader needs the
    private token; no other writer changes either fact. The persistent fact is
    only made true for longer. Positive preconditions and final +/- goals are
    preserved. Removing intervals only relaxes capacities and locks. The first
    execution and every retained timestamp survive, including first-only
    windows. Thus both makespan and execution count cannot increase.
    """
    check()
    forward_id, reset_id = certificate.get('forward_activity_id'), certificate.get('reset_activity_id')
    before, after = certificate.get('initial_state_id'), certificate.get('persistent_state_id')
    if not before or not after or before == after or forward_id == reset_id:
        return False
    if forward_id not in ids or reset_id not in ids:
        return False
    if (before not in scenario.initial_state_ids or after in scenario.initial_state_ids
            or before in scenario.goal_state_ids or after in scenario.forbidden_state_ids):
        return False
    for event in scenario.external_events:
        check()
        if event.add_state_ids or event.remove_state_ids:
            return False
    forward, reset = scenario.activity_by_id[forward_id], scenario.activity_by_id[reset_id]
    for activity, source, target in ((forward, before, after), (reset, after, before)):
        check()
        if (set(activity.output_state_ids) != {target}
                or set(activity.removed_state_ids) != {source}
                or set(activity.transition_state_ids) != {source}):
            return False
    for aid in ids:
        check()
        if aid in (forward_id, reset_id):
            continue
        activity = scenario.activity_by_id[aid]
        if {before, after} & (set(activity.output_state_ids) | set(activity.removed_state_ids)):
            return False
        if before in activity.precondition_state_ids:
            return False
    return True


def analyze_run_scope(scenario, *, deadline=None):
    """Return only fully verified reductions; preserve input and frozen times.

    A one-second preprocessing slice (within the shared solve deadline) avoids
    spending the whole search budget on pathological closures. An unfinished
    or invalid round is discarded; earlier certified rounds remain usable.
    """
    started = time.perf_counter()
    stop = min(started + 1.0, deadline) if deadline is not None else started + 1.0

    def check():
        if time.perf_counter() >= stop:
            raise _AnalysisTimeout()

    ids = tuple(a.id for a in scenario.activities)
    candidates = ids
    rounds, excluded, inverse_proofs = [], {}, []
    status = "complete"
    if any(e.add_state_ids or e.remove_state_ids for e in scenario.external_events):
        return set(ids), {"status": "unsupported_state_events", "rounds": [], "excluded_activities": {}}
    requires, outputs, removes = {}, {}, {}
    initial = set(scenario.initial_state_ids)
    goals = set(scenario.goal_state_ids)
    forbidden = set(scenario.forbidden_state_ids)
    try:
        for a in scenario.activities:
            check()
            requires[a.id] = set(a.precondition_state_ids)
            outputs[a.id] = set(a.output_state_ids)
            removes[a.id] = set(a.removed_state_ids)
        while True:
            check()
            reachable, enabled = _reachable(candidates, initial, requires, outputs, check)
            enabled_ids = tuple(aid for aid in candidates if aid in enabled)
            stable = initial - {fact for aid in enabled_ids for fact in removes[aid]}
            relevant = _relevant(enabled_ids, goals, forbidden, stable, requires, outputs, removes, check)
            if not _verify_round(candidates, reachable, enabled, relevant, initial, goals,
                                 forbidden, stable, requires, outputs, removes, check):
                status = "certificate_rejected"
                break
            dropped = {}
            for aid in candidates:
                check()
                if aid not in enabled:
                    dropped[aid] = {"reason": "unreachable_preconditions",
                                    "state_ids": sorted(requires[aid] - reachable), "round": len(rounds) + 1}
                elif aid not in relevant:
                    dropped[aid] = {"reason": "not_goal_relevant", "round": len(rounds) + 1}
            check()
            rounds.append({"input_activities": len(candidates), "reachable_activities": len(enabled),
                           "retained_activities": len(relevant), "stable_initial_state_ids": sorted(stable),
                           "certificate_verified": True})
            excluded.update(dropped)
            candidates = tuple(aid for aid in candidates if aid in relevant)
            if not dropped:
                certificates = _inverse_cycle_candidates(candidates, scenario, requires, outputs, removes, check)
                if not certificates:
                    break
                # Apply a complete batch only after every certificate verifies.
                # On timeout/rejection the current scope remains untouched.
                if not all(_verify_inverse_cycle(scenario, candidates, cert, check) for cert in certificates):
                    status = 'certificate_rejected'
                    break
                check()
                reset_ids = {cert['reset_activity_id'] for cert in certificates}
                next_candidates = tuple(aid for aid in candidates if aid not in reset_ids)
                rounds.append({'kind': 'inverse_cycle_projection', 'input_activities': len(candidates),
                               'retained_activities': len(next_candidates), 'certificate_verified': True})
                for cert in certificates:
                    proof = {**cert, 'reason': 'unnecessary_inverse_reset',
                             'round': len(rounds), 'certificate_verified': True}
                    excluded[cert['reset_activity_id']] = proof
                    inverse_proofs.append(proof)
                candidates = next_candidates
                # Rerun reachability/relevance; the private transition is now
                # nonrenewable, so _occurrence_limits can retain only one forward.
    except _AnalysisTimeout:
        status = "time_slice_exhausted"
    return set(candidates), {"policy": "initial_goal_projection_v2", "status": status,
                             "input_activities": len(ids), "retained_activities": len(candidates),
                             "seconds": time.perf_counter() - started, "rounds": rounds,
                             "excluded_activities": excluded, "inverse_cycle_proofs": inverse_proofs}

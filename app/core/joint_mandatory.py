"""Prove at-least-one activity presence; never infer ordering or new facts.

Proof rules, relative to the compiler's existing occurrence limits:
* An initially absent positive goal needs a producer.
* An initially present forbidden terminal fact needs a net remover.
* Every mandatory activity needs all its positive preconditions (including
  transitions); an initially absent one needs a producer.
Only a unique eligible activity definition is forced. Multiple occurrences of
that definition are alternatives, not different producers. Initially true
positive facts are left alone even if they could later be destroyed. We do not
infer restoration, remove slots, change limits, or force a specific schedule.

These are necessary conditions of every feasible solution of the existing
model. Lack of a producer is left to that model to diagnose. State-changing
events cause a conservative skip; pure time releases need no special handling.
"""
from collections import defaultdict, deque
import time


def identify_mandatory_activities(scenario, occurrence_limits, *, deadline=None):
    started = time.perf_counter()
    mandatory = set()
    proofs = {}
    stats = {'policy': 'unique_support_presence_v1', 'activity_ids': [], 'proofs': proofs,
             'status': 'complete', 'added_constraints': 0}

    def expired():
        return deadline is not None and time.perf_counter() >= deadline

    def finish(status):
        stats.update(status=status, activity_ids=sorted(mandatory),
                     seconds=time.perf_counter() - started)
        return mandatory, stats

    if any(e.add_state_ids or e.remove_state_ids for e in scenario.external_events):
        return finish('skipped_state_changing_events')
    producers, removers = defaultdict(set), defaultdict(set)
    eligible = {}
    for activity in scenario.activities:
        if expired():
            # A complete index is required before any unique-support conclusion.
            return finish('deadline_before_complete_index')
        if occurrence_limits.get(activity.id, 0) <= 0:
            continue
        eligible[activity.id] = activity
        for fact in activity.output_state_ids:
            producers[fact].add(activity.id)
        # Match the compiler: simultaneous addition wins over deletion.
        for fact in set(activity.removed_state_ids) - set(activity.output_state_ids):
            removers[fact].add(activity.id)

    initial = set(scenario.initial_state_ids)
    pending = deque((fact, False, 'positive_goal', None)
                    for fact in sorted(set(scenario.goal_state_ids) - initial))
    pending.extend((fact, True, 'negative_goal', None)
                   for fact in sorted(set(scenario.forbidden_state_ids) & initial))
    seen = set()
    while pending:
        if expired():
            return finish('deadline_with_proven_subset')
        fact, negative, reason, consumer = pending.popleft()
        key = (fact, negative)
        if key in seen:
            continue
        seen.add(key)
        choices = (removers if negative else producers).get(fact, set())
        if len(choices) != 1:
            continue
        aid = next(iter(choices))
        if aid in mandatory:
            continue
        mandatory.add(aid)
        proofs[aid] = {'reason': reason, 'state_id': fact, 'consumer_activity_id': consumer}
        pending.extend((pre, False, 'mandatory_precondition', aid)
                       for pre in sorted(set(eligible[aid].precondition_state_ids) - initial))
    return finish('complete')

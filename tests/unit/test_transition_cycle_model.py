"""Regression for install/dismantle cycles exhausting presolve before branching."""
import copy
import json
from pathlib import Path

from tests.unit.test_joint_cpsat import activity, core, setup_db, solve
from app.services.planner_execution_bounds import automatic_execution_bound


def test_unlimited_assembly_dismantle_prunes_proven_redundant_cycle(core):
    payload = json.loads((Path(__file__).resolve().parents[2] /
                          'deploy/examples/assembly-commissioning-20.json').read_text('utf-8'))
    for a in payload['activities']:
        a['max_instances'] = None
    install = next(a for a in payload['activities'] if a['name'] == '传动单元吊装就位')
    dismantle = activity('dismantle', 15, transition=[install['output_state_id']],
                         limit=None, resources=copy.deepcopy(install['resource_reqs']))
    payload['activities'].append(dismantle)
    install['preconditions'].append({'state_id': dismantle['output_state_id'], 'relation_role': 'transition'})
    payload['initial_state_ids'].append(dismantle['output_state_id'])
    payload['activity_packages'] = []
    payload['activity_package_memberships'] = []
    payload['max_steps'] = automatic_execution_bound(payload)['value']
    original = copy.deepcopy(payload)
    result = solve(core, payload, seconds=15, seed=11)
    assert result.status == 'OPTIMAL', result
    candidate = result.paths[0]
    assert candidate.validator_status == 'VALID'
    assert candidate.metrics.makespan == 515 and len(candidate.executions) == 20
    stats = result.stats['model']
    # Keep the original input bound; the private inverse reset is now proven
    # redundant, leaving one installation and no dismantling occurrences.
    assert payload['max_steps'] == 47 and stats['optional_occurrence_slots'] == 20
    assert stats['occurrence_pruning']['scope_analysis']['inverse_cycle_proofs']
    assert stats['variables'] < 12000 and stats['constraints'] < 30000
    assert payload == original


def test_causal_protection_growth_is_quadratic_not_cubic(core):
    counts = []
    for limit in (8, 16):
        payload = {'schema_version': 2, 'id': 'cycle-scale', 'execution_mode': 'parallel',
                   'max_steps': limit, 'initial_state_ids': ['off'], 'goal_state_ids': ['on'],
                   'activities': [activity('on', 1, transition=['off'], outputs=['on'], limit=None),
                                  activity('off', 1, transition=['on'], outputs=['off'], limit=None)]}
        _, _, _, stats = core._compile(payload)
        counts.append(stats['threat_checks'])
    assert counts[0] > 0 and counts[1] <= counts[0] * 4.5

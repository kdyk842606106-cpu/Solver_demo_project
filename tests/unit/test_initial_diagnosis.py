import copy

from app.services.planner_initial_diagnosis import diagnose_initial_states
from app.services.planner_scenarios import new_scenario


def fixture():
    s = new_scenario('诊断测试')
    s['states'] = [{'id': x, 'name': x} for x in ['off', 'on', 'fault', 'removed', 'installed', 'fixed', 'tested']]
    def action(aid, output, pre):
        return dict(id=aid, name=aid, duration=5, output_state_id=output,
                    preconditions=[dict(state_id=x, relation_role='required') for x in pre])
    s['activities'] = [action('install', 'installed', ['removed', 'off']),
                       action('remove', 'removed', ['installed', 'off']),
                       action('repair', 'fixed', ['removed', 'off', 'fault']),
                       action('test', 'tested', ['installed', 'on']),
                       action('power-on', 'on', ['off'])]
    return s


def candidates(r):
    return {s['id']: s for g in r['groups'] for s in g['states']}


def test_missing_fact_confirmation_is_read_only_and_final_forbidden_is_allowed():
    s = fixture(); s['forbidden_state_ids'] = ['fault']; before = copy.deepcopy(s)
    r = diagnose_initial_states(s, ['off', 'removed'], ['fixed'])
    assert r['status'] == 'STRUCTURALLY_BLOCKED'
    fault = candidates(r)['fault']
    assert fault['confirmable'] and fault['forbidden_at_finish']
    assert diagnose_initial_states(s, ['off', 'removed', 'fault'], ['fixed'])['status'] == 'STRUCTURALLY_REACHABLE'
    assert s == before


def test_cycle_reports_alternatives_and_does_not_offer_target_as_shortcut():
    s = fixture()
    r = diagnose_initial_states(s, ['off'], ['installed'])
    assert any(g['reason'] == 'dependency_cycle' for g in r['groups'])
    assert candidates(r)['removed']['confirmable']
    assert not candidates(r)['installed']['confirmable']
    assert diagnose_initial_states(s, ['off', 'removed'], ['installed'])['status'] == 'STRUCTURALLY_REACHABLE'


def test_unavailable_provider_is_not_confirmable_and_names_do_not_bind_states():
    s = fixture(); s['activities'][0]['is_active'] = False
    s['states'][3]['name'] = s['states'][4]['name'] = '同名状态'
    r = diagnose_initial_states(s, ['off', 'removed'], ['tested'])
    group = next(g for g in r['groups'] if g['reason'] == 'provider_unavailable')
    state = next(x for x in group['states'] if x['id'] == 'installed')
    assert not state['confirmable']
    assert not state['producer_activities'][0]['is_active']


def test_independent_missing_inputs_are_not_an_automatic_repair_set():
    s = fixture()
    r = diagnose_initial_states(s, ['removed'], ['fixed'])
    assert {'off', 'fault'} <= candidates(r).keys()
    assert diagnose_initial_states(s, ['removed', 'fault'], ['fixed'])['status'] == 'STRUCTURALLY_BLOCKED'
    assert diagnose_initial_states(s, ['removed', 'fault', 'off'], ['fixed'])['status'] == 'STRUCTURALLY_REACHABLE'


def test_structural_pass_does_not_check_transition_consumption_or_guarantee_feasibility():
    s = fixture()
    r = diagnose_initial_states(s, ['off', 'removed', 'fault'], ['tested', 'fixed'])
    assert r['status'] == 'STRUCTURALLY_REACHABLE'
    assert not r['constraints_checked']
    assert r['already_satisfied_goal_ids'] == []


def test_bad_references_empty_targets_and_existing_goals():
    s = fixture()
    assert diagnose_initial_states(s, ['unknown'], ['tested'])['status'] == 'INVALID_INPUT'
    assert diagnose_initial_states(s, ['off'], [])['status'] == 'INVALID_INPUT'
    r = diagnose_initial_states(s, ['tested'], ['tested'])
    assert r['status'] == 'STRUCTURALLY_REACHABLE'
    assert r['already_satisfied_goal_ids'] == ['tested']


def test_or_branches_keep_separate_missing_facts():
    s = fixture()
    s['activities'].append(dict(id='alternate', name='alternate', duration=1, output_state_id='fixed',
                                preconditions=[dict(state_id='on', relation_role='required')]))
    r = diagnose_initial_states(s, ['removed'], ['fixed'])
    assert {'fault', 'off'} <= candidates(r).keys()
    # Choosing one alternative does not require asserting every branch's facts.
    assert diagnose_initial_states(s, ['removed', 'off'], ['fixed'])['status'] == 'STRUCTURALLY_REACHABLE'

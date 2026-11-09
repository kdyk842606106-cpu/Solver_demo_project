"""Arrival releases combined with repeated power/calibration recovery."""
import copy
from collections import Counter

import pytest

from tests.unit.test_joint_cpsat import activity, core, setup_db, solve
from tests.unit.test_joint_pruning import assert_matches_unpruned


def material_power_case(rounds=2, *, calendar=False, legacy_materials=False, initially_on=False):
    activities = [
        activity('power_on', 5, transition=['off'], outputs=['on'], limit=None),
        activity('calibrate', 10, required=['on'], outputs=['calibrated'], limit=None),
        activity('power_off', 5, transition=['on'], outputs=['off'], delete=['calibrated'], limit=None),
    ]
    events, materials = [], {}
    for index in range(1, rounds + 1):
        scan = activity(f'scan{index}', 10, required=['on', 'calibrated',
                        *([f'done:replace{index-1}'] if index > 1 else [])])
        replacement = activity(f'replace{index}', 20, required=['off', f'done:scan{index}'])
        event = f'material{index}'
        if legacy_materials:
            materials[event] = 120 * index
            replacement['material_reqs'] = [event]
        else:
            events.append({'id': event, 'time': 120 * index, 'add_state_ids': [], 'remove_state_ids': []})
            replacement['event_reqs'] = [event]
        activities.extend([scan, replacement])
    activities.extend([activity('final', 10, required=['on', 'calibrated', f'done:replace{rounds}']),
                       activity('paperwork', 60, required=['ready'])])
    for a in activities:
        a['resource_reqs'] = {'crew': 1}
    payload = {'schema_version': 2, 'id': 'material-power-cycles', 'execution_mode': 'parallel',
               'max_steps': 5 * rounds + 4, 'activities': activities,
               'initial_state_ids': ['ready', *(['on', 'calibrated'] if initially_on else ['off'])],
               'goal_state_ids': ['done:final', 'done:paperwork', 'on', 'calibrated'],
               'forbidden_state_ids': ['off'], 'resources': [{'id': 'crew', 'capacity': 1}],
               'external_events': events, 'materials': materials}
    if calendar:
        from tests.unit.test_work_calendars import scenario
        reference = scenario(anchor='2026-11-02T08:00:00+08:00')
        for key in ('work_calendar_id', 'work_calendars', 'calendar_context'):
            payload[key] = reference[key]
    return payload


@pytest.mark.parametrize('rounds,calendar,legacy_materials,initially_on', [
    (1, False, False, False),
    (2, False, False, False),
    (2, True, False, False),
    (2, False, True, False),
    (2, False, False, True),
])
def test_late_materials_preserve_power_and_calibration_recovery(core, monkeypatch, rounds,
                                                               calendar, legacy_materials, initially_on):
    payload = material_power_case(rounds, calendar=calendar, legacy_materials=legacy_materials,
                                  initially_on=initially_on)
    saved = copy.deepcopy(payload)
    result = solve(core, payload, seconds=10)
    assert result.status == 'OPTIMAL', result
    p = result.paths[0]
    assert p.validator_status == 'VALID'
    assert p.metrics.makespan == 120 * rounds + 45 + (60 if calendar else 0)
    counts = Counter(e.activity_id for e in p.executions)
    assert counts['power_on'] == counts['calibrate'] == rounds + (0 if initially_on else 1)
    assert counts['power_off'] == rounds
    for index in range(1, rounds + 1):
        e = next(e for e in p.executions if e.activity_id == f'replace{index}')
        assert e.start_time >= 120 * index
        if calendar and index == 2:
            assert e.start_time >= 300  # Noon arrival waits until the 13:00 shift.
    # Paperwork has no power dependency and can occupy the arrival waiting gap.
    paperwork = next(e for e in p.executions if e.activity_id == 'paperwork')
    assert paperwork.end_time <= 120
    pruning = result.stats['model']['occurrence_pruning']
    assert {'power_on', 'calibrate', 'power_off'} <= pruning['retained_activities'].keys()
    assert not {'power_on', 'calibrate', 'power_off'} & pruning['activity_limits'].keys()
    assert payload == saved
    assert_matches_unpruned(core, payload, monkeypatch, result)


def test_insufficient_power_on_cap_is_infeasible_not_silently_repaired(core):
    payload = material_power_case(2)
    payload['activities'][0]['max_instances'] = 2
    result = solve(core, payload, seconds=10)
    assert result.status == 'INFEASIBLE' and not result.paths


def test_material_release_after_hard_deadline_is_infeasible(core):
    payload = material_power_case(1)
    payload['time_windows'] = [{'id': 'replacement-deadline', 'activity_id': 'replace1',
                                'earliest_start': 0, 'latest_finish': 100}]
    result = solve(core, payload, seconds=10)
    assert result.status == 'INFEASIBLE' and not result.paths

"""Check the early encoding preserves schedules, repeats and support choices."""
import copy
import pytest
from tests.unit.test_joint_cpsat import activity, core, setup_db, solve
from tests.unit.test_joint_mandatory import repair_case
from tests.unit.test_material_power_cycles import material_power_case

@pytest.mark.parametrize('linear', [True, False])
@pytest.mark.parametrize('case', ['power', 'alternatives', 'satisfied'])
def test_all_small_projected_schedules_equal(core, monkeypatch, linear, case):
    p = dict(schema_version=2, id='early-equivalence', execution_mode='parallel', max_steps=4,
             initial_state_ids=['off'], goal_state_ids=['on','done:off'], forbidden_state_ids=[],
             activities=[activity('on',1,transition=['off'],outputs=['on'],limit=2),
                         activity('off',1,transition=['on'],outputs=['off'])])
    if case == 'alternatives':
        p.update(initial_state_ids=[],goal_state_ids=['goal'],max_steps=2,
                 activities=[activity('a',1,outputs=['goal']),activity('b',1,outputs=['goal'])])
    if case == 'satisfied':
        p.update(initial_state_ids=['goal'],goal_state_ids=['goal'],max_steps=2,
                 activities=[activity('a',1,outputs=['goal'])])
    solutions = []
    for encoding in ('none','appended','early'):
        monkeypatch.setattr(core, '_MANDATORY_ENCODING', encoding)
        model, _, slots, _, finish = core._build_model_with_finish(p, deadline=None)
        model.clear_objective()
        found = set()
        class Collector(core.cp_model.CpSolverSolutionCallback):
            def on_solution_callback(self):
                found.add((self.value(finish), tuple((s.aid,s.ordinal,self.value(s.present),
                    self.value(s.start),self.value(s.end)) for s in slots)))
        solver = core.cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.new_linear_propagation = linear
        solver.parameters.enumerate_all_solutions = True
        solver.parameters.max_time_in_seconds = 5
        assert solver.solve(model, Collector()) == core.cp_model.OPTIMAL
        solutions.append(found)
    assert solutions[0] == solutions[1] == solutions[2] and solutions[0]

def test_early_model_removes_absence_guards_without_removing_repeat_slots(core, monkeypatch):
    p = repair_case()
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', 'appended')
    appended,_,old_slots,old_stats,_ = core._build_model_with_finish(p,deadline=None)
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', 'early')
    early,_,slots,stats,_ = core._build_model_with_finish(p,deadline=None)
    assert [(s.aid,s.ordinal) for s in slots] == [(s.aid,s.ordinal) for s in old_slots]
    assert len(early.proto.constraints) < len(appended.proto.constraints)
    assert stats['mandatory_activities']['fixed_first_occurrences'] == 4
    assert not stats['mandatory_activities']['added_constraints']
    for slot in slots:
        if slot.mandatory:
            assert slot.ordinal == 1
            assert list(early.proto.variables[slot.present.index].domain) == [1,1]
            assert not early.proto.constraints[slot.interval.index].enforcement_literal
        else:
            assert list(early.proto.variables[slot.present.index].domain) == [0,1]
    for key in ('support_choices','threat_checks','interval_locks','horizon'):
        assert stats[key] == old_stats[key]

@pytest.mark.parametrize('encoding', ['none','appended','early'])
def test_first_window_and_repeated_restoration(core, monkeypatch, encoding):
    monkeypatch.setattr(core,'_MANDATORY_ENCODING',encoding)
    p = material_power_case(2)
    p['run_time_windows'] = [dict(id='first-on',activity_id='power_on',earliest_start=10,latest_finish=15)]
    saved = copy.deepcopy(p)
    result = solve(core,p,seconds=10)
    assert result.status == 'OPTIMAL' and result.paths[0].validator_status == 'VALID'
    runs = [e for e in result.paths[0].executions if e.activity_id == 'power_on']
    assert len(runs) == 3 and (runs[0].start_time,runs[0].end_time) == (10,15)
    assert all(e.start_time>15 for e in runs[1:])
    assert result.paths[0].metrics.makespan == 285 and p == saved

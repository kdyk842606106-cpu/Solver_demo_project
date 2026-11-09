"""Presence-only strengthening must preserve alternatives, repeats and timing."""
import copy
import time

import pytest

from tests.unit.test_joint_cpsat import activity, core, setup_db, solve


def repair_case():
    return dict(schema_version=2, id='mandatory', execution_mode='parallel', max_steps=12,
                initial_state_ids=['on', 'installed:a', 'installed:c', 'fault'],
                goal_state_ids=['on'], forbidden_state_ids=['fault'],
                activities=[
                    activity('off', 1, transition=['on'], outputs=['off'], limit=3),
                    activity('remove_c', 1, required=['off', 'fault'], transition=['installed:c'], outputs=['out:c'], limit=3),
                    activity('remove_a', 1, required=['off', 'out:c', 'fault'], transition=['installed:a'], outputs=['out:a'], limit=3),
                    activity('repair', 1, required=['off', 'out:a', 'out:c'], transition=['fault'], limit=3),
                    activity('on', 1, required=['done:repair'], transition=['off'], outputs=['on'], limit=3),
                ])


def identify(core, p, limits=None, deadline=None):
    from planner_experiment.scenario import scenario_from_dict
    sc=scenario_from_dict(p)
    return core.identify_mandatory_activities(sc, limits if limits is not None else {a.id:3 for a in sc.activities}, deadline=deadline)


def baseline(core, p, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(core,'identify_mandatory_activities',lambda *a,**k:(set(),{'proofs':{}}))
        return core._build_model_with_finish(p,deadline=None)


def test_negative_goal_requires_unique_remover_and_its_missing_preconditions(core):
    p=repair_case();saved=copy.deepcopy(p)
    mandatory,stats=identify(core,p)
    assert mandatory=={'repair','off','remove_a','remove_c'}
    assert stats['proofs']['repair']['reason']=='negative_goal'
    assert stats['proofs']['remove_a']['consumer_activity_id']=='repair'
    # No initially-true-goal invalidation analysis is being added in this patch.
    assert 'on' not in mandatory and p==saved


def test_no_arbitrary_choice_between_alternative_producers_or_removers(core):
    p=repair_case()
    p['activities'].append(activity('alternative_repair',1,transition=['fault']))
    assert identify(core,p)[0]==set()
    p.update(initial_state_ids=['ready'],goal_state_ids=['goal'],forbidden_state_ids=[])
    p['activities']=[activity('a',1,outputs=['goal']),activity('b',2,outputs=['goal'])]
    assert identify(core,p)[0]==set()
    # Known eligibility is respected; zero slots do not count as an alternative.
    assert identify(core,p,{'a':3,'b':0})[0]=={'a'}


def test_initially_satisfied_goals_and_absent_forbidden_facts_do_not_force_work(core):
    p=dict(schema_version=2,id='satisfied',execution_mode='parallel',max_steps=3,
           initial_state_ids=['ready'],goal_state_ids=['ready'],forbidden_state_ids=['dirty'],
           activities=[activity('a',1,outputs=['ready','dirty']),activity('clean',1,delete=['dirty'])])
    assert identify(core,p)[0]==set()
    result=solve(core,p)
    assert result.status=='OPTIMAL' and not result.paths[0].executions


def test_conflicting_roles_and_unreachable_self_cycles_are_rejected(core):
    p=dict(schema_version=2,id='net-removal',execution_mode='parallel',max_steps=3,
           initial_state_ids=['dirty'],goal_state_ids=[],forbidden_state_ids=['dirty'],
           activities=[activity('refresh',1,outputs=['dirty'],delete=['dirty']),activity('clean',1,delete=['dirty'])])
    from planner_experiment.scenario import ScenarioError
    with pytest.raises(ScenarioError, match='conflicting state roles'):
        identify(core,p)
    p['activities'][0]['delete_effect_state_ids']=[]
    assert identify(core,p)[0]=={'clean'}
    p.update(initial_state_ids=[],goal_state_ids=['goal'],forbidden_state_ids=[])
    p['activities']=[activity('loop',1,required=['goal'],outputs=['goal'])]
    assert solve(core,p).status=='INFEASIBLE'


def test_state_changing_events_and_expired_analysis_conservatively_skip(core):
    p=repair_case()
    p['external_events']=[dict(id='repair-event',time=5,add_state_ids=[],remove_state_ids=['fault'])]
    mandatory,stats=identify(core,p)
    assert not mandatory and stats['status']=='skipped_state_changing_events'
    p['external_events']=[]
    assert not identify(core,p,deadline=time.perf_counter()-1)[0]


@pytest.mark.parametrize('mode',['parallel','serial'])
def test_only_presence_constraints_are_added_and_original_model_proves_them(core,monkeypatch,mode):
    monkeypatch.setattr(core,'_MANDATORY_ENCODING','appended')
    p=repair_case();p['execution_mode']=mode
    old,_,old_slots,old_stats,old_finish=baseline(core,p,monkeypatch)
    new,_,slots,stats,finish=core._build_model_with_finish(p,deadline=None)
    assert [str(x) for x in old.proto.variables]==[str(x) for x in new.proto.variables]
    assert str(old.proto.objective)==str(new.proto.objective)
    assert str(old.proto.solution_hint)==str(new.proto.solution_hint)
    assert [str(c) for c in old.proto.constraints]==[str(c) for c in new.proto.constraints if not c.name.startswith('mandatory:')]
    assert len(new.proto.constraints)-len(old.proto.constraints)==4
    for key in ['optional_occurrence_slots','support_choices','threat_checks','interval_locks','horizon']:
        assert stats[key]==old_stats[key]
    mandatory=set(stats['mandatory_activities']['activity_ids'])
    for aid in mandatory:
        # Independent CP proof: the unmodified model cannot omit this activity.
        witness=old.clone();witness.clear_objective()
        first=next(s for s in old_slots if s.aid==aid and s.ordinal==1)
        witness.add(witness.get_bool_var_from_proto_index(first.present.index)==0)
        solver=core.cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.max_time_in_seconds=3
        assert solver.solve(witness)==core.cp_model.INFEASIBLE
    solver=core.cp_model.CpSolver();solver.parameters.num_search_workers=1
    assert solver.solve(old)==core.cp_model.OPTIMAL
    optimum=solver.value(old_finish)
    assert solver.solve(new)==core.cp_model.OPTIMAL and solver.value(finish)==optimum


def test_repeat_restoration_and_first_execution_window_are_unchanged(core,monkeypatch):
    monkeypatch.setattr(core,'_MANDATORY_ENCODING','appended')
    from tests.unit.test_material_power_cycles import material_power_case
    p=material_power_case(1)
    p['run_time_windows']=[dict(id='first-on',activity_id='power_on',earliest_start=0,latest_finish=10)]
    with monkeypatch.context() as patch:
        patch.setattr(core,'identify_mandatory_activities',lambda *a,**k:(set(),{'proofs':{}}))
        old=solve(core,p,seconds=10)
    new=solve(core,p,seconds=10)
    assert old.status==new.status=='OPTIMAL'
    assert old.paths[0].metrics.makespan==new.paths[0].metrics.makespan
    assert len(old.paths[0].executions)==len(new.paths[0].executions)
    runs=[e for e in new.paths[0].executions if e.activity_id=='power_on']
    assert len(runs)==2 and runs[0].end_time<=10 and runs[1].start_time>10
    assert new.paths[0].validator_status=='VALID'

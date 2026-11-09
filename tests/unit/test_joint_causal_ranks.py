"""Instance DAG ranks preserve timed schedules and real restoration cycles."""
import copy
import pytest
from tests.unit.test_joint_cpsat import activity, core, setup_db, solve

def cycle_case():
    return dict(schema_version=2,id='rank-cycle',execution_mode='parallel',max_steps=4,
                initial_state_ids=['b'],goal_state_ids=['a','done:B'],forbidden_state_ids=[],
                activities=[activity('A',1,transition=['b'],outputs=['a'],limit=2),
                            activity('B',1,transition=['a'],outputs=['b'])])

@pytest.mark.parametrize('encoding',['none','appended','early'])
@pytest.mark.parametrize('case',['cycle','alternatives','parallel','satisfied'])
def test_exhaustive_timed_projection_is_unchanged(core,monkeypatch,encoding,case):
    p=cycle_case()
    if case=='alternatives':
        p.update(initial_state_ids=[],goal_state_ids=['goal'],max_steps=2,
                 activities=[activity('a',1,outputs=['goal']),activity('b',1,outputs=['goal'])])
    elif case=='parallel':
        p.update(initial_state_ids=['ready'],goal_state_ids=['done:a','done:b'],max_steps=2,
                 activities=[activity('a',1,required=['ready']),activity('b',1,required=['ready'])])
    elif case=='satisfied':
        p.update(initial_state_ids=['goal'],goal_state_ids=['goal'],max_steps=2,
                 activities=[activity('a',1,outputs=['goal'])])
    monkeypatch.setattr(core,'_MANDATORY_ENCODING',encoding)
    solutions=[]
    for enabled in (False,True):
        monkeypatch.setattr(core,'_CAUSAL_RANKS',enabled)
        model,_,slots,_,finish=core._build_model_with_finish(p,deadline=None)
        model.clear_objective();found=set()
        class Collector(core.cp_model.CpSolverSolutionCallback):
            def on_solution_callback(self):
                found.add((self.value(finish),tuple((s.aid,s.ordinal,self.value(s.present),
                    self.value(s.start),self.value(s.end)) for s in slots)))
        solver=core.cp_model.CpSolver();solver.parameters.num_search_workers=1
        solver.parameters.enumerate_all_solutions=True;solver.parameters.max_time_in_seconds=5
        assert solver.solve(model,Collector())==core.cp_model.OPTIMAL
        solutions.append(found)
    assert solutions[0]==solutions[1] and solutions[0]

def test_only_rank_variables_and_constraints_added(core,monkeypatch):
    p=cycle_case();saved=copy.deepcopy(p)
    monkeypatch.setattr(core,'_CAUSAL_RANKS',False)
    old,_,old_slots,old_stats,_=core._build_model_with_finish(p,deadline=None)
    monkeypatch.setattr(core,'_CAUSAL_RANKS',True)
    new,_,slots,stats,_=core._build_model_with_finish(p,deadline=None)
    assert p==saved
    assert [str(v) for v in old.proto.variables]==[str(v) for v in list(new.proto.variables)[:len(old.proto.variables)]]
    assert [str(c) for c in old.proto.constraints]==[str(c) for c in new.proto.constraints if not c.name.startswith('causal_rank:')]
    assert str(old.proto.objective)==str(new.proto.objective)
    assert str(old.proto.solution_hint)==str(new.proto.solution_hint)
    assert len(slots)==len(old_slots)==stats['causal_ranks']['variables']
    assert len(new.proto.variables)-len(old.proto.variables)==len(slots)
    assert [(s.aid,s.ordinal) for s in slots]==[(s.aid,s.ordinal) for s in old_slots]
    for key in ('support_choices','threat_checks','interval_locks','horizon'):
        assert stats[key]==old_stats[key]

def test_rank_constraints_alone_reject_selected_support_cycle(core,monkeypatch):
    monkeypatch.setattr(core,'_CAUSAL_RANKS',True)
    model,_,slots,_,_=core._build_model_with_finish(cycle_case(),deadline=None)
    ids={(s.aid,s.ordinal):s.index for s in slots}
    edges={}
    for c in model.proto.constraints:
        if c.name.startswith('causal_rank:support:'):
            _,_,selected,producer,consumer=c.name.split(':')
            edges[(int(producer),int(consumer))]=int(selected)
    # Remove every original time/resource/state constraint: this checks the
    # new layer itself detects the invalid support cycle, not the old times.
    isolated=model.clone();isolated.clear_objective()
    for c in isolated.proto.constraints:
        if not c.name.startswith('causal_rank:'):
            c.copy_from(type(c)())
    a,b=ids[('A',1)],ids[('B',1)]
    isolated.add(isolated.get_bool_var_from_proto_index(edges[(a,b)])==1)
    isolated.add(isolated.get_bool_var_from_proto_index(edges[(b,a)])==1)
    solver=core.cp_model.CpSolver();solver.parameters.num_search_workers=1
    assert solver.solve(isolated)==core.cp_model.INFEASIBLE
    r=solve(core,cycle_case())
    assert r.status=='OPTIMAL' and r.paths[0].validator_status=='VALID'
    assert [(e.activity_id,e.ordinal) for e in r.paths[0].executions]==[('A',1),('B',1),('A',2)]
    assert r.paths[0].metrics.makespan==3

def test_parallel_activities_can_share_rank(core,monkeypatch):
    monkeypatch.setattr(core,'_CAUSAL_RANKS',True)
    p=dict(schema_version=2,id='parallel-ranks',execution_mode='parallel',max_steps=2,
           initial_state_ids=['ready'],goal_state_ids=['done:a','done:b'],forbidden_state_ids=[],
           activities=[activity('a',3,required=['ready']),activity('b',2,required=['ready'])])
    model,_,slots,_,finish=core._build_model_with_finish(p,deadline=None)
    for s in slots:model.add(s.causal_rank==1)
    solver=core.cp_model.CpSolver();solver.parameters.num_search_workers=1
    assert solver.solve(model)==core.cp_model.OPTIMAL and solver.value(finish)==3


def test_inactive_rank_does_not_force_execution(core,monkeypatch):
    monkeypatch.setattr(core,'_CAUSAL_RANKS',True)
    p=dict(schema_version=2,id='unused-rank',execution_mode='parallel',max_steps=2,
           initial_state_ids=[],goal_state_ids=['goal'],forbidden_state_ids=[],
           activities=[activity('a',1,outputs=['goal']),activity('b',1,outputs=['goal'])])
    model,_,slots,_,finish=core._build_model_with_finish(p,deadline=None)
    unused=next(s for s in slots if s.aid=='b')
    model.add(unused.present==0)
    model.add(unused.causal_rank==2)
    solver=core.cp_model.CpSolver();solver.parameters.num_search_workers=1
    assert solver.solve(model)==core.cp_model.OPTIMAL and solver.value(finish)==1
    assert not any(c.name=='causal_rank:absent' for c in model.proto.constraints)

@pytest.mark.parametrize('linear',[True,False])
def test_repeated_power_and_first_window_keep_original_optimum(core,monkeypatch,linear):
    from tests.unit.test_material_power_cycles import material_power_case
    original=core.cp_model.CpSolver.solve
    def solver_call(self,*a,**k):
        self.parameters.new_linear_propagation=linear
        return original(self,*a,**k)
    monkeypatch.setattr(core.cp_model.CpSolver,'solve',solver_call)
    p=material_power_case(2)
    p['run_time_windows']=[dict(id='first-on',activity_id='power_on',earliest_start=10,latest_finish=15)]
    for enabled in (False,True):
        monkeypatch.setattr(core,'_CAUSAL_RANKS',enabled)
        r=solve(core,p,seconds=10)
        assert r.status=='OPTIMAL' and r.paths[0].validator_status=='VALID'
        assert r.paths[0].metrics.makespan==285
        runs=[e for e in r.paths[0].executions if e.activity_id=='power_on']
        assert len(runs)==3 and (runs[0].start_time,runs[0].end_time)==(10,15)
        assert all(e.start_time>15 for e in runs[1:])

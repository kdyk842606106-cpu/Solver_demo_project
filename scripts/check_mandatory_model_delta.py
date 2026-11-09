"""Check full Test A model differs only by entailed first-presence equalities."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.services.planner_scenarios import expand_packages
from app.core import joint_cpsat as core

out=ROOT/'output/mandatory-activities-20261106'
p=json.loads((ROOT/'output/test-a-install-keeps-tests-20261106/disassembly-only-input.json').read_text(encoding='utf-8'))
names={a['id']:a['name'] for a in p['activities']}
effective=expand_packages(p)
new,_,slots,stats,_=core._build_model_with_finish(effective,deadline=None)
fn=core.identify_mandatory_activities
try:
    core.identify_mandatory_activities=lambda *a,**k:(set(),{'proofs':{}})
    old,_,old_slots,old_stats,_=core._build_model_with_finish(effective,deadline=None)
finally:
    core.identify_mandatory_activities=fn

assert [str(x) for x in new.proto.variables]==[str(x) for x in old.proto.variables]
assert str(new.proto.objective)==str(old.proto.objective)
assert str(new.proto.solution_hint)==str(old.proto.solution_hint)
assert [str(c) for c in old.proto.constraints]==[str(c) for c in new.proto.constraints if not c.name.startswith('mandatory:')]
required=stats['mandatory_activities']['activity_ids']
assert len(new.proto.constraints)-len(old.proto.constraints)==len(required)==4
certificates=[]
for aid in required:
    model=old.clone();model.clear_objective()
    slot=next(s for s in old_slots if s.aid==aid and s.ordinal==1)
    model.add(model.get_bool_var_from_proto_index(slot.present.index)==0)
    solver=core.cp_model.CpSolver()
    solver.parameters.num_search_workers=1
    solver.parameters.random_seed=11
    solver.parameters.max_time_in_seconds=5
    status=solver.solve(model)
    certificates.append({'activity':names[aid],'activity_id':aid,
                         'original_model_without_activity':solver.status_name(status),
                         'seconds':solver.wall_time})
    assert status==core.cp_model.INFEASIBLE, certificates[-1]
report={'only_presence_constraints_added':True,'variables_unchanged':True,'all_other_constraints_unchanged':True,
        'objective_unchanged':True,'no_solution_hint_added':True,'new_constraints':4,'certificates':certificates}
(out/'model-delta-certificates.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))

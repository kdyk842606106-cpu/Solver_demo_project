"""Run solver regressions with a process-local compiler/propagator selection."""
import argparse
import os
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.services.planner_engine_bridge import _planner_modules
_planner_modules()
from app.core import joint_cpsat as core
import pytest
p=argparse.ArgumentParser()
p.add_argument('--encoding',choices=['none','appended','early'],required=True)
p.add_argument('--linear',choices=['new','old'],default='new')
p.add_argument('--causal-ranks',action='store_true')
p.add_argument('--output-dir',type=Path)
p.add_argument('--workers',type=int,default=1)
args=p.parse_args()
os.environ['PLANNER_JOINT_CP_SAT_WORKERS']=str(args.workers)
core._MANDATORY_ENCODING=args.encoding
core._CAUSAL_RANKS=args.causal_ranks
original=core.cp_model.CpSolver.solve
def solve(self,*a,**k):
    self.parameters.new_linear_propagation=args.linear=='new'
    return original(self,*a,**k)
core.cp_model.CpSolver.solve=solve
files=['test_joint_cpsat','test_joint_pruning','test_inverse_cycle_pruning','test_joint_feedback',
       'test_material_power_cycles','test_run_time_windows','test_work_calendars','test_night_lifts','test_exclusive_rules',
       'test_joint_causal_ranks','test_joint_optimization_switches','test_joint_parallel_workers']
if args.encoding in ('none','appended'):
    files+=['test_joint_mandatory','test_joint_mandatory_early']
out=args.output_dir or ROOT/('output/causal-ranks-20261106' if args.causal_ranks else 'output/mandatory-encoding-20261106')
out.mkdir(parents=True,exist_ok=True)
sys.exit(pytest.main(['--noconftest','-q',*[f'tests/unit/{f}.py' for f in files],
                     f'--junitxml={out}/tests-{args.encoding}-{args.linear}-workers{args.workers}.xml']))

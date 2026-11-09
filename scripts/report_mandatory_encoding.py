"""Verify the full experimental matrix and summarize without hiding timeouts."""
from collections import defaultdict
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/mandatory-encoding-20261106'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
tasks=read(OUT/'matrix-primary.json')+read(OUT/'matrix-seeds.json')
groups=defaultdict(list)
for task in tasks:
    tag=f"{task['encoding']}-{task['case']}-{task['linear']}-seed{task['seed']}"
    result=read(OUT/f'{tag}-summary.json')
    assert result['encoding']==task['encoding'] and result['seed']==task['seed']
    assert result['implementation']==task['linear'] and result['worker_threads']==1
    assert not result['validator_rejections']
    assert result['status'] not in ('ERROR','UNSUPPORTED','UNKNOWN'), (tag,result['status'])
    source=read(ROOT/result['source'])
    if task['case']=='calendar-night-150':source=source['request']['effective_scenario_snapshot']
    assert source==read(OUT/f'{tag}-input.json')
    if result.get('schedule') is not None:
        assert result['validator']=='VALID'
    groups[(task['case'],task['seed'])].append(result)
for (case,seed),runs in groups.items():
    assert len(runs)==6
    assert len({r['input_sha256'] for r in runs})==1
    assert len({r['budget_seconds'] for r in runs})==1
    for key in ('optional_occurrence_slots','support_choices','threat_checks','interval_locks','horizon'):
        assert len({r['model'][key] for r in runs})==1,(case,key)
    optimal={(r['best_makespan'],r['best_execution_count']) for r in runs if r['status']=='OPTIMAL'}
    assert len(optimal)<=1,(case,seed,optimal)
    if optimal:
        optimum=next(iter(optimal))
        for r in runs:
            assert r['status']!='INFEASIBLE'
            if r.get('schedule') is not None:
                assert (r['best_makespan'],r['best_execution_count'])>=optimum
    for encoding in ('none','appended','early'):
        pair=[r for r in runs if r['encoding']==encoding]
        assert len({r['solver_calls'][0]['initial_model_sha256'] for r in pair})==1
    proof_sets=[r['model']['mandatory_activities'].get('activity_ids',[]) for r in runs if r['encoding']!='none']
    assert all(s==proof_sets[0] for s in proof_sets)
for case in {case for case,_ in groups}:
    proven={(r['best_makespan'],r['best_execution_count']) for (c,_),runs in groups.items()
            if c==case for r in runs if r['status']=='OPTIMAL'}
    assert len(proven)<=1,(case,proven)

report={'method':{'cases':len({t['case'] for t in tasks}),'runs':len(tasks),'business_changes':False,
    'database_writes':False,'production_default':'appended + new linear propagation',
    'mandatory_encodings':['none','appended','early'],'seeds_main':[11],
    'extra_seeds':[23,37],'extra_seed_cases':['normal-a','late-material','recovery-current'],
    'budget':'60 seconds except calendar-night-150 120 seconds; equal within each comparison',
    'sequential_fresh_processes':True},'checks':{
        'all_input_files_match_frozen_source':True,'same_occurrence_limits_and_support_threat_lock_counts':True,
        'same_mandatory_proofs_in_appended_and_early':True,'same_initial_model_for_two_propagators':True,
        'all_proven_optima_agree_within_each_case':True,'all_returned_schedules_valid':True},
    'tests':{},'results':{}}
for path in OUT.glob('tests-*.xml'):
    suite=ET.parse(path).getroot().find('testsuite')
    assert int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    report['tests'][path.name]=suite.attrib
lines=['Mandatory encoding experiment, 2026-11-06','',
       'Six variants per input: none/appended/early x new/old linear propagation.',
       'No project/history writes; existing production default retained.','']
for (case,seed),runs in groups.items():
    key=f'{case}/seed{seed}'
    report['results'][key]=runs
    lines.append(key)
    for r in sorted(runs,key=lambda r:(['none','appended','early'].index(r['encoding']),r['implementation'])):
        lines.append(f"  {r['encoding']:8} {r['implementation']:3} {r['status']:14} first={r['first_solution_seconds']} total={r['elapsed_seconds']:.3f}s branches={r['branches']} best={r['best_makespan']}/{r['best_execution_count']} constraints={r['model']['constraints']}")
    lines.append('')
report['multi_seed_summary']={}
for case in ('normal-a','late-material','recovery-current'):
    entries={}
    for encoding in ('none','appended','early'):
        for linear in ('new','old'):
            runs=[r for (c,_),rs in groups.items() if c==case for r in rs if r['encoding']==encoding and r['implementation']==linear]
            entries[f'{encoding}/{linear}']={'statuses':[r['status'] for r in runs],
                'elapsed_seconds':[r['elapsed_seconds'] for r in runs],
                'median_elapsed_including_capped_runs':statistics.median(r['elapsed_seconds'] for r in runs),
                'optimal_count':sum(r['status']=='OPTIMAL' for r in runs)}
    report['multi_seed_summary'][case]=entries
report['conclusion']={
    'implemented':'Early proof, fixed first-presence domains, mandatory intervals and removal of tautological guards; later occurrences retained.',
    'correctness':'Projected small schedules exhaustively agree; solver regressions pass; all returned candidates validate; all proven optima agree across modes and seeds.',
    'performance':'Early encoding reduces raw constraints and improves several seed-11 cases, but is not uniformly faster across propagators and seeds.',
    'counterexamples':[
        'normal-a / early / old / seed23: TIMEOUT_EMPTY at 60s, versus appended old OPTIMAL about 6s.',
        'normal-a / early / old / seed37: valid 790-minute/18-execution plan at budget end, optimality unproved; known optimum is 400/10.',
        'recovery-current / early / new / seed37: about 25.39s versus appended new about 10.16s.',
        'repair-0042: all six seed-11 variants TIMEOUT_EMPTY at 60s; this does not prove infeasibility.'],
    'rollout':'New encoding remains an internal experimental option. Existing appended/new production defaults retained; no business or database changes.'}
target=ROOT/'docs/validation/MANDATORY_ENCODING_COMPARISON_20261106.json'
target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'comparison.txt').write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines))
print('Checks passed:',target)

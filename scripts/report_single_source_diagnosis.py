"""Summarize frozen historical evidence and isolated native diagnostics."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/single-source-recovery-diagnosis-20261109'

def read(path): return json.loads(path.read_text('utf8'))

historical=read(OUT/'original-benchmark-decomposition.json')
ablation=read(OUT/'presolve-ablation.json')
summaries=[read(p) for p in OUT.glob('*-summary.json')]
assert len(summaries)==16
delays=[]
for seed,repeat in [(23,0),(71,0),(11,0),(11,1),(11,2)]:
    pair=[]
    for mode in ['original','direct']:
        pair.append(next(r for r in historical if r['tag']==f'recovery-{mode}-s{seed}-r{repeat}-result'))
    a,b=pair
    delays.append({'seed':seed,'repeat':repeat,'before':a,'after':b,
        'delta':{k:b[k]-a[k] for k in ['first','improvement','proof_tail','total','build','restarts','cert_seconds']}})

stale=[]
for directory,pattern in [(ROOT/'output/single-source-20261109','recovery-*-result.json'),(OUT,'*-result.json')]:
    for path in directory.glob(pattern):
        result=read(path);s=result['stats']
        assert result['status']=='OPTIMAL' and result['paths'][0]['validator_status']=='VALID'
        assert result['paths'][0]['metrics']['makespan']==390 and len(result['paths'][0]['executions'])==10
        for cert in s['feedback_certificates']:
            eligible=[c for c in s['candidate_history'] if c['seconds']<=cert['elapsed_seconds']]
            best=min(eligible,key=lambda c:(c['delivered_makespan'],c['execution_count']))
            if cert['applied'] and (cert['makespan'],cert['execution_count'])>(best['delivered_makespan'],best['execution_count']):
                stale.append({'result':str(path.relative_to(ROOT)), 'certificate':cert,
                    'best_known_before_certificate':best})

logged=[]
for row in summaries:
    tag=row['tag'];trace=read(OUT/f'{tag}-trace.json')
    firstlog=(OUT/f'{tag}-call0.log').read_text('utf8')
    fingerprint=re.search(r'Presolved optimization model.*?model_fingerprint: ([^)]+)',firstlog,re.S)[1]
    logged.append(dict(row,raw_model_hash=trace['calls'][0]['model_hash'],presolved_fingerprint=fingerprint,
        execution_count_calls=[c for c in trace['calls'] if c['phase']=='EXECUTION_COUNT' and c['workers']==8]))
source=ROOT/'app/core/joint_cpsat.py';manifest=read(OUT/'manifest.json')
assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['compiler_sha256']
assert '_SINGLE_SOURCE_DIRECT = False' in source.read_text('utf8')
report={'status':'diagnosis_complete','production_code_changed':False,'business_constraints_changed':False,
    'default_single_source_direct':False,'new_full_diagnostic_runs':16,'presolve_ablation_variants':7,
    'all_new_full_runs_optimal_makespan':390,'all_new_full_runs_execution_count':10,'all_replay_valid':True,
    'historical_stage_decomposition':delays,'native_runs':logged,'presolve_ablation':ablation,
    'stale_feedback_records':stale,
    'findings':[
        'Original seed23/71 regressions are dominated by time to first validated solution, not construction or certificate checking; post-first optimization is faster in both compressed runs.',
        'Original seed11 repeat2 also regresses after first solution: feedback restarts 1 to 6 and improvement time 0.338 to 1.224 seconds; exact certificate checking adds only about 0.027 seconds.',
        '52 raw auxiliary variables disappear, but only 8 fewer remain after presolve (659 to 651). Four optional later A/C removal instances reading the initial repair-needed fact explain the surviving fingerprint delta.',
        'Presolve-only ablation: later-removal-only equals full-direct fingerprint; all-except-later-removal equals original fingerprint. This identifies a representation change, not proof of weaker propagation or deletion of a repair path.',
        'Eight-worker repeats have the same raw model hash within encoding but different first-solution subsolvers and timings. Original and producer-only share the same presolved fingerprint yet show different timing. Fixed seed does not eliminate this timing variability.',
        'A strict-improvement callback can set pending_feedback, then a later better raw-valid incumbent may not refresh it because it requires no normalization. The next epoch can receive an older certified upper bound/hint. The observed 760-vs-750 stale feedback is safe but can lose useful tightening; no controlled speedup claim is made.',
        'Detailed logging perturbs thread timing. New runs diagnose mechanisms, not exact reproduction of earlier wall times or a claim that a seed always regresses.'
    ]}
(OUT/'diagnosis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
(ROOT/'docs/validation/SINGLE_SOURCE_RECOVERY_DIAGNOSIS_20261109.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({'delays':[{k:v for k,v in r.items() if k not in ('before','after')} for r in delays],
    'stale_feedback':stale,'presolve_ablation':ablation},ensure_ascii=False,indent=2))

"""Submit/poll one authorized 600s API verification without editing Test A."""
import argparse
import json
from pathlib import Path
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/incumbent-feedback-20261105'
BASE = 'http://127.0.0.1:8016/api/v1'
parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['submit','poll'])
args = parser.parse_args()
def save(name, value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def api(path, data=None):
    req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),
                              headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.load(response)
source=json.loads((ROOT/'output/test-a-repair-page-diagnosis/planner-run_53c1a5d7-e959-4da6-b39e-9d0d43354554.json').read_text('utf-8-sig'))
if args.action=='submit':
    if (OUT/'api-enqueued.json').exists():
        print('Already enqueued: '+json.loads((OUT/'api-enqueued.json').read_text('utf-8'))['id'])
    else:
        live=api('/planner-scenarios/'+source['scenario_id'])
        assert live['revision']==7 and live['scenario_hash']==source['request']['base_scenario_hash'], 'Scenario changed; do not submit.'
        if (OUT/'api-request.json').exists():
            request=json.loads((OUT/'api-request.json').read_text('utf-8'))
        else:
            keys=['scenario_id','expected_revision','current_state_ids','target_state_ids','engine','seed','display_timezone','objectives','activity_time_windows']
            request={k:source['request'][k] for k in keys}
            request.update(budget_mode='manual',budget={'time_limit_seconds':600},execution_bound_mode='auto',
                display_start_at=source['request']['effective_scenario_snapshot']['calendar_context']['start_at'],
                client_request_id=str(uuid4()))
            save('api-request.json',request)
        result=api('/planner-runs/async',request)
        save('api-enqueued.json',result)
        assert result['scenario_hash']==source['scenario_hash'], 'Effective input differs; inspect frozen snapshots.'
        print(json.dumps({'id':result['id'],'status':result['status'],'identical_snapshot':True},ensure_ascii=False))
else:
    run=json.loads((OUT/'api-enqueued.json').read_text('utf-8'))
    progress=api('/planner-runs/'+run['id']+'/progress')
    save('api-progress.json',progress)
    print(json.dumps({k:v for k,v in progress.items() if k not in ('candidate','plan','result')},ensure_ascii=False))
    detail=api('/planner-runs/'+run['id'])
    if detail.get('finished_at'):
        save('api-result.json',detail)
        result=detail['result']['results']['JOINT_CP_SAT']
        assert result['stats']['feedback_policy']=='certified_incumbent_restart_v1'
        assert detail['scenario_hash']==source['scenario_hash']
        live=api('/planner-scenarios/'+source['scenario_id'])
        assert live['revision']==7 and live['scenario_hash']==source['request']['base_scenario_hash']
        print(json.dumps({'terminal':result['status'],'first':result['first_solution_seconds'],
            'elapsed':result['elapsed_seconds'],'branches':result['stats']['branches'],
            'best':result['stats']['best_makespan'],'revision_unchanged':True},ensure_ascii=False))

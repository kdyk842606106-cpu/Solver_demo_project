"""Switch Test A defaults to normal installation with one revision-checked commit."""
import copy
import json
from pathlib import Path
import time
import urllib.request

BASE='http://127.0.0.1:8016/api/v1'
SID='scenario:46d7aec2-d316-4965-81e7-4afef0dd0ffe'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output'/('test-a-normal-defaults-'+time.strftime('%Y%m%d-%H%M%S'))
OUT.mkdir(parents=True)
def api(path,data=None):
    req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data).encode(),
                              headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.load(response)
def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
path='/planner-scenarios/'+SID
before=api(path);save('before.json',before)
save('before-export.json',api(path+'/export'))
history=api('/planner-runs?scenario_id='+SID);save('history-before.json',history)
projects=api('/planner-scenarios');save('projects-before.json',projects)
s=before['scenario']
activities={a['name']:a for a in s['activities']}
assert len(s['activities'])==14 and len(s['activity_packages'])==4
changes={'activity_package_scope_ids':[],
         'initial_state_ids':[activities['下电']['output_state_id']],
         'goal_state_ids':[activities['模块联调']['output_state_id']]}
request={'expected_revision':before['revision'],
         'operations':[{'operation':'update_scenario','payload':changes}]}
save('draft-commit.json',request)
latest=api(path)
assert latest['revision']==before['revision'] and latest['scenario_hash']==before['scenario_hash']
response=api(path+'/draft-commit',request);save('commit-response.json',response)
after=api(path);save('after.json',after)
for _ in range(20):
    if after['revision'] >= response['revision']:
        break
    time.sleep(.1)
    after=api(path)
save('after.json',after)
assert after['revision']==before['revision']+1
for field,value in s.items():
    if field not in changes and field != 'revision':
        assert after['scenario'].get(field)==value, field
for field,value in changes.items():
    assert after['scenario'][field]==value
assert api('/planner-runs?scenario_id='+SID)==history
assert {p['id']:p for p in api('/planner-scenarios') if p['id']!=SID}=={p['id']:p for p in projects if p['id']!=SID}
summary={'revision':after['revision'],'activities':len(s['activities']),
         'packages':len(s['activity_packages']),'initial':['下电完成'],
         'goals':['模块联调完成'],'scope':'all','history_unchanged':True,
         'other_projects_unchanged':True,'output':str(OUT)}
save('validation.json',summary)
print(json.dumps(summary,ensure_ascii=False))

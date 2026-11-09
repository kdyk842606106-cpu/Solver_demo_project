"""Create an isolated PostgreSQL DB/API/worker for run-window acceptance."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'output/run-windows'
API='http://127.0.0.1:8037'


def request(path,body=None):
    req=urllib.request.Request(API+path,data=None if body is None else json.dumps(body).encode(),
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=20) as r: return json.load(r)


def main():
    import psycopg
    from psycopg import sql
    from tests.unit.test_material_power_cycles import material_power_case
    from app.services.planner_scenarios import new_scenario,rebuild_mirror,validate_scenario
    OUT.mkdir(parents=True,exist_ok=True)
    manifest=OUT/'environment.json'
    if manifest.exists(): raise RuntimeError('Acceptance manifest already exists; inspect it before another launch')
    for port in (8037,8038):
        with socket.socket() as sock: sock.bind(('127.0.0.1',port))
    db='planner_windows_'+uuid4().hex[:10]
    with psycopg.connect('host=127.0.0.1 port=55440 user=planner_test dbname=postgres',autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(db)))
    env={**os.environ,'DATABASE_URL':f'postgresql+asyncpg://planner_test@127.0.0.1:55440/{db}',
         'DATABASE_URL_SYNC':f'postgresql+psycopg://planner_test@127.0.0.1:55440/{db}',
         'PLANNER_PROJECT_PATH':str(ROOT.parent/'planner'),'PYTHONIOENCODING':'utf-8'}
    python=str(ROOT/'.venv/Scripts/python.exe')
    subprocess.run([python,'-m','alembic','upgrade','head'],cwd=ROOT,env=env,check=True,
                   stdout=(OUT/'migrations.log').open('w'),stderr=subprocess.STDOUT)
    state={'database':db,'api':API,'frontend':'http://127.0.0.1:8038','processes':{}}
    commands={'api':[python,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8037'],
              'worker':[python,'-m','app.planner_worker'],
              'frontend':[python,'scripts/serve_frontend_dist_proxy.py','--dist',str(OUT/'frontend'),
                          '--backend',API,'--port','8038']}
    for name,cmd in commands.items():
        p=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=(OUT/(name+'.log')).open('w'),
                           stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        state['processes'][name]={'pid':p.pid,'command':cmd}
        manifest.write_text(json.dumps(state,indent=2),encoding='utf-8')
    for _ in range(40):
        try:
            assert request('/api/v1/planner-runs/capabilities')['joint_cp_sat']['run_activity_time_windows_supported']
            break
        except Exception: time.sleep(.25)
    else: raise RuntimeError('Isolated API failed to start')
    s=new_scenario('时间窗隔离验收：物料晚到与反复上下电')
    s.update(material_power_case())
    states=set(s['initial_state_ids']+s['goal_state_ids']+s['forbidden_state_ids'])
    for a in s['activities']:
        states.update([a['output_state_id'],*a['additional_output_state_ids'],*a['delete_effect_state_ids']])
        states.update(p['state_id'] for p in a['preconditions'])
    s['states']=[{'id':sid,'name':sid,'state_kind':'seed'} for sid in sorted(states)]
    names={'power_on':'上电','power_off':'下电','calibrate':'标定','paperwork':'等待期间文档整理','final':'最终联调'}
    for i,a in enumerate(s['activities']):
        a.update(name=names.get(a['id'],a['id']),display_code=f'ACT-{i+1:04}',is_active=True)
        if a['max_instances'] is None: a['max_instances']=2 if a['id']=='power_off' else 3
    s['resources'][0].update(name='作业班组',kind='crew',is_active=True)
    rebuild_mirror(s)
    issues=validate_scenario(s)
    if issues: raise RuntimeError(issues)
    project=request('/api/v1/planner-scenarios/import',{'scenario':s,'preserve_ids':True})
    state['project_id']=project['id']
    state['scenario']=project['scenario']
    manifest.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'database':db,'api':API,'frontend':state['frontend'],'project_id':project['id']},ensure_ascii=False))


if __name__=='__main__': main()

"""Independent solve of the user's 2026-11-09 table; no database writes."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.planner_scenarios import new_scenario, create_activity, create_package, add_membership, validate_scenario
from app.services.planner_engine_bridge import run_engine

OUT = ROOT/'output/user-dismantling-table-20261109'

def main():
    s = new_scenario('用户表格：拆AB线缆、拆B、拆C｜独立验证')
    s.update(execution_mode='parallel', max_steps=45, initial_state_ids=[], goal_state_ids=[],
             exclusive_rules={'crane':False,'commissioning':False},
             night_lift_rule={'enabled':False,'night_start':'20:00','night_end':'08:00'})
    resource_names = ['AB','CD','EF','SI','1号行吊','设备右侧','设备后侧','设备左侧','设备前侧']
    resource_ids = {name:f'resource:table-{i}' for i,name in enumerate(resource_names)}
    for name in resource_names:
        crew = name in ('AB','CD','EF','SI')
        s['resources'].append({'id':resource_ids[name],'name':name,'capacity':2 if crew else 1,
                               'kind':'crew' if crew else 'crane' if name=='1号行吊' else 'workspace','is_active':True})
    # key, activity, output, minutes, required, transition, crew, spaces, crane, package
    rows = [
        ('a','模块A安装','模块A安装完成',20,['ready'],[],'EF',['右','左'],True,'机械集成'),
        ('ready','集成可准入','集成可准入完成',30,[],[],'SI',['右','后','左','前'],False,'机械集成'),
        ('b','模块B安装','模块B安装完成',20,['ready','a'],['b_off'],'EF',['右'],True,'机械集成'),
        ('c','模块C安装','模块C安装完成',30,['a','b'],['c_off'],'AB',['左'],False,'机械集成'),
        ('d','模块D安装','模块D安装完成',10,['a'],[],'CD',['左','前'],False,'机械集成'),
        ('ab','AB线缆连接','AB线缆连接完成',20,['a','b'],['ab_off'],'CD',['左','前'],False,'机械集成'),
        ('bc','BC管线连接','BC管线连接完成',40,['b','c'],[],'AB',['右','后','左','前'],False,'机械集成'),
        ('safe','安全验收','安全验收完成',20,['bc','ab','a','b','c','d'],[],'SI',['右','后','左','前'],False,'机械集成'),
        ('power','系统上电','系统上电完成',10,['safe'],[],'CD',[],False,'功能联调'),
        ('test1','功能调测1','功能调测1完成',30,['power'],[],'SI',[],False,'功能联调'),
        ('test2','功能调测2','功能调测2完成',20,['test1'],[],'SI',[],False,'功能联调'),
        ('test','系统联调','系统联调完成',20,['test1','test2'],[],'SI',[],False,'功能联调'),
        ('ab_off','拆卸线缆AB','线缆AB未安装',20,[],['ab'],'CD',['右','左'],False,None),
        ('c_off','拆卸模块C','模块C未安装',20,['ab_off'],['c'],'AB',['右','左','前'],False,None),
        ('b_off','拆卸模块B','拆卸模块B完成',20,['c','ab_off'],['b'],'EF',['右','左'],True,None),
    ]
    root_package=create_package(s,{'name':'表格活动'},display_number=1)['id']
    packages={name:create_package(s,{'name':name,'parent_id':root_package},display_number=i+2)['id']
              for i,name in enumerate(['机械集成','功能联调'])}
    acts={}
    for i,(key,name,output,minutes,required,transition,crew,spaces,crane,package) in enumerate(rows,1):
        req={resource_ids[crew]:2,**{resource_ids['设备'+side+'侧']:1 for side in spaces}}
        if crane: req[resource_ids['1号行吊']]=1
        acts[key]=create_activity(s,{'name':name,'output_state_name':output,'duration':minutes,
            'max_instances':3,'resource_reqs':req,'delete_effect_state_ids':[],
            'metadata':{'activity_type':'功能调测' if package=='功能联调' else '机械集成'}},display_number=i)
        if package: add_membership(s,packages[package],acts[key]['id'],sort_order=i)
    for key,_,_,_,required,transition,*_ in rows:
        acts[key]['preconditions']=[{'state_id':acts[k]['output_state_id'],'relation_role':role}
                                   for keys,role in [(required,'required'),(transition,'transition')] for k in keys]
    s['initial_state_ids']=[acts[k]['output_state_id'] for k in ['a','ready','b','c','d','ab','bc']]
    s['goal_state_ids']=[acts[k]['output_state_id'] for k in ['ab_off','c_off','b_off']]
    assert len(s['activities'])==15
    assert not validate_scenario(s),validate_scenario(s)
    OUT.mkdir(parents=True,exist_ok=True)
    def save(name,data): (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    save('scenario.json',s)
    result=run_engine(s,engine='JOINT_CP_SAT',run_id='independent:user-dismantling-table',seed=11,
                      budget_override={'time_limit_seconds':60},run_options={'worker_threads':8})
    save('result.json',result)
    assert result['paths'],result
    p=result['paths'][0]; names={a['id']:a['name'] for a in s['activities']}
    states={x['id']:x['name'] for x in s['states']}
    summary={'status':result['status'],'first_solution_seconds':result.get('first_solution_seconds'),
             'elapsed_seconds':result.get('stats',{}).get('elapsed_seconds'),
             'stats':result.get('stats',{}),'metrics':p['metrics'],'validator':p['validator_status'],
             'schedule':[{'name':names[e['activity_id']],**e} for e in p['executions']],
             'final_states':[states[x] for x in p['final_state_ids']]}
    save('summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='stats'},ensure_ascii=False),flush=True)
    print(json.dumps({k:result.get('stats',{}).get(k) for k in ['worker_threads','branches','conflicts','lower_bound','makespan_proven_optimal','execution_count_proven_optimal','build_seconds']},ensure_ascii=False))

if __name__=='__main__': main()

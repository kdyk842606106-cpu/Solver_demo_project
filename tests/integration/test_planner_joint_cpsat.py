import copy

import pytest

from app.services.planner_engine_bridge import planner_available, run_engine
from app.services.planner_scenarios import new_scenario,create_activity,rebuild_mirror,scenario_hash,validate_scenario

pytestmark=pytest.mark.skipif(not planner_available(),reason='external Planner runtime unavailable')


@pytest.fixture
def scenario():
    p=new_scenario('联合求解集成')
    p['states'].append({'id':'ready','name':'可执行','state_kind':'seed'})
    p['initial_state_ids']=['ready']
    a=create_activity(p,{'name':'任务','duration':2,'preconditions':[{'state_id':'ready','relation_role':'required'}],'max_instances':1},display_number=1)
    p['goal_state_ids']=[a['output_state_id']]
    p['default_budget']={'time_limit_seconds':1,'transition_limit':1000,'max_solutions':3}
    rebuild_mirror(p)
    return p


def test_bridge_skips_pop_and_keeps_snapshot(scenario,monkeypatch):
    import app.services.planner_engine_bridge as bridge
    monkeypatch.setattr(bridge,'run_legacy_pipeline',lambda *a,**kw:pytest.fail('joint engine called POP'))
    saved=copy.deepcopy(scenario)
    result=run_engine(scenario,engine='JOINT_CP_SAT',run_id='bridge-joint',seed=11)
    assert result['status']=='OPTIMAL',result
    assert result['paths'][0]['validator_status']=='VALID'
    assert result['scenario_hash']==scenario_hash(saved) and scenario==saved
    assert result['applied_objectives']==[{'type':'minimize_makespan','weight':1.0}]


def test_bridge_windows_revalidate_and_other_engines_reject(scenario):
    scenario['time_windows']=[{'id':'w','activity_id':scenario['activities'][0]['id'],'earliest_start':10,'latest_finish':12}]
    result=run_engine(scenario,engine='JOINT_CP_SAT',run_id='window',seed=11)
    assert result['status']=='OPTIMAL',result
    assert result['paths'][0]['metrics']['makespan']==12
    assert result['validator_time_windows']==1
    result=run_engine(scenario,engine='ASTAR',run_id='reject-window',seed=11)
    assert result['status']=='UNSUPPORTED' and not result['paths']


def test_invalid_window_has_preflight_issue(scenario):
    scenario['time_windows']=[{'id':'w','activity_id':scenario['activities'][0]['id'],'earliest_start':10,'latest_finish':11}]
    assert any(x['code']=='INVALID_TIME_WINDOW' for x in validate_scenario(scenario))


@pytest.mark.asyncio
@pytest.mark.parametrize('engine',['JOINT_CP_SAT','ALL_WITH_CP_SAT'])
async def test_api_persists_joint_result_and_shared_snapshot(client,scenario,engine):
    imported=await client.post('/api/v1/planner-scenarios/import',json={'scenario':scenario,'preserve_ids':True})
    assert imported.status_code==201,imported.text
    data=imported.json();p=data['scenario']
    response=await client.post('/api/v1/planner-runs',json={'scenario_id':data['id'],'expected_revision':data['revision'],
        'current_state_ids':p['initial_state_ids'],'target_state_ids':p['goal_state_ids'],'engine':engine,
        'seed':23,'budget':{'time_limit_seconds':1,'transition_limit':1000,'max_solutions':3}})
    assert response.status_code==201,response.text
    body=response.json();results=body['result']['results']
    assert results['JOINT_CP_SAT']['proven_optimal'],body
    assert results['JOINT_CP_SAT']['lower_bound']==2
    expected={'JOINT_CP_SAT'} if engine=='JOINT_CP_SAT' else {'JOINT_CP_SAT','LEGACY','ASTAR','GA'}
    assert set(results)==expected
    assert {r['scenario_hash'] for r in results.values()}=={body['scenario_hash']}
    persisted=(await client.get('/api/v1/planner-runs/'+body['id'])).json()
    assert persisted['result']['results']['JOINT_CP_SAT']['paths'][0]['validator_status']=='VALID'
    caps=(await client.get('/api/v1/planner-runs/capabilities')).json()
    assert caps['joint_cp_sat']['time_windows_supported']
    assert 'ALL' in caps['engines'] and 'ALL_WITH_CP_SAT' in caps['engines']


@pytest.mark.asyncio
@pytest.mark.parametrize('initial_goal_satisfied', [False, True])
async def test_api_persists_pruning_diagnostics_without_rewriting_business_limits(client, scenario, initial_goal_satisfied):
    scenario['activities'][0]['max_instances'] = None
    unused = create_activity(scenario, {'name': '无关作业', 'duration': 3,
        'preconditions': [{'state_id': 'ready', 'relation_role': 'required'}]}, display_number=2)
    rebuild_mirror(scenario)
    imported = await client.post('/api/v1/planner-scenarios/import',
                                json={'scenario': scenario, 'preserve_ids': True})
    assert imported.status_code == 201, imported.text
    data = imported.json()
    current = scenario['initial_state_ids'] + (scenario['goal_state_ids'] if initial_goal_satisfied else [])
    response = await client.post('/api/v1/planner-runs', json={
        'scenario_id': data['id'], 'expected_revision': data['revision'],
        'current_state_ids': current, 'target_state_ids': scenario['goal_state_ids'],
        'engine': 'JOINT_CP_SAT', 'seed': 11, 'budget': {'time_limit_seconds': 2}})
    assert response.status_code == 201, response.text
    persisted = (await client.get('/api/v1/planner-runs/' + response.json()['id'])).json()
    result = persisted['result']['results']['JOINT_CP_SAT']
    assert result['status'] == 'OPTIMAL'
    pruning = result['stats']['model']['occurrence_pruning']
    assert pruning['applied'] and pruning['effective_slots'] == (0 if initial_goal_satisfied else 1)
    assert unused['id'] in pruning['scope_analysis']['excluded_activities']
    assert pruning['removed_slots'] > 0
    assert set(persisted['request']['effective_scenario_snapshot']['initial_state_ids']) == set(current)
    assert persisted['request']['effective_scenario_snapshot']['activities'][0]['max_instances'] is None


@pytest.mark.asyncio
async def test_window_import_regenerates_activity_reference_and_solves(client,scenario):
    scenario['time_windows']=[{'id':'w','activity_id':scenario['activities'][0]['id'],'earliest_start':10,'latest_finish':12}]
    imported=await client.post('/api/v1/planner-scenarios/import',json={'scenario':scenario,'preserve_ids':False})
    assert imported.status_code==201,imported.text
    body=imported.json();p=body['scenario']
    assert p['time_windows'][0]['activity_id']==p['activities'][0]['id']
    response=await client.post('/api/v1/planner-runs',json={'scenario_id':body['id'],'expected_revision':body['revision'],
        'current_state_ids':p['initial_state_ids'],'target_state_ids':p['goal_state_ids'],'engine':'JOINT_CP_SAT',
        'budget':{'time_limit_seconds':1}})
    assert response.status_code==201,response.text
    result=response.json()['result']['results']['JOINT_CP_SAT']
    assert result['status']=='OPTIMAL',result
    assert result['paths'][0]['metrics']['makespan']==12


@pytest.mark.asyncio
@pytest.mark.parametrize('seconds,expected',[(0,'TIMEOUT_EMPTY'),(2,'INFEASIBLE')])
async def test_api_preserves_timeout_and_infeasible_status(client,scenario,seconds,expected):
    first=scenario['activities'][0]
    second=create_activity(scenario,{'name':'后续任务','duration':2,
        'preconditions':[{'state_id':first['output_state_id'],'relation_role':'required'}],
        'max_instances':1},display_number=2)
    scenario['goal_state_ids']=[second['output_state_id']]
    scenario['time_windows']=[{'id':'end','activity_id':second['id'],'earliest_start':0,'latest_finish':3}]
    imported=await client.post('/api/v1/planner-scenarios/import',json={'scenario':scenario,'preserve_ids':True})
    assert imported.status_code==201,imported.text
    body=imported.json()
    response=await client.post('/api/v1/planner-runs',json={'scenario_id':body['id'],'expected_revision':body['revision'],
        'current_state_ids':scenario['initial_state_ids'],'target_state_ids':scenario['goal_state_ids'],
        'engine':'JOINT_CP_SAT','budget':{'time_limit_seconds':seconds}})
    assert response.status_code==201,response.text
    record=response.json();result=record['result']['results']['JOINT_CP_SAT']
    assert record['status']==result['status']==expected
    assert result['proven_infeasible']==(expected=='INFEASIBLE') and not result['paths']


@pytest.mark.asyncio
async def test_window_patch_is_persisted(client,scenario):
    imported=await client.post('/api/v1/planner-scenarios/import',json={'scenario':scenario,'preserve_ids':True})
    body=imported.json()
    windows=[{'id':'w','activity_id':scenario['activities'][0]['id'],'earliest_start':5,'latest_finish':9}]
    patched=await client.patch('/api/v1/planner-scenarios/'+body['id'],
        json={'expected_revision':body['revision'],'time_windows':windows})
    assert patched.status_code==200,patched.text
    saved=await client.get('/api/v1/planner-scenarios/'+body['id'])
    assert saved.json()['scenario']['time_windows']==windows


def test_common_validator_rejection_cannot_keep_optimal_proof(scenario,monkeypatch):
    from dataclasses import replace
    import app.services.planner_engine_bridge as bridge
    modules=bridge._planner_modules()
    def reject(raw,scenario):
        return replace(raw,paths=(),status='ERROR',stats={**raw.stats,'validator_rejected':1})
    modules['validated_result']=reject
    monkeypatch.setattr(bridge,'_planner_modules',lambda:modules)
    result=run_engine(scenario,engine='JOINT_CP_SAT',run_id='reject-proof',seed=11)
    assert result['status']=='ERROR' and not result['proven_optimal']
    assert not result['stats']['proven_optimal']

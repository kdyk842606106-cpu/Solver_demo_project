import copy
from uuid import uuid4
import pytest
from tests.integration.test_planner_joint_cpsat import scenario
from app.services.planner_engine_bridge import run_engine


async def request_for(client,scenario):
    res=await client.post('/api/v1/planner-scenarios/import',json={'scenario':scenario,'preserve_ids':True})
    assert res.status_code==201,res.text
    p=res.json()
    return p,{'scenario_id':p['id'],'expected_revision':p['revision'],'current_state_ids':scenario['initial_state_ids'],
              'target_state_ids':scenario['goal_state_ids'],'engine':'JOINT_CP_SAT','seed':11,
              'display_start_at':'2026-11-05T08:00:00+08:00','display_timezone':'Asia/Shanghai',
              'budget':{'time_limit_seconds':3},'activity_time_windows':[{'activity_id':scenario['activities'][0]['id'],
              'earliest_start_at':'2026-11-05T08:10:00+08:00','latest_finish_at':None}]}


@pytest.mark.asyncio
@pytest.mark.parametrize('async_mode',[False,True])
async def test_run_windows_are_frozen_without_project_changes(client,scenario,async_mode):
    project,body=await request_for(client,scenario)
    before=(await client.get('/api/v1/planner-scenarios/'+project['id'])).json()
    if async_mode: body['client_request_id']=str(uuid4())
    url='/api/v1/planner-runs'+('/async' if async_mode else '')
    res=await client.post(url,json=body)
    assert res.status_code==(202 if async_mode else 201),res.text
    record=res.json(); snap=record['request']['effective_scenario_snapshot']
    assert snap['run_time_windows'][0]['earliest_start']==10
    result=run_engine(snap,engine='JOINT_CP_SAT',run_id='frozen',seed=11) if async_mode else record['result']['results']['JOINT_CP_SAT']
    assert result['status']=='OPTIMAL' and result['paths'][0]['metrics']['makespan']==12
    assert (await client.get('/api/v1/planner-scenarios/'+project['id'])).json()==before
    if async_mode:
        retry=await client.post(url,json=body)
        assert retry.status_code==202 and retry.json()['id']==record['id']
        body['activity_time_windows'][0]['earliest_start_at']='2026-11-05T08:11:00+08:00'
        assert (await client.post(url,json=body)).status_code==409
    old=(await client.get('/api/v1/planner-runs/'+record['id'])).json()
    assert old['request']['effective_scenario_snapshot']==snap
    legacy=run_engine(snap,engine='ASTAR',run_id='legacy',seed=11)
    assert legacy['status']=='UNSUPPORTED'


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['duplicate','unknown','naive','reversed','inactive'])
async def test_bad_windows_rejected_before_enqueue(client,scenario,bad):
    if bad=='inactive': scenario['activities'][0]['is_active']=False
    if bad=='inactive':
        # Keep the activity in the scenario, but supply an already satisfied goal.
        scenario['goal_state_ids']=scenario['initial_state_ids'][:]
    _,body=await request_for(client,scenario)
    w=body['activity_time_windows'][0]
    if bad=='duplicate': body['activity_time_windows'].append(copy.deepcopy(w))
    if bad=='unknown': w['activity_id']='missing'
    if bad=='naive': w['earliest_start_at']='2026-11-05T08:10'
    if bad=='reversed': w['latest_finish_at']='2026-11-05T08:09:00+08:00'
    body['client_request_id']=str(uuid4())
    res=await client.post('/api/v1/planner-runs/async',json=body)
    assert res.status_code==422,res.text

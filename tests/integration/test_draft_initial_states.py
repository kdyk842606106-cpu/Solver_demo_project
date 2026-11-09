import pytest


async def fixture(client):
    project=(await client.post('/api/v1/planner-scenarios',json={'name':'保存循环定义'})).json()
    base='/api/v1/planner-scenarios/'+project['id']
    seed=(await client.post(base+'/seed-states',json={'name':'已下电','initial':True})).json()['state']
    install=(await client.post(base+'/activities',json={'name':'安装','duration':3,
        'preconditions':[{'state_id':seed['id'],'relation_role':'required'}]})).json()['activity']
    remove=(await client.post(base+'/activities',json={'name':'拆卸','duration':2,
        'preconditions':[{'state_id':install['output_state_id'],'relation_role':'transition'}]})).json()['activity']
    current=(await client.get(base)).json()
    conditions=install['preconditions']+[{'state_id':remove['output_state_id'],'relation_role':'transition'}]
    operations=[{'operation':'update_activity','object_id':install['id'],'payload':{'preconditions':conditions}},
                {'operation':'update_scenario','payload':{'goal_state_ids':[install['output_state_id']]}}]
    return project,base,seed,install,remove,current,operations


@pytest.mark.asyncio
async def test_unreachable_default_is_save_warning_but_bad_run_remains_blocked(client):
    project,base,seed,install,remove,current,operations=await fixture(client)
    saved=await client.post(base+'/draft-commit',json={'expected_revision':current['revision'],'operations':operations})
    assert saved.status_code==200,saved.text
    body=saved.json()
    assert [w['code'] for w in body['warnings']]==['GOAL_STRUCTURALLY_UNREACHABLE']
    reread=(await client.get(base)).json()
    assert reread['revision']==body['revision']
    assert reread['scenario']['initial_state_ids']==[seed['id']]
    request={'scenario_id':project['id'],'expected_revision':body['revision'],'engine':'JOINT_CP_SAT',
        'seed':11,'current_state_ids':[seed['id']],'target_state_ids':[install['output_state_id']],
        'budget':{'time_limit_seconds':1},'display_start_at':'2026-11-05T00:42:00+08:00'}
    bad=await client.post('/api/v1/planner-runs/async',json={**request,'client_request_id':'bad-default'})
    assert bad.status_code==422,bad.text
    good=await client.post('/api/v1/planner-runs/async',json={**request,
        'current_state_ids':[seed['id'],remove['output_state_id']],'client_request_id':'actual-input'})
    assert good.status_code==202,good.text
    assert (await client.get(base)).json()['revision']==body['revision']


@pytest.mark.asyncio
async def test_initial_states_and_cycle_can_be_saved_in_one_commit(client):
    _,base,seed,_,remove,current,operations=await fixture(client)
    operations.append({'operation':'update_scenario','payload':{'initial_state_ids':[seed['id'],remove['output_state_id']]}})
    saved=await client.post(base+'/draft-commit',json={'expected_revision':current['revision'],'operations':operations})
    assert saved.status_code==200,saved.text
    assert saved.json()['warnings']==[]
    assert set(saved.json()['scenario']['initial_state_ids'])=={seed['id'],remove['output_state_id']}
    stale=await client.post(base+'/draft-commit',json={'expected_revision':current['revision'],'operations':operations})
    assert stale.status_code==409


@pytest.mark.asyncio
async def test_draft_still_rejects_invalid_references_without_persisting(client):
    _,base,_,install,_,current,operations=await fixture(client)
    operations.append({'operation':'update_activity','object_id':install['id'],
        'payload':{'resource_reqs':{'missing-resource':1}}})
    response=await client.post(base+'/draft-commit',json={'expected_revision':current['revision'],'operations':operations})
    assert response.status_code==422,response.text
    assert (await client.get(base)).json()['revision']==current['revision']

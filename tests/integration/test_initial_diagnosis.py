import copy
import pytest


@pytest.mark.asyncio
async def test_endpoint_revision_draft_and_read_only_confirmation(client):
    p = (await client.post('/api/v1/planner-scenarios', json={'name': '初始诊断隔离测试'})).json()
    base = '/api/v1/planner-scenarios/' + p['id']
    seed = (await client.post(base+'/seed-states', json={'name': '未安装', 'initial': False})).json()['state']
    activity = (await client.post(base+'/activities', json={'name': '安装', 'duration': 5,
        'preconditions': [{'state_id': seed['id'], 'relation_role': 'transition'}]})).json()['activity']
    before = (await client.get(base)).json()
    history = (await client.get('/api/v1/planner-runs')).json()
    body = dict(expected_revision=before['revision'], current_state_ids=[], target_state_ids=[activity['output_state_id']])
    response = await client.post(base+'/initial-state-check', json=body)
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'STRUCTURALLY_BLOCKED'
    confirmed = await client.post(base+'/initial-state-check', json={**body, 'current_state_ids': [seed['id']]})
    assert confirmed.json()['status'] == 'STRUCTURALLY_REACHABLE'
    assert confirmed.json()['input_signature'] != response.json()['input_signature']
    draft = copy.deepcopy(before['scenario'])
    draft['activities'][0]['is_active'] = False
    result = await client.post(base+'/initial-state-check', json={**body, 'draft_scenario': draft})
    assert result.status_code == 200, result.text
    assert result.json()['source'] == 'draft'
    assert result.json()['groups'][0]['reason'] == 'provider_unavailable'
    stale = await client.post(base+'/initial-state-check', json={**body, 'expected_revision': before['revision']-1})
    assert stale.status_code == 409
    draft['id'] = 'different-project'
    assert (await client.post(base+'/initial-state-check', json={**body, 'draft_scenario': draft})).status_code == 422
    assert (await client.get(base)).json() == before
    assert (await client.get('/api/v1/planner-runs')).json() == history

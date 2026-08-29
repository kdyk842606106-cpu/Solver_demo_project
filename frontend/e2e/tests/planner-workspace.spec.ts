import { expect, test } from '@playwright/test'

const scenarioId = 'scenario:11111111-1111-4111-8111-111111111111'
const rootId = 'activity-package:22222222-2222-4222-8222-222222222222'
const childId = 'activity-package:33333333-3333-4333-8333-333333333333'
const activityA = 'activity:44444444-4444-4444-8444-444444444444'
const activityB = 'activity:55555555-5555-4555-8555-555555555555'
const stateA = 'state:44444444-4444-4444-8444-444444444444:output'
const sharedStatePackageId = 'state-package:66666666-6666-4666-8666-666666666666'
const moduleXScenarioId = 'module-x-scenario'

const moduleXStates = {
  powerOff: 'state:power-off',
  powerOn: 'state:power-on',
  installed: 'state:x-installed',
  testedA: 'state:a-tested',
  testedB: 'state:b-tested',
}

const moduleXActivities = {
  powerOn: 'activity:power-on',
  powerOff: 'activity:power-off',
  install: 'activity:install-x',
  testA: 'activity:test-a',
  testB: 'activity:test-b',
}

const scenario = {
  schema_version: 1,
  id: scenarioId,
  display_code: 'SCN-DEMO',
  name: 'Planner 演示场景',
  execution_mode: 'serial',
  start_time: 0,
  max_steps: 20,
  default_budget: { time_limit_seconds: 5, transition_limit: 20000, max_solutions: 10 },
  states: [
    { id: 'state:seed', name: '初始状态', state_kind: 'seed' },
    { id: stateA, name: '准备完成', state_kind: 'activity_output' },
    { id: 'state:b-output', name: '执行完成', state_kind: 'activity_output' },
  ],
  initial_state_ids: ['state:seed'], goal_state_ids: ['state:b-output'], forbidden_state_ids: [], target_activity_ids: [],
  target_activity_package_ids: [], activity_package_scope_ids: [], resources: [], external_events: [],
  activity_packages: [
    { id: rootId, display_code: 'AP-0001', name: '一级总包', level: 1, parent_id: null, layout: { x: 20, y: 20, width: 1120, height: 520 }, mirrored_state_package_id: 'state-package:22222222-2222-4222-8222-222222222222' },
    { id: childId, display_code: 'AP-0002', name: '二级实施包', level: 2, parent_id: rootId, layout: { x: 50, y: 70, width: 620, height: 390 }, mirrored_state_package_id: 'state-package:33333333-3333-4333-8333-333333333333' },
  ],
  activities: [
    { id: activityA, display_code: 'ACT-0001', name: '准备', duration: 2, preconditions: [{ state_id: 'state:seed', relation_role: 'transition' }], output_state_id: stateA, output_state_name: '准备完成', additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], is_milestone: false, is_active: true },
    { id: activityB, display_code: 'ACT-0002', name: '执行', duration: 3, preconditions: [{ state_id: stateA, relation_role: 'transition' }], output_state_id: 'state:b-output', output_state_name: '执行完成', additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], is_milestone: false, is_active: true },
  ],
  activity_package_memberships: [
    { id: 'activity-package-member:a', package_id: childId, activity_id: activityA, layout: {} },
    { id: 'activity-package-member:b', package_id: childId, activity_id: activityB, layout: {} },
  ],
  state_packages: [
    { id: 'state-package:22222222-2222-4222-8222-222222222222', name: '一级总包', level: 1, parent_id: null, source_activity_package_id: rootId, is_active: true },
    { id: 'state-package:33333333-3333-4333-8333-333333333333', name: '二级实施包', level: 2, parent_id: 'state-package:22222222-2222-4222-8222-222222222222', source_activity_package_id: childId, is_active: true },
    { id: sharedStatePackageId, name: '二级共享包', level: 2, parent_id: 'state-package:22222222-2222-4222-8222-222222222222', is_active: true },
  ],
  state_package_memberships: [
    { id: 'state-package-member:a', state_package_id: 'state-package:33333333-3333-4333-8333-333333333333', state_id: stateA, source_membership_id: 'activity-package-member:a' },
    { id: 'state-package-member:b', state_package_id: 'state-package:33333333-3333-4333-8333-333333333333', state_id: 'state:b-output', source_membership_id: 'activity-package-member:b' },
    { id: 'state-package-member:shared-a', state_package_id: sharedStatePackageId, state_id: stateA, source_membership_id: 'activity-package-member:a' },
  ], provenance: {},
}

const graph = {
  scenario_id: scenarioId,
  revision: 4,
  containers: scenario.activity_packages,
  nodes: [
    { id: 'activity-package-member:a', kind: 'activity', canonical_activity_id: activityA, package_id: childId, display_code: 'ACT-0001', name: '准备', duration: 2, layout: { x: 90, y: 130 }, seed_preconditions: ['state:seed'], event_preconditions: [] },
    { id: 'activity-package-member:b', kind: 'activity', canonical_activity_id: activityB, package_id: childId, display_code: 'ACT-0002', name: '执行', duration: 3, layout: { x: 300, y: 130 }, seed_preconditions: [], event_preconditions: [] },
  ],
  edges: [{ id: 'dependency:a:b', kind: 'activity_dependency', source: 'activity-package-member:a', target: 'activity-package-member:b', state_id: stateA, relation_role: 'transition' }],
  summary: { activity_count: 2, display_node_count: 2, package_count: 2, state_node_count: 0 },
}

const moduleXScenario = {
  schema_version: 'planner-shared-scenario/v1',
  id: moduleXScenarioId,
  display_code: 'SCN-MODULE-X',
  name: '模块X到料延迟提拉测试',
  execution_mode: 'serial',
  start_time: 0,
  max_steps: 12,
  default_budget: { time_limit_seconds: 10, transition_limit: 20000, max_solutions: 20 },
  states: [
    { id: moduleXStates.powerOff, name: '电源已下电', state_kind: 'seed' },
    { id: moduleXStates.powerOn, name: '电源已上电', state_kind: 'activity_output' },
    { id: moduleXStates.installed, name: '模块 X 已安装', state_kind: 'activity_output' },
    { id: moduleXStates.testedA, name: '功能 A 已调测', state_kind: 'activity_output' },
    { id: moduleXStates.testedB, name: '功能 B 已调测', state_kind: 'activity_output' },
  ],
  initial_state_ids: [moduleXStates.powerOff],
  goal_state_ids: [moduleXStates.powerOn, moduleXStates.installed, moduleXStates.testedA, moduleXStates.testedB],
  forbidden_state_ids: [], target_activity_ids: [], target_activity_package_ids: [], activity_package_scope_ids: [],
  resources: [], external_events: [{ id: 'event:x-arrival', name: '模块 X 到料', time: 45, add_state_ids: [], remove_state_ids: [] }],
  activity_packages: [], activity_package_memberships: [], state_packages: [], state_package_memberships: [], provenance: {},
  activities: [
    { id: moduleXActivities.powerOn, display_code: 'ACT-0001', name: '上电', duration: 5, preconditions: [{ state_id: moduleXStates.powerOff, relation_role: 'transition' }], output_state_id: moduleXStates.powerOn, additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], max_instances: 2 },
    { id: moduleXActivities.powerOff, display_code: 'ACT-0002', name: '下电', duration: 5, preconditions: [{ state_id: moduleXStates.powerOn, relation_role: 'transition' }], output_state_id: moduleXStates.powerOff, additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], max_instances: 1 },
    { id: moduleXActivities.install, display_code: 'ACT-0003', name: '安装模块 X', duration: 10, preconditions: [{ state_id: moduleXStates.powerOff, relation_role: 'required' }], output_state_id: moduleXStates.installed, additional_output_state_ids: [], resource_reqs: {}, event_reqs: ['event:x-arrival'], max_instances: 1 },
    { id: moduleXActivities.testA, display_code: 'ACT-0004', name: '功能 A 调测', duration: 30, preconditions: [{ state_id: moduleXStates.powerOn, relation_role: 'required' }], output_state_id: moduleXStates.testedA, additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], max_instances: 1 },
    { id: moduleXActivities.testB, display_code: 'ACT-0005', name: '功能 B 调测', duration: 30, preconditions: [{ state_id: moduleXStates.powerOn, relation_role: 'required' }, { state_id: moduleXStates.installed, relation_role: 'required' }], output_state_id: moduleXStates.testedB, additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], max_instances: 1 },
  ],
}

function result(engine: string) {
  return {
    algorithm: engine,
    status: 'OK',
    engine_pipeline: engine === 'LEGACY' ? 'partial_order_pathfinder+cp_sat_scheduler' : `${engine.toLowerCase()}_temporal_search`,
    requested_objectives: [{ type: 'minimize_makespan', weight: 1 }],
    applied_objectives: engine === 'LEGACY'
      ? [{ type: 'minimize_makespan', weight: 1 }]
      : [{ type: 'engine_native_path_metrics', weight: 1 }],
    scenario_hash: 'same-hash',
    elapsed_seconds: 0.02,
    paths: [{
      validator_status: 'VALID',
      metrics: { makespan: 5, execution_count: 2, critical_path_length: 5, resource_peak: [] },
      executions: [
        { activity_id: activityA, instance_id: `${activityA}#1`, activity_name: '准备', start_time: 0, end_time: 2, before_state_ids: ['state:seed'], after_state_ids: [stateA] },
        { activity_id: activityB, instance_id: `${activityB}#1`, activity_name: '执行', start_time: 2, end_time: 5, before_state_ids: [stateA], after_state_ids: ['state:b-output'] },
      ],
    }],
  }
}

function moduleXResult(engine: string) {
  const executions = [
    { activity_id: moduleXActivities.powerOn, instance_id: 'power-on#1', activity_name: '上电', start_time: 0, end_time: 5, before_state_ids: [moduleXStates.powerOff], after_state_ids: [moduleXStates.powerOn] },
    { activity_id: moduleXActivities.testA, instance_id: 'test-a#1', activity_name: '功能 A 调测', start_time: 5, end_time: 35, before_state_ids: [moduleXStates.powerOn], after_state_ids: [moduleXStates.powerOn, moduleXStates.testedA] },
    { activity_id: moduleXActivities.powerOff, instance_id: 'power-off#1', activity_name: '下电', start_time: 35, end_time: 40, before_state_ids: [moduleXStates.powerOn, moduleXStates.testedA], after_state_ids: [moduleXStates.powerOff, moduleXStates.testedA] },
    { activity_id: moduleXActivities.install, instance_id: 'install-x#1', activity_name: '安装模块 X', start_time: 45, end_time: 55, before_state_ids: [moduleXStates.powerOff, moduleXStates.testedA], after_state_ids: [moduleXStates.powerOff, moduleXStates.testedA, moduleXStates.installed] },
    { activity_id: moduleXActivities.powerOn, instance_id: 'power-on#2', activity_name: '上电', start_time: 55, end_time: 60, before_state_ids: [moduleXStates.powerOff, moduleXStates.testedA, moduleXStates.installed], after_state_ids: [moduleXStates.powerOn, moduleXStates.testedA, moduleXStates.installed] },
    { activity_id: moduleXActivities.testB, instance_id: 'test-b#1', activity_name: '功能 B 调测', start_time: 60, end_time: 90, before_state_ids: [moduleXStates.powerOn, moduleXStates.testedA, moduleXStates.installed], after_state_ids: [moduleXStates.powerOn, moduleXStates.testedA, moduleXStates.installed, moduleXStates.testedB] },
  ]
  return {
    algorithm: engine,
    status: engine === 'GA' ? 'TIMEOUT_PARTIAL' : 'OK',
    engine_pipeline: engine === 'LEGACY' ? 'partial_order_pathfinder+cp_sat_scheduler' : `${engine.toLowerCase()}_temporal_search`,
    requested_objectives: [{ type: 'minimize_makespan', weight: 1 }],
    applied_objectives: engine === 'LEGACY'
      ? [{ type: 'minimize_makespan', weight: 1 }]
      : [{ type: 'engine_native_path_metrics', weight: 1 }],
    scenario_hash: 'module-x-hash',
    elapsed_seconds: 0.02,
    paths: [{ validator_status: 'VALID', metrics: { makespan: 90, execution_count: 6, critical_path_length: 90, resource_peak: [] }, executions }],
  }
}

test.beforeEach(async ({ page }) => {
  await page.route(/\/(health|api\/v1\/)/, async (route, request) => {
    const url = request.url()
    if (url.endsWith('/health')) return route.fulfill({ json: { status: 'healthy', version: 'test' } })
    if (url.endsWith('/api/v1/planner-scenarios') && request.method() === 'GET') return route.fulfill({ json: [
      { id: scenarioId, display_code: 'SCN-DEMO', name: scenario.name, revision: 4, activity_count: 2, package_count: 2 },
      { id: moduleXScenarioId, display_code: 'SCN-MODULE-X', name: moduleXScenario.name, revision: 1, activity_count: 5, package_count: 0 },
    ] })
    if (url.includes('/graph')) return route.fulfill({ json: graph })
    if (url.includes('/draft-commit') && request.method() === 'POST') return route.fulfill({ json: { revision: 5, created_refs: {}, scenario, graph } })
    if (url.includes(`/api/v1/planner-scenarios/${moduleXScenarioId}`) && request.method() === 'GET') return route.fulfill({ json: { id: moduleXScenarioId, display_code: 'SCN-MODULE-X', name: moduleXScenario.name, revision: 1, scenario_hash: 'module-x-hash', scenario: moduleXScenario } })
    if (url.includes('/api/v1/planner-scenarios/') && request.method() === 'GET') return route.fulfill({ json: { id: scenarioId, display_code: 'SCN-DEMO', name: scenario.name, revision: 4, scenario_hash: 'same-hash', scenario } })
    if (url.endsWith('/api/v1/planner-runs/capabilities')) return route.fulfill({ json: {
      planner_available: true,
      engines: ['LEGACY', 'ASTAR', 'GA', 'ALL'],
      legacy_pipeline: 'partial_order_pathfinder+cp_sat_scheduler',
      legacy_objectives: ['minimize_makespan', 'minimize_activity_group_span', 'minimize_activity_group_gaps', 'minimize_activity_group_interruptions', 'minimize_state_group_span', 'minimize_state_group_gaps', 'minimize_state_group_interruptions'],
      resource_model: 'aggregate_capacity',
      resource_instances_supported: false,
    } })
    if (url.endsWith('/api/v1/planner-runs') && request.method() === 'POST') {
      const body = request.postDataJSON()
      const isModuleX = body.scenario_id === moduleXScenarioId
      const engineResult = isModuleX ? moduleXResult : result
      const hash = isModuleX ? 'module-x-hash' : 'same-hash'
      return route.fulfill({ status: 201, json: { id: 'planner-run:1', status: 'OK', scenario_hash: hash, request: body, result: { engines_share_mutable_state: false, results: { LEGACY: engineResult('LEGACY'), ASTAR: engineResult('ASTAR'), GA: engineResult('GA') } } } })
    }
    return route.fulfill({ status: 404, json: { error: `unmocked ${request.method()} ${url}` } })
  })
})

test('activity-only canvas uses package containers and no visible state nodes', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('tab', { name: '活动网络' }).click()

  const canvas = page.getByTestId('planner-activity-x6-canvas')
  await expect(canvas.locator('.x6-network-node.x6-activity-node')).toHaveCount(2)
  await expect(canvas.locator('.x6-network-container.x6-activity-container')).toHaveCount(2)
  await expect(canvas.locator('.x6-state-node, .x6-state-container')).toHaveCount(0)
  await expect(canvas.getByTestId('network-editor-flow-edge-line')).toHaveCount(1)
  await expect(page.getByText('知识版本')).toHaveCount(0)
})

test('activity package containers collapse, expand, and auto-arrange as one layout draft', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('tab', { name: '活动网络' }).click()

  const canvas = page.getByTestId('planner-activity-x6-canvas')
  const childPackage = canvas.getByTestId(`network-editor-activity-node-${childId}`)
  await childPackage.locator('[data-action="toggle"]').click()
  await expect(canvas.locator('.x6-network-node.x6-activity-node')).toHaveCount(1)
  await expect(canvas.locator('.x6-network-container.x6-activity-container')).toHaveCount(1)

  await canvas.getByTestId(`network-editor-activity-node-${childId}`).locator('[data-action="toggle"]').click()
  await expect(canvas.locator('.x6-network-node.x6-activity-node')).toHaveCount(2)
  await expect(canvas.locator('.x6-network-container.x6-activity-container')).toHaveCount(2)

  await page.getByRole('button', { name: '进入编辑' }).click()
  await page.getByTestId('planner-network-auto-arrange').click()
  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  await expect(page.getByRole('button', { name: '统一提交（1）' })).toBeVisible()
  await expect(page.getByText('已加入草稿：自动整理活动网络')).toBeVisible()

  const commitRequest = page.waitForRequest((request) => request.url().includes('/draft-commit') && request.method() === 'POST')
  await page.getByRole('button', { name: '统一提交（1）' }).click()
  const body = (await commitRequest).postDataJSON()
  const layout = body.operations.find((operation) => operation.operation === 'update_layout')
  const first = layout.payload.activity_refs.find((item) => item.id === 'activity-package-member:a')
  const second = layout.payload.activity_refs.find((item) => item.id === 'activity-package-member:b')
  expect(second.x).toBeGreaterThan(first.x)
  expect(Math.abs(second.y - first.y)).toBeLessThan(100)
})

test('activity creation derives its type without a milestone switch', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('button', { name: '进入编辑' }).click()
  await page.getByRole('button', { name: '新增活动' }).click()

  const dialog = page.getByRole('dialog', { name: '新增活动' })
  await expect(dialog.getByText('里程碑', { exact: true })).toHaveCount(0)
  await expect(dialog.getByText('活动类型由前置关系自动识别')).toBeVisible()
  await expect(dialog.getByText('前置状态绑定', { exact: true })).toBeVisible()
  await expect(dialog.getByText('外部事件绑定', { exact: true })).toBeVisible()
  await expect(dialog.getByTestId('activity-event-bindings').getByRole('combobox')).toBeDisabled()
  const bindings = dialog.getByTestId('activity-state-bindings')
  await bindings.locator('.state-binding-select').first().click()
  await page.locator('.el-select-dropdown:visible').getByText('初始状态', { exact: true }).click()
  await dialog.getByTestId('add-activity-state-binding').click()
  await expect(bindings.locator('.state-binding-row')).toHaveCount(2)
  await bindings.locator('.state-binding-select').nth(1).click()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect(bindings.locator('.state-binding-row').nth(1).getByText('准备完成', { exact: true })).toBeVisible()
  await bindings.locator('.state-binding-row').nth(1).getByText('执行后保留', { exact: true }).click()
  await dialog.getByRole('textbox', { name: '活动名称' }).fill('自动识别类型活动')
  await dialog.getByRole('button', { name: '加入草稿' }).click()

  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  await expect(page.getByRole('button', { name: '统一提交（1）' })).toBeVisible()
})

test('existing activity can be edited with a new maximum execution count', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('button', { name: '进入编辑' }).click()

  const activityRow = page.locator('.el-table__body-wrapper tbody tr').filter({ hasText: '准备' }).last()
  await activityRow.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '编辑活动' })
  await expect(dialog.getByRole('textbox', { name: '活动名称' })).toHaveValue('准备')
  const limit = dialog.getByTestId('activity-instance-limit')
  await limit.locator('.el-switch').click()
  await limit.getByRole('spinbutton').fill('2')
  await dialog.getByRole('button', { name: '保存到草稿' }).click()

  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  const commitRequest = page.waitForRequest((request) => request.url().includes('/draft-commit') && request.method() === 'POST')
  await page.getByRole('button', { name: '统一提交（1）' }).click()
  const body = (await commitRequest).postDataJSON()
  expect(body.operations).toHaveLength(1)
  expect(body.operations[0]).toMatchObject({ operation: 'update_activity', object_id: activityA, payload: { name: '准备', duration: 2, max_instances: 2 } })
})

test('activity creation binds existing external events', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-MODULE-X · 模块X到料延迟提拉测试', { exact: true }).click()
  await page.getByRole('button', { name: '进入编辑' }).click()
  await page.getByRole('button', { name: '新增活动' }).click()

  const dialog = page.getByRole('dialog', { name: '新增活动' })
  const eventBindings = dialog.getByTestId('activity-event-bindings')
  await expect(eventBindings.getByRole('combobox')).toBeEnabled()
  await eventBindings.click()
  await page.locator('.el-select-dropdown:visible').getByText('模块 X 到料（T+45）', { exact: true }).click()
  await expect(eventBindings.getByText('模块 X 到料（T+45）', { exact: true })).toBeVisible()
  await dialog.getByRole('textbox', { name: '活动名称' }).fill('等待到料活动')
  await dialog.getByRole('button', { name: '加入草稿' }).click()

  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  await expect(page.getByRole('button', { name: '统一提交（1）' })).toBeVisible()
})

test('existing external event can be edited and submitted as one draft', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-MODULE-X · 模块X到料延迟提拉测试', { exact: true }).click()
  await page.getByRole('button', { name: '进入编辑' }).click()
  await page.getByRole('tab', { name: '资源与事件' }).click()

  const eventRow = page.getByTestId('external-events-table').locator('tbody tr').filter({ hasText: '模块 X 到料' })
  await eventRow.getByRole('button', { name: '编辑', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '编辑外部事件' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('textbox', { name: '名称' })).toHaveValue('模块 X 到料')
  await dialog.getByRole('textbox', { name: '名称' }).fill('模块 X 延迟到料')
  await dialog.getByRole('spinbutton', { name: '发生时间' }).fill('60')
  await dialog.getByRole('button', { name: '保存到草稿' }).click()

  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  const commitRequest = page.waitForRequest((request) => request.url().includes('/draft-commit') && request.method() === 'POST')
  await page.getByRole('button', { name: '统一提交（1）' }).click()
  const body = (await commitRequest).postDataJSON()
  expect(body.operations).toEqual([{
    operation: 'update_event',
    object_id: 'event:x-arrival',
    payload: { name: '模块 X 延迟到料', time: 60, add_state_ids: [], remove_state_ids: [] },
  }])
})

test('activity connection is staged as one draft without exposing state nodes', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('button', { name: '进入编辑' }).click()
  await page.getByRole('tab', { name: '活动网络' }).click()
  await page.getByRole('button', { name: '连接活动' }).click()

  const nodes = page.getByTestId('planner-activity-x6-canvas').locator('.x6-network-node.x6-activity-node')
  await nodes.nth(1).click()
  await nodes.nth(0).click()

  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  await expect(page.getByRole('button', { name: '统一提交（1）' })).toBeVisible()
  await expect(page.getByTestId('planner-activity-x6-canvas').locator('.x6-state-node, .x6-state-container')).toHaveCount(0)
})

test('planner network reuses the three-pane editor with property drafts, undo, and impact analysis', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('tab', { name: '活动网络' }).click()

  const workbench = page.getByTestId('network-editor-workbench-frame')
  await expect(workbench.locator('.resource-pane')).toBeVisible()
  await expect(workbench.locator('.canvas-pane')).toBeVisible()
  await expect(workbench.locator('.properties-pane')).toBeVisible()
  await expect(workbench.getByText('初始状态', { exact: true })).toBeVisible()

  await workbench.getByText('ACT-0001 · 准备', { exact: true }).click()
  const properties = workbench.locator('.properties-pane')
  await expect(properties.getByLabel('活动名称')).toHaveValue('准备')
  await expect(properties.getByLabel('系统主输出')).toHaveValue('准备完成')

  await page.getByRole('button', { name: '进入编辑' }).click()
  await properties.getByLabel('活动名称').fill('准备（已调整）')
  await properties.getByRole('button', { name: '保存到草稿' }).click()
  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  await expect(workbench.getByText('编辑活动 准备（已调整）', { exact: true })).toBeVisible()

  await properties.getByRole('button', { name: '影响分析' }).click()
  await expect(page.getByRole('heading', { name: '活动影响分析' })).toBeVisible()
  await expect(page.getByText('直接前置', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')

  await workbench.getByRole('button', { name: '撤回' }).click()
  await expect(page.getByText('当前有 1 项未提交变更')).toHaveCount(0)
  await expect(page.getByRole('button', { name: '统一提交（0）' })).toBeDisabled()
})

test('all engines display one shared snapshot and valid replay results', async ({ page }) => {
  await page.goto('/')
  await page.getByText('多引擎求解', { exact: true }).click()
  await expect(page.getByText('Planner 已连接')).toBeVisible()
  await expect(page.getByTestId('current-state-select').first().locator('.el-select__tags-text').filter({ hasText: '初始状态' })).toBeVisible()
  await expect(page.getByTestId('target-state-select').first().locator('.el-select__tags-text').filter({ hasText: '执行完成' })).toBeVisible()
  await expect(page.getByText('目标活动包')).toHaveCount(0)
  await expect(page.getByTestId('legacy-objectives')).toContainText('添加目标')
  const runRequest = page.waitForRequest((request) => request.url().endsWith('/api/v1/planner-runs') && request.method() === 'POST')
  await page.getByRole('button', { name: '开始求解' }).click()
  const requestBody = (await runRequest).postDataJSON()
  expect(requestBody).toMatchObject({
    expected_revision: 4,
    current_state_ids: ['state:seed'],
    target_state_ids: ['state:b-output'],
    objectives: [{ type: 'minimize_makespan', weight: 1 }],
  })
  expect(requestBody.target_state_node_ids).toBeUndefined()
  await expect(page.getByText('隔离且一致')).toBeVisible()
  await expect(page.locator('.comparison-card').getByText('旧引擎', { exact: true })).toBeVisible()
  await expect(page.getByText('引擎结果对比')).toBeVisible()
  await expect(page.getByRole('tab', { name: '甘特图' })).toBeVisible()
  await expect(page.getByTestId('gantt-chart-canvas').locator('canvas')).toBeVisible()
  await page.getByRole('tab', { name: '活动网络图' }).click()
  await expect(page.locator('.network-board canvas')).toBeVisible()
  await expect(page.getByText('VALID', { exact: true })).toHaveCount(4)
})

test('current and target trees cascade packages and submit canonical states once', async ({ page }) => {
  await page.goto('/')
  await page.getByText('多引擎求解', { exact: true }).click()

  const current = page.getByTestId('current-state-select').first()
  await current.locator('.el-tag__close').click()
  await page.keyboard.press('Escape')
  await current.click()
  let visibleTree = current.locator('.el-tree:visible')
  await expect(visibleTree.getByText('一级状态包 · 一级总包', { exact: true })).toBeVisible()
  await expect(visibleTree.getByText('二级状态包 · 二级实施包', { exact: true })).toBeVisible()
  await visibleTree.locator('.el-tree-node__content').filter({ hasText: '二级状态包 · 二级实施包' }).locator('.el-checkbox').click()
  const currentRootNode = visibleTree.locator('.el-tree-node').filter({ hasText: '一级状态包 · 一级总包' }).first()
  await expect(currentRootNode.locator(':scope > .el-tree-node__content .el-checkbox')).toHaveAttribute('aria-checked', 'mixed')
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('state-selection-summary')).toContainText('当前状态 2')

  const target = page.getByTestId('target-state-select').first()
  await target.locator('.el-tag__close').click()
  await page.keyboard.press('Escape')
  await target.click()
  visibleTree = target.locator('.el-tree:visible')
  await expect(visibleTree.getByText('二级状态包 · 二级共享包', { exact: true })).toBeVisible()
  const targetRootCheckbox = visibleTree.locator('.el-tree-node__content').filter({ hasText: '一级状态包 · 一级总包' }).first().locator('.el-checkbox')
  await targetRootCheckbox.dispatchEvent('click')
  await page.keyboard.press('Escape')

  const summary = page.getByTestId('state-selection-summary')
  await expect(summary).toContainText('当前状态 2')
  await expect(summary).toContainText('目标状态 2')
  await target.click()
  visibleTree = target.locator('.el-tree:visible')
  await visibleTree.locator('.el-tree-node__content').filter({ hasText: '一级状态包 · 一级总包' }).first().locator('.el-checkbox').dispatchEvent('click')
  await page.keyboard.press('Escape')
  await expect(summary).toContainText('目标状态 0')
  await target.click()
  visibleTree = target.locator('.el-tree:visible')
  await visibleTree.locator('.el-tree-node__content').filter({ hasText: '一级状态包 · 一级总包' }).first().locator('.el-checkbox').dispatchEvent('click')
  await page.keyboard.press('Escape')
  await expect(summary).toContainText('目标状态 2')
  const runRequest = page.waitForRequest((request) => request.url().endsWith('/api/v1/planner-runs') && request.method() === 'POST')
  await page.getByRole('button', { name: '开始求解' }).click()
  const body = (await runRequest).postDataJSON()
  expect(body.current_state_ids).toEqual([stateA, 'state:b-output'].sort())
  expect(body.target_state_ids).toEqual([stateA, 'state:b-output'].sort())
  expect(body.objectives).toEqual([{ type: 'minimize_makespan', weight: 1 }])
  expect(body.target_state_node_ids).toBeUndefined()
})

test('module X repeated power states render a 90-minute acyclic result', async ({ page }) => {
  const pageErrors: Error[] = []
  page.on('pageerror', (error) => pageErrors.push(error))

  await page.goto('/')
  await page.getByText('多引擎求解', { exact: true }).click()
  await page.locator('.control-card .el-select').first().click()
  await page.getByText('SCN-MODULE-X · 模块X到料延迟提拉测试', { exact: true }).click()
  await expect(page.getByTestId('current-state-select').first().locator('.el-select__tags-text').filter({ hasText: '电源已下电' })).toBeVisible()
  await expect(page.getByTestId('target-state-select').first().locator('.el-select__tags-text').filter({ hasText: '模块 X 已安装' })).toBeVisible()
  await page.getByRole('button', { name: '开始求解' }).click()

  await expect(page.getByText('引擎结果对比')).toBeVisible()
  await expect(page.locator('.comparison-card').getByText('90', { exact: true })).toHaveCount(3)
  await expect(page.getByTestId('gantt-chart-canvas').locator('canvas')).toBeVisible()
  await page.getByRole('tab', { name: '活动网络图' }).click()
  await expect(page.getByText('6 个活动', { exact: true })).toBeVisible()
  await expect(page.getByText('6 条依赖', { exact: true })).toBeVisible()
  await expect(page.locator('.network-board canvas')).toBeVisible()
  expect(pageErrors).toEqual([])
})

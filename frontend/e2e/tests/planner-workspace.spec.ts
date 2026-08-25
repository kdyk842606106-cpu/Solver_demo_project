import { expect, test } from '@playwright/test'

const scenarioId = 'scenario:11111111-1111-4111-8111-111111111111'
const rootId = 'activity-package:22222222-2222-4222-8222-222222222222'
const childId = 'activity-package:33333333-3333-4333-8333-333333333333'
const activityA = 'activity:44444444-4444-4444-8444-444444444444'
const activityB = 'activity:55555555-5555-4555-8555-555555555555'
const stateA = 'state:44444444-4444-4444-8444-444444444444:output'

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
  initial_state_ids: ['state:seed'], goal_state_ids: [], forbidden_state_ids: [], target_activity_ids: [],
  target_activity_package_ids: [rootId], activity_package_scope_ids: [], resources: [], external_events: [],
  activity_packages: [
    { id: rootId, display_code: 'AP-0001', name: '一级总包', level: 1, parent_id: null, mirrored_state_package_id: 'state-package:22222222-2222-4222-8222-222222222222' },
    { id: childId, display_code: 'AP-0002', name: '二级实施包', level: 2, parent_id: rootId, mirrored_state_package_id: 'state-package:33333333-3333-4333-8333-333333333333' },
  ],
  activities: [
    { id: activityA, display_code: 'ACT-0001', name: '准备', duration: 2, preconditions: [{ state_id: 'state:seed', relation_role: 'transition' }], output_state_id: stateA, output_state_name: '准备完成', additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], is_milestone: false, is_active: true },
    { id: activityB, display_code: 'ACT-0002', name: '执行', duration: 3, preconditions: [{ state_id: stateA, relation_role: 'transition' }], output_state_id: 'state:b-output', output_state_name: '执行完成', additional_output_state_ids: [], resource_reqs: {}, event_reqs: [], is_milestone: false, is_active: true },
  ],
  activity_package_memberships: [
    { id: 'activity-package-member:a', package_id: childId, activity_id: activityA, layout: {} },
    { id: 'activity-package-member:b', package_id: childId, activity_id: activityB, layout: {} },
  ],
  state_packages: [], state_package_memberships: [], provenance: {},
}

const graph = {
  scenario_id: scenarioId,
  revision: 4,
  containers: scenario.activity_packages,
  nodes: [
    { id: 'activity-package-member:a', kind: 'activity', canonical_activity_id: activityA, package_id: childId, display_code: 'ACT-0001', name: '准备', duration: 2, seed_preconditions: ['state:seed'], event_preconditions: [] },
    { id: 'activity-package-member:b', kind: 'activity', canonical_activity_id: activityB, package_id: childId, display_code: 'ACT-0002', name: '执行', duration: 3, seed_preconditions: [], event_preconditions: [] },
  ],
  edges: [{ id: 'dependency:a:b', kind: 'activity_dependency', source: 'activity-package-member:a', target: 'activity-package-member:b', state_id: stateA, relation_role: 'transition' }],
  summary: { activity_count: 2, display_node_count: 2, package_count: 2, state_node_count: 0 },
}

function result(engine: string) {
  return {
    algorithm: engine,
    status: 'OK',
    scenario_hash: 'same-hash',
    elapsed_seconds: 0.02,
    paths: [{ validator_status: 'VALID', metrics: { makespan: 5, execution_count: 2 }, executions: [{ activity_name: '准备', start_time: 0, end_time: 2 }, { activity_name: '执行', start_time: 2, end_time: 5 }] }],
  }
}

test.beforeEach(async ({ page }) => {
  await page.route(/\/(health|api\/v1\/)/, async (route, request) => {
    const url = request.url()
    if (url.endsWith('/health')) return route.fulfill({ json: { status: 'healthy', version: 'test' } })
    if (url.endsWith('/api/v1/planner-scenarios') && request.method() === 'GET') return route.fulfill({ json: [{ id: scenarioId, display_code: 'SCN-DEMO', name: scenario.name, revision: 4, activity_count: 2, package_count: 2 }] })
    if (url.includes('/graph')) return route.fulfill({ json: graph })
    if (url.includes('/api/v1/planner-scenarios/') && request.method() === 'GET') return route.fulfill({ json: { id: scenarioId, display_code: 'SCN-DEMO', name: scenario.name, revision: 4, scenario_hash: 'same-hash', scenario } })
    if (url.endsWith('/api/v1/planner-runs/capabilities')) return route.fulfill({ json: { planner_available: true, engines: ['LEGACY', 'ASTAR', 'GA', 'ALL'], resource_model: 'aggregate_capacity', resource_instances_supported: false } })
    if (url.endsWith('/api/v1/planner-runs') && request.method() === 'POST') return route.fulfill({ status: 201, json: { id: 'planner-run:1', status: 'OK', scenario_hash: 'same-hash', result: { engines_share_mutable_state: false, results: { LEGACY: result('LEGACY'), ASTAR: result('ASTAR'), GA: result('GA') } } } })
    return route.fulfill({ status: 404, json: { error: `unmocked ${request.method()} ${url}` } })
  })
})

test('activity-only canvas uses package containers and no visible state nodes', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('tab', { name: '活动网络' }).click()

  const canvas = page.getByTestId('planner-activity-canvas')
  await expect(canvas.locator('[data-node-kind="activity"]')).toHaveCount(2)
  await expect(canvas.locator('[data-container-kind="activity-package"]')).toHaveCount(2)
  await expect(canvas.locator('[data-node-kind="state"], [data-node-kind="state_package"]')).toHaveCount(0)
  await expect(canvas.locator('svg[aria-label="活动依赖线"] path').last()).toBeVisible()
  await expect(page.getByText('知识版本')).toHaveCount(0)
})

test('activity connection is staged as one draft without exposing state nodes', async ({ page }) => {
  await page.goto('/')
  await page.locator('.hero-actions .el-select').click()
  await page.getByText('SCN-DEMO · Planner 演示场景', { exact: true }).click()
  await page.getByRole('button', { name: '进入编辑' }).click()
  await page.getByRole('tab', { name: '活动网络' }).click()
  await page.getByRole('button', { name: '连接活动' }).click()

  const nodes = page.getByTestId('planner-activity-canvas').locator('[data-node-kind="activity"]')
  await nodes.nth(1).click()
  await nodes.nth(0).click()

  await expect(page.getByText('当前有 1 项未提交变更')).toBeVisible()
  await expect(page.getByRole('button', { name: '统一提交（1）' })).toBeVisible()
  await expect(page.getByTestId('planner-activity-canvas').locator('[data-node-kind="state"], [data-node-kind="state_package"]')).toHaveCount(0)
})

test('all engines display one shared snapshot and valid replay results', async ({ page }) => {
  await page.goto('/')
  await page.getByText('多引擎求解').click()
  await expect(page.getByText('Planner 已连接')).toBeVisible()
  await page.getByRole('button', { name: '开始求解' }).click()
  await expect(page.getByText('隔离且一致')).toBeVisible()
  await expect(page.locator('.engine-name').getByText('旧引擎', { exact: true })).toBeVisible()
  await expect(page.locator('.engine-name').getByText('Anytime A*', { exact: true })).toBeVisible()
  await expect(page.locator('.engine-name').getByText('遗传算法 GA', { exact: true })).toBeVisible()
  await expect(page.locator('.validator .el-tag').getByText('VALID', { exact: true })).toHaveCount(3)
})

import { test, expect } from '@playwright/test'
import {
  BASE_SCHEDULE,
  STATE_LANE_RESULT_EXTRAS,
  STATE_LANE_SCHEDULE,
  createMockRouteHandler,
} from '../fixtures/mock-api'

const STATE_LANE_DELAYED_SCHEDULE = {
  ...STATE_LANE_SCHEDULE,
  schedule_id: 203,
  makespan: 80,
  tasks: STATE_LANE_SCHEDULE.tasks.map((task: any) => {
    if (task.step_order === 1) {
      return {
        ...task,
        start_min: 25,
        end_min: 45,
        step_role: 'delayed',
        is_delayed: true,
        not_before: 25,
      }
    }
    if (task.step_order === 2) {
      return {
        ...task,
        start_min: 45,
        end_min: 65,
        predecessor_ids: [1],
      }
    }
    return {
      ...task,
      start_min: 65,
      end_min: 80,
      predecessor_ids: [2],
    }
  }),
}

function createLayeredBlockageMockRouteHandler() {
  const fallback = createMockRouteHandler(STATE_LANE_SCHEDULE, STATE_LANE_RESULT_EXTRAS)
  return async (route: any, request: any) => {
    const url = request.url()
    const method = request.method()

    if (url.endsWith('/api/v1/solve/layered') && method === 'POST') {
      const payload = JSON.parse(request.postData() || '{}')
      const isReplan = payload.parent_plan_id != null || payload.blockage_constraints != null
      const schedule = isReplan ? STATE_LANE_DELAYED_SCHEDULE : STATE_LANE_SCHEDULE
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule,
          candidate_plan_id: schedule.schedule_id,
          state_delta: [],
          critical_path: [],
          ...STATE_LANE_RESULT_EXTRAS,
        }),
      })
      return
    }

    if (url.endsWith('/api/v1/solve') && method === 'POST') {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule: {
            ...BASE_SCHEDULE,
            schedule_id: 204,
            tasks: BASE_SCHEDULE.tasks.map((task: any, index: number) => ({
              ...task,
              start_min: index === 0 ? 25 : 55,
              end_min: index === 0 ? 55 : 70,
              step_role: index === 0 ? 'delayed' : 'normal',
              state_continuity_groups: [],
            })),
          },
          candidate_plan_id: 204,
          state_delta: [],
          critical_path: [],
        }),
      })
      return
    }

    await fallback(route, request)
  }
}

test.describe('Solve Page — Happy Path', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/(health|api\/v1\/)/, createMockRouteHandler(BASE_SCHEDULE))
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.click('.el-menu-item:has-text("求解")')
    await page.waitForSelector('h2:has-text("求解")', { timeout: 10000 })
    // Give Vue time to fully render the form
    await page.waitForTimeout(2000)
  })

  test('page loads and shows solve form', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('求解')
    await expect(page.locator('.el-form')).toBeVisible()
    await expect(page.locator('.objective-controls')).toContainText('活动连续性')
    await page.locator('.objective-controls .el-switch').click()
    await expect(page.locator('.objective-weight')).toBeVisible()
  })

  test('can select machine and auto-populate states', async ({ page }) => {
    // Click the first el-select (machine)
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(500)

    // Verify states are populated
    const currentStateText = await page.locator('.el-select__wrapper').nth(1).locator('.el-select__placeholder').textContent()
    const targetStateText = await page.locator('.el-select__wrapper').nth(2).locator('.el-select__placeholder').textContent()
    expect(currentStateText).not.toBe('请选择')
    expect(targetStateText).not.toBe('请选择')
  })

  test('can select a top-level state package as layered target', async ({ page }) => {
    await page.locator('.el-radio-group').first().locator('.el-radio-button').nth(1).click()

    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')

    const targetTree = page.getByTestId('solve-layered-target-state-tree').first()
    await targetTree.locator('.el-select__wrapper').click()
    const rootNode = page.locator('.el-tree-node', { hasText: 'PKG_MECH_DONE' }).first()
    await expect(rootNode).toBeVisible()
    await expect(rootNode).not.toHaveClass(/is-disabled/)
    await rootNode.locator('.el-checkbox').click({ force: true })
    await expect(targetTree).toContainText('PKG_MECH_DONE')

    const [request] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/solve/layered') &&
        request.method() === 'POST',
      ),
      page.locator('.toolbar-actions .el-button--primary').click(),
    ])
    const payload = JSON.parse(request.postData() || '{}')
    expect(payload.target_state_node_ids).toEqual([10])
  })

  test('shows referenced atomic library states in layered target tree', async ({ page }) => {
    await page.locator('.el-radio-group').first().locator('.el-radio-button').nth(1).click()

    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')

    const targetTree = page.getByTestId('solve-layered-target-state-tree').first()
    await targetTree.locator('.el-select__wrapper').click()
    const input = targetTree.locator('input').last()
    await input.fill('REF_MODULE_B_DONE')
    const referencedNode = page.locator('.el-tree-node__content:visible', { hasText: 'REF_MODULE_B_DONE' }).last()
    await expect(referencedNode).toBeVisible()
    await referencedNode.locator('.el-checkbox__input').click({ force: true })
    await expect(targetTree).toContainText('REF_MODULE_B_DONE')
    await page.locator('h2:has-text("求解")').click({ force: true })
    const solveButton = page.getByRole('button', { name: '开始求解' })
    await expect(solveButton).toBeEnabled()

    const [request] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/solve/layered') &&
        request.method() === 'POST',
      ),
      solveButton.click({ force: true }),
    ])
    const payload = JSON.parse(request.postData() || '{}')
    expect(payload.target_state_node_ids).toEqual([12])
  })

  test('full solve flow produces schedule', async ({ page }) => {
    // Click the first el-select (machine)
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(500)

    // Click solve button
    await page.click('button:has-text("开始求解")')

    // Wait for results
    await page.click('.el-tabs__item:has-text("任务明细")')
    await page.waitForSelector('.el-table__body tr:visible', { timeout: 30000 })

    // Verify 2 tasks in table
    const rows = page.locator('.el-table__body tr:visible')
    await expect(rows).toHaveCount(2)

    // Verify Gantt chart is visible
    await page.click('.el-tabs__item:has-text("甘特图")')
    await expect(page.locator('text=排程 Gantt 图')).toBeVisible()
    await expect(page.locator('.gantt-controls')).not.toContainText('当前结果没有状态包归属数据')
    await expect(page.locator('.el-radio-button:has-text("状态泳道")')).toHaveClass(/is-disabled/)

    // Verify makespan statistic
    const makespan = await page.locator('.metric-item.primary strong').first().textContent()
    expect(makespan).toContain('45')
  })
})

test.describe('Solve Page — Gantt State Lanes', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(
      /\/(health|api\/v1\/)/,
      createMockRouteHandler(STATE_LANE_SCHEDULE, STATE_LANE_RESULT_EXTRAS),
    )
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.click('.el-menu-item:has-text("求解")')
    await page.waitForSelector('h2:has-text("求解")', { timeout: 10000 })
    await page.waitForTimeout(2000)
  })

  test('switches between traditional Gantt and state lanes', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(500)

    await page.click('button:has-text("开始求解")')
    await page.click('.el-tabs__item:has-text("甘特图")')

    const summary = page.getByTestId('state-lane-summary')
    await expect(summary).toContainText('STRUCTURE_ASSEMBLY_COMPLETE')
    await expect(summary).toContainText('TRANSFER_MECHANISM_READY')
    await expect(summary).toContainText('未归属状态包')
    await expect(page.locator('.gantt-controls')).toContainText('未启用连续性优化')

    await page.click('.el-radio-button:has-text("传统视图")')
    await expect(page.locator('.hierarchy-controls')).toContainText('MECH_ASSEMBLY')
    await expect(page.locator('.hierarchy-controls')).toContainText('TRANSFER_READY')

    await page.click('.el-radio-button:has-text("状态泳道")')
    await expect(summary).toContainText('STRUCTURE_ASSEMBLY_COMPLETE')
  })
})

test.describe('Solve Page layered blockage replan', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.route(/\/(health|api\/v1\/)/, createLayeredBlockageMockRouteHandler())
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.locator('.el-menu-item').nth(1).click()
    await page.waitForSelector('.solve-page', { timeout: 10000 })
    await page.waitForTimeout(2000)
  })

  test('keeps state lanes and task details after Strategy A replan', async ({ page }) => {
    await page.locator('.el-radio-group').first().locator('.el-radio-button').nth(1).click()
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')

    const targetTree = page.getByTestId('solve-layered-target-state-tree').first()
    await targetTree.locator('.el-select__wrapper').click()
    const rootNode = page.locator('.el-tree-node__content:visible', { hasText: 'PKG_MECH_DONE' }).first()
    await expect(rootNode).toBeVisible()
    await rootNode.locator('.el-checkbox__input').click({ force: true })

    await page.locator('.toolbar-actions .el-button--primary').click()
    await expect(page.getByTestId('state-lane-summary')).toContainText('STRUCTURE_ASSEMBLY_COMPLETE')

    await page.locator('.result-tabs .el-tabs__item').nth(2).click()
    const structureRow = page.locator('.el-table__body tr:visible').filter({ hasText: 'OP_STRUCTURE_BASE' })
    await expect(structureRow).toBeVisible()
    await structureRow.locator('button').last().click()

    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await page.fill('.el-input-number input', '25')
    const [replanRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/solve/layered') &&
        request.method() === 'POST' &&
        JSON.parse(request.postData() || '{}').parent_plan_id === 202,
      ),
      page.click('.el-dialog__footer .el-button--primary'),
    ])

    const payload = JSON.parse(replanRequest.postData() || '{}')
    expect(payload.blockage_constraints?.strategy).toBe('A')
    expect(payload.target_state_node_ids).toEqual([10])

    await expect(page.getByTestId('state-lane-summary')).toContainText('STRUCTURE_ASSEMBLY_COMPLETE')
    await page.locator('.result-tabs .el-tabs__item').nth(2).click()
    await expect(page.locator('.el-table__body tr:visible').filter({ hasText: 'OP_TRANSFER_READY' })).toBeVisible()
    await expect(
      page
        .locator('.el-table__body tr:visible')
        .filter({ hasText: 'OP_STRUCTURE_BASE' })
        .locator('.el-tag'),
    ).toBeVisible()
  })
})

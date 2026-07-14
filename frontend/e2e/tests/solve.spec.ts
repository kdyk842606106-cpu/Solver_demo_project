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
    await expect(page.locator('.objective-controls')).toContainText('集成规则')
    await expect(page.getByTestId('solve-scheduling-rule-select')).toBeVisible()
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

  test('uses an explicit synchronized activity scope before constraint editing', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.getByRole('button', { name: '开始求解' }).click()

    const [created] = await Promise.all([
      page.waitForRequest((request: any) =>
        /\/api\/v1\/plans\/\d+\/adjustments$/.test(request.url()) && request.method() === 'POST',
      ),
      page.getByRole('button', { name: '计划调整 / 重排' }).click(),
    ])
    expect(JSON.parse(created.postData() || '{}')).toEqual({ kind: 'schedule' })
    await expect(page.getByText('选择待调整范围')).toBeVisible()

    await page.getByRole('tab', { name: '任务明细' }).click()
    const taskRows = page.locator('.el-table__body-wrapper tbody tr')
    await taskRows.first().locator('.el-checkbox').click()
    await expect(page.getByText('已选择 1 个活动')).toBeVisible()

    const [scopeRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        /\/api\/v1\/plan-adjustments\/\d+$/.test(request.url()) && request.method() === 'PATCH',
      ),
      page.getByRole('button', { name: '确认范围并编辑约束' }).click(),
    ])
    const scopePayload = JSON.parse(scopeRequest.postData() || '{}')
    expect(scopePayload.scope_step_ids).toEqual([501])
    expect(scopePayload).not.toHaveProperty('cutoff_min')
    expect(scopePayload).not.toHaveProperty('brush')
    await expect(page.getByText('本次范围由计划师显式选择')).toBeVisible()
    await expect(page.getByText('不得早于开始（not_before）').first()).toBeVisible()

    await page.getByRole('button', { name: '加入约束清单' }).click()
    const [savedRequest, previewRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        /\/api\/v1\/plan-adjustments\/\d+$/.test(request.url()) && request.method() === 'PATCH',
      ),
      page.waitForRequest((request: any) =>
        /\/api\/v1\/plan-adjustments\/\d+\/preview$/.test(request.url()) && request.method() === 'POST',
      ),
      page.getByRole('button', { name: '保存并试算' }).click(),
    ])
    expect(JSON.parse(savedRequest.postData() || '{}').constraints).toHaveLength(1)
    expect(previewRequest.method()).toBe('POST')
    await expect(page.getByText('候选计划试算完成，可以查看影响并确认新基线。')).toBeVisible()
    await expect(page.getByRole('button', { name: '确认候选为新基线' })).toBeEnabled()
  })

  test('selects every Gantt task bar intersected by a rectangle brush', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.getByRole('button', { name: '开始求解' }).click()
    await page.getByRole('button', { name: '计划调整 / 重排' }).click()

    const canvas = page.getByTestId('gantt-chart-canvas').locator('canvas')
    await canvas.scrollIntoViewIfNeeded()
    const box = await canvas.boundingBox()
    expect(box).not.toBeNull()
    if (!box) return

    // Enable the rectangle brush from the ECharts toolbox, then drag across
    // the complete plot area. Custom-series task bars must be hit-tested by
    // their rendered rectangles rather than relying on built-in series data.
    await page.mouse.click(box.x + box.width - 54, box.y + 18)
    await page.mouse.move(box.x + 168, box.y + 12)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width - 26, box.y + box.height - 36, { steps: 10 })
    await page.mouse.up()

    await expect(page.getByText(`已选择 ${BASE_SCHEDULE.tasks.length} 个活动`)).toBeVisible()
  })

  test('sends explicit work calendar context', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.locator('.calendar-controls .el-switch').click()
    const dateInput = page.locator('.calendar-controls .el-date-editor input').first()
    await dateInput.fill('2026-07-13 08:00')
    await dateInput.press('Enter')
    const [request] = await Promise.all([
      page.waitForRequest((request: any) => request.url().endsWith('/api/v1/solve') && request.method() === 'POST'),
      page.getByRole('button', { name: '开始求解' }).click(),
    ])
    const payload = JSON.parse(request.postData() || '{}')
    expect(payload.calendar_context.enabled).toBe(true)
    expect(payload.calendar_context.display_timezone).toBe('Asia/Shanghai')
    expect(payload.calendar_context.schedule_start_at).toContain('2026-07-13')
    expect(new Date(payload.calendar_context.schedule_start_at).getUTCSeconds()).toBe(0)
    expect(new Date(payload.calendar_context.schedule_start_at).getUTCMilliseconds()).toBe(0)
  })

  test('locks required scheduling rules and allows optional rules to be switched independently', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')

    const ruleSelect = page.getByTestId('solve-scheduling-rule-select')
    await ruleSelect.locator('.el-select__wrapper').click()
    const required = page.locator('.el-select-dropdown__item:visible', { hasText: '行吊作业仅允许指定班次' })
    const optional = page.locator('.el-select-dropdown__item:visible', { hasText: '功能调测优先独占' })
    await expect(required).toHaveClass(/is-disabled/)
    await optional.click()
    await page.keyboard.press('Escape')

    const [request] = await Promise.all([
      page.waitForRequest((item: any) => item.url().endsWith('/api/v1/solve') && item.method() === 'POST'),
      page.getByRole('button', { name: '开始求解' }).click(),
    ])
    const payload = JSON.parse(request.postData() || '{}')
    expect(payload.constraints.scheduling_rules.active_rule_codes).toEqual([
      'CRANE_EXCLUSIVE',
      'CRANE_DAY_SHIFT_ONLY',
    ])
  })

  test('offers registered state-package continuity only for layered and maintenance modes', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')

    const ruleSelect = page.getByTestId('solve-scheduling-rule-select')
    await ruleSelect.locator('.el-select__wrapper').click()
    const snapshotOption = page.locator('.el-select-dropdown__item:visible', { hasText: '状态包连续性' })
    await expect(snapshotOption).toHaveClass(/is-disabled/)
    await page.keyboard.press('Escape')

    await page.locator('.el-radio-group').first().locator('.el-radio-button').nth(1).click()
    await ruleSelect.locator('.el-select__wrapper').click()
    const layeredOption = page.locator('.el-select-dropdown__item:visible', { hasText: '状态包连续性' })
    await expect(layeredOption).not.toHaveClass(/is-disabled/)
    await layeredOption.click()
    await expect(layeredOption).toHaveClass(/is-selected/)
    await page.keyboard.press('Escape')

    const targetTree = page.getByTestId('solve-layered-target-state-tree').first()
    await targetTree.locator('.el-select__wrapper').click()
    const rootNode = page.locator('.el-tree-node', { hasText: 'PKG_MECH_DONE' }).first()
    await expect(rootNode).toBeVisible()
    await rootNode.locator('.el-checkbox').click({ force: true })
    const [request] = await Promise.all([
      page.waitForRequest((item: any) => item.url().endsWith('/api/v1/solve/layered') && item.method() === 'POST'),
      page.locator('.toolbar-actions .el-button--primary').click(),
    ])
    const payload = JSON.parse(request.postData() || '{}')
    expect(payload.constraints.scheduling_rules.active_rule_codes).toContain('STATE_PACKAGE_CONTINUITY')
    expect(payload.objectives).toEqual([{ type: 'minimize_makespan', weight: 1 }])
  })

  test('submits a post-solve task exception as a child-plan replan', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.getByRole('button', { name: '开始求解' }).click()
    await expect(page.getByRole('tab', { name: '任务明细' })).toBeVisible()
    await page.getByRole('tab', { name: '任务明细' }).click()
    await page.getByRole('button', { name: '规则例外' }).first().click()

    const shiftSelect = page.locator('.el-dialog .el-select').nth(1)
    await shiftSelect.locator('.el-select__wrapper').click()
    const input = shiftSelect.locator('input')
    await input.fill('NIGHT_SHIFT')
    await page.locator('.el-select-dropdown__item:visible', { hasText: 'NIGHT_SHIFT' }).last().click()
    await expect(shiftSelect).toContainText('NIGHT_SHIFT')
    await page.locator('.el-dialog textarea').fill('需要连续完成本次吊装作业')

    const [request] = await Promise.all([
      page.waitForRequest((item: any) => {
        if (!item.url().endsWith('/api/v1/solve') || item.method() !== 'POST') return false
        return JSON.parse(item.postData() || '{}').parent_plan_id === 101
      }),
      page.getByRole('button', { name: '确认并完整重排' }).click(),
    ])
    const payload = JSON.parse(request.postData() || '{}')
    expect(payload.constraints.scheduling_rules.new_override).toMatchObject({
      rule_code: 'CRANE_DAY_SHIFT_ONLY',
      source_step_id: 501,
      reason: '需要连续完成本次吊装作业',
    })
    expect(payload.constraints.scheduling_rules.new_override.parameters.allow_shift_codes).toEqual(['NIGHT_SHIFT'])
    expect(payload.constraints.scheduling_rules.carry_parent_override_keys).toEqual([])
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

  test('renders rule markers and segment shift presentation in Gantt views', async ({ page }) => {
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.locator('.toolbar-actions .el-button--primary').click()
    await page.locator('.result-tabs .el-tabs__item').first().click()

    const legend = page.getByTestId('gantt-presentation-legend')
    await expect(legend).toBeVisible()
    await expect(legend).toContainText('甘特图例')
    await expect(page.getByTestId('gantt-marker-legend-section')).toContainText('作业标识')
    await expect(page.getByTestId('gantt-shift-legend-section')).toContainText('班次')
    await expect(page.getByTestId('gantt-marker-legend-item')).toHaveCount(1)
    await expect(page.getByTestId('gantt-marker-legend-item')).toContainText('吊')
    await expect(page.getByTestId('gantt-marker-legend-item')).toContainText('行吊作业独占')
    await expect(page.getByTestId('gantt-shift-legend-item')).toHaveCount(3)
    await expect(legend).toContainText('白班 (DAY_SHIFT)')
    await expect(legend).toContainText('夜班 (NIGHT_SHIFT)')
    await expect(legend).toContainText('保障班 (SUPPORT_SHIFT)')

    const accessible = page.getByTestId('gantt-accessibility-summary')
    await expect(accessible).toContainText('OP_STRUCTURE_BASE')
    await expect(accessible).toContainText('甘特标识 吊')
    await expect(accessible).toContainText('白班 (DAY_SHIFT)')
    await expect(accessible).toContainText('夜班 (NIGHT_SHIFT)')

    await page.locator('.gantt-controls .el-radio-button').first().click()
    const mechanicalGroup = page.locator('.hierarchy-controls .el-button', { hasText: 'MECH_ASSEMBLY' })
    await mechanicalGroup.click()
    await expect(accessible).toContainText('甘特标识 吊×1')
    await expect(legend).toContainText('白班 (DAY_SHIFT)')
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

  test('maps Strategy A to a not_before candidate without rerunning Planner', async ({ page }) => {
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
    await structureRow.getByRole('button', { name: '标记阻塞' }).click()

    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await page.fill('.el-input-number input', '25')
    const [adjustmentRequest] = await Promise.all([
      page.waitForRequest((request: any) =>
        request.url().endsWith('/api/v1/plans/202/adjustments') &&
        request.method() === 'POST',
      ),
      page.click('.el-dialog__footer .el-button--primary'),
    ])

    const payload = JSON.parse(adjustmentRequest.postData() || '{}')
    expect(payload.kind).toBe('blockage')
    expect(payload.scope_step_ids).toEqual([501])
    expect(payload.constraints).toEqual([{
      type: 'not_before',
      step_ids: [501],
      value_min: 25,
    }])
    expect(payload).not.toHaveProperty('cutoff_min')
    await expect(page.getByText('计划调整 / 重排').first()).toBeVisible()
    await expect(page.getByText('not_before').first()).toBeVisible()

    await expect(page.getByTestId('state-lane-summary')).toContainText('STRUCTURE_ASSEMBLY_COMPLETE')
  })
})

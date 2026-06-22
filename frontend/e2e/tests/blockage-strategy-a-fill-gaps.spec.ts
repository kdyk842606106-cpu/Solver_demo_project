import { test, expect } from '@playwright/test'
import {
  MOCK_MACHINE_TYPES,
  MOCK_MACHINES,
  MOCK_RESOURCES,
  MOCK_STATES,
} from '../fixtures/mock-api'

const PARALLEL_SCHEDULE = {
  schedule_id: 201,
  makespan: 45,
  tasks: [
    {
      task_id: 1,
      step_order: 1,
      op_rule_id: 1,
      op_rule_code: 'OP_WARMUP',
      op_rule_name: 'Warm Up Machine',
      start_min: 0,
      end_min: 30,
      duration_min: 30,
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      predecessors: [],
      step_role: 'normal',
    },
    {
      task_id: 2,
      step_order: 2,
      op_rule_id: 2,
      op_rule_code: 'OP_CLEANING',
      op_rule_name: 'Clean Machine',
      start_min: 0,
      end_min: 20,
      duration_min: 20,
      resources: [{ resource_code: 'CLEAN-01', resource_name: 'Cleaning Robot' }],
      predecessors: [],
      step_role: 'normal',
    },
    {
      task_id: 3,
      step_order: 3,
      op_rule_id: 3,
      op_rule_code: 'OP_CALIBRATE',
      op_rule_name: 'Calibrate Machine',
      start_min: 30,
      end_min: 45,
      duration_min: 15,
      resources: [{ resource_code: 'TECH-01', resource_name: 'Technician Alice' }],
      predecessors: [1],
      step_role: 'normal',
    },
  ],
}

const DELAYED_FILL_GAP_SCHEDULE = {
  ...PARALLEL_SCHEDULE,
  schedule_id: 202,
  makespan: 70,
  tasks: [
    {
      ...PARALLEL_SCHEDULE.tasks[0],
      start_min: 25,
      end_min: 55,
      step_role: 'delayed',
    },
    PARALLEL_SCHEDULE.tasks[1],
    {
      ...PARALLEL_SCHEDULE.tasks[2],
      start_min: 55,
      end_min: 70,
    },
  ],
}

function createFillGapMockHandler() {
  return async (route: any, request: any) => {
    const url = request.url()
    const method = request.method()

    if (url.endsWith('/health')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ status: 'ok' }) })
      return
    }

    if (url.includes('/states')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ states: MOCK_STATES }) })
      return
    }

    if (url.includes('/api/v1/machines')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_MACHINES) })
      return
    }

    if (url.includes('/api/v1/machine-types')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_MACHINE_TYPES) })
      return
    }

    if (url.includes('/api/v1/resources')) {
      await route.fulfill({ status: 200, body: JSON.stringify(MOCK_RESOURCES) })
      return
    }

    if (url.includes('/features')) {
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          {
            feature_key: 'blockage_reason',
            display_name: 'Blockage Reason',
            value_type: 'enum',
            allowed_values: ['mechanical_wear', 'electrical_fault', 'coolant_leak', 'tool_breakage'],
          },
        ]),
      })
      return
    }

    if (url.includes('/api/v1/solve') && method === 'POST') {
      const payload = JSON.parse(request.postData() || '{}')
      const schedule = payload.parent_plan_id != null || payload.blockage_constraints != null
        ? DELAYED_FILL_GAP_SCHEDULE
        : PARALLEL_SCHEDULE

      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule,
          candidate_plan_id: schedule.schedule_id,
          state_delta: [],
          critical_path: [],
        }),
      })
      return
    }

    if (url.includes('/plans/') && url.includes('/versions')) {
      const id = url.match(/\/plans\/(\d+)\/versions/)?.[1]
      await route.fulfill({
        status: 200,
        body: JSON.stringify([{ id: Number(id), version: 1, created_at: new Date().toISOString() }]),
      })
      return
    }

    if (url.includes('/plans/') && url.includes('/diff/')) {
      await route.fulfill({ status: 200, body: JSON.stringify({ steps: [] }) })
      return
    }

    await route.continue()
  }
}

test.describe('Blockage — Strategy A fill gaps with parallel activities', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/(health|api\/v1\/)/, createFillGapMockHandler())
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.click('.el-menu-item:has-text("求解")')
    await page.waitForSelector('h2:has-text("求解")', { timeout: 10000 })
    await page.waitForTimeout(2000)

    // Select machine (auto-select will pick parallel states id=1→2)
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(500)
  })

  test('initial solve shows parallel warmup and cleaning', async ({ page }) => {
    // Click solve
    await page.click('button:has-text("开始求解")')
    await page.click('.el-tabs__item:has-text("任务明细")')
    await page.waitForSelector('.el-table__body tr:visible', { timeout: 30000 })

    // Screenshot for GIF frame (fixed viewport, no fullPage to keep dimensions consistent)
    await page.screenshot({ path: 'test-results/gif-frames/01-initial-parallel-schedule.png' })

    // Verify 3 tasks appear (parallel scenario: WARMUP + CLEANING + CALIBRATE)
    const rows = page.locator('.el-table__body tr:visible')
    await expect(rows).toHaveCount(3)

    // Verify all tasks are visible
    const warmupRow = rows.filter({ hasText: 'OP_WARMUP' })
    const cleaningRow = rows.filter({ hasText: 'OP_CLEANING' })
    const calibrateRow = rows.filter({ hasText: 'OP_CALIBRATE' })

    await expect(warmupRow).toBeVisible()
    await expect(cleaningRow).toBeVisible()
    await expect(calibrateRow).toBeVisible()

    // Check start times: WARMUP and CLEANING both start at 0 (parallel)
    const warmupStart = await warmupRow.locator('td').nth(4).textContent()
    const cleaningStart = await cleaningRow.locator('td').nth(4).textContent()
    expect(warmupStart).toContain('0')
    expect(cleaningStart).toContain('0')
  })

  test('not_before delay pushes warmup, cleaning fills gap', async ({ page }) => {
    // Initial solve
    await page.click('button:has-text("开始求解")')
    await page.click('.el-tabs__item:has-text("任务明细")')
    await page.waitForSelector('.el-table__body tr:visible', { timeout: 30000 })

    // Frame: initial schedule (fixed viewport)
    await page.screenshot({ path: 'test-results/gif-frames/02-initial-schedule.png' })

    // Mark WARMUP as blocked
    const warmupRow = page.locator('.el-table__body tr:visible').filter({ hasText: 'OP_WARMUP' })
    await warmupRow.locator('button:has-text("标记阻塞")').click()

    // Dialog opens
    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await expect(page.locator('.el-dialog__title')).toContainText('标记阻塞并重排')

    // Frame: blockage dialog (fixed viewport)
    await page.screenshot({ path: 'test-results/gif-frames/03-blockage-dialog.png' })

    // Strategy A with 25 min offset
    await page.click('.el-radio:has-text("策略 A")')
    await page.fill('.el-input-number input', '25')

    // Frame: strategy A selected (fixed viewport)
    await page.screenshot({ path: 'test-results/gif-frames/04-strategy-a-selected.png' })

    await page.click('.el-dialog__footer button:has-text("提交重排")')

    // Wait for success
    await page.waitForSelector('.el-message--success', { timeout: 30000 })
    await page.waitForTimeout(500)

    // Frame: delayed schedule with fill-gaps (fixed viewport)
    await page.screenshot({ path: 'test-results/gif-frames/05-delayed-schedule-fill-gaps.png' })

    // Verify new schedule
    const rows = page.locator('.el-table__body tr:visible')
    await expect(rows).toHaveCount(3)

    // Find WARMUP row - should have "延后" tag and start at 25
    const warmupRowNew = rows.filter({ hasText: 'OP_WARMUP' })
    const delayedTag = warmupRowNew.locator('.el-tag:has-text("延后")')
    await expect(delayedTag).toBeVisible()

    const warmupStartNew = await warmupRowNew.locator('td').nth(4).textContent()
    expect(warmupStartNew).toContain('25')

    // CLEANING should still start at 0 (fills the gap)
    const cleaningRowNew = rows.filter({ hasText: 'OP_CLEANING' })
    const cleaningStartNew = await cleaningRowNew.locator('td').nth(4).textContent()
    expect(cleaningStartNew).toContain('0')

    // CALIBRATE should start after delayed WARMUP ends (25 + 30 = 55)
    const calibrateRowNew = rows.filter({ hasText: 'OP_CALIBRATE' })
    const calibrateStartNew = await calibrateRowNew.locator('td').nth(4).textContent()
    expect(calibrateStartNew).toContain('55')
  })
})

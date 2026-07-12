import { test, expect } from '@playwright/test'
import { BASE_SCHEDULE, REPAIR_SCHEDULE } from '../fixtures/mock-api'

// Shared mock data
const MOCK_MACHINES = [
  { id: 1, code: 'M-001', name: 'Main CNC Lathe', location: 'Workshop A', machine_type_id: 1 },
]
const MOCK_MACHINE_TYPES = [
  { id: 1, code: 'LATHE', name: 'CNC Lathe', description: 'Standard lathe' },
]
const MOCK_RESOURCES = [
  { id: 1, code: 'TECH-01', name: 'Technician Alice', resource_type: 'human' },
]
const MOCK_STATES = [
  { state_id: 1, state_type: 'current', label: 'Cold Dirty Standby', features: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off' } },
  { state_id: 2, state_type: 'target', label: 'Hot Clean Calibrated', features: { temperature_level: 'hot', clean_level: 'clean', calibration: 'on' } },
  { state_id: 3, state_type: 'current', label: 'Cold Standby with Blockage', features: { temperature_level: 'cold', clean_level: 'dirty', calibration: 'off', blockage_reason: 'mechanical_wear' } },
  { state_id: 4, state_type: 'target', label: 'Ready for Production with Blockage', features: { temperature_level: 'hot', clean_level: 'clean', calibration: 'on', blockage_reason: '' } },
]

// Build a smart mock handler:
// - Initial POST /solve  → returns BASE_SCHEDULE
// - Replan POST /solve   → returns REPAIR_SCHEDULE (when parent_plan_id or blockage_constraints present)
function createSmartMockHandler() {
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
            display_name: '阻塞原因',
            value_type: 'enum',
            allowed_values: ['mechanical_wear', 'electrical_fault', 'coolant_leak', 'tool_breakage'],
          },
        ]),
      })
      return
    }

    if (url.includes('/api/v1/solve') && method === 'POST') {
      const postData = request.postData() || '{}'
      const payload = JSON.parse(postData)
      const isReplan = payload.parent_plan_id != null || payload.blockage_constraints != null
      const schedule = isReplan ? REPAIR_SCHEDULE : BASE_SCHEDULE

      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule: schedule,
          candidate_plan_id: schedule.schedule_id,
          state_delta: [],
          critical_path: [],
        })
      })
      return
    }

    if (url.includes('/api/v1/solve/') && method === 'PATCH') {
      await route.fulfill({
        status: 200,
        body: JSON.stringify({
          status: 'done',
          schedule: REPAIR_SCHEDULE,
          candidate_plan_id: REPAIR_SCHEDULE.schedule_id,
          state_delta: [],
          critical_path: [],
        })
      })
      return
    }

    if (url.includes('/plans/') && url.includes('/versions')) {
      const id = url.match(/\/plans\/(\d+)\/versions/)?.[1]
      await route.fulfill({
        status: 200,
        body: JSON.stringify([
          { id: Number(id), version: 1, created_at: new Date().toISOString() },
        ]),
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

test.describe('Blockage — Strategy B (repair insertion)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route(/\/(health|api\/v1\/)/, createSmartMockHandler())
    await page.goto('/')
    await page.waitForSelector('.el-header', { timeout: 10000 })
    await page.click('.el-menu-item:has-text("求解")')
    await page.waitForSelector('h2:has-text("求解")', { timeout: 10000 })
    await page.waitForTimeout(2000)

    // Select machine
    await page.click('.el-select__wrapper')
    await page.waitForSelector('.el-select-dropdown', { timeout: 5000 })
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe (M-001)")')
    await page.waitForTimeout(2000)

    // Select current state with blockage
    await page.keyboard.press('Escape')
    await page.locator('.el-select__wrapper').nth(1).click()
    await page.locator('.el-select-dropdown').nth(1).locator('.el-select-dropdown__item:has-text("Cold Standby with Blockage")').click()

    // Select target state
    await page.keyboard.press('Escape')
    await page.locator('.el-select__wrapper').nth(2).click()
    await page.locator('.el-select-dropdown').nth(2).locator('.el-select-dropdown__item:has-text("Ready for Production with Blockage")').click()

    // Run initial solve → should return BASE_SCHEDULE (no repair task yet)
    await page.click('button:has-text("开始求解")')
    await page.click('.el-tabs__item:has-text("任务明细")')
    await page.waitForSelector('.el-table__body tr:visible', { timeout: 30000 })
  })

  test('repair task is inserted and marked red', async ({ page }) => {
    const framesDir = 'test-results/gif-frames';
    const takeShot = async (name: string) => {
      await page.screenshot({ path: `${framesDir}/${name}.png`, fullPage: false });
    };

    await takeShot('01-initial');

    // Verify initial solve has no repair task
    await expect(page.locator('.el-table__body tr:visible')).toHaveCount(2)
    await expect(page.locator('.el-table__body tr:visible').filter({ hasText: 'OP_REPAIR_WORN' })).toHaveCount(0)

    // Mark blockage on the first row (OP_WARMUP)
    const firstRow = page.locator('.el-table__body tr:visible').first()
    await firstRow.locator('button:has-text("标记阻塞")').click()
    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await takeShot('02-dialog-open');

    // Select strategy B
    await page.click('.el-radio:has-text("策略 B")')
    await page.waitForTimeout(500)
    await takeShot('03-strategy-b-selected');

    // Select blockage reason
    await page.locator('.el-dialog .el-select__wrapper').click()
    await page.locator('.el-select-dropdown').last().locator('.el-select-dropdown__item:has-text("mechanical_wear")').click()
    await takeShot('04-reason-selected');

    // Submit replan → mock will return REPAIR_SCHEDULE
    await page.click('.el-dialog__footer button:has-text("提交重排")')
    await page.waitForSelector('.el-message--success', { timeout: 30000 })
    await page.waitForTimeout(800)
    await takeShot('05-replan-success');

    // Now verify repair task appears
    await expect(page.locator('.el-table__body tr:visible')).toHaveCount(3)

    const repairTag = page.locator('.el-table__body tr:visible .el-tag--danger:has-text("维修")')
    await expect(repairTag.first()).toBeVisible()

    const repairRow = page.locator('.el-table__body tr:visible').filter({ hasText: 'OP_REPAIR_WORN' })
    await expect(repairRow).toBeVisible()

    await takeShot('06-repair-row-visible');
  })
})

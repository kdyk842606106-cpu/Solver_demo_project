import { test, expect } from '@playwright/test'
import { BASE_SCHEDULE, createMockRouteHandler } from '../fixtures/mock-api'

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

    // Verify makespan statistic
    const makespan = await page.locator('.metric-item.primary strong').first().textContent()
    expect(makespan).toContain('45')
  })
})

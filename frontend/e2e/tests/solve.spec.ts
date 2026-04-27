import { test, expect } from '@playwright/test'

test.describe('Solve Page — Happy Path', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    // Wait for page to load machine list
    await page.waitForSelector('.el-select', { timeout: 10000 })
  })

  test('page loads and shows solve form', async ({ page }) => {
    await expect(page.locator('h2')).toContainText('求解')
    await expect(page.locator('.el-form')).toBeVisible()
  })

  test('can select machine and states', async ({ page }) => {
    // Select machine
    await page.click('.el-form-item:nth-child(1) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe")')

    // States should auto-populate after machine selection
    await page.waitForTimeout(500)
    const currentState = await page.inputValue('.el-form-item:nth-child(2) .el-select .el-input__inner')
    const targetState = await page.inputValue('.el-form-item:nth-child(3) .el-select .el-input__inner')
    expect(currentState).not.toBe('')
    expect(targetState).not.toBe('')
  })

  test('full solve flow produces schedule', async ({ page }) => {
    // Select machine
    await page.click('.el-form-item:nth-child(1) .el-select')
    await page.click('.el-select-dropdown__item:has-text("Main CNC Lathe")')
    await page.waitForTimeout(500)

    // Click solve
    await page.click('button:has-text("开始求解")')

    // Wait for result
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })

    // Verify tasks appear
    const rows = page.locator('.el-table__body tr')
    await expect(rows).toHaveCount(2) // serial: WARMUP + CALIBRATE

    // Verify Gantt chart renders
    await expect(page.locator('text=排程 Gantt 图')).toBeVisible()
  })
})

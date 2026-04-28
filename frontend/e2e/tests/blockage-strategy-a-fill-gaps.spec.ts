import { test, expect } from '@playwright/test'

test.describe('Blockage — Strategy A fill gaps with parallel activities', () => {
  test.beforeEach(async ({ page }) => {
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
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })

    // Verify 3 tasks appear (parallel scenario: WARMUP + CLEANING + CALIBRATE)
    const rows = page.locator('.el-table__body tr')
    await expect(rows).toHaveCount(3)

    // Verify all tasks are visible
    const warmupRow = rows.filter({ hasText: 'OP_WARMUP' })
    const cleaningRow = rows.filter({ hasText: 'OP_CLEANING' })
    const calibrateRow = rows.filter({ hasText: 'OP_CALIBRATE' })

    await expect(warmupRow).toBeVisible()
    await expect(cleaningRow).toBeVisible()
    await expect(calibrateRow).toBeVisible()

    // Check start times: WARMUP and CLEANING both start at 0 (parallel)
    const warmupStart = await warmupRow.locator('td').nth(3).textContent()
    const cleaningStart = await cleaningRow.locator('td').nth(3).textContent()
    expect(warmupStart).toContain('0')
    expect(cleaningStart).toContain('0')
  })

  test('not_before delay pushes warmup, cleaning fills gap', async ({ page }) => {
    // Initial solve
    await page.click('button:has-text("开始求解")')
    await page.waitForSelector('.el-table__body tr', { timeout: 30000 })

    // Mark WARMUP as blocked
    const warmupRow = page.locator('.el-table__body tr').filter({ hasText: 'OP_WARMUP' })
    await warmupRow.locator('button:has-text("标记阻塞")').click()

    // Dialog opens
    await page.waitForSelector('.el-dialog', { timeout: 5000 })
    await expect(page.locator('.el-dialog__title')).toContainText('标记阻塞并重排')

    // Strategy A with 25 min offset
    await page.click('.el-radio:has-text("策略 A")')
    await page.fill('.el-input-number input', '25')
    await page.click('.el-dialog__footer button:has-text("提交重排")')

    // Wait for success
    await page.waitForSelector('.el-message--success', { timeout: 30000 })
    await page.waitForTimeout(500)

    // Verify new schedule
    const rows = page.locator('.el-table__body tr')
    await expect(rows).toHaveCount(3)

    // Find WARMUP row - should have "延后" tag and start at 25
    const warmupRowNew = rows.filter({ hasText: 'OP_WARMUP' })
    const delayedTag = warmupRowNew.locator('.el-tag:has-text("延后")')
    await expect(delayedTag).toBeVisible()

    const warmupStartNew = await warmupRowNew.locator('td').nth(3).textContent()
    expect(warmupStartNew).toContain('25')

    // CLEANING should still start at 0 (fills the gap)
    const cleaningRowNew = rows.filter({ hasText: 'OP_CLEANING' })
    const cleaningStartNew = await cleaningRowNew.locator('td').nth(3).textContent()
    expect(cleaningStartNew).toContain('0')

    // CALIBRATE should start after delayed WARMUP ends (25 + 30 = 55)
    const calibrateRowNew = rows.filter({ hasText: 'OP_CALIBRATE' })
    const calibrateStartNew = await calibrateRowNew.locator('td').nth(3).textContent()
    expect(calibrateStartNew).toContain('55')
  })
})
